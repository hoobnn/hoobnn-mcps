"""stdio MCP server：提供 generate_image 一个工具。

环境变量：ARK_API_KEY（必需）、SEEDREAM_OUT_DIR（默认 ~/Downloads/seedream）、ARK_BASE_URL（可选）。
"""

import os
import time
from pathlib import Path

from mcp.server.mcpserver import MCPServer

from . import ark

OUT_ROOT = Path(os.environ.get("SEEDREAM_OUT_DIR", "~/Downloads/seedream")).expanduser()

mcp = MCPServer("seedream")


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
    - out_dir：输出目录，默认 SEEDREAM_OUT_DIR 下按时间戳新建。

    场景写法：
    - 图层拆分：prompt 可留空自动拆主要元素；要指定拆哪些，用 0–1000 的归一化坐标框选，如
      「标题的坐标为<bbox>180 64 812 198</bbox>，鹦鹉的坐标为<bbox>347 305 642 997</bbox>」。最多 16 个图层，
      任一图层失败整次报错。返回底图 layer-00 和各图层 png，layers 字段与 layers.json 记录 z_index、名称和
      bounding_box；用 bounding_box.absolute 按 z_index 从小到大贴回底图即可还原。
    - 交互编辑：先在原图上画框、箭头或草图标出位置，再把这张图传入，prompt 写「在左下角标记区域添加…，
      移除所有标记线条，保持构图不变」。

    按成功生成的张数计费：组图和图层拆分会一次产出多张（图层拆分底图和每层各算一张，一张照片自动拆分实测
    产出 11 张），调用前先和用户确认数量。同步调用，单图约半分钟，组图或图层拆分要一两分钟。
    返回 ok、files、layers、usage、errors（组图里单张失败）、error。
    """
    opts = dict(prompt=prompt or None, model=model, images=images or [], size=size,
                output_format=output_format, transparent=transparent, layers=layers, group=group,
                web_search=web_search, fast=fast, watermark=watermark)
    target = Path(out_dir).expanduser() if out_dir else OUT_ROOT / time.strftime("%Y%m%d-%H%M%S")
    return ark.generate(opts, target)


def main():
    mcp.run()
