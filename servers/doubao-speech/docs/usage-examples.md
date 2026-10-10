# 豆包语音：官方示例与使用技巧

核对日期：2026-10-10。官方体验中心模板与 API 请求示例用于归纳用法；下列提示词和正文为改写，并非官方原文。参数经过 MCP schema 检查，未进行真实云端生成。所有文件、URL、分配音色 ID、任务和会话 ID 占位符需替换。

通过 `get_speech_usage_examples(product="audio", category="timing")` 查询单类；省略 `category` 返回该产品所有示例。其他 `product`：`tts`、`voice`、`podcast`、`asr`、`translation`、`minutes`、`realtime`。查询仅返回本地资料，不触发生成、训练、上传或计费。

## 其他产品的示例补充范围

| 产品 | 官方示例形态 | 本次补充 |
|---|---|---|
| 音频生成1.0 | 四类可载入的提示词模板 | 角色、音效、配乐、参考绑定、时间编排、多语种 |
| 合成2.0 | 指令/方言/引用上文对比示例 | 指令与正文分离、读音修正、上下文、流式与异步长文本 |
| 音色设计 | 说唱者、老人、文人、促销员模板 | 声线描述、代表性试听文本、图文优先级 |
| 声音复刻 | 官方录音及合成最佳实践 | 录音质量、双语覆盖、查询后复用 |
| 播客 | 体验题材及四种API输入示例 | 文章、URL、逐轮脚本、联网话题与续传 |
| 识别 | 热词/上下文和SSD版本请求示例 | 专名提示、最近上下文、会议模型与说话人分离 |
| 翻译/同传 | 机器翻译请求和同传接入示例 | 术语词典、语种选择、字幕/语音与输入规格 |
| 妙记 | 功能开关与请求参数示例 | 摘要、待办/问答、章节与异步查询 |
| 实时语音 | 角色配置与会话事件示例 | 指令、输入判停、接收、打断与关闭 |

在所查看的识别、机器翻译、同传和实时体验页中，没有看到类似音频生成四分类的可载入模板库；这些产品按 API 示例和最佳实践补充。管理 API 与历史接口以 `list_speech_capabilities` 给出的 Action/operation 和官方字段为准，不套用创作提示词模板。端侧 SDK 示例需原生客户端集成。

## 音频生成 1.0 的四类用法

MCP 查询：`{"product": "audio"}`。

来源：[官方来源1](https://console.volcengine.com/speech/new/experience/audio?projectName=default)、[官方来源2](https://docs.volcengine.com/docs/DoubaoVoice/audio-generation-http?lang=zh)。

### 文本生成（`text`）

查看的官方模板：古装喜剧片、悬疑刑侦片、双人播客对谈。

古装喜剧片先定义两位男声，再把衣物摩擦、铃声、喜剧音效和配乐转折嵌入对白。

双人播客对谈保留迟疑、重复、吞咽、重读、短附和和轻笑，营造自然交谈。

- 先写角色声线与场景，再按顺序写台词、情绪、动作和声音事件。
- 固定角色称呼，台词加引号；呼吸、笑声、停顿写在对应台词附近。
- 配乐写清乐器、进入/退出时机及强弱；音效可用拟声词，避免遮盖人声。

### 参考生成（`reference`）

查看的官方模板：带货双人、多角演绎、韩语 ASMR。

带货双人把两段参考分别绑定两位主播，用短附和、插话和包装摩擦声建立互动。

多角演绎以同一段参考为基础提出不同角色的成熟度、音域和情绪要求。

韩语 ASMR结合参考声线、近耳气声、低音量衣物摩擦与细小触麦声。

- reference_audios的顺序对应@音频1、@音频2；每个角色明确绑定哪段参考。
- 写清保留哪些音色特征、改变哪些表演特征；一段参考也能提出不同角色演绎要求。
- 参考生成不注册持久音色；长期复用音色使用clone_voice或design_voice。
- 最多3段参考，每段<=30秒/10MB；图片参考不能与speaker或音频参考混用。

### 时间控制（`timing`）

查看的官方模板：控制音效卡点、控制情绪递进、控制叙事转场、控制旁白推进。

音效卡点在广告台词之间安排水声、气泡与收尾提示音，使用小数秒区间。

情绪递进用带气的句尾、强忍哭意的吸气和空白间隔组织三段表演。

叙事转场明确旁白模仿人物与恢复叙述的切换；旁白推进将翻页、引擎与配乐渐强绑定到句段。

- 使用[2.7s:5.7s]，说明总长并为对白、呼吸和转场留足间隔。
- 音效写清持续到哪里、如何淡出；情绪变化分段说明，角色切换后注明恢复旁白。
- 时间标记随prompt传给text_prompt，没有独立timeline参数或MCP裁切对齐。
- 这是生成引导，需试听核对实际落点；字幕start_time/end_time是毫秒且只覆盖人声。

### 多语种（`multilingual`）

查看的官方模板：英语、日语、韩语。

英语模板用英文定义美式口音、不同年龄的角色和呼吸、脚步、冲击等声音。

日语模板完整描述便利店雨声、门铃、微波炉与杯子声，明确钢琴和弦乐始终低于人声。

- 台词使用目标语言；可同时用目标语言写场景与表演说明，明确口音和角色差异。
- 使用目标语言习惯的拟声词，保持环境声连续，注明人声与配乐音量层级。
- generate_audio没有language参数；可以同时结合参考样音和时间标记。

- 四类可组合；单次最长120秒，prompt最多3000字符。先生成短片段检查角色和节奏，再扩展。

### 有音效的双人对白

工具：`generate_audio`。以下是工具参数：

```json
{
  "prompt": "古代书房，角色甲是清亮好奇的青年男声，角色乙是低沉从容的男声。轻快拨弦配乐低于人声。甲疑惑地说：‘这封信是谁送的？’纸张展开沙沙响。乙轻笑，停顿后说：‘你看看落款。’最后配乐轻轻收尾。"
}
```

### 自然播客对谈

工具：`generate_audio`。以下是工具参数：

```json
{
  "prompt": "两位主持人自然交谈。甲是低沉略沙哑的男声，乙是温暖明亮的女声。甲带一点迟疑说：‘嗯，我其实……是第一次自己录节目。’乙轻笑，短短附和：‘我也是。’甲把‘自己’重读，放松地接着说：‘但自己试试，挺有意思。’无配乐。"
}
```

### 两位主播分别参考样音

工具：`generate_audio`。以下是工具参数：

```json
{
  "prompt": "甲参考@音频1的声线，活泼地说：‘打开看看。’包装袋轻轻摩擦。乙参考@音频2的声线，轻笑着附和：‘颜色真好看。’甲稍停顿后继续介绍，无背景音乐。",
  "reference_audios": [
    "/absolute/path/host_a.wav",
    "/absolute/path/host_b.wav"
  ]
}
```

### 一段参考多种表演

工具：`generate_audio`。以下是工具参数：

```json
{
  "prompt": "三个人物都参考@音频1的声音特征。甲保持自然原声说：‘准备好了吗？’乙用更低沉、成熟克制的表演回答：‘可以开始。’丙用更明亮、轻快的表演说：‘我来试试！’依次发言，角色间留短暂停顿。",
  "reference_audios": [
    "/absolute/path/reference.wav"
  ]
}
```

### 广告音效卡点

工具：`generate_audio`。以下是工具参数：

```json
{
  "prompt": "总长12秒，清亮温柔的女声，轻柔电子乐低于人声。[1s:4s]女声平静地说：‘留一点时间，给自己。’[5s:6s]水滴声，随后轻微气泡咕噜声。[7s:10s]女声温暖地说：‘慢下来，也很好。’最后音乐淡出。",
  "subtitles": true
}
```

### 情绪递进与旁白转场

工具：`generate_audio`。以下是工具参数：

```json
{
  "prompt": "总长16秒，女旁白清晰平静，低音量钢琴持续。[1s:5s]旁白说：‘她终于走到门口。’短暂停顿，转为紧张人物语气。[6s:9s]轻声说：‘你还在吗？’听到开门声后呼吸放松，恢复旁白。[11s:15s]温暖地说：‘这一次，她听到了回应。’音乐淡出。"
}
```

### 日语场景对白

工具：`generate_audio`。以下是工具参数：

```json
{
  "prompt": "雨の夜の小さな店。若い女性は明るく自然な標準日本語、店主は低く穏やかな声。雨音は続き、ピアノは声より小さく。ドアのベルが鳴る。女性：『こんばんは。まだ開いていますか？』店主は少し間を置き、優しく：『はい、どうぞ。』カップを置く小さな音。最後に雨音が遠ざかる。"
}
```

## 合成2.0：语音指令、方言、读音修正与引用上文

MCP 查询：`{"product": "tts"}`。

来源：[官方来源1](https://docs.volcengine.com/docs/DoubaoVoice/DoubaoTextToSpeech20CapabilityIntroduction?lang=zh)、[官方来源2](https://docs.volcengine.com/docs/DoubaoVoice/unidirectional-streaming-text-to-speech-http?lang=zh)。

官方展示用法：吵架、暧昧悄悄话、四川话、北京话、承接问询语境、承接老友相见语境。

- text只放需要朗读的正文；instructions放情绪、语气和速度，先明确主情绪，再补局部变化。
- 支持能力取决于音色；方言用dialect，读音纠正用pronunciations。
- 引用上文让模型理解上一轮问答但不朗读：parameters.req_params.additions.context_texts，additions可直接写对象。
- instructions也映射context_texts；多个上下文、SSML或其他高级选项都放parameters。
- 超过5000字自动走异步长文本（long_text可强制），返回job_id后用get_job查询并下载。

### 安静近耳表演

工具：`text_to_speech`。以下是工具参数：

```json
{
  "text": "今天辛苦了，先好好休息。",
  "instructions": "像安静的深夜聊天，轻柔、亲切、略慢，避免夸张。"
}
```

### 方言与读音

工具：`text_to_speech`。以下是工具参数：

```json
{
  "text": "我们明天去重庆看看。",
  "dialect": "sichuan",
  "pronunciations": [
    "重庆/(chong2)(qing4)"
  ]
}
```

### 引用上一轮提问

工具：`text_to_speech`。以下是工具参数：

```json
{
  "text": "别急，我们一起看看哪里出了问题。",
  "parameters": {
    "req_params": {
      "additions": {
        "context_texts": [
          "用户刚才着急地问：我怎么总是做不好？"
        ]
      }
    }
  }
}
```

### 双向流式输入文本

工具：`speech_raw_request`。以下是工具参数：

```json
{
  "product": "tts_websocket",
  "mode": "bidirectional",
  "request": {
    "req_params": {
      "speaker": "zh_female_vv_uranus_bigtts",
      "audio_params": {
        "format": "mp3",
        "sample_rate": 24000
      }
    }
  },
  "text_chunks": [
    "先听一个小故事。",
    "窗外的雨，慢慢停了。"
  ]
}
```

### 整本长文本异步合成

工具：`text_to_speech`。以下是工具参数：

```json
{
  "text": "这里替换为需要合成的长文本。",
  "long_text": true
}
```

### 查询长文本结果

工具：`get_job`。以下是工具参数：

```json
{
  "job_id": "REPLACE_WITH_TEXT_TO_SPEECH_JOB_ID",
  "wait": 30
}
```

## 音色设计与复刻：声线描述、试听与录音准备

MCP 查询：`{"product": "voice"}`。

来源：[官方来源1](https://docs.volcengine.com/docs/DoubaoVoice/SoundDesignAPI?lang=zh)、[官方来源2](https://docs.volcengine.com/docs/DoubaoVoice/SoundReplication20BestPractices?lang=zh)、[官方来源3](https://docs.volcengine.com/docs/DoubaoVoice/tone-training-http?lang=zh)。

官方展示用法：街头说唱者、儒雅老人、古代文人、超市促销员。

- 设计描述按性别/年龄感、音色质感、语言、角色、语速/语调/情绪展开；优先写最重要的辨识特征。
- preview_text是试听正文，description是声音描述；用与最终场景一致的文本试听，促销场景可包含价格数字。
- 设计描述<=200字符，试听<=300字符；图片<=10MB。图文同时提交时图片优先。
- 设计和复刻需已分配的speaker_id，消耗训练次数；查询状态成功/激活后再用该音色合成，试听URL只有1小时。
- 复刻最佳实践推荐14–30秒WAV、单声道、单人、低噪声和一致的表演；避免重叠人声、混响，过度降噪可能损失相似度。
- 中英混读目标应在样音覆盖中英；稳定助理选平稳样音，表达型复刻还需结合正文语义与语音指令试听。

### 亲切长者音色

工具：`design_voice`。以下是工具参数：

```json
{
  "speaker_id": "S_REPLACE_WITH_ALLOCATED_ID",
  "preview_text": "早上给花浇一点水，慢慢来，它会长得很好。",
  "description": "六十岁左右的男性，温暖略沙哑，普通话清晰，语速适中，语调平稳，像耐心讲故事的长者。"
}
```

### 图片设计音色

工具：`design_voice`。以下是工具参数：

```json
{
  "speaker_id": "S_REPLACE_WITH_ALLOCATED_ID",
  "preview_text": "你好，很高兴认识你。",
  "image": "/absolute/path/character.png"
}
```

### 准备好的单人录音复刻

工具：`clone_voice`。以下是工具参数：

```json
{
  "speaker_id": "S_REPLACE_WITH_ALLOCATED_ID",
  "audio_file": "/absolute/path/clean_mono.wav",
  "language": "zh",
  "text": "这里替换为训练录音对应的实际文字。"
}
```

### 查询训练状态

工具：`get_voice`。以下是工具参数：

```json
{
  "speaker_id": "S_REPLACE_WITH_ALLOCATED_ID"
}
```

## 播客：文章、链接、逐轮脚本与联网话题

MCP 查询：`{"product": "podcast"}`。

来源：[官方来源1](https://docs.volcengine.com/docs/DoubaoVoice/PodcastAPI-websocket-v3protocol?lang=zh)、[官方来源2](https://console.volcengine.com/speech/new/experience/podcast?projectName=default)。

- text/url改写文章或链接；dialogue直接演绎逐轮脚本；topic根据话题联网生成。topic只是话题，不具备格式指令能力。
- url支持网页及PDF/doc/txt链接，不把控制台上传格式直接视为API格式。
- script_only=true先生成脚本；dialogue每轮<=300字、总量<=10000字。
- speakers必须是两个音色，建议同系列配对，按给出的顺序发言。
- 文章推荐<=12000字（parameters.input_text_max_length可调），超过会截断；音频URL有效1小时。
- 收到partial后保留task_id和last_finished_round_id，通过retry_info显式续传，不能把局部音频当完整成品。

### 文章先生成脚本

工具：`generate_podcast`。以下是工具参数：

```json
{
  "text": "这里替换为完整文章。",
  "script_only": true
}
```

### 链接转播客

工具：`generate_podcast`。以下是工具参数：

```json
{
  "url": "https://example.com/article"
}
```

### 指定逐轮脚本

工具：`generate_podcast`。以下是工具参数：

```json
{
  "speakers": [
    "zh_male_dayixiansheng_v2_saturn_bigtts",
    "zh_female_mizaitongxue_v2_saturn_bigtts"
  ],
  "dialogue": [
    {
      "speaker": "zh_male_dayixiansheng_v2_saturn_bigtts",
      "text": "今天我们聊聊怎样开始记录生活。"
    },
    {
      "speaker": "zh_female_mizaitongxue_v2_saturn_bigtts",
      "text": "先从每天一个小片段开始吧。"
    }
  ]
}
```

### 联网话题

工具：`generate_podcast`。以下是工具参数：

```json
{
  "topic": "城市步行与日常健康"
}
```

## 识别：热词、上下文与说话人分离

MCP 查询：`{"product": "asr"}`。

来源：[官方来源1](https://docs.volcengine.com/docs/DoubaoVoice/hot-words-and-context?lang=zh)、[官方来源2](https://docs.volcengine.com/docs/DoubaoVoice/speaker-separation?lang=zh)。

- 热词只放难识别的专名，不堆通用词；热词是概率引导，替换词表是后处理强制替换。
- 热词效果差时补生僻字解释或领域背景；上下文优先最近几轮，按新到旧排列。
- 流式高级corpus.context必须序列化为JSON字符串，可同时含hotwords、context_type=dialog_ctx、context_data；不要传裸对象。
- 容量因链路而异：双向流式热词100 tokens，非流式/二遍5000词；非流式/二遍上下文800 tokens/20轮，不能套用便捷极速版参数限制。
- speakers=true自动用标准版并开启说话人分离（ssd_version=200）；长会议用parameters.request.ssd_version=300，长非会议用200加ssd_mode=1。
- 这些SSD选项用于对应标准/流式链路，不把便捷极速版utterances开关当成会议模型选择。说话人编号不等于已知身份；声纹匹配需先注册声纹。
- 重叠人声、相近音色和不足1秒的短插话会影响分离；流式定稿优先采用最终/二遍结果。

### 领域音频快速转写

工具：`speech_to_text`。以下是工具参数：

```json
{
  "audio": "/absolute/path/talk.wav",
  "hotwords": [
    "火山引擎",
    "Kubernetes"
  ],
  "context": "这是一段云计算技术分享，讨论容器部署。",
  "utterances": true
}
```

### 长会议说话人分离

工具：`speech_to_text`。以下是工具参数：

```json
{
  "audio": "https://example.com/meeting.wav",
  "speakers": true,
  "parameters": {
    "request": {
      "ssd_version": "300"
    }
  }
}
```

### 流式热词加最近上下文

工具：`speech_raw_request`。以下是工具参数：

```json
{
  "product": "asr_stream",
  "audio": "/absolute/path/mono16k.wav",
  "mode": "realtime",
  "request": {
    "request": {
      "enable_nonstream": true,
      "corpus": {
        "context": "{\"hotwords\":[{\"word\":\"火山引擎\"}],\"context_type\":\"dialog_ctx\",\"context_data\":[{\"text\":\"刚才讨论的是火山引擎的容器服务。\"}]}"
      }
    }
  }
}
```

## 翻译与同传：术语一致性、字幕和语音输出

MCP 查询：`{"product": "translation"}`。

来源：[官方来源1](https://docs.volcengine.com/docs/DoubaoVoice/MachineTranslationLargeModel-APIAccessDocumentation?lang=zh)、[官方来源2](https://docs.volcengine.com/docs/DoubaoVoice/SimultaneousInterpretation20APIAccessDocumentation?lang=zh)。

- 固定品牌和专业术语用glossary；直传术语优先于术语表。不要把ASR热词当作翻译词典。
- 机器翻译不指定source_language可自动检测；1–16条文本，按原顺序处理，每条<=1024 tokens。
- 同传文件需16kHz/16bit/单声道；s2t只要字幕，s2s还返回目标语音。
- 录音保持安静、避免多人同时发言；本工具处理文件，麦克风实时采集由客户端负责。

### 指定术语译法

工具：`translate_text`。以下是工具参数：

```json
{
  "texts": [
    "火山引擎提供语音服务。"
  ],
  "target_language": "en",
  "source_language": "zh",
  "glossary": {
    "火山引擎": "Volcengine"
  }
}
```

### 同传字幕

工具：`interpret_audio`。以下是工具参数：

```json
{
  "audio": "/absolute/path/mono16k.wav",
  "source_language": "zh",
  "target_language": "en",
  "mode": "s2t"
}
```

### 同传目标语音

工具：`interpret_audio`。以下是工具参数：

```json
{
  "audio": "/absolute/path/mono16k.wav",
  "source_language": "zh",
  "target_language": "en",
  "mode": "s2s"
}
```

## 妙记：按需启用摘要与章节

MCP 查询：`{"product": "minutes"}`。

来源：[官方来源1](https://docs.volcengine.com/docs/DoubaoVoice/DoubaoVoiceMinutes-APIAccessDocumentation?lang=zh)。

- bundle_billing（AllActivate）只选择计费方式，不会开启功能；summary、chapters、todos、qa、translate_to按需打开。
- 只需原始转写用speech_to_text；妙记至少启用一项附加功能。
- speaker_count已知时填写，未知保持0自动识别。
- 提交后用get_job查询，完成时自动下载结果JSON；等待中不要重复提交。

### 会议转写与摘要

工具：`summarize_meeting`。以下是工具参数：

```json
{
  "file_url": "https://example.com/meeting.wav"
}
```

### 转写并提取待办和问答

工具：`summarize_meeting`。以下是工具参数：

```json
{
  "file_url": "https://example.com/meeting.wav",
  "summary": false,
  "todos": true,
  "qa": true,
  "chapters": true
}
```

### 查询妙记结果

工具：`get_job`。以下是工具参数：

```json
{
  "job_id": "REPLACE_WITH_SUMMARIZE_MEETING_JOB_ID",
  "wait": 30
}
```

## 实时语音：角色指令、输入判停、打断与工具回传

MCP 查询：`{"product": "realtime"}`。

来源：[官方来源1](https://docs.volcengine.com/docs/DoubaoVoice/endtoend-realtime-voice-full-duplex-version?lang=zh)。

- 实时会话工具默认不启用，需在MCP配置设MCP_TOOL_GROUPS包含realtime并重启。
- session.instructions定义角色、语气和回答范围；不要照搬音频生成的时间区间标记。
- 按open→append音频→commit→receive→close处理；输入文件是16kHz单声道int16裸PCM，append后需显式commit。
- response.cancel用于打断；工具调用应执行后按call_id回传结果，不能只收到调用就视为已完成。
- session_id是当前MCP进程的句柄，重启后失效；退出或完成后关闭连接。

### 简短语言陪练

工具：`open_realtime_session`。以下是工具参数：

```json
{
  "session": {
    "instructions": "你是耐心的英语口语陪练，每次只问一个简短问题，纠错时用简单中文解释。",
    "audio": {
      "output": {
        "voice": "zh_female_vv_jupiter_bigtts"
      }
    }
  }
}
```

### 追加客户端采集音频

工具：`send_realtime_event`。以下是工具参数：

```json
{
  "session_id": "REPLACE_WITH_OPEN_RESULT",
  "event": {
    "type": "input_audio_buffer.append"
  },
  "audio_file": "/absolute/path/mono16k.pcm"
}
```

### 文件结束强制判停

工具：`send_realtime_event`。以下是工具参数：

```json
{
  "session_id": "REPLACE_WITH_OPEN_RESULT",
  "event": {
    "type": "input_audio_buffer.commit"
  }
}
```

### 接收回复

工具：`receive_realtime_events`。以下是工具参数：

```json
{
  "session_id": "REPLACE_WITH_OPEN_RESULT",
  "timeout": 10
}
```

### 打断回复

工具：`send_realtime_event`。以下是工具参数：

```json
{
  "session_id": "REPLACE_WITH_OPEN_RESULT",
  "event": {
    "type": "response.cancel"
  }
}
```

### 结束会话

工具：`close_realtime_session`。以下是工具参数：

```json
{
  "session_id": "REPLACE_WITH_OPEN_RESULT"
}
```
