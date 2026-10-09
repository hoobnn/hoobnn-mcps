# 官方接口、模型与文档更新核实

日期：2026-10-10。范围为本仓库三个 MCP 暴露的工具、实际调用的 HTTP/WebSocket 接口、管理/旧版分支及固定模型/资源 ID。用户任意传入的模型、提供商全部产品和当前账号授权不能一概标为已验证。

## 逐项审计

| MCP | 接口、模型与差异记录 | 机器可读官方来源 |
|---|---|---|
| 火山方舟 | [volcengine-ark.md](audits/volcengine-ark.md) | [sources](audits/volcengine-ark-sources.json) |
| 阿里百炼 | [ali-bailian.md](audits/ali-bailian.md) | [sources](audits/ali-bailian-sources.json) |
| 豆包语音 | [doubao-speech.md](audits/doubao-speech.md) | [sources](audits/doubao-speech-sources.json) |

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

[upstream-docs.yml](../.github/workflows/upstream-docs.yml) 提供 `workflow_dispatch` 手动触发，权限 `contents: read`。输出 Job Summary 和保留 14 天的 artifact，失败也尽量留报告；不自动接受基线、改默认模型、提交、发 Issue/PR 或部署。

工作流已推送到默认分支，可在 GitHub 手动触发文档检查，目前没有启用 schedule。后续确定频率时可添加每天一次、避开整点的 schedule。GitHub 定时任务在默认分支运行，繁忙时可能延迟，不能保证实时提醒。[GitHub 触发规则](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)

处理顺序：正文/目录 diff → 判断新增、兼容变化、下线或文案调整 → 定位工具/模型 → 更新契约和必要实现 → 合同回归 → 确有需要的云端小样本 → 审查基线与发布。自动抓取和差异定位可运行，自动修改/提交/合并未启用。

## 本轮验证回执

全部 59 个工具已盘点（Ark 10、Bailian 20、Speech 29，含共享帮助工具），所有远程工具通过 source 覆盖检查。实际抓取 **118/118 成功、0 错误**：Ark 16 篇正文 + 目录，Bailian 27 篇正文，Speech 73 篇正文 + 目录。建立已核实基线后，逐份解压并核验 SHA-256，正文到基线 roundtrip 为零差异。

**220 项测试通过**：Ark 29、Bailian 32、Speech 125、跨包及文档链路 34。包括三个实际 stdio 入口、官方契约回归、HTML 壳/合法表格、文档身份、目录顺序、参数正文 diff、缺失/截断快照及抓取失败不误判删除。共享源码同步与 diff 检查通过。

没有执行真实云端生成、识别、训练或管理操作；模型权限、旧文本向量型号、文本向量 dimensions 等未确认项保留在逐项报告中。远端 CI 状态见 [Actions](https://github.com/hoobnn/hoobnn-mcps/actions/workflows/test.yml)。
