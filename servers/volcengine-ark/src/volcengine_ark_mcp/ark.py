"""火山方舟图片生成 API 的校验、请求与落盘。通过共享 HTTP 连接池请求。"""

import base64
import json
import os
import re
import urllib.error
import urllib.request

from . import transport
from .mcp_runtime import merge_parameters
from pathlib import Path

BASE_URL = os.environ.get("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
MODELS = {
    "pro": "doubao-seedream-5-0-pro-260628",
    "lite": "doubao-seedream-5-0-260128",
    "flash": "doubao-seedream-5-0-flash-260915",
}
MAX_REF = {"pro": 10, "flash": 10, "lite": 14}
IMAGE_EXT = {"png", "jpeg", "jpg", "webp", "bmp", "tiff", "tif", "gif", "heic", "heif"}


class InputError(ValueError):
    pass


def family(model):
    if "seedream-5-0-flash" in model:
        return "flash"
    if "seedream-5-0-pro" in model:
        return "pro"
    if "seedream-5-0-26" in model:
        return "lite"
    return None  # Endpoint ID 等无法识别的，跳过本地校验，交给服务端


def encode_image(src):
    if src.startswith(("http://", "https://", "data:")):
        return src
    p = Path(src).expanduser()
    if not p.is_file():
        raise InputError(f"参考图不存在：{src}")
    ext = p.suffix.lower().lstrip(".")
    if ext not in IMAGE_EXT:
        raise InputError(f"不支持的图片格式：{p.name}")
    if p.stat().st_size > 30 * 1024 * 1024:
        raise InputError(f"参考图超过 30MB：{p.name}")
    mime = {"jpg": "jpeg", "tif": "tiff"}.get(ext, ext)
    return f"data:image/{mime};base64," + base64.b64encode(p.read_bytes()).decode()


def check(o, fam):
    """服务端也会拒，但本地先挡掉，省一次请求和一段等待。"""
    n = len(o["images"])
    if fam in ("pro", "flash") and (o["group"] is not None or o["web_search"]):
        return f"Seedream 5.0 {fam} 不支持组图（group）和联网搜索（web_search），改用 model=lite"
    if fam == "flash" and o["fast"]:
        return "Seedream 5.0 flash 不支持 fast 提示词优化模式"
    if fam == "lite":
        if o["layers"] or o["transparent"]:
            return "图层拆分（layers）和透明背景（transparent）仅 Seedream 5.0 pro/flash 支持"
        if o["fast"]:
            return "fast 只有 Seedream 5.0 pro 支持"
    if fam and n > MAX_REF[fam]:
        return f"{fam} 最多 {MAX_REF[fam]} 张参考图，当前 {n} 张"
    if o["layers"] and n != 1:
        return "图层拆分必须且只能传 1 张图（png / jpeg）"
    if o["transparent"]:
        if n != 1:
            return "透明背景只支持图生图，且只能传 1 张带透明通道的图"
        if o["output_format"] == "jpeg":
            return "透明背景输出是 png，不能同时指定 output_format=jpeg"
    if o["group"] is not None and (isinstance(o["group"], bool) or not isinstance(o["group"], int) or o["group"] < 1 or n + o["group"] > 15):
        return f"组图要求 参考图数 + 生成数 ≤ 15（当前 {n} + {o['group']}）"
    if o["output_format"] is not None and o["output_format"] not in ("png", "jpeg"):
        return "output_format 必须为 png 或 jpeg"
    if fam and o["size"] is not None:
        allowed = {"2K", "3K", "4K"} if fam == "lite" else {"1K", "1.5K", "2K"}
        if o["layers"]:
            allowed.add("auto")
        size = o["size"]
        if size not in allowed:
            dimensions = re.fullmatch(r"([1-9][0-9]*)x([1-9][0-9]*)", size)
            if not dimensions or o["layers"]:
                return "所选模型/场景不支持该 size；图层拆分仅支持分辨率档位"
            width, height = map(int, dimensions.groups())
            minimum, maximum = (3686400, 16777216) if fam == "lite" else (921600, 4624220)
            if not minimum <= width * height <= maximum or not 1 / 16 <= width / height <= 16:
                return "size 超出所选模型的像素总量或宽高比范围"
    if not o["prompt"] and not o["layers"]:
        return "缺少提示词（只有图层拆分可以不写）"
    return None


def build_body(o, model, mode="local"):
    body = {"model": model, "response_format": "url" if mode == "url" else "b64_json",
            "watermark": o["watermark"]}
    if o["prompt"]:
        body["prompt"] = o["prompt"]
    if o["images"]:
        imgs = [encode_image(s) for s in o["images"]]
        body["image"] = imgs[0] if len(imgs) == 1 else imgs
    if o["size"]:
        body["size"] = o["size"]
    if o["output_format"]:
        body["output_format"] = o["output_format"]
    if o["transparent"]:
        body["background"] = "transparent"
    if o["layers"]:
        body["layer_decomposition"] = True
    if o["group"]:
        body["sequential_image_generation"] = "auto"
        body["sequential_image_generation_options"] = {"max_images": o["group"]}
    if o["web_search"]:
        body["tools"] = [{"type": "web_search"}]
    if o["fast"]:
        body["optimize_prompt_options"] = {"mode": "fast"}
    extra = o.get("parameters")
    if extra:
        if not isinstance(extra, dict) or set(extra) & {"model", "response_format"}:
            raise InputError("parameters 必须是 object，且不能覆盖 model/response_format")
        merge_parameters(body, extra)
    return body


def post(body, timeout):
    key = os.environ.get("ARK_API_KEY")
    if not key:
        return None, "未设置环境变量 ARK_API_KEY"
    req = urllib.request.Request(
        BASE_URL.rstrip("/") + "/images/generations",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
    )
    try:
        with transport.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read())
            if not isinstance(data, dict):
                return None, "响应状态未知：服务端返回非对象JSON"
            data.setdefault("request_id", r.headers.get("X-Request-Id"))
            return data, None
    except urllib.error.HTTPError as e:
        raw = e.read().decode(errors="replace")
        try:
            err = json.loads(raw).get("error") or {}
            return None, f"HTTP {e.code} {err.get('code', '')}: {err.get('message', raw)}".strip()
        except (json.JSONDecodeError, AttributeError):
            return None, f"HTTP {e.code}: {raw[:500]}"
    except (urllib.error.URLError, TimeoutError) as e:
        return None, f"请求失败：{e}"
    except (OSError, ValueError) as e:
        return None, f"响应状态未知：{e}"


def generate(o, out_dir, timeout=300, mode="local"):
    """mode=local 下载到 out_dir；mode=url 只返回 24 小时内有效的图片 URL，不落盘。"""
    model = MODELS.get(o["model"], o["model"])
    result = {"ok": False, "model": model, "files": [], "layers": [], "usage": None,
              "errors": [], "error": None, "out_dir": None}
    try:
        err = check(o, family(model))
        body = None if err else build_body(o, model, mode)
    except InputError as e:
        err = str(e)
    if err:
        result["error"] = err
        return result

    from .products import STORE
    job = STORE.create("image", model, out_dir, mode,
                       summary={"size": o["size"], "group": o["group"], "layers": o["layers"],
                                "output_format": o["output_format"] or ("png" if o["transparent"] else "jpeg")})
    with STORE.processing(job):
        resp, err = post(body, timeout)
        if err:
            job.update(error=err, state="failed" if err.startswith(("HTTP 4", "未设置")) else "unknown")
            STORE.save(job)
            return STORE.result(job)
        if resp.get("error"):
            job.update(state="failed", error=str(resp["error"]))
            STORE.save(job)
            return STORE.result(job)
        STORE.record_response(job, resp)
        return deliver_image(resp, job)


def deliver_image(resp, job):
    from .products import STORE
    from .jobs import atomic_bytes
    errors = []
    job.update(usage=resp.get("usage"), request_id=resp.get("request_id"), state="generated")
    STORE.save(job)
    for i, item in enumerate(resp.get("data") or []):
        if item.get("error"):
            errors.append({"index": i, "error": item["error"]})
            continue
        z = item.get("z_index")
        output_format = item.get("output_format")
        if not output_format:
            output_format = "png" if isinstance(z, int) and z > 0 else job.get("summary", {}).get("output_format", "jpeg")
            # Legacy records do not persist output_format; trust actual inline bytes.
            if item.get("b64_json"):
                try:
                    signature = base64.b64decode(item["b64_json"][:16])
                    if signature.startswith(b"\x89PNG\r\n\x1a\n"):
                        output_format = "png"
                    elif signature.startswith(b"\xff\xd8\xff"):
                        output_format = "jpeg"
                except ValueError:
                    pass  # Full base64 validation below records the artifact failure.
        ext = "jpg" if output_format == "jpeg" else "png"
        name = f"layer-{z:02d}.{ext}" if isinstance(z, int) else f"image-{i + 1:02d}.{ext}"
        metadata = {k: item.get(k) for k in ("z_index", "name", "description", "size", "bounding_box")}
        try:
            STORE.add(job, name, url=item.get("url"),
                      data=base64.b64decode(item["b64_json"], validate=True) if item.get("b64_json") else None,
                      metadata=metadata)
        except (OSError, ValueError) as exc:
            errors.append({"index": i, "error": str(exc)})
    job["result"]["errors"] = errors
    if not job["artifacts"]:
        job.update(state="failed", error="没有可交付的图片")
        STORE.save(job)
        return STORE.result(job)
    STORE.deliver(job)
    layers = [{**a["metadata"], **({"file": a["file"]} if a.get("file") else {"url": a.get("url")})}
              for a in job["artifacts"] if a.get("metadata", {}).get("z_index") is not None]
    job["result"]["layers"] = layers
    if layers and job["mode"] == "local":
        try:
            atomic_bytes(Path(job["out_dir"]) / "layers.json", json.dumps(layers, ensure_ascii=False, indent=2).encode())
        except OSError as exc:
            job.update(state="download_failed", error=f"图层索引保存失败：{exc}")
    if errors and job["state"] == "delivered":
        job.update(state="partial", error="部分图片生成失败；恢复不会重新生成失败项")
    STORE.save(job)
    return STORE.result(job)
