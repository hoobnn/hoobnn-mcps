"""stdio MCP server：Seedream、Seedance、方舟语言/搜索/向量与本地任务恢复。

环境变量：ARK_API_KEY（必需）、ARK_OUT_DIR（默认 ~/Downloads/volcengine-ark）、
ARK_RESOURCE_MODE（local 下载到本地，url 只返回链接；默认 local）、ARK_BASE_URL（可选）。
旧名 SEEDREAM_OUT_DIR / SEEDREAM_RESOURCE_MODE / SEEDREAM_JOB_DIR 在新名未设置时仍然生效。
"""

import os
import time
import uuid
from pathlib import Path

from mcp.server.mcpserver import MCPServer

from . import ark, products

def env(name, default):
    return os.environ.get(f"ARK_{name}") or os.environ.get(f"SEEDREAM_{name}") or default


OUT_ROOT = Path(env("OUT_DIR", "~/Downloads/volcengine-ark")).expanduser()
MODE = env("RESOURCE_MODE", "local").strip().lower()
if MODE not in ("local", "url"):
    raise SystemExit(f"ARK_RESOURCE_MODE 只能是 local 或 url，当前是 {MODE!r}")

mcp = MCPServer("volcengine-ark")


@mcp.tool()
def generate_image(
    prompt: str = "",
    model: str = "pro",
    images: list[str] | None = None,
    size: str | None = None,
    output_format: str | None = None,
    transparent: bool = False,
    layers: bool = False,
    group: int | None = None,
    web_search: bool = False,
    fast: bool = False,
    watermark: bool = False,
    out_dir: str | None = None,
) -> dict:
    """用火山方舟 Seedream 5.0 生成或编辑图片，结果保存到本地，返回文件路径。

    选模型：
    - model="pro"（默认）：单张高质量图，支持多语言提示词；只有 pro 支持 layers（图层拆分）、
      transparent（透明背景）、fast（低时延）和交互编辑。最多 10 张参考图。
    - model="lite"：只有 lite 支持 group（组图，生成 N 张相互关联的图）、web_search（联网搜索）、3K / 4K。
      最多 14 张参考图，参考图数加 group 不超过 15。
    也可以直接传完整的模型 ID 或 Endpoint ID，此时跳过本地的能力校验。

    参数：
    - prompt：中文不超过 300 字、英文不超过 600 词，太长会丢细节。多图参考时用「图1」「图2」指明各取什么。
    - images：参考图，本地绝对路径或 URL。layers、transparent 只能传 1 张（transparent 要求带透明通道的 png）。
    - size：推荐只给档位，宽高比写进 prompt（如「竖版 9:16」）。pro 可选 1K / 1.5K / 2K（默认 2K，1.5K 与 1K 同价、
      效果更好），lite 可选 2K / 3K / 4K。也可以写 宽x高：pro 总像素 921600–4624220，lite 3686400–16777216，
      宽高比 1/16–16。图层拆分默认 auto（按原图尺寸，夹在 1K–2K）。
    - output_format：png 或 jpeg。图层拆分时只影响底图，图层总是 png。
    - watermark：是否加「AI 生成」水印，默认不加。
    - out_dir：输出目录，默认 ARK_OUT_DIR 下按时间戳新建。交付方式为 url 时忽略。

    场景写法：
    - 图层拆分：prompt 可留空自动拆主要元素；要指定拆哪些，用 0–1000 的归一化坐标框选，如
      「标题的坐标为<bbox>180 64 812 198</bbox>，鹦鹉的坐标为<bbox>347 305 642 997</bbox>」。最多 16 个图层，
      任一图层失败整次报错。返回底图 layer-00 和各图层 png，layers 字段与 layers.json 记录 z_index、名称和
      bounding_box；用 bounding_box.absolute 按 z_index 从小到大贴回底图即可还原。
    - 交互编辑：先在原图上画框、箭头或草图标出位置，再把这张图传入，prompt 写「在左下角标记区域添加…，
      移除所有标记线条，保持构图不变」。

    按成功生成的张数计费：组图和图层拆分会一次产出多张（图层拆分底图和每层各算一张，一张照片自动拆分实测
    产出 11 张），调用前先和用户确认数量。同步调用，单图约半分钟，组图或图层拆分要一两分钟。
    返回 job_id、job_state、artifacts、request_id、ok、files、layers、usage、errors（组图里单张失败）、error。交付方式由 ARK_RESOURCE_MODE 决定：
    local 时 files 是本地路径，url 时 files 是 24 小时内有效的图片链接，需要长期保存要及时下载。
    """
    opts = dict(prompt=prompt or None, model=model, images=images or [], size=size,
                output_format=output_format, transparent=transparent, layers=layers, group=group,
                web_search=web_search, fast=fast, watermark=watermark)
    target = Path(out_dir).expanduser() if out_dir else OUT_ROOT / (time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8])
    return ark.generate(opts, target, mode=MODE)


@mcp.tool()
def generate_video(
    prompt: str = "", model: str = "seedance", first_frame: str | None = None,
    last_frame: str | None = None, reference_images: list[str] | None = None,
    reference_videos: list[str] | None = None, reference_audios: list[str] | None = None,
    resolution: str = "720p", ratio: str = "adaptive", duration: int | None = None,
    audio: bool = True, watermark: bool = False, seed: int | None = None, wait: int = 0,
    out_dir: str | None = None, parameters: dict | None = None,
) -> dict:
    """调用火山方舟 Seedance 生成视频。seedance=2.5，seedance-2/seedance-fast/seedance-mini=2.0 系列，也可传完整模型或 Endpoint ID。
    支持文生、首帧、首尾帧、多模态参考；2.5 可在 prompt 明确写视频编辑或延长意图，编辑须 duration=-1、ratio=adaptive。
    图片支持本地路径/URL，参考视频和音频须公网 URL 或 asset://ID；本工具不上传本地视频/音频。
    具体素材数量、时长、分辨率由模型校验。parameters 透传官方顶层选项，如 draft、return_last_frame、output_format。
    wait=0 默认只提交，1–90 秒可轮询，返回 task_id/job_id；query_video 查询，recover_job 可跨重启恢复。
    按生成视频计费；账户需开通模型。所有新增能力尚未测试，返回文件仅表示下载完成。
    """
    opts = dict(prompt=prompt, model=model, first_frame=first_frame, last_frame=last_frame,
                reference_images=reference_images or [], reference_videos=reference_videos or [],
                reference_audios=reference_audios or [], resolution=resolution, ratio=ratio,
                duration=duration, audio=audio, watermark=watermark, seed=seed, parameters=parameters)
    target = Path(out_dir).expanduser() if out_dir else OUT_ROOT / (time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8])
    return products.submit_video(opts, target, wait, MODE)


@mcp.tool()
def query_video(task_id: str, wait: int = 0, job_id: str | None = None, out_dir: str | None = None) -> dict:
    """查询 Seedance 任务并交付视频。wait=0 查一次，最多90秒；传原 job_id 复用原输出目录并跳过已完整保存的产物。
    未传job_id会创建新的本地记录；不会重新提交生成。返回status、job_state、files、usage、原始response。
    """
    target = Path(out_dir).expanduser() if out_dir else OUT_ROOT / (time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8])
    return products.query_video(task_id, target, wait, MODE, job_id)


@mcp.tool()
def chat(prompt: str, model: str = "pro", system: str | None = None, history: list[dict] | None = None,
         images: list[str] | None = None, videos: list[str] | None = None, thinking: bool | None = None,
         max_tokens: int | None = None, temperature: float | None = None, json_mode: bool = False,
         web_search: bool = False, previous_response_id: str | None = None, parameters: dict | None = None) -> dict:
    """调用方舟语言/多模态模型，pro=豆包Seed 2.1 pro；其他模型传完整ID。
    images支持本地图片或URL，videos为公网URL。history用Chat消息格式，工具不保存对话。
    web_search=true或传previous_response_id时使用Responses API，保留sources和response_id；否则走Chat API。
    thinking控制深度思考；json_mode要求提示词明确JSON结构；parameters透传模型支持的高级字段。
    返回content、reasoning、usage和完整response。按token与搜索调用计费，模型和搜索服务须已开通；尚未测试。
    """
    return products.chat(prompt, model, system, history, images, videos, thinking, max_tokens,
                         temperature, json_mode, web_search, previous_response_id, parameters)


@mcp.tool()
def embed(model: str, texts: list[str] | None = None, contents: list[dict] | None = None,
          dimensions: int | None = None, parameters: dict | None = None) -> dict:
    """方舟文本/多模态向量化，model必须显式指定。texts为文本列表；contents用官方格式，如
    [{"type":"text","text":"猫"},{"type":"image_url","image_url":{"url":"/absolute/cat.png"}}]。
    两项只能选一项；图片支持本地路径，视频须URL。parameters支持instructions、multi_embedding等模型选项。
    保留data和usage，不自动建索引或知识库；按输入计费。尚未测试。
    """
    return products.embed(model, texts, contents, dimensions, parameters)


@mcp.tool()
def list_jobs(limit: int = 20, kind: str | None = None) -> dict:
    """列出最近本地任务，不联网。工具超时未拿到job_id时可按时间/model/summary找回记录；limit=1–100，kind可筛选image/video/tts等。"""
    return products.STORE.list(limit, kind)


@mcp.tool()
def get_job(job_id: str) -> dict:
    """读取本地图片/视频任务记录，不联网。ok仅代表记录读取成功，job_state才表示交付状态。"""
    return products.STORE.get(job_id)


@mcp.tool()
def recover_job(job_id: str, wait: int = 0) -> dict:
    """恢复已有任务：图片只补交付；视频查询原task_id并刷新结果URL。跳过校验完整的本地文件。
    不重新生成；状态未知且没有task_id的任务不可自动恢复。wait=0查一次，最多90秒。临时链接过期可能无法恢复。
    """
    if not 0 <= wait <= 90:
        return {"ok": False, "error": "wait 范围为0–90秒"}
    return products.recover(job_id, wait)


@mcp.tool()
def list_capabilities() -> dict:
    """列出本MCP的方舟能力和官方来源，不联网，不代表当前账号权限；新增功能尚未测试。"""
    return {"ok": True, "account_verified": False, "validation": "not_tested",
            "tools": {"image": ["generate_image"], "video": ["generate_video", "query_video"],
                      "language": ["chat"], "embedding": ["embed"], "jobs": ["list_jobs", "get_job", "recover_job"]},
            "video_models": products.VIDEO_MODELS, "chat_models": products.CHAT_MODELS,
            "image_models": ark.MODELS, "docs": products.DOCS,
            "limits": ["模型权限及参数限制以账号与官方接口为准", "本地视频/音频不会自动上传",
                       "Seedance 2.5首帧/首尾帧ratio仅adaptive；视频编辑duration仅-1",
                       "恢复锁使用POSIX flock，面向macOS/Linux"]}


def main():
    mcp.run()
