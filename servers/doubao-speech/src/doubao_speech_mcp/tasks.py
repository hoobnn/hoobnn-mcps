"""Durable asynchronous speech tasks: long-text TTS, file ASR and Minutes.

A local record is written before each paid submission. Queries never resubmit;
finished results are saved through the shared job store.
"""

import json

from . import management, products
from .jobs import Store

STORE = Store("DOUBAO_SPEECH_JOB_DIR", "~/.local/share/doubao-speech-mcp/jobs")
MINUTES_FILES = {"AudioTranscriptionFile": "transcription.json", "ChapterFile": "chapters.json",
                 "InformationExtractionFile": "extraction.json", "SummarizationFile": "summary.json",
                 "TranslationFile": "translation.json"}


def _submit(kind, model, out_dir, summary, context, send):
    """Persist before submitting; a missing response stays unknown and is never retried."""
    job = STORE.create(kind, model, out_dir, resume=context, summary=summary)
    with STORE.processing(job):
        response = send()
        task_id = response.get("task_id")
        if not response.get("ok") or not task_id:
            error = str(response.get("error") or "提交响应缺少 task_id")
            # Only transport failures leave the submission outcome unknown (possibly billed).
            unknown = error.startswith(("请求失败", "响应中途断开")) or response.get("ok")
            job.update(state="unknown" if unknown else "failed", error=error)
            if unknown and task_id:
                # Client-generated IDs (file ASR) let get_job check whether the task exists.
                job["task_id"] = task_id
        else:
            job.update(task_id=task_id, state="running", request_id=response.get("request_id") or response.get("logid"))
        STORE.save(job)
        return STORE.result(job)


def _finish_text(job, text, data):
    """Save recognized text and the full provider result as job artifacts."""
    if text:
        STORE.add(job, "transcript.txt", data=text.encode("utf-8"))
    STORE.add(job, "result.json", data=json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"))
    return STORE.deliver(job)


# ---------- 长文本合成 ----------

def submit_tts(body, resource_id, out_dir):
    params = body["req_params"]
    return _submit("tts_long", resource_id, out_dir, {"speaker": params["speaker"], "characters": len(params["text"]),
                   "format": params["audio_params"]["format"]}, {"resource_id": resource_id},
                   lambda: _tts_submitted(products.tts_submit(body, resource_id)))


def _tts_submitted(response):
    data = (response.get("data") or {}).get("data") or {}
    return {**response, "task_id": data.get("task_id") if isinstance(data, dict) else None}


def poll_tts(job, wait=0):
    response = _poll(lambda: products.tts_query(job["task_id"], job["resume"]["resource_id"]), wait)
    payload = (response.get("data") or {}).get("data") or {}
    status = response.get("status")
    if not response.get("ok") and status != "failed":
        job["error"] = response.get("error")
        STORE.save(job)
        return {**STORE.result(job), "ok": False, "query_failed": True}
    job["result"] = {"status": status, "sentences": payload.get("sentences"),
                     "url_expire_time": payload.get("url_expire_time")}
    if status == "failed":
        job.update(state="failed", error=response.get("error"))
    elif status == "succeeded":
        url = payload.get("audio_url")
        if not url:
            job.update(state="unknown", error="任务成功但缺少 audio_url")
        else:
            fmt = job["summary"].get("format", "mp3")
            STORE.add(job, f"speech.{'ogg' if fmt == 'ogg_opus' else fmt}", url=url)
            if payload.get("sentences"):
                STORE.add(job, "sentences.json", data=json.dumps(payload["sentences"], ensure_ascii=False).encode())
            return STORE.deliver(job)
    else:
        job.update(state="running", error=None)
    STORE.save(job)
    return STORE.result(job)


# ---------- 录音文件识别（标准 / 闲时） ----------

def submit_asr(body, mode, out_dir):
    _, resource = products._asr_mode(mode, None)
    return _submit("asr", resource, out_dir, {"mode": mode, "audio": body["audio"]["url"].split("?")[0]},
                   {"mode": mode, "resource_id": resource}, lambda: products.asr_submit(body, mode))


def poll_asr(job, wait=0):
    context = job["resume"]
    response = _poll(lambda: products.asr_query(job["task_id"], context["mode"], context["resource_id"]), wait)
    status = response.get("status")
    if not response.get("ok"):
        job.update(state="failed" if status == "failed" and response.get("code") else job["state"],
                   error=response.get("error"))
        STORE.save(job)
        return {**STORE.result(job), "ok": False, "query_failed": job["state"] != "failed"}
    data = response.get("data") or {}
    if status == "silent":
        job.update(state="delivered", error=None, result={"status": status, "text": ""})
        STORE.save(job)
        return STORE.result(job)
    if status != "succeeded":
        job.update(state="running", error=None, result={"status": status})
        STORE.save(job)
        return STORE.result(job)
    result = data.get("result") or {}
    text = (result.get("text") or "") if isinstance(result, dict) else ""
    job.update(error=None, usage=data.get("audio_info"),
               result={"status": status, "text": text, "duration_ms": (data.get("audio_info") or {}).get("duration")})
    return _finish_text(job, text, data)


# ---------- 妙记 ----------

def submit_minutes(request, out_dir):
    features = [name for name in ("SummarizationEnabled", "ChapterEnabled", "InformationExtractionEnabled",
                                  "TranslationEnable") if request["Params"].get(name)]
    return _submit("minutes", "volc.lark.minutes", out_dir,
                   {"file": request["Input"]["Offline"]["FileURL"].split("?")[0], "features": features}, {},
                   lambda: management.minutes_submit(request))


def poll_minutes(job, wait=0):
    response = _poll(lambda: management.minutes_query(job["task_id"], job["request_id"]), wait,
                     done=lambda r: r.get("state") in ("success", "failed"))
    state = response.get("state")
    if not response.get("ok"):
        job.update(state="failed" if state == "failed" else job["state"], error=response.get("error"))
        STORE.save(job)
        return {**STORE.result(job), "ok": False, "query_failed": state != "failed"}
    if state != "success":
        job.update(state="running", error=None, result={"status": state})
        STORE.save(job)
        return STORE.result(job)
    files = (((response.get("response") or {}).get("Data") or {}).get("Result") or {})
    job["result"] = {"status": state}
    for field, name in MINUTES_FILES.items():
        if files.get(field):
            STORE.add(job, name, url=files[field])
    return STORE.deliver(job)


POLLERS = {"tts_long": poll_tts, "asr": poll_asr, "minutes": poll_minutes}


def _poll(query, wait, done=None):
    """Query once, or until finished within wait seconds. Never resubmits."""
    import time
    from . import transport
    done = done or (lambda r: r.get("status") not in ("running", "queued"))
    deadline = time.monotonic() + max(0, min(wait, 90))
    while True:
        response = query()
        if not response.get("ok") or done(response) or time.monotonic() >= deadline:
            return response
        transport.sleep(min(5, max(0, deadline - time.monotonic())))


def get_job(job_id=None, task_id=None, wait=0):
    return STORE.lookup(job_id, task_id, wait, POLLERS)


def recover(job_id):
    """Re-deliver saved results; a pending task is queried again, never resubmitted."""
    def handle(job):
        poll = POLLERS.get(job["kind"])
        if job["state"] == "download_failed" and job["artifacts"]:
            result = STORE.deliver(job)
            if result["ok"] or not poll:
                return result
        if poll and job["task_id"] and job["state"] != "delivered":
            return poll(job, 0)
        if job["state"] in ("unknown", "failed"):
            return {**STORE.result(job), "ok": False, "error": "没有可恢复的结果，不会自动重新提交"}
        return STORE.deliver(job)
    return STORE.recover(job_id, handle)

