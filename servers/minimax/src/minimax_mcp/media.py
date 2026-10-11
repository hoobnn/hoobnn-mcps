"""Synchronous media capabilities retained from the official MCP tool surface."""
import base64
import copy
import mimetypes
import re
from pathlib import Path

from . import client
from .video import STORE, failure, result


def options(body, parameters, protected=()):
    if parameters is not None:
        if not isinstance(parameters, dict) or set(parameters) & set(protected):
            raise ValueError(f"parameters 不能覆盖 {sorted(protected)}")
        for key, value in parameters.items():
            if isinstance(value, dict) and isinstance(body.get(key), dict):
                body[key].update(copy.deepcopy(value))
            else:
                body[key] = copy.deepcopy(value)
    return body


def generate(path, body, kind, out_dir, mode):
    client.configuration()
    job = STORE.create(kind, body.get("model", kind), out_dir, mode,
                       summary={"voice_id": body.get("voice_id"), "n": body.get("n")})
    with STORE.processing(job):
        received = False
        try:
            response = client.request(path, body)
            received = True
            STORE.record_response(job, response)
            job.update(state="generated", usage=response.get("usage") or response.get("extra_info"),
                       request_id=response.get("request_id") or response.get("trace_id"))
            if kind == "image":
                urls = response.get("data", {}).get("image_urls") or []
                for index, url in enumerate(urls):
                    STORE.add(job, f"image-{index + 1:02d}.jpg", url=url)
                metadata = response.get("metadata") or {}
                job["result"]["metadata"] = metadata
                if int(metadata.get("failed_count", 0)) > 0 or len(urls) < body["n"]:
                    job["result"]["errors"] = ["部分图片未生成；不会自动重试"]
            elif kind == "voice_design":
                if not response.get("voice_id"):
                    raise ValueError("音色设计响应缺少 voice_id")
                job["result"]["voice_id"] = response["voice_id"]
                STORE.add(job, "preview.mp3", data=bytes.fromhex(response.get("trial_audio", "")))
            elif kind == "voice_clone":
                sensitive = response.get("input_sensitive") or {}
                if sensitive.get("type") not in (None, 0):
                    raise ValueError("音色复刻输入未通过服务端检查")
                job["result"]["voice_id"] = body["voice_id"]
                if response.get("demo_audio"):
                    STORE.add(job, "preview.wav", url=response["demo_audio"])
                else:
                    job.update(state="delivered", error=None)
                    STORE.save(job)
                    return result(job)
            else:
                audio = response.get("data", {}).get("audio")
                if not audio:
                    raise ValueError("响应缺少 data.audio")
                name = "audio." + body["audio_setting"]["format"]
                if body["output_format"] == "url":
                    STORE.add(job, name, url=audio)
                else:
                    STORE.add(job, name, data=bytes.fromhex(audio))
            STORE.deliver(job)
            return result(job)
        except Exception as exc:
            if received:
                job["state"] = "failed"
            return failure(job, exc, submitting=not received)


def image(prompt, model, aspect_ratio, n, prompt_optimizer, subject_reference, parameters, out_dir, mode):
    body = options({"prompt": prompt, "model": model, "aspect_ratio": aspect_ratio, "n": n,
                    "prompt_optimizer": prompt_optimizer, "response_format": "url"}, parameters,
                   {"model", "response_format", "subject_reference"})
    if model not in {"image-01", "image-01-live"}:
        raise ValueError("图片模型支持 image-01 / image-01-live")
    if not isinstance(body["prompt"], str) or not 1 <= len(body["prompt"].strip()) <= 1500:
        raise ValueError("图片 prompt 须为1–1500字符")
    if type(body["n"]) is not int or not 1 <= body["n"] <= 9:
        raise ValueError("n 须为1–9")
    if body["aspect_ratio"] not in {"1:1", "16:9", "4:3", "3:2", "2:3", "3:4", "9:16", "21:9"}:
        raise ValueError("不支持的 aspect_ratio")
    if model == "image-01-live" and body["aspect_ratio"] == "21:9":
        raise ValueError("image-01-live 不支持21:9")
    if subject_reference:
        value = subject_reference
        if not value.startswith(("http://", "https://", "data:")):
            path = Path(value).expanduser()
            if (not path.is_absolute() or not path.is_file() or path.suffix.lower() not in {".jpg", ".jpeg", ".png"}
                    or not 0 < path.stat().st_size < 10 * 1024 * 1024):
                raise ValueError("人物参考须为本地 JPG/PNG 绝对路径且小于10 MB，或公网URL/data URI")
            value = f"data:{mimetypes.guess_type(path.name)[0]};base64," + base64.b64encode(path.read_bytes()).decode()
        body["subject_reference"] = [{"type": "character", "image_file": value}]
    return generate("/v1/image_generation", body, "image", out_dir, mode)


def speech(text, voice_id, model, speed, vol, pitch, emotion, sample_rate, bitrate, channel,
           format, language_boost, parameters, out_dir, mode):
    body = options({"text": text, "model": model, "stream": False, "output_format": "url" if mode == "url" else "hex",
                    "voice_setting": {"voice_id": voice_id, "speed": speed, "vol": vol, "pitch": pitch},
                    "audio_setting": {"sample_rate": sample_rate, "bitrate": bitrate, "channel": channel, "format": format},
                    "language_boost": language_boost}, parameters, {"model", "stream", "output_format"})
    if emotion:
        body["voice_setting"]["emotion"] = emotion
    if not isinstance(body["text"], str) or not 1 <= len(body["text"].strip()) <= 10000:
        raise ValueError("text 须为1–10000字符；本工具为同步合成")
    voice = body["voice_setting"]
    if not voice.get("voice_id") or not 0.5 <= voice["speed"] <= 2 or not 0 < voice["vol"] <= 10 or not -12 <= voice["pitch"] <= 12:
        raise ValueError("voice_id 必填；speed 0.5–2，vol (0,10]，pitch -12–12")
    audio = body["audio_setting"]
    if audio["format"] not in {"mp3", "wav", "flac", "pcm"} or audio["channel"] not in {1, 2}:
        raise ValueError("无效音频格式或声道数")
    return generate("/v1/t2a_v2", body, "speech", out_dir, mode)


def music(prompt, lyrics, model, is_instrumental, lyrics_optimizer, parameters, out_dir, mode):
    body = options({"model": model, "prompt": prompt, "lyrics": lyrics, "is_instrumental": is_instrumental,
                    "lyrics_optimizer": lyrics_optimizer, "stream": False, "output_format": "url",
                    "audio_setting": {"format": "mp3", "sample_rate": 44100, "bitrate": 256000}},
                   parameters, {"model", "stream", "output_format"})
    if model not in {"music-3.0", "music-2.6"}:
        raise ValueError("支持 music-3.0 / music-2.6；免费模型已停服，翻唱不在此工具范围")
    if len(body["prompt"]) > 2000 or len(body["lyrics"]) > 3500:
        raise ValueError("prompt 最多2000字符，lyrics最多3500字符")
    if (body["is_instrumental"] or body["lyrics_optimizer"]) and not body["prompt"].strip():
        raise ValueError("纯音乐 / 歌词优化需要 prompt")
    if not body["is_instrumental"] and not body["lyrics_optimizer"] and not body["lyrics"].strip():
        raise ValueError("人声歌曲需要 lyrics 或 lyrics_optimizer=true")
    if body["audio_setting"]["format"] not in {"mp3", "wav", "pcm"}:
        raise ValueError("无效音乐输出格式")
    return generate("/v1/music_generation", body, "music", out_dir, mode)


def design(prompt, preview_text, voice_id, parameters, out_dir, mode):
    body = options({"prompt": prompt, "preview_text": preview_text}, parameters, {"voice_id"})
    if not body["prompt"].strip() or not 1 <= len(body["preview_text"].strip()) <= 500:
        raise ValueError("prompt 必填，preview_text 须为1–500字符")
    if voice_id:
        body["voice_id"] = voice_id
    return generate("/v1/voice_design", body, "voice_design", out_dir, mode)


def clone(voice_id, file, file_id, text, model, parameters, out_dir, mode):
    if bool(file) == bool(file_id):
        raise ValueError("file 与 file_id 必须且只能提供一个")
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{6,254}[A-Za-z0-9]", voice_id):
        raise ValueError("voice_id 须8–256字符，字母开头，不能以-或_结尾")
    body = options({"voice_id": voice_id}, parameters, {"file_id", "voice_id", "model", "text"})
    if len(text) > 1000:
        raise ValueError("试听 text 最多1000字符")
    if text:
        body.update(text=text, model=model)
    client.configuration()
    # Upload only; voice creation is separately persisted before the paid request.
    file_id = client.upload(file, "voice_clone")["file_id"] if file else client.identifier(file_id)
    if not str(file_id).isdigit():
        raise ValueError("音色复刻 file_id 须为数字")
    body["file_id"] = int(file_id)
    return generate("/v1/voice_clone", body, "voice_clone", out_dir, mode)
