"""Offline examples rewritten from official console templates and API documentation."""
from copy import deepcopy

DOC = "https://docs.volcengine.com/docs/DoubaoVoice/"
CONSOLE = "https://console.volcengine.com/speech/new/experience/"


def example(name, tool, arguments, category=None):
    result = {"name": name, "tool": tool, "arguments": arguments}
    if category:
        result["category"] = category
    return result


GUIDES = {
    "audio": {
        "title": "音频生成 1.0 的四类用法",
        "sources": [CONSOLE + "audio?projectName=default", DOC + "audio-generation-http?lang=zh"],
        "categories": {
            "text": {
                "name": "文本生成",
                "official_templates": ["古装喜剧片", "悬疑刑侦片", "双人播客对谈"],
                "observations": ["古装喜剧片先定义两位男声，再把衣物摩擦、铃声、喜剧音效和配乐转折嵌入对白。", "双人播客对谈保留迟疑、重复、吞咽、重读、短附和和轻笑，营造自然交谈。"],
                "tips": ["先写角色声线与场景，再按顺序写台词、情绪、动作和声音事件。", "固定角色称呼，台词加引号；呼吸、笑声、停顿写在对应台词附近。", "配乐写清乐器、进入/退出时机及强弱；音效可用拟声词，避免遮盖人声。"],
            },
            "reference": {
                "name": "参考生成",
                "official_templates": ["带货双人", "多角演绎", "韩语 ASMR"],
                "observations": ["带货双人把两段参考分别绑定两位主播，用短附和、插话和包装摩擦声建立互动。", "多角演绎以同一段参考为基础提出不同角色的成熟度、音域和情绪要求。", "韩语 ASMR结合参考声线、近耳气声、低音量衣物摩擦与细小触麦声。"],
                "tips": ["reference_audios的顺序对应@音频1、@音频2；每个角色明确绑定哪段参考。", "写清保留哪些音色特征、改变哪些表演特征；一段参考也能提出不同角色演绎要求。", "参考生成不注册持久音色；长期复用音色使用clone_voice或design_voice。", "最多3段参考，每段<=30秒/10MB；图片参考不能与speaker或音频参考混用。"],
            },
            "timing": {
                "name": "时间控制",
                "official_templates": ["控制音效卡点", "控制情绪递进", "控制叙事转场", "控制旁白推进"],
                "observations": ["音效卡点在广告台词之间安排水声、气泡与收尾提示音，使用小数秒区间。", "情绪递进用带气的句尾、强忍哭意的吸气和空白间隔组织三段表演。", "叙事转场明确旁白模仿人物与恢复叙述的切换；旁白推进将翻页、引擎与配乐渐强绑定到句段。"],
                "tips": ["使用[2.7s:5.7s]，说明总长并为对白、呼吸和转场留足间隔。", "音效写清持续到哪里、如何淡出；情绪变化分段说明，角色切换后注明恢复旁白。", "时间标记随prompt传给text_prompt，没有独立timeline参数或MCP裁切对齐。", "这是生成引导，需试听核对实际落点；字幕start_time/end_time是毫秒且只覆盖人声。"],
            },
            "multilingual": {
                "name": "多语种",
                "official_templates": ["英语", "日语", "韩语"],
                "observations": ["英语模板用英文定义美式口音、不同年龄的角色和呼吸、脚步、冲击等声音。", "日语模板完整描述便利店雨声、门铃、微波炉与杯子声，明确钢琴和弦乐始终低于人声。"],
                "tips": ["台词使用目标语言；可同时用目标语言写场景与表演说明，明确口音和角色差异。", "使用目标语言习惯的拟声词，保持环境声连续，注明人声与配乐音量层级。", "generate_audio没有language参数；可以同时结合参考样音和时间标记。"],
            },
        },
        "tips": ["四类可组合；单次最长120秒，prompt最多3000字符。先生成短片段检查角色和节奏，再扩展。"],
        "examples": [
            example("有音效的双人对白", "generate_audio", {"prompt": "古代书房，角色甲是清亮好奇的青年男声，角色乙是低沉从容的男声。轻快拨弦配乐低于人声。甲疑惑地说：‘这封信是谁送的？’纸张展开沙沙响。乙轻笑，停顿后说：‘你看看落款。’最后配乐轻轻收尾。"}, "text"),
            example("自然播客对谈", "generate_audio", {"prompt": "两位主持人自然交谈。甲是低沉略沙哑的男声，乙是温暖明亮的女声。甲带一点迟疑说：‘嗯，我其实……是第一次自己录节目。’乙轻笑，短短附和：‘我也是。’甲把‘自己’重读，放松地接着说：‘但自己试试，挺有意思。’无配乐。"}, "text"),
            example("两位主播分别参考样音", "generate_audio", {"prompt": "甲参考@音频1的声线，活泼地说：‘打开看看。’包装袋轻轻摩擦。乙参考@音频2的声线，轻笑着附和：‘颜色真好看。’甲稍停顿后继续介绍，无背景音乐。", "reference_audios": ["/absolute/path/host_a.wav", "/absolute/path/host_b.wav"]}, "reference"),
            example("一段参考多种表演", "generate_audio", {"prompt": "三个人物都参考@音频1的声音特征。甲保持自然原声说：‘准备好了吗？’乙用更低沉、成熟克制的表演回答：‘可以开始。’丙用更明亮、轻快的表演说：‘我来试试！’依次发言，角色间留短暂停顿。", "reference_audios": ["/absolute/path/reference.wav"]}, "reference"),
            example("广告音效卡点", "generate_audio", {"prompt": "总长12秒，清亮温柔的女声，轻柔电子乐低于人声。[1s:4s]女声平静地说：‘留一点时间，给自己。’[5s:6s]水滴声，随后轻微气泡咕噜声。[7s:10s]女声温暖地说：‘慢下来，也很好。’最后音乐淡出。", "subtitles": True}, "timing"),
            example("情绪递进与旁白转场", "generate_audio", {"prompt": "总长16秒，女旁白清晰平静，低音量钢琴持续。[1s:5s]旁白说：‘她终于走到门口。’短暂停顿，转为紧张人物语气。[6s:9s]轻声说：‘你还在吗？’听到开门声后呼吸放松，恢复旁白。[11s:15s]温暖地说：‘这一次，她听到了回应。’音乐淡出。"}, "timing"),
            example("日语场景对白", "generate_audio", {"prompt": "雨の夜の小さな店。若い女性は明るく自然な標準日本語、店主は低く穏やかな声。雨音は続き、ピアノは声より小さく。ドアのベルが鳴る。女性：『こんばんは。まだ開いていますか？』店主は少し間を置き、優しく：『はい、どうぞ。』カップを置く小さな音。最後に雨音が遠ざかる。"}, "multilingual"),
        ],
    },
    "tts": {
        "title": "合成2.0：语音指令、方言、读音修正与引用上文",
        "sources": [DOC + "DoubaoTextToSpeech20CapabilityIntroduction?lang=zh", DOC + "unidirectional-streaming-text-to-speech-http?lang=zh"],
        "official_examples": ["吵架", "暧昧悄悄话", "四川话", "北京话", "承接问询语境", "承接老友相见语境"],
        "tips": ["text只放需要朗读的正文；instructions放情绪、语气和速度，先明确主情绪，再补局部变化。", "支持能力取决于音色；方言用dialect，读音纠正用pronunciations。", "引用上文让模型理解上一轮问答但不朗读；高级入口用req_params.additions中的context_texts，additions需JSON字符串。", "当前便捷instructions也映射context_texts；多个上下文、SSML或高级选项用speech_http_request。", "长文本便捷接口按句切段；需整段异步任务用submit_long_text_speech，查询沿用提交resource_id。"],
        "examples": [
            example("安静近耳表演", "text_to_speech", {"text": "今天辛苦了，先好好休息。", "instructions": "像安静的深夜聊天，轻柔、亲切、略慢，避免夸张。"}),
            example("方言与读音", "text_to_speech", {"text": "我们明天去重庆看看。", "dialect": "sichuan", "pronunciations": ["重庆/(chong2)(qing4)"]}),
            example("引用上一轮提问", "speech_http_request", {"product": "tts", "request": {"req_params": {"speaker": "zh_female_vv_uranus_bigtts", "text": "别急，我们一起看看哪里出了问题。", "audio_params": {"format": "mp3"}, "additions": '{"context_texts":["用户刚才着急地问：我怎么总是做不好？"]}'}}}),
            example("双向流式输入文本", "websocket_text_to_speech", {"mode": "bidirectional", "request": {"req_params": {"speaker": "zh_female_vv_uranus_bigtts", "audio_params": {"format": "mp3", "sample_rate": 24000}}}, "text_chunks": ["先听一个小故事。", "窗外的雨，慢慢停了。"]}),
            example("提交长文本合成", "submit_long_text_speech", {"request": {"req_params": {"speaker": "zh_female_vv_uranus_bigtts", "text": "这里替换为需要合成的长文本。", "audio_params": {"format": "mp3"}}}, "resource_id": "seed-tts-2.0"}),
            example("查询长文本结果", "query_long_text_speech", {"task_id": "REPLACE_WITH_SUBMIT_RESULT", "resource_id": "seed-tts-2.0"}),
        ],
    },
    "voice": {
        "title": "音色设计与复刻：声线描述、试听与录音准备",
        "sources": [DOC + "SoundDesignAPI?lang=zh", DOC + "SoundReplication20BestPractices?lang=zh", DOC + "tone-training-http?lang=zh"],
        "official_examples": ["街头说唱者", "儒雅老人", "古代文人", "超市促销员"],
        "tips": ["设计描述按性别/年龄感、音色质感、语言、角色、语速/语调/情绪展开；优先写最重要的辨识特征。", "text是试听正文，prompt.text_prompt是声音描述；用与最终场景一致的文本试听，促销场景可包含价格数字。", "设计描述<=200字符，试听<=300字符；图片<=10MB。图文同时提交时image_prompt优先，image_bytes优于image_url。", "设计和复刻需已分配的speaker_id，消耗训练次数；查询状态成功/激活后再用该音色合成，试听URL只有1小时。", "复刻最佳实践推荐14–30秒WAV、单声道、单人、低噪声和一致的表演；避免重叠人声、混响，过度降噪可能损失相似度。", "中英混读目标应在样音覆盖中英；稳定助理选平稳样音，表达型复刻还需结合正文语义与语音指令试听。"],
        "examples": [
            example("亲切长者音色", "design_voice", {"request": {"speaker_id": "S_REPLACE_WITH_ALLOCATED_ID", "text": "早上给花浇一点水，慢慢来，它会长得很好。", "prompt": {"text_prompt": "六十岁左右的男性，温暖略沙哑，普通话清晰，语速适中，语调平稳，像耐心讲故事的长者。"}}}),
            example("图片设计音色", "design_voice", {"request": {"speaker_id": "S_REPLACE_WITH_ALLOCATED_ID", "text": "你好，很高兴认识你。"}, "image_file": "/absolute/path/character.png"}),
            example("准备好的单人录音复刻", "clone_voice", {"request": {"speaker_id": "S_REPLACE_WITH_ALLOCATED_ID", "language": "zh", "text": "这里替换为训练录音对应的实际文字。"}, "audio_file": "/absolute/path/clean_mono.wav"}),
            example("查询训练状态", "query_voice", {"request": {"speaker_id": "S_REPLACE_WITH_ALLOCATED_ID"}}),
        ],
    },
    "podcast": {
        "title": "播客：文章、链接、逐轮脚本与联网话题",
        "sources": [DOC + "PodcastAPI-websocket-v3protocol?lang=zh", CONSOLE + "podcast?projectName=default"],
        "tips": ["action=0文章/链接；action=3直接演绎逐轮脚本；action=4根据话题联网生成。prompt_text是话题，不具备格式指令能力。", "文章与URL同时传时input_text优先；API的文件URL支持PDF/doc/txt，不把控制台上传格式直接视为API格式。", "input_info.only_nlp_text=true先生成脚本；逐轮脚本每轮<=300字、总量<=10000字。", "speaker_info.speakers必须是两个音色，建议同系列配对；random_order=false固定提供的顺序。", "文章input_text_max_length推荐<=12000，超过设置会截断；音频URL有效1小时。", "收到partial后保留task_id和last_finished_round_id，通过retry_info显式续传，不能把局部音频当完整成品。"],
        "examples": [
            example("文章先生成脚本", "generate_podcast", {"request": {"action": 0, "input_text": "这里替换为完整文章。", "input_info": {"only_nlp_text": True}}}),
            example("链接转播客", "generate_podcast", {"request": {"action": 0, "input_info": {"input_url": "https://example.com/article"}, "audio_config": {"format": "mp3"}}}),
            example("指定逐轮脚本", "generate_podcast", {"request": {"action": 3, "speaker_info": {"speakers": ["zh_male_dayixiansheng_v2_saturn_bigtts", "zh_female_mizaitongxue_v2_saturn_bigtts"], "random_order": False}, "nlp_texts": [{"speaker": "zh_male_dayixiansheng_v2_saturn_bigtts", "text": "今天我们聊聊怎样开始记录生活。"}, {"speaker": "zh_female_mizaitongxue_v2_saturn_bigtts", "text": "先从每天一个小片段开始吧。"}], "audio_config": {"format": "mp3"}}}),
            example("联网话题", "generate_podcast", {"request": {"action": 4, "prompt_text": "城市步行与日常健康", "audio_config": {"format": "mp3"}}}),
        ],
    },
    "asr": {
        "title": "识别：热词、上下文与说话人分离",
        "sources": [DOC + "hot-words-and-context?lang=zh", DOC + "speaker-separation?lang=zh"],
        "tips": ["热词只放难识别的专名，不堆通用词；热词是概率引导，替换词表是后处理强制替换。", "热词效果差时补生僻字解释或领域背景；上下文优先最近几轮，按新到旧排列。", "流式高级corpus.context必须序列化为JSON字符串，可同时含hotwords、context_type=dialog_ctx、context_data；不要传裸对象。", "容量因链路而异：双向流式热词100 tokens，非流式/二遍5000词；非流式/二遍上下文800 tokens/20轮，不能套用便捷极速版参数限制。", "分离说话人同时开enable_speaker_info与show_utterances。标准AUC短音频用ssd_version=200，长会议用300，长非会议用200加ssd_mode=1。", "这些SSD选项用于对应标准/流式链路，不把便捷极速版utterances开关当成会议模型选择。说话人编号不等于已知身份；声纹匹配需先注册声纹。", "重叠人声、相近音色和不足1秒的短插话会影响分离；流式定稿优先采用最终/二遍结果。"],
        "examples": [
            example("领域音频快速转写", "speech_to_text", {"audio": "/absolute/path/talk.wav", "hotwords": ["火山引擎", "Kubernetes"], "context": "这是一段云计算技术分享，讨论容器部署。", "utterances": True}),
            example("长会议标准识别", "submit_transcription", {"mode": "standard", "request": {"user": {"uid": "mcp"}, "audio": {"url": "https://example.com/meeting.wav"}, "request": {"model_name": "bigmodel", "enable_speaker_info": True, "show_utterances": True, "ssd_version": "300"}}}),
            example("流式热词加最近上下文", "streaming_speech_to_text", {"audio": "/absolute/path/mono16k.wav", "mode": "realtime", "request": {"request": {"enable_nonstream": True, "corpus": {"context": '{"hotwords":[{"word":"火山引擎"}],"context_type":"dialog_ctx","context_data":[{"text":"刚才讨论的是火山引擎的容器服务。"}]}'}}}}),
        ],
    },
    "translation": {
        "title": "翻译与同传：术语一致性、字幕和语音输出",
        "sources": [DOC + "MachineTranslationLargeModel-APIAccessDocumentation?lang=zh", DOC + "SimultaneousInterpretation20APIAccessDocumentation?lang=zh"],
        "tips": ["固定品牌和专业术语用corpus.glossary_list；直传术语优先于术语表。不要把ASR热词当作翻译词典。", "机器翻译不指定source_language可自动检测；1–16条文本，按原顺序处理，每条<=1024 tokens。", "同传文件需16kHz/16bit/单声道；s2t只要字幕，s2s还返回目标语音。", "录音保持安静、避免多人同时发言；本工具处理文件，麦克风实时采集由客户端负责。"],
        "examples": [
            example("指定术语译法", "translate_text", {"text_list": ["火山引擎提供语音服务。"], "target_language": "en", "source_language": "zh", "corpus": {"glossary_list": {"火山引擎": "Volcengine"}}}),
            example("同传字幕", "interpret_audio", {"audio": "/absolute/path/mono16k.wav", "source_language": "zh", "target_language": "en", "mode": "s2t"}),
            example("同传目标语音", "interpret_audio", {"audio": "/absolute/path/mono16k.wav", "source_language": "zh", "target_language": "en", "mode": "s2s"}),
        ],
    },
    "minutes": {
        "title": "妙记：按需启用摘要与章节",
        "sources": [DOC + "DoubaoVoiceMinutes-APIAccessDocumentation?lang=zh"],
        "tips": ["AllActivate选择计费方式，不等于自动开启功能；明确开启所需摘要、章节、翻译或信息提取。", "只需原始转写可使用ASR；妙记请求至少启用一项妙记附加功能。", "转写需显式填写SpeakerIdentification、NumberOfSpeaker（未知填0）和NeedWordTimeSeries。摘要传SummarizationParams.Types=[summary]，提取传InformationExtractionParams.Types。", "提交保留task_id/request_id，再查询；临时结果URL应及时保存，等待中不重复提交。"],
        "examples": [
            example("会议转写与摘要", "submit_minutes", {"request": {"Input": {"Offline": {"FileURL": "https://example.com/meeting.wav", "FileType": "audio"}}, "Params": {"AllActivate": False, "SourceLang": "zh_cn", "AudioTranscriptionEnable": True, "AudioTranscriptionParams": {"SpeakerIdentification": True, "NumberOfSpeaker": 0, "NeedWordTimeSeries": False}, "SummarizationEnabled": True, "SummarizationParams": {"Types": ["summary"]}}}}),
            example("转写并提取待办和问答", "submit_minutes", {"request": {"Input": {"Offline": {"FileURL": "https://example.com/meeting.wav", "FileType": "audio"}}, "Params": {"AllActivate": False, "SourceLang": "zh_cn", "AudioTranscriptionEnable": True, "AudioTranscriptionParams": {"SpeakerIdentification": True, "NumberOfSpeaker": 0, "NeedWordTimeSeries": False}, "InformationExtractionEnabled": True, "InformationExtractionParams": {"Types": ["todo_list", "question_answer"]}, "ChapterEnabled": True}}}),
            example("查询妙记结果", "query_minutes", {"task_id": "REPLACE_WITH_SUBMIT_RESULT", "request_id": "REPLACE_WITH_SUBMIT_REQUEST_ID"}),
        ],
    },
    "realtime": {
        "title": "实时语音：角色指令、输入判停、打断与工具回传",
        "sources": [DOC + "endtoend-realtime-voice-full-duplex-version?lang=zh"],
        "tips": ["session.instructions定义角色、语气和回答范围；不要照搬音频生成的时间区间标记。", "按open→append音频→commit→receive→close处理；输入文件是16kHz单声道int16裸PCM，append后需显式commit。", "response.cancel用于打断；工具调用应执行后按call_id回传结果，不能只收到调用就视为已完成。", "session_id是当前MCP进程的句柄，重启后失效；退出或完成后关闭连接。"],
        "examples": [
            example("简短语言陪练", "open_realtime_session", {"session": {"instructions": "你是耐心的英语口语陪练，每次只问一个简短问题，纠错时用简单中文解释。", "audio": {"output": {"voice": "zh_female_vv_jupiter_bigtts"}}}}),
            example("追加客户端采集音频", "send_realtime_event", {"session_id": "REPLACE_WITH_OPEN_RESULT", "event": {"type": "input_audio_buffer.append"}, "audio_file": "/absolute/path/mono16k.pcm"}),
            example("文件结束强制判停", "send_realtime_event", {"session_id": "REPLACE_WITH_OPEN_RESULT", "event": {"type": "input_audio_buffer.commit"}}),
            example("接收回复", "receive_realtime_events", {"session_id": "REPLACE_WITH_OPEN_RESULT", "timeout": 10}),
            example("打断回复", "send_realtime_event", {"session_id": "REPLACE_WITH_OPEN_RESULT", "event": {"type": "response.cancel"}}),
            example("结束会话", "close_realtime_session", {"session_id": "REPLACE_WITH_OPEN_RESULT"}),
        ],
    },
}


def get_examples(product="audio", category=None):
    if product not in GUIDES:
        return {"ok": False, "error": "未知product", "available_products": list(GUIDES)}
    guide = deepcopy(GUIDES[product])
    if category is not None:
        categories = guide.get("categories", {})
        if category not in categories:
            return {"ok": False, "error": "该产品不存在此category", "available_categories": list(categories)}
        guide["categories"] = {category: categories[category]}
        guide["examples"] = [e for e in guide["examples"] if e.get("category") == category]
    return {"ok": True, "product": product, "verified_on": "2026-10-09",
            "available_products": list(GUIDES),
            "validation": "官方模板已阅读；示例为改写的MCP参数，未实际云端生成。路径、URL、音色ID和会话ID占位符需替换。",
            **guide}
