"""stdio MCP server：提供 generate_image、chat、list_models 三个工具。

环境变量：DASHSCOPE_API_KEY（必需）、BAILIAN_OUT_DIR（默认 ~/Downloads/ali-bailian）、
BAILIAN_RESOURCE_MODE（local 下载到本地，url 只返回链接；默认 local）、DASHSCOPE_BASE_URL（可选）。
"""

import os
import time
from pathlib import Path

from mcp.server.mcpserver import MCPServer

from . import dashscope

OUT_ROOT = Path(os.environ.get("BAILIAN_OUT_DIR", "~/Downloads/ali-bailian")).expanduser()
MODE = os.environ.get("BAILIAN_RESOURCE_MODE", "local").strip().lower()
if MODE not in ("local", "url"):
    raise SystemExit(f"BAILIAN_RESOURCE_MODE 只能是 local 或 url，当前是 {MODE!r}")

mcp = MCPServer("ali-bailian")


@mcp.tool()
def generate_image(
    prompt: str,
    model: str = "qwen",
    images: list[str] | None = None,
    size: str | None = None,
    n: int | None = None,
    group: int | None = None,
    negative_prompt: str | None = None,
    prompt_extend: bool | None = None,
    seed: int | None = None,
    thinking: bool | None = None,
    watermark: bool = False,
    out_dir: str | None = None,
) -> dict:
    """用阿里云百炼的生图模型生成或编辑图片，结果保存到本地，返回文件路径。

    选模型（别名或完整模型 ID 都行）：
    - "qwen"（默认）→ qwen-image-3.0-pro：千问旗舰，文字渲染最强（中英文海报、标题、招牌），文生图和图片编辑
      二合一。总像素 512*512–2560*2560，默认 2048*2048，n 最多 6。
    - "wan" → wan2.7-image-pro：万相旗舰，0–9 张参考图（多图融合、换装、风格迁移），支持 1K / 2K / 4K 档位、
      group 组图（1–12 张连贯的图）和 thinking。wan2.7-image 是更便宜的标准版（最高 2K）。
    - "z" → z-image-turbo：最快最便宜，写实人像和产品图好，只支持文生图，每次 1 张。
    其他可用 ID：qwen-image-2.0-pro / qwen-image-2.0（文生图 + 编辑，n 最多 6）、qwen-image-max（写实）/
    qwen-image-plus-2026-01-09（艺术风格），这两个只支持文生图和固定尺寸 1664*928、1328*1328、928*1664 等；
    qwen-image-edit-max / qwen-image-edit-plus（专用图片编辑）。完整列表用 list_models("image")。

    参数：
    - prompt：千问和万相都能理解长提示词（万相最多 5000 字）。要画的文字用引号括起来。多图时用「图1」「图2」指明
      各取什么。
    - images：参考图或待编辑的图，本地绝对路径或 URL，单张不超过 10MB。
    - size：写 宽*高（如 1024*1536，也接受 1024x1536）；wan 还可以只写 1K / 2K / 4K 档位（4K 仅文生图），
      宽高比写进 prompt。不写用模型默认值。
    - n：一次生成几张相互独立的图；group：只有 wan 支持，生成 N 张内容连贯的组图（如分镜、系列海报），会覆盖 n。
    - negative_prompt：不想出现的内容。prompt_extend：是否让模型改写扩充提示词，不传用模型默认值（千问默认开），
      要严格按原文出图时设 false。seed：固定随机种子。thinking：wan 的推理增强，默认开。
    - watermark：是否加「AI 生成」水印，默认不加。
    - out_dir：输出目录，默认 BAILIAN_OUT_DIR 下按时间戳新建。交付方式为 url 时忽略。

    按成功生成的张数计费，n 和 group 越大越贵，批量生成前先和用户确认数量。同步调用，单张通常十几秒到一分钟。
    返回 ok、model、files、text（模型改写后的提示词，有的话）、usage、error。交付方式由 BAILIAN_RESOURCE_MODE
    决定：local 时 files 是本地路径，url 时 files 是 24 小时内有效的图片链接，需要长期保存要及时下载。
    """
    opts = dict(prompt=prompt, model=model, images=images or [], size=size, n=n, group=group,
                negative_prompt=negative_prompt, prompt_extend=prompt_extend, seed=seed, thinking=thinking,
                watermark=watermark)
    target = Path(out_dir).expanduser() if out_dir else OUT_ROOT / time.strftime("%Y%m%d-%H%M%S")
    return dashscope.generate_image(opts, target, mode=MODE)


@mcp.tool()
def chat(
    prompt: str,
    model: str = "max",
    system: str | None = None,
    history: list[dict] | None = None,
    images: list[str] | None = None,
    thinking: bool | None = None,
    thinking_budget: int | None = None,
    max_tokens: int | None = None,
    temperature: float | None = None,
    json_mode: bool = False,
    web_search: bool = False,
) -> dict:
    """调用阿里云百炼上的语言模型，返回回答文本。适合要第二意见、换个模型交叉验证、或用特定模型处理任务。

    选模型（别名或完整模型 ID 都行）：
    - "max"（默认）→ qwen3.8-max：千问旗舰，能看图。
    - "plus" → qwen3.7-plus：性价比均衡。
    - "flash" → qwen3.8-flash：最快最便宜，适合简单任务和批量处理。
    百炼也托管第三方模型，直接写 ID：deepseek-v4-pro、kimi-k3、glm-5.3、MiniMax/MiniMax-M3 等。模型更新很快，
    不确定 ID 时先用 list_models 查。

    参数：
    - prompt：本轮用户消息。system：系统提示词。
    - history：之前的多轮对话，OpenAI 格式的列表，如 [{"role": "user", "content": "..."},
      {"role": "assistant", "content": "..."}]，不含本轮 prompt。工具本身不保存会话，多轮要自己带上历史。
    - images：随 prompt 一起发的图片，本地绝对路径或 URL，需要模型支持看图（qwen3.8-max、qwen3.6-plus、
      qwen3-vl-plus 等）。
    - thinking：是否开启深度思考，不传用模型默认值（千问新模型默认开）。简单问题设 false 更快更省。
      thinking_budget：思考的最大 token 数。
    - max_tokens：回答的最大 token 数。temperature：采样温度。
    - json_mode：要求输出合法 JSON，prompt 里要写明 JSON 结构，且最好同时设 thinking=false。
    - web_search：让模型联网搜索后回答（千问系列支持）。

    返回 ok、model、content（回答）、reasoning（思考过程，有的话）、finish_reason（length 表示被 max_tokens 截断）、
    usage、error。
    """
    opts = dict(prompt=prompt, model=model, system=system, history=history, images=images or [],
                thinking=thinking, thinking_budget=thinking_budget, max_tokens=max_tokens,
                temperature=temperature, json_mode=json_mode, web_search=web_search)
    return dashscope.chat(opts)


@mcp.tool()
def list_models(keyword: str | None = None) -> dict:
    """列出当前 API Key 能调用的百炼模型 ID，可按关键字过滤（不区分大小写），如 "image"、"qwen3.8"、"deepseek"。

    列表包含语言、生图、语音、向量等所有模型。返回 ok、models、error。
    """
    return dashscope.list_models(keyword)


def main():
    mcp.run()
