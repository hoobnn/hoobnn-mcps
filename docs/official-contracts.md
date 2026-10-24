# 官方接口、模型与文档更新核实

日期：2026-10-10；MiniMax 于 2026-10-11 补入。范围为本仓库四个 MCP 暴露的工具、实际调用的 HTTP/WebSocket 接口、管理/旧版分支及固定模型/资源 ID。用户任意传入的模型、提供商全部产品和当前账号授权不能一概标为已验证。

## 逐项审计

| MCP | 接口、模型与差异记录 | 机器可读官方来源 |
|---|---|---|
| 火山方舟 | [volcengine-ark.md](audits/volcengine-ark.md) | [sources](audits/volcengine-ark-sources.json) |
| 阿里百炼 | [ali-bailian.md](audits/ali-bailian.md) | [sources](audits/ali-bailian-sources.json) |
| 豆包语音 | [doubao-speech.md](audits/doubao-speech.md) | [sources](audits/doubao-speech-sources.json) |
| MiniMax | [minimax-contracts.md](minimax-contracts.md) | [sources](audits/minimax-sources.json) |

每份报告记录工具到 endpoint、认证、模型/资源、关键字段、限制与完成协议的映射，区分官方确认、差异修正、未接入协议和无法核实项。目录存在不等于账号可调用；HTTP、实时、文件转写等名称相似也不能互换。

本轮修正方舟视频时长/素材限制、图片/尾帧格式、flash 图片别名；百炼目录分页、ASR 路由、Wan3 网页参考及图像/试听限制；豆包音频编码/采样率和同传 protobuf 字段。现有默认模型保持不变。具体证据和限制以上述报告为准。

## 获取官方最新正文

### 阿里云

官方文章地址追加 `.md` 返回 `text/markdown`，已逐页实测，无需登录/API Key：

```bash
curl --fail --location https://help.aliyun.com/zh/model-studio/list-models.md
```

`https://help.aliyun.com/llms.txt`、`https://help.aliyun.com/en/model-studio/llms.txt` 可作发现入口。语言与重定向可能不同，具体契约以 sources 登记页为准。模型目录、发布/下线、价格、限流和上传规则也纳入检查，以发现现有接口之外的新能力。

HTML 回退读取 `window.__ICE_PAGE_PROPS__` 的 `docDetailData.storeData.data.content`，同级有标题/更新时间。只提取正文，避免导航/脚本噪声。合法 Markdown 内嵌 HTML 表格可以保留，不能误判成 HTML 空壳。

### 火山方舟与豆包语音

官网公开文档读取路径实测可用，取 `Result.MDContent`：

```text
GET https://docs.volcengine.com/api/doc/getDocDetail?LibraryCode=ark&DocumentCode=<slug>
GET https://docs.volcengine.com/api/doc/getDocDetail?LibraryCode=DoubaoVoice&DocumentCode=<slug>
```

同响应保留 `Title/DocumentID/DocumentCode/UpdatedTime`。`ContentType=json` 表示另一字段 `Content` 的编辑器富文本，不代表没有 Markdown；不对随机编辑器块 ID 计算契约指纹。

目录由 `getDocList?LibraryCode=ark`、`getDocList?LibraryCode=DoubaoVoice` 获取，用于发现新增/移除页面。旧数字地址可用 `getDocumentCode?LibraryID=...&DocumentID=...` 映射 slug。目录排序和请求元数据不进入正文指纹。

本次火山 `.md/llms.txt/llms-full.txt` 返回 HTTP 200 HTML 壳，不能作为正文成功。上述读取路径是官方前端自用接口，未查到对外稳定性承诺，格式变化应显式修适配器，不能当作正式云产品 OpenAPI。

### MiniMax

中国站接口文档地址追加 `.md` 返回 Mintlify 导出的 Markdown，内含 OpenAPI 3.1 正文：

```bash
curl --fail --location https://platform.minimax.cn/docs/api-reference/video-generation-v2-create.md
```

`fetch_kind=minimax_markdown` 要求开头的 `> ## Documentation Index` 索引前言、一级标题、`openapi: 3.1.0` 与 `paths:` 同时存在，缺一即判失败；指纹只计算一级标题起的正文，不含索引前言。范围以 [minimax-sources.json](audits/minimax-sources.json) 登记的 14 个接口页为准，暂无目录发现。

## 更新检查已落地

[scripts/upstream_docs.py](../scripts/upstream_docs.py) 只用 Python 标准库，无需生成 Key、Cookie、模型请求或后台进程。

```bash
# source 映射覆盖所有远程工具，不联网
python3 scripts/upstream_docs.py --check-coverage
# 抓取正文/目录，对比已核实基线
python3 scripts/upstream_docs.py
```

输出 `.upstream-docs/`（Git 忽略）：当前正文、`result.json`、`report.md` 及 `diffs/` 完整 unified diff。报告列受影响工具、候选模型标识、API 地址、新增文档链接/DocumentCode。候选字符串必须回到官方模型表确认，不能自动当成可调用 ID。

基线在 `docs/upstream/baseline.json`，旧正文以内容寻址 gzip 快照保存在 `docs/upstream/snapshots/<sha256>.md.gz`。它们是官方公开资料的核对凭据，解压后生成真实参数差异，避免只有 hash。正文规范化后计算 SHA-256；请求 ID、页序、响应头或更新时间单独改变不算正文变化。

HTTP/读取失败、空/短正文、HTML 壳、身份或 doc/index 类型错配、快照缺失/损坏/指纹不符均报失败，禁止接受新基线。失败保留旧指纹，不伪装文档删除；只有从 sources 登记中移除的条目记为登记删除。

审查 diff、修实现并通过相称测试后，显式更新本地基线：

```bash
python3 scripts/upstream_docs.py --accept-baseline
```

此操作不代表账号/云端验收。语音协议附件还应按审计报告重新核对官方 schema bundle；正文指纹不能保证同一附件 URL 的二进制内容永远不变。

## GitHub Actions

[upstream-docs.yml](../.github/workflows/upstream-docs.yml) 每天北京时间 **10:23**（UTC 02:23）检查一次，并支持手动选择全部或单个平台。任务、失败、artifact、基线和 PR 按 `volcengine-ark`、`ali-bailian`、`doubao-speech`、`minimax` 分开；一个平台失败不阻断其他平台。

流程：拉取该平台公开官方正文 → 对比默认分支中该平台的基线 → 验证抓取完整性及 SHA-256 → 创建该平台的文档更新 PR。无需 API Key，不自动修改实现或触发 Codex，不批准、合并、打 tag 或发布。

PR 提交的内容：

- `docs/upstream/<server>/baseline.json`：本次捕获的待审基线，只有手动合并后成为后续检测基线。
- `docs/upstream/<server>/review/<fingerprint>/report.md`、`result.json`、`diffs/`：受影响工具、候选模型/接口变化及完整正文差异；不同批次分目录保留，不删除你补充的说明。
- `docs/upstream/snapshots/<sha256>.md.gz`：经过指纹核验的官方正文快照，共享内容寻址目录；不会修改其他平台基线。

用户查看 PR，在同一分支补充实现、测试和说明，处理完契约变化后手动合并。正文变化不代表接口必然变化，也不代表账号已有模型权限。自动提交仅验证文档与快照，不代表实现或云端验收。

每个平台最多保留一个待审 PR，分支为 `docs/upstream-<server>-<fingerprint>`。已有待审 PR 时继续拉取并输出新报告，但**不改写 PR 分支、报告、描述或人工提交**。若本次捕获指纹与 PR 分支指纹不同，会在该 PR 下评论并 @仓库所有者，附报告与回执链接；同一指纹只提醒一次。新变化在 Actions 的平台 artifact 中保留 14 天；合并或关闭后下一次检查再处理。没有变化不创建 PR。

新开 PR 的描述也会 @仓库所有者，即使仓库 Watch 设为 Participating 也能收到通知。

分平台基线优先于旧的 `docs/upstream/baseline.json`；首次分平台运行从旧基线只取对应平台。全量 CLI 检查也会读取分平台基线，不会将其他平台来源误判删除：

```bash
python3 scripts/upstream_docs.py --server minimax --output .upstream-docs/minimax
# 人工完成契约审查后，显式接受对应平台的新基线
python3 scripts/upstream_docs.py --server minimax --accept-baseline
```

前置条件：将工作流合并到默认分支，并在 Settings → Actions → General → Workflow permissions 允许 Actions 创建 PR。GitHub 将创建与批准合并为同一仓库设置；本工作流只创建 PR，没有批准或合并步骤。仓库默认 token 权限仍可保留 read，本工作流显式申请 `contents: write`、`pull-requests: write`。未开启创建权限时会保留平台报告，但创建 PR 会失败。

自动 PR 使用 `GITHUB_TOKEN`，该事件不自动触发后续 PR CI；你的人工提交会触发正常 CI。定时任务可能延迟。[GitHub token 说明](https://docs.github.com/en/actions/tutorials/authenticate-with-github_token)

首次验收：合入工作流并开启创建权限后，手动选择一个平台运行，查看该平台报告和实际 PR。其他平台依次核对；无变化的运行只能验证抓取和跳过路径，不能证明创建 PR 已运行。

## 本轮验证回执

全部 59 个工具已盘点（Ark 10、Bailian 20、Speech 29，含共享帮助工具），所有远程工具通过 source 覆盖检查。实际抓取 **118/118 成功、0 错误**：Ark 16 篇正文 + 目录，Bailian 27 篇正文，Speech 73 篇正文 + 目录。建立已核实基线后，逐份解压并核验 SHA-256，正文到基线 roundtrip 为零差异。

**220 项测试通过**：Ark 29、Bailian 32、Speech 125、跨包及文档链路 34。包括三个实际 stdio 入口、官方契约回归、HTML 壳/合法表格、文档身份、目录顺序、参数正文 diff、缺失/截断快照及抓取失败不误判删除。共享源码同步与 diff 检查通过。

2026-10-11 补入 MiniMax：17 个工具，14 个中国站 OpenAPI 正文来源纳入覆盖检查、基线和 gzip 快照，其他供应商基线未变；登记来源合计 132 个。验证回执见 [minimax-contracts.md](minimax-contracts.md)。

没有执行真实云端生成、识别、训练或管理操作；模型权限、旧文本向量型号、文本向量 dimensions 等未确认项保留在逐项报告中。远端 CI 状态见 [Actions](https://github.com/hoobnn/hoobnn-mcps/actions/workflows/test.yml)。
