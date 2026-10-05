"""火山方舟图片生成 API 的校验、请求与落盘。只依赖标准库。"""

import base64
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

BASE_URL = os.environ.get("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
MODELS = {
    "pro": "doubao-seedream-5-0-pro-260628",
    "lite": "doubao-seedream-5-0-260128",
}
MAX_REF = {"pro": 10, "lite": 14}
IMAGE_EXT = {"png", "jpeg", "jpg", "webp", "bmp", "tiff", "tif", "gif", "heic", "heif"}


class InputError(ValueError):
    pass


def family(model):
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
    if fam == "pro" and (o["group"] or o["web_search"]):
        return "Seedream 5.0 pro 不支持组图（group）和联网搜索（web_search），改用 model=lite"
    if fam == "lite":
        if o["layers"] or o["transparent"]:
            return "图层拆分（layers）和透明背景（transparent）只有 Seedream 5.0 pro 支持"
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
    if o["group"] and (o["group"] < 1 or n + o["group"] > 15):
        return f"组图要求 参考图数 + 生成数 ≤ 15（当前 {n} + {o['group']}）"
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
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read()), None
    except urllib.error.HTTPError as e:
        raw = e.read().decode(errors="replace")
        try:
            err = json.loads(raw).get("error") or {}
            return None, f"HTTP {e.code} {err.get('code', '')}: {err.get('message', raw)}".strip()
        except (json.JSONDecodeError, AttributeError):
            return None, f"HTTP {e.code}: {raw[:500]}"
    except (urllib.error.URLError, TimeoutError) as e:
        return None, f"请求失败：{e}"


def save(resp, out_dir):
    """out_dir 为 None 时不落盘，只收集图片 URL。"""
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)
    files, layers, errors = [], [], []
    for i, d in enumerate(resp.get("data") or []):
        if d.get("error"):
            errors.append({"index": i, **d["error"]})
            continue
        ext = "jpg" if d.get("output_format") == "jpeg" else d.get("output_format") or "png"
        z = d.get("z_index")
        if not out_dir:
            if d.get("url"):
                files.append(d["url"])
                if z is not None:
                    layers.append({k: d.get(k) for k in ("z_index", "name", "description", "size", "bounding_box")}
                                  | {"url": d["url"]})
            continue
        path = out_dir / (f"layer-{z:02d}.{ext}" if z is not None else f"image-{i + 1:02d}.{ext}")
        if d.get("b64_json"):
            path.write_bytes(base64.b64decode(d["b64_json"]))
        elif d.get("url"):
            urllib.request.urlretrieve(d["url"], path)
        else:
            continue
        files.append(str(path))
        if z is not None:
            layers.append({k: d.get(k) for k in ("z_index", "name", "description", "size", "bounding_box")}
                          | {"file": str(path)})
    if layers and out_dir:
        (out_dir / "layers.json").write_text(json.dumps(layers, ensure_ascii=False, indent=2))
    return files, layers, errors


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

    resp, err = post(body, timeout)
    if err:
        result["error"] = err
        return result
    if resp.get("error"):
        result["error"] = f"{resp['error'].get('code')}: {resp['error'].get('message')}"
        return result
    if mode == "url":
        out_dir = None
    files, layers, errors = save(resp, out_dir)
    result.update(ok=bool(files), files=files, layers=layers, errors=errors,
                  usage=resp.get("usage"), out_dir=str(out_dir) if out_dir else None)
    if not files:
        result["error"] = "没有生成任何图片"
    return result
