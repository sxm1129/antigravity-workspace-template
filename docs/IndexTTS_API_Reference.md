# IndexTTS API 接口文档

> 本文档整理自 DolphinInfoFactory 项目中实际调用的 IndexTTS 服务接口，供外部项目快速对接使用。

## 服务信息

| 项目 | 值 |
|------|-----|
| 默认地址 | `http://39.102.122.9:8049` |
| 环境变量 | `INDEX_TTS_URL`（服务地址）、`INDEX_TTS_VOICE`（默认音色） |
| 音频输出 | WAV 格式，Base64 编码，采样率 24000Hz |

---

## API 端点一览

| 方法 | 端点 | 说明 |
|------|------|------|
| `POST` | `/api/v1/tts` | 基础语音合成（核心接口） |
| `POST` | `/api/v1/tts/emotion` | 情感控制语音合成 |
| `POST` | `/api/v1/tts/advanced` | 高级参数语音合成 |
| `GET` | `/api/v1/health` | 健康检查 |
| `GET` | `/api/v1/prompts` | 获取可用音色/情感索引列表 |
| `GET` | `/api/v1/stats/concurrency` | 并发状态查询 |

---

## 1. 基础 TTS 合成

**`POST /api/v1/tts`**

这是项目中**最常用**的接口，支持索引模式（推荐）和上传模式两种方式。

### 请求参数（Form Data）

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `input_text` | string | ✅ | — | 要合成的文本 |
| `index` | string | ⚠️ 二选一 | — | 预配置音色索引（推荐） |
| `prompt_audio` | file | ⚠️ 二选一 | — | 自定义音色参考音频 |
| `beam_size` | int | ❌ | `1` | 束搜索大小 (1-5，越大质量越好) |
| `sample_rate` | int | ❌ | `24000` | 采样率 |
| `use_cache` | string | ❌ | `"true"` | 是否使用缓存 |
| `seed` | int | ❌ | `42` | 随机种子 |

> `index` 和 `prompt_audio` 二选一，优先使用 `index`。

### 请求示例

```bash
curl -X POST http://39.102.122.9:8049/api/v1/tts \
  -F "input_text=你好，欢迎使用语音合成服务。" \
  -F "index=zh_male_tech" \
  -F "beam_size=1" \
  -F "sample_rate=24000" \
  -F "use_cache=true"
```

### 成功响应

```json
{
    "success": true,
    "message": "Audio generated successfully",
    "audio_base64": "UklGRiQAAABXQVZFZm10...",
    "sample_rate": 24000,
    "generation_time": 1.08
}
```

### 失败响应

```json
{
    "success": false,
    "message": "Generation failed",
    "error": "错误详情"
}
```

### 响应字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `success` | bool | 是否成功 |
| `message` | string | 响应消息 |
| `audio_base64` | string | Base64 编码的 WAV 音频数据 |
| `sample_rate` | int | 音频采样率 |
| `generation_time` | float | 生成耗时（秒） |
| `error` | string | 错误信息（仅失败时） |

---

## 2. 情感控制 TTS

**`POST /api/v1/tts/emotion`**

在基础 TTS 的基础上增加情感控制能力。

### 额外参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `emo_index` | string | — | 情感参考音频索引（如 `emo_sad`） |
| `emo_audio` | file | — | 上传情感参考音频 |
| `emo_alpha` | float | `1.0` | 情感强度权重 (0.0-1.0) |
| `emo_vector` | string | — | JSON 格式 8 维情感向量 |
| `emo_text` | string | — | 情感描述文本（实验性） |

> 情感向量格式：`[happy, angry, sad, afraid, disgusted, melancholic, surprised, calm]`

### 请求示例

```bash
# 使用情感索引
curl -X POST http://39.102.122.9:8049/api/v1/tts/emotion \
  -F "input_text=这真是太令人难过了。" \
  -F "index=zh_male_talk_show" \
  -F "emo_index=emo_sad" \
  -F "emo_alpha=0.65"

# 使用情感向量
curl -X POST http://39.102.122.9:8049/api/v1/tts/emotion \
  -F "input_text=哇塞！太棒了！" \
  -F "index=zh_male_tech" \
  -F 'emo_vector=[0,0,0,0,0,0,0.45,0]' \
  -F "emo_alpha=0.8"
```

---

## 3. 高级参数 TTS

**`POST /api/v1/tts/advanced`**

暴露全部生成参数，适合精细调优。

### 额外参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `do_sample` | string | `"true"` | 是否启用采样 |
| `temperature` | float | `0.8` | 温度 (0.1-2.0) |
| `top_p` | float | `0.8` | Top-P 核采样 (0.0-1.0) |
| `top_k` | int | `30` | Top-K 采样 (0-100) |
| `num_beams` | int | `3` | 束搜索大小 (1-10) |
| `repetition_penalty` | float | `10.0` | 重复惩罚 |
| `length_penalty` | float | `0.0` | 长度惩罚 |
| `max_mel_tokens` | int | `1500` | 最大梅尔频谱 token 数 |
| `max_text_tokens_per_segment` | int | `120` | 每段最大文本 token 数 |

---

## 4. 健康检查

**`GET /api/v1/health`**

```bash
curl http://39.102.122.9:8049/api/v1/health
```

```json
{
    "status": "healthy",
    "model_loaded": true,
    "model_version": "2.0",
    "device": "cuda:0",
    "fp16_enabled": true,
    "available_prompts": 28,
    "available_emotions": 2
}
```

---

## 5. 获取音色索引列表

**`GET /api/v1/prompts`**

返回所有可用的音色索引和情感索引。

```bash
curl http://39.102.122.9:8049/api/v1/prompts
```

---

## 6. 并发状态查询

**`GET /api/v1/stats/concurrency`**

```bash
curl http://39.102.122.9:8049/api/v1/stats/concurrency
```

---

## 可用音色索引

### 中文音色

| 索引 | 描述 | 适用场景 |
|------|------|----------|
| `zh_female_gossip` | 🎭 活泼八卦风格 | 娱乐、八卦类内容 |
| `zh_female_morning` | ☀️ 温和亲切早间主播 | 新闻播报、晨间节目 |
| `zh_female_intellectual` | 🎓 专业稳重知性风格 | 知识性内容、教育 |
| `zh_female_investigative` | 🔍 严肃质询调查记者 | 深度报道、访谈 |
| `zh_male_sports` | ⚽ 激情体育解说 | 体育赛事解说 |
| `zh_male_tech` | 💻 年轻活力科技UP主 | 科技评测、教程（**默认音色**） |
| `zh_male_breaking_news` | 📢 紧急严肃突发新闻 | 新闻快讯 |
| `zh_male_talk_show` | 🎤 幽默轻松脱口秀 | 娱乐节目 |

### 英文音色

| 索引 | 描述 |
|------|------|
| `en_female_gossip` | Lively gossip style |
| `en_female_morning` | Warm morning anchor |
| `en_female_intellectual` | Professional commentary |
| `en_female_investigative` | Serious investigative |
| `en_female_midnight` | Mysterious late-night voice |
| `en_female_midnight_2` | Alternate midnight variant |
| `en_female_mature` | Mature confident voice |
| `en_female_smoky` | Smoky textured voice |
| `en_female_whisper` | Soft whispering voice |
| `en_male_sports` | Energetic sports commentary |
| `en_male_tech` | Tech reviews & tutorials |
| `en_male_breaking_news` | Urgent news reporter |
| `en_male_talk_show` | Casual talk show host |

### 通用音色

| 索引 | 说明 |
|------|------|
| `voice_01` ~ `voice_12` | 原有音色参考 01-12 |

### 情感索引

| 索引 | 描述 |
|------|------|
| `emo_sad` | 悲伤情感参考 |
| `emo_hate` | 厌恶情感参考 |

---

## 快速对接指南

### Python 示例

```python
import httpx
import base64

async def tts_synthesize(text: str, voice: str = "zh_male_tech") -> bytes:
    """调用 IndexTTS 合成语音，返回 WAV 音频数据"""
    api_url = "http://39.102.122.9:8049/api/v1/tts"

    data = {
        "input_text": text,
        "index": voice,
        "beam_size": "1",
        "sample_rate": "24000",
        "use_cache": "true",
    }

    # 超时：基础 60s + 每 50 字增加 10s，上限 600s
    timeout = min(60.0 + len(text) // 50 * 10.0, 600.0)

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(api_url, data=data)

    if response.status_code == 200:
        result = response.json()
        if result.get("success"):
            return base64.b64decode(result["audio_base64"])
        else:
            raise Exception(f"TTS 失败: {result.get('error')}")
    else:
        raise Exception(f"HTTP 错误: {response.status_code}")
```

### JavaScript/Node.js 示例

```javascript
const axios = require('axios');
const FormData = require('form-data');

async function ttsSynthesize(text, voice = 'zh_male_tech') {
  const formData = new FormData();
  formData.append('input_text', text);
  formData.append('index', voice);
  formData.append('beam_size', '1');
  formData.append('sample_rate', '24000');
  formData.append('use_cache', 'true');

  const response = await axios.post(
    'http://localhost:8049/api/v1/tts',
    formData,
    { timeout: 600000, headers: formData.getHeaders() }
  );

  if (response.data.success) {
    return Buffer.from(response.data.audio_base64, 'base64');
  } else {
    throw new Error(`TTS 失败: ${response.data.error}`);
  }
}
```

---

## 注意事项

### 超时设置

| 文本长度 | 建议超时 |
|----------|----------|
| < 50 字 | 60 秒 |
| 50-200 字 | 120-300 秒 |
| > 200 字 | 300-600 秒 |

### 并发限制

| 文本长度 | 最大并发 |
|----------|----------|
| ≤ 100 字符 | 3 |
| 101-300 字符 | 2 |
| > 300 字符 | 1 |

### 音频处理

- 返回的 `audio_base64` 解码后为 **WAV 格式**（24kHz，16-bit）
- 如需 MP3，需自行使用 ffmpeg 转换：
  ```bash
  ffmpeg -y -i input.wav -codec:a libmp3lame -b:a 192k output.mp3
  ```

### 错误码

| HTTP 状态码 | 说明 | 处理建议 |
|-------------|------|----------|
| 200 | 请求成功（需检查 `success` 字段） | — |
| 400 | 请求参数错误 | 检查参数格式 |
| 404 | 端点不存在 | 检查 API 路径 |
| 408 | 请求超时 | 增加超时时间或缩短文本 |
| 500 | 服务器内部错误 | 检查服务器日志 |

### 业务错误码

| 错误标识 | 说明 |
|----------|------|
| `EMPTY_TEXT` | 输入文本为空 |
| `INDEX_NOT_FOUND` | 音色索引不存在 |
| `MISSING_PROMPT` | 缺少音色参数（index 或 prompt_audio） |
| `INVALID_EMO_VECTOR` | 情感向量格式错误（需为 8 个浮点数的数组） |

---

## 性能参考

基于 NVIDIA L20 GPU (46GB) + FP16 模式：

| 文本长度 | 生成时间 | 显存占用 |
|----------|----------|----------|
| 10 字 | ~1-2 秒 | ~5.3 GB |
| 50 字 | ~3-5 秒 | ~5.3 GB |
| 200 字 | ~10-15 秒 | ~5.3 GB |
