from __future__ import annotations
"""AI Writer service — generates outline, script, and parses scenes.

Uses OpenRouter API with google/gemini-3-flash-preview.
In mock mode, returns canned responses for testing.
"""

import json
import logging
import re

from app.config import get_settings
from app.services.llm_client import llm_call

logger = logging.getLogger(__name__)
settings = get_settings()

# _call_openrouter is now a thin wrapper around llm_client.llm_call()

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
      "dialogue_text": "角色的台词内容（仅台词本身，不要包含角色名称前缀如"齐齐："）",
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
4. dialogue_text 只写台词内容，绝不能包含 "角色名:" 或 "角色名：" 前缀，因为会直接用于语音合成
5. 严格输出合法 JSON"""

EXTRACT_EPISODES_SYSTEM_PROMPT = """你是一个专业的漫剧编剧助手。请从以下世界观大纲中提取所有剧集信息。

严格按以下 JSON 格式输出：
{
  "episodes": [
    {
      "episode_number": 1,
      "title": "剧集标题",
      "synopsis": "该剧集的完整概要，包含关键情节和钩子"
    }
  ]
}

要求：
1. 按照大纲中剧集出现的顺序提取
2. title 只需要标题名，不包含"第X集"前缀
3. synopsis 要尽可能保留原文的关键幕和钩子信息
4. 严格输出合法 JSON"""

EPISODE_SCRIPT_SYSTEM_PROMPT = """你是一位经验丰富的漫剧编剧。请根据以下世界观大纲和特定剧集概要，
扩写出这一集的完整对白剧本。要求：
1. 包含场景描述（时间、地点、氛围）
2. 角色对白（含表情、动作指示）
3. 旁白和音效提示
4. 分镜提示（画面描述）
5. 剧本应该有5-8个场景，确保情节完整

请用 Markdown 格式输出，使用场景编号标记。"""


async def generate_outline(logline: str, style: str = "default", custom_prompt: str | None = None) -> str:
    """Generate a world outline from a logline.

    Args:
        logline: A one-sentence story idea.
        style: Style preset name for prompt template selection.
        custom_prompt: Optional user-edited system prompt (highest priority).

    Returns:
        Markdown-formatted story outline with world-building.
    """
    if settings.USE_MOCK_API:
        return _mock_outline(logline, style)

    # Priority: custom_prompt > style template > hardcoded default
    if custom_prompt:
        system_prompt = custom_prompt
    else:
        from app.prompts.manager import PromptManager
        system_prompt = PromptManager.get_prompt("outline", style) or OUTLINE_SYSTEM_PROMPT

    return await _call_openrouter(
        system_prompt=system_prompt,
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


async def extract_episodes(outline: str) -> list[dict]:
    """Extract episode information from a world outline.

    Args:
        outline: The world outline containing episode descriptions.

    Returns:
        List of dicts with episode_number, title, synopsis.
    """
    if settings.USE_MOCK_API:
        return _mock_extract_episodes(outline)

    response_text = await _call_openrouter(
        system_prompt=EXTRACT_EPISODES_SYSTEM_PROMPT,
        user_prompt=f"世界观大纲：\n\n{outline}",
        json_mode=True,
    )

    json_text = _extract_json_text(response_text)

    try:
        data = json.loads(json_text)
        episodes = data.get("episodes", data) if isinstance(data, dict) else data
        if isinstance(episodes, list):
            return episodes
        raise ValueError(f"Expected list of episodes, got {type(episodes).__name__}")
    except (json.JSONDecodeError, ValueError) as e:
        logger.error("Failed to parse episode JSON: %s\nRaw: %s", e, response_text[:500])
        raise ValueError(f"AI returned invalid JSON for episode extraction: {e}")


async def generate_episode_script(outline: str, episode_number: int, episode_title: str, episode_synopsis: str) -> str:
    """Generate a full script for a single episode.

    Args:
        outline: The full world outline for context.
        episode_number: The episode number.
        episode_title: The episode title.
        episode_synopsis: The episode synopsis/summary.

    Returns:
        Markdown-formatted full script for this episode.
    """
    if settings.USE_MOCK_API:
        return _mock_episode_script(episode_number, episode_title, episode_synopsis)

    user_prompt = f"""世界观大纲：
{outline}

---

请为以下剧集编写完整的对白剧本：

第{episode_number}集：{episode_title}
剧集概要：{episode_synopsis}"""

    return await _call_openrouter(
        system_prompt=EPISODE_SCRIPT_SYSTEM_PROMPT,
        user_prompt=user_prompt,
    )


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
    first_obj = stripped.find("{")
    first_arr = stripped.find("[")
    if first_obj == -1 and first_arr == -1:
        return stripped

    first_brace = min(p for p in (first_obj, first_arr) if p != -1)

    last_obj = stripped.rfind("}")
    last_arr = stripped.rfind("]")
    last_brace = max(p for p in (last_obj, last_arr) if p != -1)

    if last_brace > first_brace:
        return stripped[first_brace : last_brace + 1]

    return stripped


async def _call_openrouter(
    system_prompt: str,
    user_prompt: str,
    json_mode: bool = False,
) -> str:
    """Call LLM via unified llm_client (multi-key rotation + retry)."""
    return await llm_call(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        json_mode=json_mode,
        caller="ai_writer",
    )


# ---------------------------------------------------------------------------
# Mock implementations (kept for testing with USE_MOCK_API=True)
# ---------------------------------------------------------------------------

def _mock_outline(logline: str, style: str = "default") -> str:
    """Generate a mock outline with content dynamically derived from the logline.

    Uses keyword extraction and theme mapping to produce characters
    and plot that are contextually relevant to the user's story idea.
    """
    import re
    import hashlib

    # --- Keyword extraction (simple Chinese-aware) ---
    logline_lower = logline.lower()

    # Theme detection via keyword groups
    _THEMES = {
        "亲情": ["爸爸", "妈妈", "父亲", "母亲", "爷爷", "奶奶", "家人", "孩子", "儿子", "女儿", "家庭"],
        "校园": ["学校", "校园", "同学", "老师", "考试", "高中", "大学", "班级", "课堂"],
        "职场": ["公司", "老板", "程序员", "医生", "律师", "工程师", "职场", "办公室", "上班"],
        "冒险": ["探险", "冒险", "发现", "神秘", "宝藏", "旅行", "穿越", "异世界"],
        "科幻": ["机器人", "太空", "未来", "科技", "AI", "星球", "飞船", "时空"],
        "历史": ["古代", "朝代", "皇帝", "太医", "将军", "宫廷", "三国", "唐朝", "清朝"],
        "都市": ["城市", "都市", "街道", "咖啡", "地铁", "北京", "上海", "深圳"],
        "交通": ["火车", "列车", "高铁", "货运", "车站", "铁路", "飞机", "轮船", "汽车"],
        "美食": ["料理", "厨师", "美食", "餐厅", "烹饪", "食材", "味道"],
        "体育": ["足球", "篮球", "比赛", "运动", "训练", "冠军", "教练"],
    }

    detected_themes = []
    for theme, keywords in _THEMES.items():
        for kw in keywords:
            if kw in logline:
                detected_themes.append(theme)
                break

    # Extract specific nouns/entities from the logline for use in content
    # Use a simple approach: split by common Chinese particles and punctuation
    _PARTICLES = set("的了在是和与去到从把被也都还有个一不我你他她它们这那而且但")
    raw_tokens = re.findall(r'[\u4e00-\u9fff]+', logline)
    key_nouns = []
    for token in raw_tokens:
        cleaned = "".join(c for c in token if c not in _PARTICLES)
        if len(cleaned) >= 2:
            key_nouns.append(cleaned)
    # Deduplicate while preserving order
    seen = set()
    key_nouns = [n for n in key_nouns if n not in seen and not seen.add(n)]

    # --- Generate deterministic but varied content based on logline hash ---
    h = int(hashlib.md5(logline.encode()).hexdigest(), 16)

    # Character name pools by theme
    _NAMES_POOL = [
        ("小明", "小红", "老王"), ("天宇", "晓月", "赵叔"),
        ("阿杰", "小琳", "刘师傅"), ("子轩", "雨萱", "陈伯"),
        ("浩然", "思琪", "张大爷"), ("一凡", "诗涵", "周叔"),
    ]
    names = _NAMES_POOL[h % len(_NAMES_POOL)]

    # Determine setting from logline or themes
    setting_text = logline  # default: use the logline itself as setting basis

    # Build character descriptions relevant to the logline
    def _make_char_desc(role_idx: int) -> str:
        """Generate a character description relevant to the logline context."""
        # Role-specific templates that incorporate detected themes
        if "亲情" in detected_themes:
            roles = [
                (names[0], "10岁的小男孩", "好奇心旺盛，活泼好动", "喜欢问各种问题，对世界充满好奇"),
                (names[1], "35岁的父亲", "耐心温和，知识渊博", "总是用生动的方式给孩子讲解知识"),
                (names[2], "热心的工作人员", "爽朗健谈，经验丰富", "乐于分享自己的专业知识"),
            ]
        elif "校园" in detected_themes:
            roles = [
                (names[0], "17岁的高中生", "聪明但内向", "对学习有独特见解"),
                (names[1], "同班同学", "开朗外向，善于交际", "总能带动身边人的情绪"),
                (names[2], "班主任", "严格但关心学生", "有着不为人知的过去"),
            ]
        elif "历史" in detected_themes or "穿越" in logline:
            roles = [
                (names[0], "穿越者", "现代思维，适应力强", "携带现代知识来到古代"),
                (names[1], "古代当地人", "忠厚正直，武艺高强", "对穿越者的奇异行为感到好奇"),
                (names[2], "权贵势力代表", "老谋深算，城府极深", "对穿越者的能力虎视眈眈"),
            ]
        elif "交通" in detected_themes:
            roles = [
                (names[0], "小朋友", "充满好奇心，精力充沛", "对各种机械和车辆着迷"),
                (names[1], "陪伴的家长", "耐心细致，知识丰富", "享受与孩子一起探索的时光"),
                (names[2], "资深工作人员", "经验老到，热情开朗", "对自己的工作充满自豪"),
            ]
        elif "冒险" in detected_themes or "科幻" in detected_themes:
            roles = [
                (names[0], "年轻探索者", "勇敢果断，好奇心强", "天生对未知充满向往"),
                (names[1], "可靠的伙伴", "冷静理性，技术过硬", "在关键时刻总能提供帮助"),
                (names[2], "神秘的向导", "深不可测，亦正亦邪", "掌握着关键信息"),
            ]
        else:
            # Generic but still uses logline context
            roles = [
                (names[0], "故事主角", "性格鲜明，有成长弧线", f"与「{logline}」的核心主题有深刻联系"),
                (names[1], "重要配角", "性格互补，提供支持", "在故事中起到催化剂的作用"),
                (names[2], "关键角色", "立场复杂，动机多元", "推动故事走向转折"),
            ]
        return roles[role_idx] if role_idx < len(roles) else roles[-1]

    char_a = _make_char_desc(0)
    char_b = _make_char_desc(1)
    char_c = _make_char_desc(2)

    # Build world setting based on key nouns
    noun_str = "、".join(key_nouns[:5]) if key_nouns else logline
    world_setting = f"故事以「{logline}」为背景展开。\n{noun_str}构成了这个世界的核心元素，赋予故事独特的氛围和质感。"

    # Build plot that references the actual logline themes
    plot_seed = key_nouns[0] if key_nouns else "故事"
    plot_conflict = key_nouns[1] if len(key_nouns) > 1 else "意想不到的发现"

    return f"""# 故事大纲：{logline}

## 世界观设定
{world_setting}

## 主要角色
### {char_a[0]}
- **身份**：{char_a[1]}
- **性格**：{char_a[2]}
- **特点**：{char_a[3]}

### {char_b[0]}
- **身份**：{char_b[1]}
- **性格**：{char_b[2]}
- **特点**：{char_b[3]}

### {char_c[0]}
- **身份**：{char_c[1]}
- **性格**：{char_c[2]}
- **特点**：{char_c[3]}

## 故事主线

### 第一集：开端
{char_a[0]}在一个普通的日子里，因为「{logline}」而开启了一段特别的经历。
{char_b[0]}的出现让这段经历变得更加丰富多彩。

### 第二集：探索
随着对{plot_seed}的深入了解，{char_a[0]}发现了许多之前不曾注意到的细节。
{char_c[0]}带来了关于{plot_conflict}的新视角，让故事走向了意想不到的方向。

### 第三集：转折
一个围绕{plot_seed}的突发事件打破了平静，{char_a[0]}和{char_b[0]}必须面对新的挑战。
在这个过程中，他们不仅收获了成长，也加深了彼此之间的羁绊。

### 第四集：升华
经历了种种波折后，{char_a[0]}对「{logline}」有了全新的理解。
故事在温暖而充满希望的氛围中收束，留下了令人回味的余韵。
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


def _mock_extract_episodes(outline: str) -> list[dict]:
    """Mock episode extraction for testing."""
    return [
        {
            "episode_number": 1,
            "title": "相遇",
            "synopsis": "林小雨在学校图书馆中意外激活了一颗远古心灵之石，释放出强大的能量波动。陈风感知到波动赶来，两人初次相遇。",
        },
        {
            "episode_number": 2,
            "title": "危机",
            "synopsis": "一个神秘组织\"暗影会\"出现，他们企图收集心灵之石来控制整座城市。林小雨和陈风被卷入冲突。",
        },
        {
            "episode_number": 3,
            "title": "成长",
            "synopsis": "在逃亡与战斗中，两人学会了合作，并发现了心灵之石更深层的秘密。",
        },
    ]


def _mock_episode_script(episode_number: int, episode_title: str, episode_synopsis: str) -> str:
    """Mock episode script for testing."""
    return f"""# 第{episode_number}集：{episode_title}

## 场景 1
**地点：** 学校图书馆
**时间：** 黄昏
**氛围：** 暖黄色的光线，宁静的氛围。

**【画面】**
1. 远景：校园全景，夕阳西下。
2. 中景：图书馆内部，书架整齐排列。

**旁白：**
{episode_synopsis}

## 场景 2
**地点：** 校门口
**时间：** 日暮

**角色A：**
"我们必须找到答案。"

**角色B：**
"一起走吧。"

## 场景 3
**地点：** 神秘洞穴
**时间：** 夜晚

**角色A：**
"你看到了吗？那道光..."

**【音效】**
（远处传来回响声）
"""

