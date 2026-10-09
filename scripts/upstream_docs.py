"""Fetch official contracts, fail closed on shells, compare reviewed fingerprints.

No cloud API keys, model requests, repository writes or remote publication.
Baseline replacement is an explicit local CLI option after contract review.
"""
import argparse
import ast
import concurrent.futures
import datetime
import difflib
import gzip
import hashlib
import html
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import tempfile
import time
import urllib.parse
import urllib.request
import zlib

ROOT = Path(__file__).resolve().parents[1]
HOSTS = {"docs.volcengine.com", "www.volcengine.com", "help.aliyun.com"}
MODEL = re.compile(r"\b(?:doubao|seedream|seedance|qwen|wan[0-9]|happyhorse|cosyvoice|"
                   r"text-embedding|multimodal-embedding|gte-rerank|seed-tts|seed-icl|"
                   r"volc\.speech|bigmodel)[A-Za-z0-9_.-]*", re.I)
URL = re.compile(r"(?:https?|wss)://[^\s<>\"'`\\]+")


def is_api_endpoint(url):
    try:
        parsed = urllib.parse.urlsplit(url)
    except ValueError:
        return False  # Literal placeholders/examples are not concrete URLs.
    host = parsed.hostname or ""
    valid = (host == "openspeech.bytedance.com" or host == "open.volcengineapi.com"
             or bool(re.fullmatch(r"dashscope(?:-intl|-us)?\.aliyuncs\.com", host))
             or bool(re.fullmatch(r"ark\.[a-z0-9-]+\.volces\.com", host))
             or bool(re.fullmatch(r"[^.]+\.[a-z0-9-]+\.maas\.aliyuncs\.com", host)))
    return valid and (parsed.path.startswith(("/api/", "/compatible-api/", "/compatible-mode/")) or host == "open.volcengineapi.com")


def is_document_link(url):
    try:
        return urllib.parse.urlsplit(url).hostname in HOSTS and "/api/doc/" not in url
    except ValueError:
        return False


def official_url(url):
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname not in HOSTS or parsed.username or parsed.password:
        raise ValueError("Source must use an allowlisted official HTTPS documentation host")
    if parsed.port not in (None, 443):
        raise ValueError("Nonstandard documentation port")
    return url


class OfficialRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        official_url(newurl)
        return super().redirect_request(request, fp, code, message, headers, newurl)


class ArticleText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.output = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.skip += 1
        if tag in {"p", "br", "div", "tr", "li", "pre", "h1", "h2", "h3", "h4"}:
            self.output.append("\n")
        if tag == "a":
            target = dict(attrs).get("href")
            if target:
                self.output.append(f" [{target}] ")

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.skip = max(0, self.skip - 1)

    def handle_data(self, data):
        if not self.skip:
            self.output.append(data)


def normalize(text):
    return "\n".join(line.rstrip() for line in text.replace("\r\n", "\n").replace("\r", "\n").splitlines()).strip() + "\n"


def extract(body, source):
    """Only documented bodies/official structured responses count as success."""
    mode = source.get("fetch_kind", "auto")
    stripped = body.lstrip()
    if mode in {"volcengine_doc", "volcengine_index"} or (mode == "auto" and stripped.startswith("{")):
        response = json.loads(body)
        if response.get("ResponseMetadata", {}).get("Error"):
            raise ValueError("Official documentation API returned an error")
        result = response.get("Result")
        fetch_url = source.get("fetch_url", source.get("url", ""))
        expected = urllib.parse.parse_qs(urllib.parse.urlsplit(fetch_url).query)
        if (mode == "volcengine_doc" or "getDocDetail" in fetch_url) and not isinstance(result, dict):
            raise ValueError("Expected an official document, received a directory")
        if (mode == "volcengine_index" or "getDocList" in fetch_url) and not isinstance(result, list):
            raise ValueError("Expected an official directory, received a document")
        if isinstance(result, list):
            # Index changes identify new/removed documents, not volatile ordering.
            entries = [{key: item.get(key) for key in ("DocumentCode", "DocumentID", "Title", "ParentCode", "Status")}
                       for item in result if isinstance(item, dict)]
            if not entries or any(not item["DocumentCode"] for item in entries):
                raise ValueError("Invalid official document index")
            entries.sort(key=lambda item: str(item["DocumentCode"]))
            return json.dumps(entries, ensure_ascii=False, indent=2), {"title": source["id"], "documents": len(entries),
                      "document_codes": sorted(str(item["DocumentCode"]) for item in entries)}
        if not isinstance(result, dict):
            raise ValueError("Official documentation response has no Result")
        for field in ("DocumentCode", "DocumentID", "LibraryCode", "LibraryID"):
            if field in expected and str(result.get(field)) != expected[field][0]:
                raise ValueError(f"Official document identity mismatch: {field}")
        text = result.get("MDContent")
        if not text and result.get("ContentType") in {"md", "markdown"}:
            text = result.get("Content")
        if not isinstance(text, str) or len(text.strip()) < 100:
            raise ValueError("Official MDContent missing; requires extractor review (do not hash raw editor JSON)")
        return text, {"title": result.get("Title"), "updated_at": result.get("UpdatedTime"),
                      "document_id": str(result.get("DocumentID", ""))}
    if mode == "aliyun_html":
        # Fallback for articles lacking a working .md export.
        match = re.search(r"window\.__ICE_PAGE_PROPS__\s*=\s*", body)
        if not match:
            raise ValueError("Aliyun article metadata missing")
        state, _ = json.JSONDecoder().raw_decode(body[match.end():].lstrip())
        data = state["docDetailData"]["storeData"]["data"]
        parser = ArticleText()
        parser.feed(data["content"])
        text = "".join(parser.output)
        if len(text.strip()) < 100 or not data.get("docTitle"):
            raise ValueError("Aliyun article is empty or lacks its title")
        return text, {"title": data.get("docTitle"), "updated_at": data.get("lastModifiedTime")}
    if not stripped.startswith("#") and re.search(r"<(?:!doctype|html|body|script|div|p|head|h1)\b", stripped[:2000], re.I):
        raise ValueError("HTML shell received instead of official Markdown/text")
    heading = next((line.lstrip("# ") for line in body.splitlines() if line.startswith("#")), "")
    if len(stripped) < 100 or not stripped.startswith("#") or not heading:
        raise ValueError("Documentation body is empty or unexpectedly short")
    if re.fullmatch(r"error|not found|access denied|404|403", heading.strip(), re.I):
        raise ValueError("Error page received instead of documentation")
    return body, {"title": heading}


def load_sources(directory):
    sources = []
    for path in sorted(directory.glob("*-sources.json")):
        server = path.name.removesuffix("-sources.json")
        for raw in json.loads(path.read_text()):
            source = dict(raw, server=server)
            source["key"] = f"{server}/{source['id']}"
            if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", source["id"]):
                raise ValueError(f"Unsafe source id: {source['id']}")
            official_url(source["url"])
            official_url(source.get("fetch_url", source["url"]))
            sources.append(source)
    if not sources or len({source["key"] for source in sources}) != len(sources):
        raise ValueError("Empty source inventory or duplicate IDs")
    return sources


def check_coverage(sources, root=ROOT):
    local = {"list_jobs", "get_job", "list_capabilities", "list_speech_capabilities", "get_speech_usage_examples"}
    errors = []
    for server in ("volcengine-ark", "ali-bailian", "doubao-speech"):
        path = root / "servers" / server / "src" / (server.replace("-", "_") + "_mcp") / "server.py"
        tree = ast.parse(path.read_text())
        tools = {node.name for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                 and any(isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute)
                         and decorator.func.attr == "tool" for decorator in node.decorator_list)}
        covered = {tool for source in sources if source["server"] == server for tool in source.get("tools", [])}
        missing = tools - local - covered
        unknown = covered - tools - {"get_tool_help"}
        if missing or unknown:
            errors.append(f"{server}: missing={sorted(missing)}, unknown={sorted(unknown)}")
    if errors:
        raise ValueError("Official source coverage incomplete: " + "; ".join(errors))


def fetch(source, timeout=30):
    url = official_url(source.get("fetch_url", source["url"]))
    request = urllib.request.Request(url, headers={"User-Agent": "hoobnn-mcps-doc-audit/1.0",
                                                  "Accept": "text/markdown,application/json,text/plain"})
    started = time.monotonic()
    with urllib.request.build_opener(OfficialRedirect()).open(request, timeout=timeout) as response:
        official_url(response.url)
        chunks, size = [], 0
        while block := response.read(65536):
            size += len(block)
            if size > 16 * 1024 * 1024 or time.monotonic() - started > timeout:
                raise ValueError("Documentation response exceeds fetch budget")
            chunks.append(block)
        body = b"".join(chunks).decode("utf-8")
        headers = {key: response.headers.get(key) for key in ("ETag", "Last-Modified", "Content-Type")}
        content_type = (headers["Content-Type"] or "").lower()
        if "text/html" in content_type and source.get("fetch_kind") != "aliyun_html":
            raise ValueError("Documentation export returned text/html, not a machine-readable body")
    content, metadata = extract(body, source)
    content = normalize(content)
    record = {"key": source["key"], "server": source["server"], "id": source["id"], "url": source["url"],
              "fetch_url": url, "kind": source.get("kind", "api"), "tools": sorted(set(source.get("tools", []))),
              "sha256": hashlib.sha256(content.encode()).hexdigest(), "bytes": len(content.encode()),
              "models": sorted(set(MODEL.findall(URL.sub("", content)))),
              "endpoints": sorted({url.rstrip(".,;，。)") for url in URL.findall(content) if is_api_endpoint(url)}),
              "doc_links": sorted({url.rstrip(".,;，。)") for url in URL.findall(content) if is_document_link(url)}),
              **metadata, "headers": headers}
    return record, content


def compare(current, baseline):
    previous = {record["key"]: record for record in baseline.get("sources", [])}
    now = {record["key"]: record for record in current}
    changes = []
    for key in sorted(previous.keys() | now.keys()):
        old, new = previous.get(key), now.get(key)
        if old and new and all(old.get(field) == new.get(field) for field in ("sha256", "url", "fetch_url", "tools")):
            continue
        change = {"key": key, "status": "added" if old is None else "removed" if new is None else "changed",
                  "tools": sorted(set((old or {}).get("tools", []) + (new or {}).get("tools", []))),
                  "url": (new or old)["url"]}
        for field in ("models", "endpoints", "document_codes", "doc_links"):
            before, after = set((old or {}).get(field, [])), set((new or {}).get(field, []))
            change[field + "_added"] = sorted(after - before)
            change[field + "_removed"] = sorted(before - after)
        changes.append(change)
    return changes


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)


def atomic_bytes(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)


def run(sources, baseline, output, workers=4, timeout=30, snapshot_dir=None):
    output.mkdir(parents=True, exist_ok=True)
    records, errors = [], []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fetch, source, timeout): source for source in sources}
        for future in concurrent.futures.as_completed(futures):
            source = futures[future]
            try:
                record, content = future.result()
                records.append(record)
                directory = output / source["server"]
                directory.mkdir(exist_ok=True)
                (directory / (source["id"] + ".md")).write_text(content, encoding="utf-8")
            except Exception as exc:
                errors.append({"key": source["key"], "url": source["url"], "error": f"{type(exc).__name__}: {exc}"})
    records.sort(key=lambda record: record["key"])
    # Failed sources are not removed documents. Retain their old fingerprints
    # for comparison, report failures separately, and refuse baseline updates.
    failed = {error["key"] for error in errors}
    compared = records + [record for record in baseline.get("sources", []) if record["key"] in failed]
    changes = compare(compared, baseline)
    previous = {record["key"]: record for record in baseline.get("sources", [])}
    if snapshot_dir is not None:
        for change in changes:
            old = previous.get(change["key"])
            new = next((record for record in records if record["key"] == change["key"]), None)
            if not old or not new:
                continue
            snapshot = snapshot_dir / (old["sha256"] + ".md.gz")
            try:
                before = gzip.decompress(snapshot.read_bytes()).decode("utf-8")
                if hashlib.sha256(before.encode()).hexdigest() != old["sha256"]:
                    raise ValueError("Reviewed snapshot fingerprint mismatch")
                after = (output / new["server"] / (new["id"] + ".md")).read_text()
                difference = "".join(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                                       fromfile="reviewed/" + change["key"], tofile="current/" + change["key"]))
                directory = output / "diffs" / new["server"]
                directory.mkdir(parents=True, exist_ok=True)
                (directory / (new["id"] + ".diff")).write_text(difference)
            except (OSError, ValueError, UnicodeError, EOFError, zlib.error) as exc:
                errors.append({"key": change["key"], "url": change["url"], "error": f"SnapshotError: {exc}"})
    result = {"format_version": 1, "checked_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "sources": records, "changes": changes, "errors": sorted(errors, key=lambda error: error["key"])}
    atomic_json(output / "result.json", result)
    lines = ["# 官方文档变更检查", "", f"成功 {len(records)} / {len(sources)}，变更 {len(changes)}，抓取失败 {len(errors)}。", "",
             "正文指纹变化表示需要重新核实契约，不表示代码必须更新或模型已对账号开放。models 字段仅是候选标识，需按官方模型表确认。完整差异见 diffs/。", ""]
    for change in changes:
        lines += [f"- **{change['status']}** [{change['key']}]({change['url']})；工具：{', '.join(change['tools']) or '目录发现'}"]
        for field in ("models_added", "models_removed", "endpoints_added", "endpoints_removed", "document_codes_added", "document_codes_removed", "doc_links_added", "doc_links_removed"):
            if change[field]:
                lines += [f"  - {field}: " + ", ".join(change[field])]
    if errors:
        lines += ["", "## 抓取失败", ""] + [f"- {item['key']}: {item['error']}" for item in errors]
    (output / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sources-dir", type=Path, default=ROOT / "docs" / "audits")
    parser.add_argument("--baseline", type=Path, default=ROOT / "docs" / "upstream" / "baseline.json")
    parser.add_argument("--output", type=Path, default=ROOT / ".upstream-docs")
    parser.add_argument("--snapshot-dir", type=Path, default=ROOT / "docs" / "upstream" / "snapshots")
    parser.add_argument("--workers", type=int, default=4, choices=range(1, 9))
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--accept-baseline", action="store_true", help="Replace reviewed local baseline only if every source fetched")
    parser.add_argument("--check-coverage", action="store_true", help="Check source mapping only, without network")
    args = parser.parse_args()
    if not 0 < args.timeout <= 120:
        parser.error("timeout must be in (0, 120]")
    sources = load_sources(args.sources_dir)
    check_coverage(sources)
    if args.check_coverage:
        print(f"Official document mapping covers every remote tool ({len(sources)} sources)")
        return
    baseline = json.loads(args.baseline.read_text()) if args.baseline.exists() else {"sources": []}
    result = run(sources, baseline, args.output, args.workers, args.timeout, args.snapshot_dir)
    if args.accept_baseline and not result["errors"]:
        args.snapshot_dir.mkdir(parents=True, exist_ok=True)
        for record in result["sources"]:
            content = (args.output / record["server"] / (record["id"] + ".md")).read_bytes()
            if hashlib.sha256(content).hexdigest() != record["sha256"]:
                raise ValueError("Fetched body fingerprint mismatch; refusing baseline")
            atomic_bytes(args.snapshot_dir / (record["sha256"] + ".md.gz"), gzip.compress(content, mtime=0))
        atomic_json(args.baseline, {"format_version": 1, "reviewed_at": result["checked_at"], "sources": result["sources"]})
    print(f"sources={len(result['sources'])}/{len(sources)} changes={len(result['changes'])} errors={len(result['errors'])}")
    raise SystemExit(1 if result["errors"] else 0)


if __name__ == "__main__":
    main()
