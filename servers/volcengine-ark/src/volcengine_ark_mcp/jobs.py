"""Durable local jobs. Vendored in each independently installed server package.

No automatic generation retries. URLs and resumable TTS inputs stay on disk.
"""
import contextlib
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path


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
        with os.fdopen(fd, "wb") as target, urllib.request.urlopen(url, timeout=60) as source:
            shutil.copyfileobj(source, target)
            size = target.tell()
            length = source.headers.get("Content-Length")
            if not size or (length is not None and size != int(length)):
                raise ValueError("下载为空或长度与 Content-Length 不符")
            target.flush()
            os.fsync(target.fileno())
        os.replace(tmp, path)
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
        if not re.fullmatch(r"[a-f0-9]{32}", job_id):
            raise ValueError("job_id 必须是工具返回的 32 位 ID")
        return self.root / job_id / "job.json"

    def save(self, job):
        job["updated_at"] = time.time()
        atomic_bytes(self.path(job["job_id"]), json.dumps(job, ensure_ascii=False, indent=2).encode())
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
        return json.loads(self.path(job_id).read_text())

    def record_response(self, job, response):
        path = self.path(job["job_id"]).parent / "response.json"
        atomic_bytes(path, json.dumps(response, ensure_ascii=False).encode())
        job["response_file"] = str(path)
        self.save(job)

    @contextlib.contextmanager
    def locked(self, job_id):
        """Fail quickly on concurrent recovery. Kernel releases the lock on crash."""
        import fcntl
        path = self.path(job_id)
        if not path.is_file():
            raise ValueError("找不到任务记录")
        with (path.parent / "job.lock").open("a+b") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ValueError("任务正在由另一个调用处理，请稍后查询") from None
            try:
                yield self.load(job_id)
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def add(self, job, name, url=None, data=None, metadata=None):
        if Path(name).name != name:
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

    def deliver(self, job):
        for item in job["artifacts"]:
            item.update(state="pending", file=None, error=None)
            path = Path(job["out_dir"]) / item["name"]
            if path.is_file() and item.get("integrity"):
                try:
                    if fingerprint(path) == item["integrity"]:
                        item.update(state="saved", file=str(path))
                        continue
                except OSError:
                    pass
            if job["mode"] == "url" and item.get("url"):
                item["state"] = "linked"
                continue
            try:
                if item.get("source"):
                    atomic_bytes(path, Path(item["source"]).read_bytes())
                else:
                    download(item.get("url"), path)
                item.update(file=str(path), state="saved", integrity=fingerprint(path))
                item["media_info"] = media_info(path)
            except (OSError, ValueError) as exc:
                item.update(state="download_failed", error=str(exc))
            self.save(job)
        if job["artifacts"]:
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
                job = json.loads(path.read_text())
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
