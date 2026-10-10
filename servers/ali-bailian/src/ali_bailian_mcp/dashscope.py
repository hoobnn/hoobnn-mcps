"""百炼 DashScope 通用请求，以及生图（multimodal-generation 同步接口）、对话（OpenAI 兼容接口）、模型列表。通过共享 HTTP 连接池请求。"""

import base64
import json
import os
import re
import urllib.error
import urllib.request

from . import transport
from .mcp_runtime import merge_parameters
from pathlib import Path

HOST = os.environ.get("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com").rstrip("/")
IMAGE_MODELS = {
    "qwen": "qwen-image-3.0-pro",
    "wan": "wan2.7-image-pro",
    "z": "z-image-turbo",
}
CHAT_MODELS = {
    "max": "qwen3.8-max",
    "plus": "qwen3.7-plus",
    "flash": "qwen3.8-flash",
}
IMAGE_EXT = {"png", "jpeg", "jpg", "webp", "bmp", "tiff", "tif", "gif"}


class InputError(ValueError):
    pass


def encode_image(src):
    if src.startswith(("http://", "https://", "data:", "oss://")):
        return src
    p = Path(src).expanduser()
    if not p.is_file():
        raise InputError(f"图片不存在：{src}")
    ext = p.suffix.lower().lstrip(".")
    if ext not in IMAGE_EXT:
        raise InputError(f"不支持的图片格式：{p.name}")
    if p.stat().st_size > 10 * 1024 * 1024:
        raise InputError(f"图片超过 10MB：{p.name}")
    mime = {"jpg": "jpeg", "tif": "tiff"}.get(ext, ext)
    return f"data:image/{mime};base64," + base64.b64encode(p.read_bytes()).decode()


def request(path, body=None, timeout=300, headers=None):
    """返回 (json, error)。body 为 None 时发 GET。"""
    key = os.environ.get("DASHSCOPE_API_KEY")
    if not key:
        return None, "未设置环境变量 DASHSCOPE_API_KEY"
    req = urllib.request.Request(
        HOST + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}", **(headers or {})},
    )
    try:
        with transport.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read())
            if not isinstance(data, dict):
                return None, "响应状态未知：服务端返回非对象JSON"
            data.setdefault("request_id", r.headers.get("X-Request-Id"))
            return data, None
    except urllib.error.HTTPError as e:
        return None, http_error(e)
    except (urllib.error.URLError, TimeoutError) as e:
        return None, f"请求失败：{e}"
    except (OSError, ValueError) as e:
        return None, f"响应状态未知：{e}"


def http_error(e):
    raw = e.read().decode(errors="replace")
    try:
        d = json.loads(raw)
    except json.JSONDecodeError:
        return f"HTTP {e.code}: {raw[:500]}"
    if not isinstance(d, dict):
        return f"HTTP {e.code}: {raw[:500]}"
    err = d.get("error") if isinstance(d.get("error"), dict) else d  # 兼容模式包在 error 里，原生接口平铺
    return f"HTTP {e.code} {err.get('code', '')}: {err.get('message', raw[:500])}"


# ---------- 生图 ----------

def image_family(model):
    if model.startswith("wan"):
        return "wan"
    if model.startswith("z-image"):
        return "z"
    if model.startswith(("qwen-image-max", "qwen-image-plus")):
        return "qwen-t2i"  # 只支持文生图、固定尺寸
    if model.startswith("qwen-image"):
        return "qwen"
    return None


def check_image(o, model, fam):
    """服务端也会拒，但本地先挡掉明显的错误组合，省一次请求。"""
    n = len(o["images"])
    if not o["prompt"]:
        return "缺少提示词"
    if fam in ("z", "qwen-t2i") and n:
        return f"{model} 只支持文生图，不能传参考图；编辑图片用 qwen-image-3.0-pro / qwen-image-edit-max 或 wan"
    if fam == "wan" and n > 9:
        return f"wan 最多 9 张参考图，当前 {n} 张"
    if model.startswith(("qwen-image-3.0", "qwen-image-2.1", "qwen-image-2.0")) and o["n"] is not None and not 1 <= o["n"] <= 6:
        return "此Qwen图像系列n范围1–6"
    if model.startswith("qwen-image-3.0") and n > 3:
        return "qwen-image-3.0系列最多3张参考图"
    if model.startswith("qwen-image-2.1") and n > 10:
        return "qwen-image-2.1系列最多10张参考图"
    if fam in ("z", "qwen-t2i") and o["n"] not in (None, 1):
        return f"{model}固定输出1张图片"
    if model.startswith("wan2.7"):
        if not o["group"] and o["n"] is not None and not 1 <= o["n"] <= 4:
            return "wan2.7非组图n范围1–4"
        if o["size"] and o["size"].upper() == "4K" and (model != "wan2.7-image-pro" or n or o["group"]):
            return "4K仅支持wan2.7-image-pro无参考图的非组图文生图"
    if fam != "wan" and (o["group"] or o["thinking"] is not None):
        return "group（组图）和 thinking 只有 wan 系列支持"
    if fam != "wan" and o["size"] and o["size"].upper() in ("1K", "2K", "4K"):
        return "1K / 2K / 4K 档位只有 wan 系列支持，其他模型写 宽*高"
    if o["group"] and not 1 <= o["group"] <= 12:
        return "组图张数 group 范围 1–12"
    return None


def build_image_body(o, model):
    content = [{"text": o["prompt"]}] + [{"image": encode_image(s)} for s in o["images"]]
    params = {"watermark": o["watermark"]}
    if o["size"]:
        s = o["size"].strip()
        params["size"] = s.upper() if s.upper() in ("1K", "2K", "4K") else re.sub(r"\s*[xX×]\s*", "*", s)
    if o["group"]:
        params["enable_sequential"] = True
        params["n"] = o["group"]
    elif o["n"]:
        params["n"] = o["n"]
    if o["negative_prompt"]:
        params["negative_prompt"] = o["negative_prompt"]
    if o["prompt_extend"] is not None:
        params["prompt_extend"] = o["prompt_extend"]
    if o["seed"] is not None:
        params["seed"] = o["seed"]
    if o["thinking"] is not None:
        params["thinking_mode"] = o["thinking"]
    merge_parameters(params, o.get("parameters"))
    return {"model": model, "input": {"messages": [{"role": "user", "content": content}]}, "parameters": params}


def generate_image(o, out_dir, mode="local", timeout=300):
    """mode=local 下载到 out_dir；mode=url 只返回 24 小时内有效的图片 URL。"""
    model = IMAGE_MODELS.get(o["model"], o["model"])
    fam = image_family(model)
    result = {"ok": False, "model": model, "files": [], "text": None, "usage": None, "error": None, "out_dir": None}
    try:
        err = check_image(o, model, fam)
        body = None if err else build_image_body(o, model)
    except InputError as e:
        err = str(e)
    if err:
        result["error"] = err
        return result

    from .products import STORE
    job = STORE.create("image", model, out_dir, mode,
                       summary={"size": o["size"], "n": o["n"], "group": o["group"]})
    with STORE.processing(job):
        resp, err = request("/api/v1/services/aigc/multimodal-generation/generation", body, timeout)
        if err:
            job.update(error=err, state="failed" if err.startswith(("HTTP 4", "未设置")) else "unknown")
            STORE.save(job)
            return STORE.result(job)
        if resp.get("code"):
            job.update(state="failed", error=f"{resp['code']}: {resp.get('message')}")
            STORE.save(job)
            return STORE.result(job)

        STORE.record_response(job, resp)
        return deliver_image(resp, job)


def deliver_image(resp, job):
    from .products import STORE
    urls, texts = [], []
    for c in (resp.get("output") or {}).get("choices") or []:
        for part in (c.get("message") or {}).get("content") or []:
            if part.get("image"):
                urls.append(part["image"])
            elif part.get("text"):
                texts.append(part["text"])
    job.update(usage=resp.get("usage"), request_id=resp.get("request_id"), state="generated",
               result={"text": "\n".join(texts) or None})
    STORE.save(job)
    for i, url in enumerate(urls):
        ext = Path(url.split("?")[0]).suffix.lower()
        ext = ext if ext in (".png", ".jpg", ".jpeg", ".webp") else ".png"
        STORE.add(job, f"image-{i + 1:02d}{ext}", url=url)
    if not urls:
        job.update(state="failed", error="没有生成任何图片")
        STORE.save(job)
        return STORE.result(job)
    return STORE.deliver(job)


# ---------- 对话 ----------

def build_chat_body(o, model):
    messages = []
    if o["system"]:
        messages.append({"role": "system", "content": o["system"]})
    messages += o["history"] or []
    if o["images"]:
        content = [{"type": "image_url", "image_url": {"url": encode_image(s)}} for s in o["images"]]
        content.append({"type": "text", "text": o["prompt"]})
    else:
        content = o["prompt"]
    messages.append({"role": "user", "content": content})
    # 统一走流式：部分模型（思考模型、omni 等）只支持流式
    body = {"model": model, "messages": messages, "stream": True, "stream_options": {"include_usage": True}}
    if o["thinking"] is not None:
        body["enable_thinking"] = o["thinking"]
    if o["thinking_budget"]:
        body["thinking_budget"] = o["thinking_budget"]
    if o["max_tokens"]:
        body["max_tokens"] = o["max_tokens"]
    if o["temperature"] is not None:
        body["temperature"] = o["temperature"]
    if o["json_mode"]:
        body["response_format"] = {"type": "json_object"}
    if o["web_search"]:
        body["enable_search"] = True
    extra = o.get("parameters") or {}
    if set(extra) & {"model", "messages", "stream"}:
        raise InputError("parameters 不能覆盖 model/messages/stream")
    merge_parameters(body, extra)
    return body


def sse_data(lines):
    """Parse SSE frames, including multiline data and ignored heartbeat comments."""
    pending = []
    for raw in lines:
        line = raw.decode("utf-8").rstrip("\r\n")
        if not line:
            if pending:
                yield "\n".join(pending)
                pending = []
        elif line.startswith("data:"):
            pending.append(line[5:].lstrip(" "))
    if pending:
        # Some providers omit the final blank line; the DONE check still detects
        # a premature transport EOF after a nonterminal event.
        yield "\n".join(pending)


def chat(o, timeout=600):
    model = CHAT_MODELS.get(o["model"], o["model"])
    result = {"ok": False, "model": model, "content": "", "reasoning": None, "finish_reason": None,
              "usage": None, "error": None}
    if not o["prompt"]:
        result["error"] = "缺少 prompt"
        return result
    key = os.environ.get("DASHSCOPE_API_KEY")
    if not key:
        result["error"] = "未设置环境变量 DASHSCOPE_API_KEY"
        return result
    try:
        body = build_chat_body(o, model)
    except InputError as e:
        result["error"] = str(e)
        return result

    req = urllib.request.Request(
        HOST + "/compatible-mode/v1/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
    )
    content, reasoning = [], []
    done = False
    try:
        with transport.urlopen(req, timeout=timeout) as r:
            for data in sse_data(r):
                if data == "[DONE]":
                    done = True
                    break
                chunk = json.loads(data)
                if not isinstance(chunk, dict):
                    raise ValueError("SSE chunk must be an object")
                if chunk.get("error"):
                    result["error"] = str(chunk["error"])
                    break
                if chunk.get("usage"):
                    result["usage"] = chunk["usage"]
                for c in chunk.get("choices") or []:
                    delta = c.get("delta") or {}
                    if delta.get("content"):
                        content.append(delta["content"])
                    if delta.get("reasoning_content"):
                        reasoning.append(delta["reasoning_content"])
                    if c.get("finish_reason"):
                        result["finish_reason"] = c["finish_reason"]
        if not result["error"] and not done:
            result["error"] = "流式响应提前结束，未收到 [DONE]；不会自动重新请求"
        if not result["error"] and not content:
            result["error"] = "响应没有回答文本"
    except urllib.error.HTTPError as e:
        result["error"] = http_error(e)
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        result["error"] = f"请求失败：{e}"
    except (ValueError, TypeError, AttributeError) as e:
        result["error"] = f"无效流式响应：{e}"
    result.update(ok=result["error"] is None, content="".join(content), reasoning="".join(reasoning) or None,
                  partial=bool(result["error"] and (content or reasoning)))
    return result


def list_models(keyword=None, max_pages=20):
    """Read the official paginated model catalog, not account authorization."""
    from urllib.parse import urlencode
    if not 1 <= max_pages <= 100:
        return {"ok": False, "models": [], "error": "max_pages范围1–100"}
    records, seen, total = [], set(), None
    for page in range(1, max_pages + 1):
        query = {"page_no": page, "page_size": 100, "language": "zh-CN"}
        if keyword:
            query["name"] = keyword
        resp, err = request("/api/v1/models?" + urlencode(query), timeout=30)
        if not err and (resp.get("code") or resp.get("success") is False):
            err = f"{resp.get('code')}: {resp.get('message')}"
        if err:
            return {"ok": False, "models": sorted(seen), "catalog": records,
                    "complete": False, "account_verified": False, "error": err}
        output = resp.get("output") or {}
        items = output.get("models")
        if not isinstance(items, list) or any(not isinstance(item, dict) or not item.get("model") for item in items):
            return {"ok": False, "models": sorted(seen), "complete": False,
                    "account_verified": False, "error": "模型目录响应缺少output.models[].model"}
        total = output.get("total")
        previous = len(seen)
        for item in items:
            if item["model"] not in seen:
                seen.add(item["model"])
                records.append(item)
        if not items or (isinstance(total, (int, float)) and len(seen) >= total):
            return {"ok": True, "models": sorted(seen), "catalog": records, "total": total,
                    "complete": True, "account_verified": False, "error": None}
        if len(seen) == previous:
            return {"ok": False, "models": sorted(seen), "catalog": records, "complete": False,
                    "account_verified": False, "error": "模型目录分页未前进，不能声称列表完整"}
    return {"ok": True, "models": sorted(seen), "catalog": records, "total": total,
            "complete": False, "account_verified": False, "error": None}
