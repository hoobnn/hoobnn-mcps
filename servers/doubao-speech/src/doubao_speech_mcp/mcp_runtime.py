"""MCP boundary: bounded workers, deadlines, cancellation and honest results."""
import asyncio
import concurrent.futures
import contextvars
import functools
import inspect
import json
import logging
import os
import time
from typing import Annotated, Any

import anyio
from mcp.server.mcpserver import MCPServer
from mcp.types import CallToolResult, TextContent, ToolAnnotations
from pydantic import Field

from . import transport

logger = logging.getLogger(__name__)
COMPACT_TOOLS = {"chat", "embed", "rerank", "get_job", "recover_job"}
LOCAL_TOOLS = {"list_jobs", "list_capabilities", "list_speech_capabilities", "get_speech_usage_examples", "get_tool_help"}


def merge_parameters(body, parameters, label="parameters"):
    """Deep-merge documented provider fields over a typed request; caller values win."""
    if parameters is None:
        return body
    if not isinstance(parameters, dict):
        raise ValueError(f"{label} 必须是 JSON object")
    for key, value in parameters.items():
        if isinstance(value, dict) and isinstance(body.get(key), dict):
            merge_parameters(body[key], value, label)
        else:
            body[key] = value
    return body


def deadline_payload():
    return {"ok": False, "error_code": "deadline_exceeded", "retryable": False,
            "error": "调用超过总超时预算；已提交任务请查询或恢复，不要直接重新生成"}

SHORT_DESCRIPTIONS = {
    ("volcengine-ark", "generate_image"): "Seedream 生成或编辑图片；图层拆分、透明背景、组图选这里，海报文字渲染可改用 ali-bailian 的 qwen。model=pro（默认）或flash支持layers/transparent，最多10张参考图；fast仅pro支持；lite支持group/web_search/3K/4K，最多14张参考图，参考数+group<=15。images为本地路径或URL；layers/transparent只能传1张。size默认2K，宽高比写入prompt。按成功张数计费，组图/图层会生成多张。返回job_id、job_state、files、artifacts、usage；recover_job只补交付。未列出的官方字段放parameters。完整尺寸、图层与提示词用法见get_tool_help。",
    ("ali-bailian", "generate_image"): "百炼生成或编辑图片；中英文字渲染选 qwen，多图融合选 wan，图层拆分/透明背景用 volcengine-ark。model=qwen（默认）、wan或z，也可传完整ID。qwen默认3.0支持文字和编辑，最多3张参考图、n<=6；wan最多9张参考图，非组图n<=4、group<=12；4K仅pro无参考非组图支持；z仅文生图，单张。images为本地路径或URL，size为档位或宽*高，默认不加watermark。返回job_id、job_state、files、artifacts、usage，交付失败可recover_job补下载。多张按生成数量计费。未列出的官方字段放parameters。完整参数与限制见get_tool_help。",
    ("ali-bailian", "chat"): "调用百炼语言或视觉模型（千问及 DeepSeek、Kimi、GLM 等第三方）；豆包 Seed 模型用 volcengine-ark 的 chat。model=max（默认）、plus、flash或完整ID；不确定ID用list_models。history为OpenAI消息列表，不含本轮prompt；images支持本地路径或URL，模型须支持视觉。thinking/thinking_budget控制思考，max_tokens限制回答，json_mode需提示词明确JSON，web_search联网计费。返回content、reasoning、usage、finish_reason；断流保留partial文本并标记失败。未列出的官方字段放parameters。完整用法见get_tool_help。",
    ("ali-bailian", "generate_video"): "万相3.0生成视频，本地参考视频/音频会自动上传（volcengine-ark 的 Seedance 需公网 URL）；model=wan（默认）或wan-fast。支持文生、首帧、首尾帧、图片/视频/音频参考及file文档或link网页；file/link二选一且需prompt_extend，参考素材与首尾帧互斥。素材可用本地路径或URL，本地文件自动上传临时存储。resolution=1080P/720P/480P；ratio默认adaptive；duration=2–30或-1；audio默认true。wait默认0只提交，最多90秒轮询。返回task_id/job_id，之后用get_job查进度并自动下载。按输出秒数计费。参考数量与完整模型参数见get_tool_help。",
    ("doubao-speech", "text_to_speech"): "豆包语音合成（中文音色、方言、字幕、长文本首选；千问音色用 ali-bailian），text为文本，voice为官方音色ID或S_复刻ID；instructions控制语气，dialect/language控制方言/语言，pronunciations指定读音。format=mp3或wav；多段字幕必须wav，sample_rate为采样率。支持subtitles输出SRT，按段合成，失败保留已完成段。超过5000字自动改走异步长文本（long_text可强制），返回job_id后用get_job取结果。SSML、水印等未列出的官方字段放parameters。按字数计费。完整音色与调节范围见get_tool_help。",
    ("doubao-speech", "generate_audio"): "Seed Audio生成对白、唱歌、音效或配乐；只朗读文字用 text_to_speech。prompt<=3000字，可用speaker或最多3段reference_audios；reference_image不能同时配音频参考或speaker。参考素材支持本地路径/URL。format=mp3/wav/ogg_opus/pcm；ogg_opus仅48000Hz，其他采样率见完整说明。subtitles开启字幕，model选择已开通模型。返回files、duration、subtitle，按服务规则计费。未列出的官方字段放parameters。对白与时间戳提示词示例见get_speech_usage_examples；完整参数见get_tool_help。",
}


class ReliableMCPServer(MCPServer):
    def __init__(self, name, *, lifespan=None, groups=None, optional_groups=()):
        # SDK INFO logging otherwise includes HTTPX URLs, including signed
        # download/upload credentials. Keep only our body-free timing logs.
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)
        self.full_descriptions = {}
        self.groups = groups or {}
        self.timeout = transport.positive_setting("MCP_TOOL_TIMEOUT_SEC", 300, 3600)
        self.workers = transport.integer_setting("MCP_WORKERS", 8, 64)
        self.executor = None
        self.local_executor = None
        self.async_limiter = None
        self.optional_groups = set(optional_groups)
        self.selected = {group.strip() for group in os.environ.get("MCP_TOOL_GROUPS", "").split(",") if group.strip()}
        unknown = (self.selected | self.optional_groups) - set(self.groups)
        if unknown:
            raise ValueError(f"Unknown MCP_TOOL_GROUPS: {sorted(unknown)}")
        # Optional groups (admin, long-lived sessions) stay hidden unless named.
        self.active = self.selected or set(self.groups) - self.optional_groups

        from contextlib import asynccontextmanager
        @asynccontextmanager
        async def managed_lifespan(server):
            self.async_limiter = anyio.CapacityLimiter(self.workers)
            try:
                async with transport.runtime.lifespan():
                    if lifespan is None:
                        yield {}
                    else:
                        async with lifespan(server) as context:
                            yield context
            finally:
                for executor in (self.executor, self.local_executor):
                    if executor is not None:
                        executor.shutdown(wait=False, cancel_futures=True)
                self.executor = self.local_executor = None
        super().__init__(name, lifespan=managed_lifespan)

        @self.tool()
        def get_tool_help(tool: str) -> dict:
            """按工具名读取完整用法、模型限制与示例，不联网、不计费。"""
            if tool not in self.full_descriptions:
                return {"ok": False, "error": "未知工具", "available_tools": sorted(self.full_descriptions)}
            return {"ok": True, "tool": tool, "description": self.full_descriptions[tool]}

    def tool(self, *args, **kwargs):
        register = super().tool
        def decorate(fn):
            name = kwargs.get("name") or fn.__name__
            self.full_descriptions[name] = inspect.getdoc(fn) or ""
            grouped = any(name in tools for tools in self.groups.values())
            if name != "get_tool_help" and (self.selected or grouped) and not any(
                    name in self.groups[group] for group in self.active):
                return fn
            options = dict(kwargs)
            summary = SHORT_DESCRIPTIONS.get((self.name, name))
            if summary:
                options.setdefault("description", summary)
            # Local reads are the only safe defaults; paid calls and generic admin
            # actions must not inherit misleading read-only/idempotent hints.
            local = name in LOCAL_TOOLS
            readonly = local or name in {"list_models", "list_voices", "get_voice"}
            # get_job may poll the provider and download results, but never submits work.
            options.setdefault("annotations", ToolAnnotations(read_only_hint=readonly,
                destructive_hint=name in {"manage_word_table", "speech_console", "upgrade_voice", "close_realtime_session"},
                idempotent_hint=readonly or name == "get_job", open_world_hint=not local))
            signature = inspect.signature(fn)
            parameters = []
            for parameter in signature.parameters.values():
                bounds = {"wait": (0, 90), "limit": (1, 100), "page_size": (1, 100),
                          "page_index": (0, None), "max_pages": (1, 100), "max_events": (1, 500)}.get(parameter.name)
                if parameter.name == "timeout":
                    maximum = 60 if name in {"receive_realtime_events", "close_realtime_session"} else 120
                    parameter = parameter.replace(annotation=Annotated[parameter.annotation, Field(gt=0, le=maximum)])
                elif bounds:
                    parameter = parameter.replace(annotation=Annotated[parameter.annotation, Field(ge=bounds[0], le=bounds[1])])
                parameters.append(parameter)
            if name in COMPACT_TOOLS:
                parameters.append(inspect.Parameter("include_response", inspect.Parameter.KEYWORD_ONLY, default=False,
                    annotation=Annotated[bool, Field(description="返回原始响应，默认false")]))
            signature = signature.replace(parameters=parameters, return_annotation=dict[str, Any])
            @functools.wraps(fn)
            async def invoke(**arguments):
                include = arguments.pop("include_response", False)
                if inspect.iscoroutinefunction(fn):
                    if self.async_limiter is None:
                        self.async_limiter = anyio.CapacityLimiter(self.workers)
                    async with self.async_limiter:
                        result = await fn(**arguments)
                else:
                    attribute = "local_executor" if local else "executor"
                    executor = getattr(self, attribute)
                    if executor is None:
                        executor = concurrent.futures.ThreadPoolExecutor(max_workers=2 if local else self.workers,
                                                                       thread_name_prefix="mcp-local" if local else "mcp-tool")
                        setattr(self, attribute, executor)
                    future = executor.submit(contextvars.copy_context().run, functools.partial(fn, **arguments))
                    # Cancellation cancels queued work. Running workers keep their
                    # physical slot until they actually exit, even after timeout.
                    try:
                        result = await asyncio.wrap_future(future)
                    except TimeoutError:
                        current = transport.operation.get()
                        if current is None or time.monotonic() < current.deadline:
                            raise
                        # A cooperative worker can reach its deadline before
                        # fail_after fires. Normalize before the SDK wraps it.
                        current.cancelled.set()
                        result = deadline_payload()
                if isinstance(result, dict):
                    result = dict(result)
                    result.setdefault("ok", True)
                    if name in {"list_capabilities", "list_speech_capabilities"}:
                        result["enabled_tools"] = [tool.name for tool in await self.list_tools()]
                        result["selected_groups"] = sorted(self.selected)
                        result["tool_groups"] = {group: sorted(tools) for group, tools in sorted(self.groups.items())}
                        disabled = sorted(set(self.groups) - self.active)
                        result["disabled_groups"] = disabled
                        if disabled:
                            result["enable_hint"] = ("这些工具组当前未启用，模型看不到也不能调用。需要时在 MCP 配置的环境变量设 "
                                                     f"MCP_TOOL_GROUPS={','.join(sorted(self.active | set(disabled)))}"
                                                     "（按需保留），然后重启 MCP。")
                    if not include and name in COMPACT_TOOLS:
                        result.pop("response", None)
                    state = result.get("job_state")
                    if state in ("running", "queued") and not result.get("error"):
                        result.update(ok=True, completed=False)
                    elif state is not None:
                        result["completed"] = state == "delivered"
                return result
            invoke.__signature__ = signature
            invoke.__annotations__ = {**fn.__annotations__, "return": dict[str, Any], "include_response": bool}
            register(*args, **options)(invoke)
            return fn
        return decorate

    async def list_tools(self):
        tools = sorted(await super().list_tools(), key=lambda tool: tool.name)
        for tool in tools:
            tool.output_schema = {"type": "object", "required": ["ok"],
                                  "properties": {"ok": {"type": "boolean"}}, "additionalProperties": True}
        return tools

    async def call_tool(self, name, arguments, context=None):
        started = time.monotonic()
        current = transport.Operation(started + self.timeout)
        token = transport.operation.set(current)
        outcome = "error"
        progress = None
        if context is not None:
            async def heartbeat():
                try:
                    await context.report_progress(0, message=f"开始执行 {name}")
                    tick = 0
                    while True:
                        await asyncio.sleep(5)
                        tick += 1
                        await context.report_progress(tick, message=f"{name} 已执行 {int(time.monotonic() - started)} 秒")
                except Exception:
                    # Progress is optional and must not fail the operation.
                    return
            progress = asyncio.create_task(heartbeat())
        try:
            with anyio.fail_after(self.timeout):
                result = await super().call_tool(name, arguments, context)
            if isinstance(result, CallToolResult):
                payload = result.structured_content
                if isinstance(payload, dict):
                    result.is_error = payload.get("ok") is False
                    if result.is_error:
                        payload.setdefault("retryable", False)
                        payload.setdefault("error_code", "tool_failed")
                    result.content = [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False, separators=(",", ":")))]
                outcome = "error" if result.is_error else "ok"
            return result
        except TimeoutError:
            current.cancelled.set()
            outcome = "timeout"
            payload = deadline_payload()
            return CallToolResult(content=[TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))],
                                  structured_content=payload, is_error=True)
        except asyncio.CancelledError:
            outcome = "cancelled"
            current.cancelled.set()
            raise
        finally:
            current.cancelled.set()
            if progress is not None:
                progress.cancel()
                await asyncio.gather(progress, return_exceptions=True)
            transport.operation.reset(token)
            # No prompts, keys, request bodies or signed URLs in logs.
            logger.info("tool=%s outcome=%s duration_ms=%d", name, outcome, (time.monotonic() - started) * 1000)
