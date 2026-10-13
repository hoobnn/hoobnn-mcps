"""MiniMax stdio tools, independent of the official minimax-mcp distribution."""
import functools
import os
import time
import uuid
from pathlib import Path

from mcp.types import ToolAnnotations

from . import client, media, video
from .mcp_runtime import ReliableMCPServer

OUT_ROOT = Path(os.environ.get("MINIMAX_OUT_DIR", os.environ.get("MINIMAX_MCP_BASE_PATH", "~/Downloads/minimax"))).expanduser()
MODE = os.environ.get("MINIMAX_RESOURCE_MODE", os.environ.get("MINIMAX_API_RESOURCE_MODE", "local")).lower()
if MODE not in {"local", "url"}:
    raise ValueError("MINIMAX_RESOURCE_MODE / MINIMAX_API_RESOURCE_MODE 须为 local 或 url")

mcp = ReliableMCPServer("minimax", groups={
    "video": {"generate_video", "query_video_generation", "list_video_tasks", "create_h3_context_ir_task", "regenerate_video"},
    "image": {"text_to_image"}, "speech": {"text_to_audio", "list_voices", "voice_clone", "voice_design"},
    "music": {"music_generation"}, "files": {"upload_file"},
    "jobs": {"list_jobs", "get_job", "recover_job"},
    "admin": {"delete_video_task"}, "help": {"list_capabilities", "get_tool_help"}}, optional_groups={"admin"})


def guarded(fn):
    @functools.wraps(fn)
    def call(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except (ValueError, OSError, TypeError, KeyError) as exc:
            answer = {"ok": False, "error": str(exc), "retryable": False}
            if isinstance(exc, client.APIError):
                answer.update(error_code=exc.code, request_id=exc.request_id)
            return answer
    return call


def target_dir(output_directory=None):
    root = Path(output_directory).expanduser() if output_directory else OUT_ROOT
    return root / (time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8])


@mcp.tool()
@guarded
def generate_video(prompt: str = "", model: str = "MiniMax-H3", content: list[dict] | None = None,
                   first_frame: str | None = None, last_frame: str | None = None,
                   reference_images: list[str] | None = None, reference_videos: list[str] | None = None,
                   reference_audios: list[str] | None = None, duration: int = 5, resolution: str | None = None,
                   ratio: str | None = None, wait: int = 0, output_directory: str | None = None,
                   parameters: dict | None = None) -> dict:
    """MiniMax H3 V2 音画视频生成，支持文生、首帧、尾帧、首尾帧和多模态参考。按量计费。
    H3: 4–15整数秒，768P/2K（默认2K）；H3-Max: 5–15秒，480P/768P（默认768P），不支持2K。
    prompt 与快捷素材参数可组合；或单独传官方 content 数组，不能混用。所有模式需要1个非空text，最多7000字符。
    素材接受公网URL、mm_file://ID、data URI或本地绝对路径；本地文件自动上传，有效期7天。
    首/尾帧各最多1张，与参考素材互斥；参考图<=9、视频<=3、音频<=3。图片<=30MB，视频<=50MB，音频<=15MB；
    参考视频/音频每段2–15秒且各自总长<=15秒，具体尺寸/编码由上传接口校验。请求体<=64MB。
    ratio省略时文生为16:9，其余adaptive；首尾帧总是跟随图片比例。parameters支持callback_url/aigc_watermark；
    H3-Max另支持extra.prompt_expansion_mode=disabled/balanced/quality。不允许覆盖模型或content。
    wait=0只提交，最多等待90秒；返回job_id/task_id，get_job后续查询及下载，recover_job只补交付不重新生成。
    工具超时可用list_jobs找回。HTTP超时且无task_id时不自动重试，避免重复付费。离线契约已测试，账号权限需实际调用验证。
    """
    body = video.build_request("generation", prompt=prompt, model=model, content=content, duration=duration,
                               resolution=resolution, ratio=ratio, first_frame=first_frame, last_frame=last_frame,
                               reference_images=reference_images, reference_videos=reference_videos,
                               reference_audios=reference_audios, parameters=parameters)
    return video.submit(body, "generation", target_dir(output_directory), MODE, wait)


@mcp.tool()
@guarded
def create_h3_context_ir_task(prompt: str = "", content: list[dict] | None = None, duration: int = 5,
                         ratio: str | None = None, wait: int = 0, output_directory: str | None = None,
                         parameters: dict | None = None) -> dict:
    """创建 H3-Context-IR 任务（官方 POST /v2/h3_context_ir）：深度理解多模态输入，异步返回结构化增强提示词，不直接生成视频；按Token计费。
    纯文本传prompt，多模态传官方content数组（二选一）；素材/组合限制同generate_video。duration为4–15秒。
    parameters仅支持callback_url。wait=0只提交，后续get_job返回prompt及prompt.txt；需要生成视频时把返回的prompt交给generate_video。
    """
    body = video.build_request("h3_context_ir", prompt=prompt, content=content, duration=duration,
                               ratio=ratio, parameters=parameters)
    return video.submit(body, "h3_context_ir", target_dir(output_directory), MODE, wait)


@mcp.tool()
@guarded
def regenerate_video(source_task_id: str | None = None, content: list[dict] | None = None,
                     wait: int = 0, output_directory: str | None = None, parameters: dict | None = None) -> dict:
    """创建视频再生成任务（官方 POST /v2/video_regeneration）：将符合MiniMax-H3 768P输出规格的视频再生成为2K，单独计费；不是任意视频放大。
    source_task_id与content二选一。按ID需要白名单、属于本账号且7天内成功生成的源任务。
    content须原样包含源视频生成时最终prompt和全部参考素材，加且只加1个type=video_url/role=base_video项。
    源视频须带音轨、24fps、宽高均可被32整除，像素面积589824–1032192，总帧数107–362且每档递增17帧。
    本地输入自动上传；parameters支持callback_url/aigc_watermark。返回task_id/job_id，后续get_job查询并下载。
    """
    body = video.build_request("regeneration", source_task_id=source_task_id, content=content, parameters=parameters)
    return video.submit(body, "regeneration", target_dir(output_directory), MODE, wait)


@mcp.tool()
@guarded
def query_video_generation(task_id: str, output_directory: str | None = None, wait: int = 0) -> dict:
    """查询H3 V2任务（generation/h3_context_ir/regeneration），成功后下载或返回URL，不重新生成。
    保留官方MCP工具名，但不支持旧V1任务。平台查询窗口7天；未知task_id会建立本地记录，已有记录沿用原输出目录。
    """
    return video.get_job(task_id=task_id, wait=wait, out_dir=target_dir(output_directory), mode=MODE)


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, idempotent_hint=True, open_world_hint=True))
@guarded
def list_video_tasks(page_num: int = 1, page_size: int = 20, status: str | None = None,
                     task_ids: list[str] | None = None, model: str | None = None, task_type: str | None = None) -> dict:
    """分页查询云端最近7天H3任务，不下载。task_type为generation/h3_context_ir/regeneration。
    status为queued/running/succeeded/failed/cancelled；本地历史记录用list_jobs。
    """
    if page_num < 1 or not 1 <= page_size <= 100:
        raise ValueError("page_num>=1，page_size为1–100")
    if status and status not in {"queued", "running", "succeeded", "failed", "cancelled"}:
        raise ValueError("无效status")
    if task_type and task_type not in video.ENDPOINTS:
        raise ValueError("无效task_type")
    return {"ok": True, **client.request("/v2/query/video_generation", query={
        "page_num": page_num, "page_size": page_size, "filter.status": status,
        "filter.task_ids": [client.identifier(value) for value in task_ids] if task_ids else None,
        "filter.model": model, "filter.task_type": task_type})}


@mcp.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True, idempotent_hint=False, open_world_hint=True))
@guarded
def delete_video_task(task_id: str) -> dict:
    """取消queued任务，或删除succeeded/failed任务的云端记录；running任务不支持取消。
    会影响云端任务，仅用户要求取消/删除时调用；保留本地已下载文件。admin工具组默认关闭。
    """
    return {"ok": True, **client.request("/v2/video_generation/" + client.identifier(task_id), method="DELETE")}


@mcp.tool()
@guarded
def upload_file(file: str, purpose: str = "video_generation_input") -> dict:
    """上传指定本地绝对路径，返回file_id和mm_file://引用，不生成媒体。
    purpose支持video_generation_input（图片<=30MB/视频<=50MB/音频<=15MB，保存7天）、voice_clone和prompt_audio（<=20MB）。
    generate_video也可自动上传本地素材。远端媒体请直接传URL，无需本工具下载后重传。
    """
    return client.upload(file, purpose)


@mcp.tool()
@guarded
def text_to_image(prompt: str, model: str = "image-01", aspect_ratio: str = "1:1", n: int = 1,
                  prompt_optimizer: bool = False, subject_reference: str | None = None,
                  output_directory: str | None = None, parameters: dict | None = None) -> dict:
    """MiniMax文生图/人物参考图生图，model=image-01或image-01-live，n=1–9，按张计费。
    subject_reference为单人人像公网URL/data URI或本地JPG/PNG(<10MB)。prompt最多1500字符。
    parameters支持官方高级字段（如style、seed、aigc_watermark），不能覆盖model/response_format/subject_reference。
    local模式下载图片，url模式返回24小时链接；部分失败如实报告，recover_job只补交付。
    """
    return media.image(prompt, model, aspect_ratio, n, prompt_optimizer, subject_reference, parameters,
                       target_dir(output_directory), MODE)


@mcp.tool()
@guarded
def text_to_audio(text: str, voice_id: str = "male-qn-qingse", model: str = "speech-2.8-hd",
                  speed: float = 1, vol: float = 1, pitch: int = 0, emotion: str | None = None,
                  sample_rate: int = 32000, bitrate: int = 128000, channel: int = 1, format: str = "mp3",
                  language_boost: str = "auto", output_directory: str | None = None,
                  parameters: dict | None = None) -> dict:
    """同步语音合成，text最多10000字符，按字符计费；默认speech-2.8-hd，也可显式选择其他官方语音模型。
    voice_id用list_voices获取；speed=0.5–2，vol=(0,10]，pitch=-12–12，format=mp3/wav/flac/pcm。
    parameters深度合并voice_setting/audio_setting等官方选项，不支持stream；结果持久保存，可recover_job补下载。
    """
    return media.speech(text, voice_id, model, speed, vol, pitch, emotion, sample_rate, bitrate, channel,
                        format, language_boost, parameters, target_dir(output_directory), MODE)


@mcp.tool()
@guarded
def list_voices(voice_type: str = "all") -> dict:
    """查询本账号可用音色；voice_type为all/system/voice_cloning/voice_generation，不生成语音。"""
    if voice_type not in {"all", "system", "voice_cloning", "voice_generation"}:
        raise ValueError("无效voice_type")
    return {"ok": True, **client.request("/v1/get_voice", {"voice_type": voice_type})}


@mcp.tool()
@guarded
def voice_clone(voice_id: str, file: str | None = None, file_id: str | None = None, text: str = "",
                model: str = "speech-2.8-hd", output_directory: str | None = None,
                parameters: dict | None = None) -> dict:
    """音色快速复刻，file（本地绝对路径）或已上传file_id二选一；mp3/m4a/wav，10秒–5分钟，<=20MB。
    voice_id须8–256字符且字母开头，仅字母数字-_且不能以-_结尾。可选试听text<=1000字符，试听按合成计费。
    parameters支持clone_prompt等官方参数；示例音频可用upload_file(purpose=prompt_audio)上传。
    需账号认证；复刻音色首次正式合成时收取复刻费用，7天内未使用会被删除。
    """
    return media.clone(voice_id, file, file_id, text, model, parameters, target_dir(output_directory), MODE)


@mcp.tool()
@guarded
def voice_design(prompt: str, preview_text: str, voice_id: str | None = None,
                 output_directory: str | None = None, parameters: dict | None = None) -> dict:
    """按声音描述设计音色，preview_text为1–500字符且试听计费；返回voice_id和本地试听音频。
    官方试听只提供hex，即使url模式也落地音频，避免将大段hex混进工具上下文。首次正式合成收取音色设计费用，7天未使用删除。
    """
    return media.design(prompt, preview_text, voice_id, parameters, target_dir(output_directory), MODE)


@mcp.tool()
@guarded
def music_generation(prompt: str = "", lyrics: str = "", model: str = "music-3.0",
                     is_instrumental: bool = False, lyrics_optimizer: bool = False,
                     output_directory: str | None = None, parameters: dict | None = None) -> dict:
    """生成歌曲或纯音乐，music-3.0（默认）/music-2.6；prompt<=2000字符，lyrics<=3500字符，生成计费。
    人声歌曲须lyrics或lyrics_optimizer=true；纯音乐设is_instrumental=true并填写prompt。
    官方2026-08-20公告：付费音乐API仅历史付费用户可继续使用，免费接口已停止。账号可用性以服务端为准。
    parameters支持audio_setting等官方字段，不支持stream；结果可recover_job补下载。
    """
    return media.music(prompt, lyrics, model, is_instrumental, lyrics_optimizer, parameters, target_dir(output_directory), MODE)


@mcp.tool()
@guarded
def list_jobs(limit: int = 20, kind: str | None = None) -> dict:
    """列出本地任务，不联网；超时后按时间找回job_id。kind为video/image/speech/music/voice_clone/voice_design。"""
    return video.STORE.list(limit, kind)


@mcp.tool()
@guarded
def get_job(job_id: str | None = None, task_id: str | None = None, wait: int = 0) -> dict:
    """查本地任务；H3排队/运行时查询云端，完成即下载，wait最多90秒。支持采用外部提交的V2 task_id。
    返回completed=false表示仍在进行；失败返回ok=false。同步媒体任务只读本地结果，补下载用recover_job。
    """
    return video.get_job(job_id, task_id, wait, out_dir=target_dir(), mode=MODE)


@mcp.tool()
@guarded
def recover_job(job_id: str, wait: int = 0) -> dict:
    """只修复交付，不重新生成。H3按原task_id刷新链接后下载；同步产物复用保存的URL/音频。
    校验完好的文件跳过下载。无task_id的未知提交不重试；同步URL过期后可能无法恢复。
    """
    return video.get_job(job_id=job_id, wait=wait, recover=True)


@mcp.tool()
def list_capabilities() -> dict:
    """列出本MCP已实现能力与官方来源，不联网；不是账号权限/模型在线可用性证明。"""
    return {"ok": True, "account_verified": False, "validation": "offline_only", "video_models": video.MODELS,
            "docs": "https://platform.minimax.cn/docs/api-reference/api-overview",
            "implementation": "hoobnn-minimax-mcp", "official_package": False,
            "not_implemented": ["legacy Hailuo V1 video", "local speaker playback", "chat", "ASR", "streaming TTS", "async long TTS"],
            "limits": ["H3查询窗口和输入上传有效期为7天", "恢复不重新生成", "macOS/Linux（POSIX任务锁）"]}


def main():
    mcp.run()


if __name__ == "__main__":
    main()
