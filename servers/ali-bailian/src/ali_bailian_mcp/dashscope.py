"""百炼 DashScope 通用请求，以及生图（multimodal-generation 同步接口）、对话（OpenAI 兼容接口）、模型列表。只依赖标准库。"""

import base64
import json
import os
import re
import urllib.error
import urllib.request
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
        with urllib.request.urlopen(req, timeout=timeout) as r:
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
    return body


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
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            for line in r:
                line = line.decode().strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                chunk = json.loads(data)
                if chunk.get("error"):
                    result["error"] = f"{chunk['error'].get('code', '')}: {chunk['error'].get('message')}"
                    return result
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
    except urllib.error.HTTPError as e:
        result["error"] = http_error(e)
        return result
    except (urllib.error.URLError, TimeoutError) as e:
        result["error"] = f"请求失败：{e}"
        return result
    result.update(ok=True, content="".join(content), reasoning="".join(reasoning) or None)
    return result


def list_models(keyword=None):
    resp, err = request("/compatible-mode/v1/models", timeout=30)
    if err:
        return {"ok": False, "models": [], "error": err}
    ids = sorted(m["id"] for m in resp.get("data") or [])
    if keyword:
        ids = [i for i in ids if keyword.lower() in i.lower()]
    return {"ok": True, "models": ids, "error": None}
