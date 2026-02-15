from __future__ import annotations
"""AI Writer service — generates outline, script, and parses scenes.

Uses OpenRouter API with google/gemini-3-flash-preview.
In mock mode, returns canned responses for testing.
"""

import json
import logging
import re

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

OPENROUTER_URL = f"{settings.OPENROUTER_BASE_URL}/chat/completions"

OUTLINE_SYSTEM_PROMPT = """你是一位经验丰富的漫剧编剧。根据用户提供的一句话灵感（logline），
请扩写出一个完整的故事大纲，包含：
1. 世界观设定
2. 主要角色列表（姓名、外貌特征、性格）
3. 故事主线（开端、发展、高潮、结局）
4. 每一集/幕的简要描述

请用 Markdown 格式输出。"""

SCRIPT_SYSTEM_PROMPT = """你是一位经验丰富的漫剧编剧。根据以下故事大纲，
请扩写出完整的对白剧本。要求：
1. 包含场景描述（时间、地点、氛围）
2. 角色对白（含表情、动作指示）
3. 旁白和音效提示
4. 分镜提示（画面描述）

请用 Markdown 格式输出，使用场景编号标记。"""

PARSE_SCENES_SYSTEM_PROMPT = """你是一个专业的漫剧分镜拆解助手。请将以下剧本拆解为一系列分镜镜头。

对于每一个镜头，请严格按以下 JSON 格式输出：
{
  "scenes": [
    {
      "sequence_order": 1,
      "dialogue_text": "角色的台词（如果有）",
      "prompt_visual": "详细的画面描述，用于 AI 生图，包含构图、光影、色调等",
      "prompt_motion": "动作描述，用于 AI 生视频，包含角色动作、镜头运动等",
      "sfx_text": "画面上需要渲染的文字效果（如音效文字、标题文字）"
    }
  ]
}

要求：
1. 每个镜头应该是一个独立的、可视化的画面
2. prompt_visual 要尽可能详细，包含人物外貌、表情、服装、背景等
3. prompt_motion 描述动作和镜头运动
4. 严格输出合法 JSON"""


async def generate_outline(logline: str) -> str:
    """Generate a world outline from a logline.

    Args:
        logline: A one-sentence story idea.

    Returns:
        Markdown-formatted story outline with world-building.
    """
    if settings.USE_MOCK_API:
        return _mock_outline(logline)

    return await _call_openrouter(
        system_prompt=OUTLINE_SYSTEM_PROMPT,
        user_prompt=f"灵感：{logline}",
    )


async def generate_script(outline: str) -> str:
    """Expand an approved outline into a full dialogue script.

    Args:
        outline: The approved story outline.

    Returns:
        Markdown-formatted full script with dialogues and directions.
    """
    if settings.USE_MOCK_API:
        return _mock_script(outline)

    return await _call_openrouter(
        system_prompt=SCRIPT_SYSTEM_PROMPT,
        user_prompt=f"故事大纲：\n\n{outline}",
    )


async def parse_scenes(script: str) -> list[dict]:
    """Parse a full script into structured scene data using JSON mode.

    Args:
        script: The full dialogue script.

    Returns:
        List of scene dicts with visual/motion prompts.
    """
    if settings.USE_MOCK_API:
        return _mock_parse_scenes(script)

    response_text = await _call_openrouter(
        system_prompt=PARSE_SCENES_SYSTEM_PROMPT,
        user_prompt=f"剧本：\n\n{script}",
        json_mode=True,
    )

    # Robust JSON extraction: strip markdown code fences if present
    json_text = _extract_json_text(response_text)

    try:
        data = json.loads(json_text)
        scenes = data.get("scenes", data) if isinstance(data, dict) else data
        if isinstance(scenes, list):
            return scenes
        raise ValueError(f"Expected list of scenes, got {type(scenes).__name__}")
    except (json.JSONDecodeError, ValueError) as e:
        logger.error("Failed to parse JSON response: %s\nRaw: %s", e, response_text[:500])
        raise ValueError(f"AI returned invalid JSON for scene parsing: {e}")


def _extract_json_text(text: str) -> str:
    """Extract JSON from text that may be wrapped in markdown code fences.

    Handles: ```json ... ```, ``` ... ```, and bare JSON.
    """
    # Try to extract from markdown code fence: ```json ... ``` or ``` ... ```
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if fence_match:
        return fence_match.group(1).strip()

    # Already bare JSON — strip whitespace
    stripped = text.strip()
    if stripped.startswith(("{", "[")):
        return stripped

    # Last resort: find first { or [ and last } or ]
    first_brace = min(
        (stripped.find(c) for c in ("{", "[") if stripped.find(c) != -1),
        default=-1,
    )
    if first_brace != -1:
        last_brace = max(
            (stripped.rfind(c) for c in ("}", "]") if stripped.rfind(c) != -1),
            default=-1,
        )
        if last_brace > first_brace:
            return stripped[first_brace : last_brace + 1]

    return stripped


async def _call_openrouter(
    system_prompt: str,
    user_prompt: str,
    json_mode: bool = False,
) -> str:
    """Call OpenRouter chat completions API.

    Uses google/gemini-3-flash-preview for story generation tasks.
    """
    headers = {
        "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://motionweaver.app",
        "X-Title": "MotionWeaver",
    }

    body: dict = {
        "model": settings.STORY_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.8,
        "max_tokens": 8192,
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}

    logger.info("Calling OpenRouter model=%s json_mode=%s", settings.STORY_MODEL, json_mode)

    async with httpx.AsyncClient(timeout=180.0) as client:
        response = await client.post(OPENROUTER_URL, headers=headers, json=body)
        response.raise_for_status()

    data = response.json()
    content = data["choices"][0]["message"]["content"]
    logger.info("OpenRouter response received, length=%d", len(content))
    return content


# ---------------------------------------------------------------------------
# Mock implementations (kept for testing with USE_MOCK_API=True)
# ---------------------------------------------------------------------------

def _mock_outline(logline: str) -> str:
    return f"""# 故事大纲：{logline}

## 世界观设定
在一个充满科技与魔法并存的近未来都市中，人类发现了一种名为"心灵之石"的神秘矿物，
它能将人的情感转化为可视化的能量。

## 主要角色
### 林小雨
- **外貌**：黑色长发，大眼睛，常穿蓝色校服，身高165cm
- **性格**：善良温柔，内向但坚定
- **特点**：天生拥有极强的"心灵感应"能力

### 陈风
- **外貌**：棕色短发，高挺的鼻子，穿黑色夹克，身高178cm
- **性格**：外向开朗，正义感强
- **特点**：擅长将情感能量转化为物理力量

## 故事主线

### 第一幕：相遇
林小雨在学校图书馆中意外激活了一颗远古心灵之石，释放出强大的能量波动。
陈风感知到波动赶来，两人初次相遇。

### 第二幕：危机
一个神秘组织"暗影会"出现，他们企图收集心灵之石来控制整座城市。
林小雨和陈风被卷入冲突。

### 第三幕：成长
在逃亡与战斗中，两人学会了合作，并发现了心灵之石更深层的秘密。

### 第四幕：决战
最终决战中，林小雨牺牲自己的能力封印了暗影会的野心，
但心灵之石的碎片散落世界各地，暗示着新的冒险即将开始。
"""


def _mock_script(outline: str) -> str:
    return """# 第一幕：相遇

## 场景一：学校图书馆 · 黄昏

> 暖黄色的夕阳光线从高窗洒入，尘埃在光束中轻轻舞动。

**林小雨**（坐在角落翻阅古书，喃喃自语）：
"这些符号...好像在哪里见过..."

> 她的手指触碰到书中一颗嵌入的蓝色宝石，突然发出耀眼光芒

**[SFX: ✨ 轰！！]**

**林小雨**（惊恐后退）：
"什...什么？！"

## 场景二：图书馆外走廊 · 同一时间

> 陈风正走在走廊上，手中的饮料突然开始震动

**陈风**（停下脚步，警惕地看向图书馆方向）：
"这股能量波动...太强了！"

> 他扔下饮料，快步冲向图书馆

## 场景三：图书馆内 · 紧接

> 蓝色能量在空中盘旋，书架上的书本被气浪吹得四散

**陈风**（推门冲入）：
"你没事吧？！"

**林小雨**（蹲在地上颤抖）：
"我...我不知道发生了什么..."

**陈风**（走上前，伸出手）：
"先离开这里，我来帮你。"

**[SFX: 💫 嗡嗡嗡~]**
"""


def _mock_parse_scenes(script: str) -> list[dict]:
    return [
        {
            "sequence_order": 1,
            "dialogue_text": "这些符号...好像在哪里见过...",
            "prompt_visual": "黄昏的学校图书馆内景，暖黄色阳光从高窗照入，明暗对比鲜明。一位黑色长发的女高中生（蓝色校服）独自坐在角落木桌前，低头翻阅一本散发微光的古书。画面构图三分法，女孩在右侧三分之一处，背景是高耸的书架。电影感色调，偏暖。",
            "prompt_motion": "女孩慢慢翻书页，手指轻触蓝色宝石的特写。镜头从中景缓慢推至手部近景。",
            "sfx_text": None,
        },
        {
            "sequence_order": 2,
            "dialogue_text": "什...什么？！",
            "prompt_visual": "图书馆突然爆发蓝色光芒，女孩被光芒包围，惊恐地向后倒退。书本被气浪吹起飞散在空中。明暗强烈对比，蓝白色能量光线穿透整个图书馆。高对比度，赛博朋克风格光效。",
            "prompt_motion": "蓝色光球从书中爆射而出，镜头快速拉远展现整个图书馆被光芒充满。女孩后退的动作。",
            "sfx_text": "✨ 轰！！",
        },
        {
            "sequence_order": 3,
            "dialogue_text": "这股能量波动...太强了！",
            "prompt_visual": "学校走廊，黄昏光线。一位棕色短发的高中男生（黑色夹克）站在走廊中央，手中的饮料瓶在微微震动。他的表情从困惑变为警惕，目光看向远处图书馆方向。透视构图，走廊纵深感强。",
            "prompt_motion": "男生停下脚步，饮料瓶震动的特写，然后他扔下饮料开始奔跑。镜头先特写表情再拉远。",
            "sfx_text": None,
        },
        {
            "sequence_order": 4,
            "dialogue_text": "你没事吧？！",
            "prompt_visual": "图书馆内，蓝色能量盘旋在空中，制造出奇幻般的光影效果。男生推门冲入的动态画面。前景散落的书本，中景跑入的男生，背景蓝光漩涡。动感构图，运动模糊效果。",
            "prompt_motion": "男生猛推大门冲入图书馆，斗篷般的夹克随风飘动。镜头从门口跟随推进。",
            "sfx_text": "💫 嗡嗡嗡~",
        },
        {
            "sequence_order": 5,
            "dialogue_text": "先离开这里，我来帮你。",
            "prompt_visual": "图书馆内，男生站在蹲在地上的女孩面前，向她伸出手。逆光构图，背后蓝色能量光芒形成光环。两人之间的信任感。温暖与冷色光的对比。电影感大特写。",
            "prompt_motion": "男生微笑伸出手的慢动作，女孩抬头看向他。镜头从低角度仰拍，缓慢升起。",
            "sfx_text": None,
        },
    ]
