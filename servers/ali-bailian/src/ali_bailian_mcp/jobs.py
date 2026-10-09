"""Durable local jobs. Vendored in each independently installed server package.

No automatic generation retries. URLs and resumable TTS inputs stay on disk.
"""
import contextlib
import contextvars
import concurrent.futures
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import tempfile
import time
import threading
import urllib.request

from . import transport
from pathlib import Path


_leases = threading.local()


def _sync_directory(path):
    """Persist renamed directory entries as well as the file contents."""
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_copy(path, source):
    """Copy spooled media without loading the entire artifact into memory."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".mcp-copy-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as target, Path(source).open("rb") as stream:
            shutil.copyfileobj(stream, target, length=1024 * 1024)
            if not target.tell():
                raise ValueError("产物数据为空")
            target.flush()
            os.fsync(target.fileno())
        os.replace(tmp, path)
        _sync_directory(path.parent)
    finally:
        Path(tmp).unlink(missing_ok=True)
    return str(path)


def atomic_bytes(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".mcp-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
        _sync_directory(path.parent)
    finally:
        Path(tmp).unlink(missing_ok=True)
    return str(path)


def download(url, path):
    """Bounded network wait; never expose a partial file as a completed artifact."""
    if not isinstance(url, str) or not url.startswith(("http://", "https://")):
        raise ValueError("产物缺少可下载的 HTTP/HTTPS URL")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".mcp-download-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as target, transport.urlopen(url, timeout=60) as source:
            shutil.copyfileobj(source, target)
            size = target.tell()
            length = source.headers.get("Content-Length")
            if not size or (length is not None and size != int(length)):
                raise ValueError("下载为空或长度与 Content-Length 不符")
            target.flush()
            os.fsync(target.fileno())
        os.replace(tmp, path)
        _sync_directory(path.parent)
    finally:
        Path(tmp).unlink(missing_ok=True)
    return str(path)


def fingerprint(path):
    path = Path(path)
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return {"bytes": path.stat().st_size, "sha256": digest.hexdigest()}


def media_info(path):
    """Optional local metadata; no provider estimates are presented as measured sizes."""
    path = Path(path)
    try:
        with path.open("rb") as stream:
            head = stream.read(24)
            if head.startswith(b"\x89PNG\r\n\x1a\n") and len(head) == 24:
                width, height = struct.unpack(">II", head[16:24])
                return {"width": width, "height": height, "source": "png_header"}
        executable = shutil.which("ffprobe")
        if executable:
            response = subprocess.run([executable, "-v", "error", "-show_entries",
                                       "format=duration:stream=codec_type,width,height,sample_rate,channels",
                                       "-of", "json", str(path)], capture_output=True, text=True, timeout=10)
            if response.returncode == 0:
                return {"source": "ffprobe", **json.loads(response.stdout)}
    except (OSError, ValueError, subprocess.TimeoutExpired):
        pass
    return {"source": None, "available": False}


class Store:
    def __init__(self, env, default):
        self.root = Path(os.environ.get(env, default)).expanduser().resolve()

    def path(self, job_id):
        if not isinstance(job_id, str) or not re.fullmatch(r"[a-f0-9]{32}", job_id):
            raise ValueError("job_id 必须是工具返回的 32 位 ID")
        return self.root / job_id / "job.json"

    @contextlib.contextmanager
    def _lease(self, job_id):
        """Cross-process exclusion, reentrant only in the owning thread."""
        import fcntl
        path = self.path(job_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        key = str(path)
        held = getattr(_leases, "held", None)
        if held is None:
            held = _leases.held = set()
        if key in held:
            yield
            return
        with (path.parent / "job.lock").open("a+b") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ValueError("任务正在由另一个调用处理，请稍后查询") from None
            held.add(key)
            try:
                yield
            finally:
                held.remove(key)
                fcntl.flock(lock, fcntl.LOCK_UN)

    def _check_revision(self, job):
        path = self.path(job["job_id"])
        if path.is_file() and self.load(job["job_id"]).get("revision", 0) != job.get("revision", 0):
            raise ValueError("任务记录已由另一个调用更新，请重新查询后恢复")

    @contextlib.contextmanager
    def processing(self, job):
        """Hold from before a paid request through response persistence/delivery.

        Callers should wrap the initial generation in this context after create().
        Every mutation also checks revision, so stale callers cannot overwrite
        recovery even when the caller does not hold the full operation lease.
        """
        with self._lease(job["job_id"]):
            self._check_revision(job)
            yield job

    def save(self, job):
        with self.processing(job):
            snapshot = {**job, "updated_at": time.time(), "revision": job.get("revision", 0) + 1}
            atomic_bytes(self.path(job["job_id"]), json.dumps(snapshot, ensure_ascii=False, indent=2).encode())
            job.update(updated_at=snapshot["updated_at"], revision=snapshot["revision"])
        return job

    def create(self, kind, model, out_dir, mode="local", resume=None, summary=None):
        import uuid
        job = {"job_id": uuid.uuid4().hex, "kind": kind, "model": model,
               "created_at": time.time(), "state": "unknown", "task_id": None,
               "out_dir": str(Path(out_dir).expanduser().resolve()), "mode": mode,
               "summary": summary or {}, "resume": resume, "artifacts": [],
               "usage": None, "request_id": None, "error": None, "result": {}}
        self.save(job)  # Durable BEFORE any paid request.
        return job

    def load(self, job_id):
        job = json.loads(self.path(job_id).read_text())
        required = ("job_id", "kind", "model", "state", "task_id", "out_dir", "mode",
                    "artifacts", "usage", "request_id", "error", "created_at", "updated_at", "summary", "result")
        if not isinstance(job, dict) or any(key not in job for key in required):
            raise ValueError("任务记录损坏：缺少必要字段")
        if job["job_id"] != job_id or not isinstance(job["artifacts"], list):
            raise ValueError("任务记录损坏：ID 或产物列表无效")
        if (not isinstance(job["out_dir"], str) or not isinstance(job["state"], str)
                or not isinstance(job.get("result", {}), dict)
                or not isinstance(job.get("summary", {}), dict)
                or not isinstance(job.get("revision", 0), int)):
            raise ValueError("任务记录损坏：字段类型无效")
        names = set()
        for item in job["artifacts"]:
            if (not isinstance(item, dict) or not isinstance(item.get("name"), str)
                    or Path(item["name"]).name != item["name"] or item["name"] in ("", ".", "..")
                    or "state" not in item or "file" not in item or item["name"] in names
                    or item["state"] not in ("pending", "saved", "linked", "download_failed")
                    or (item["state"] == "saved" and not isinstance(item["file"], str))):
                raise ValueError("任务记录损坏：产物字段无效或名称重复")
            names.add(item["name"])
        if not isinstance(job["created_at"], (int, float)):
            raise ValueError("任务记录损坏：创建时间无效")
        return job

    def record_response(self, job, response):
        with self.processing(job):
            path = self.path(job["job_id"]).parent / "response.json"
            atomic_bytes(path, json.dumps(response, ensure_ascii=False).encode())
            job["response_file"] = str(path)
            self.save(job)

    @contextlib.contextmanager
    def locked(self, job_id):
        """Fail quickly on concurrent work. Kernel releases the lock on crash."""
        if not self.path(job_id).is_file():
            raise ValueError("找不到任务记录")
        with self._lease(job_id):
            yield self.load(job_id)

    def add(self, job, name, url=None, data=None, metadata=None):
        with self.processing(job):
            return self._add(job, name, url=url, data=data, metadata=metadata)

    def _add(self, job, name, url=None, data=None, metadata=None):
        if not isinstance(name, str) or name in ("", ".", "..") or Path(name).name != name:
            raise ValueError("产物名称必须是不含目录的文件名")
        item = next((a for a in job["artifacts"] if a["name"] == name), None)
        if item is None:
            item = {"name": name, "state": "pending", "file": None, "error": None}
            job["artifacts"].append(item)
        if url:
            item["url"] = url
        if metadata:
            item["metadata"] = metadata
        if data is not None:
            if not data:
                raise ValueError("产物数据为空")
            spool = self.path(job["job_id"]).parent / ("source-" + name)
            atomic_bytes(spool, data)
            item["source"] = str(spool)
        self.save(job)  # Persist sources before attempting final delivery.
        return item

    @staticmethod
    def _deliver_item(item, out_dir, mode):
        # Workers never mutate shared job state or write job.json.
        item = dict(item)
        path = Path(out_dir) / item["name"]
        item.update(state="pending", file=None, error=None)
        try:
            if path.is_file() and item.get("integrity") and fingerprint(path) == item["integrity"]:
                item.update(state="saved", file=str(path))
                return item
            if mode == "url" and item.get("url"):
                item["state"] = "linked"
                return item
            if item.get("source"):
                atomic_copy(path, item["source"])
            else:
                download(item.get("url"), path)
            item.update(file=str(path), state="saved", integrity=fingerprint(path))
            item["media_info"] = media_info(path)
        except Exception as exc:
            # Isolate delivery failures, including transport-specific exceptions.
            item.update(state="download_failed", error=str(exc))
        return item

    def deliver(self, job):
        with self.processing(job):
            if not job["artifacts"]:
                if job["state"] != "partial":
                    job["state"] = "failed"
                job["error"] = job.get("error") or "生成结果没有可交付产物；恢复不会重新生成"
                self.save(job)
                return self.result(job)
            # A small per-job bound avoids overwhelming providers and disks.
            with concurrent.futures.ThreadPoolExecutor(max_workers=min(4, len(job["artifacts"]))) as pool:
                futures = {pool.submit(contextvars.copy_context().run, self._deliver_item, item, job["out_dir"], job["mode"]): index
                           for index, item in enumerate(job["artifacts"])}
                for future in concurrent.futures.as_completed(futures):
                    job["artifacts"][futures[future]] = future.result()
                    self.save(job)  # Only the coordinating thread persists state.
            complete = all(a["state"] in ("saved", "linked") for a in job["artifacts"])
            job["state"] = "delivered" if complete else "download_failed"
            job["error"] = None if complete else "部分产物交付失败；recover_job 可补下载，不重新生成"
            if complete and job.get("result", {}).get("errors"):
                job.update(state="partial", error="部分产物生成失败；恢复不会重新生成失败项")
            if complete and job["kind"] == "tts":
                job["state"] = "partial"  # Merge and remaining chunks are handled by resume_tts.
            self.save(job)
            return self.result(job)

    def result(self, job):
        files = [a["file"] if a["state"] == "saved" else a.get("url")
                 for a in job["artifacts"] if a["state"] in ("saved", "linked")]
        if job["kind"] == "tts" and job["state"] == "delivered" and job.get("result", {}).get("speech_file"):
            files = [job["result"]["speech_file"]]
        return {**job.get("result", {}), "ok": job["state"] == "delivered", "job_id": job["job_id"],
                "model": job["model"], "task_id": job["task_id"], "job_state": job["state"],
                "files": files, "artifacts": job["artifacts"], "usage": job["usage"],
                "request_id": job["request_id"], "out_dir": job["out_dir"], "error": job["error"]}

    def get(self, job_id):
        try:
            job = self.load(job_id)
            return {**self.result(job), "ok": True, "kind": job["kind"],
                    "summary": job["summary"], "created_at": job["created_at"], "updated_at": job["updated_at"]}
        except (OSError, ValueError) as exc:
            return {"ok": False, "error": str(exc)}

    def list(self, limit=20, kind=None):
        if not 1 <= limit <= 100:
            return {"ok": False, "error": "limit范围1–100"}
        records, errors = [], []
        for path in self.root.glob("*/job.json"):
            try:
                job = self.load(path.parent.name)
                if kind and job["kind"] != kind:
                    continue
                records.append({key: job.get(key) for key in
                                ("job_id", "kind", "model", "state", "task_id", "summary", "created_at", "updated_at")})
            except (OSError, ValueError, KeyError) as exc:
                errors.append({"record": path.parent.name, "error": str(exc)})
        records.sort(key=lambda item: item["created_at"], reverse=True)
        return {"ok": True, "jobs": records[:limit], "errors": errors}

    def recover(self, job_id, handler=None):
        try:
            with self.locked(job_id) as job:
                if handler:
                    return handler(job)
                if job["state"] in ("unknown", "failed", "partial"):
                    return {**self.result(job), "ok": False,
                            "error": "任务未取得完整生成结果，不能自动重新提交；请检查任务状态"}
                return self.deliver(job)
        except (OSError, ValueError) as exc:
            return {"ok": False, "error": str(exc), "job_id": job_id}
