"""
图片生成服务（豆包视觉 / 火山方舟）。

职责：
1. 检测用户消息中的图片请求意图（关键词匹配）
2. 基于角色人格 + 对话上下文构建图片生成 Prompt
3. 调用火山方舟图片生成 API
4. 下载图片到本地，返回可访问的 URL

不做内容审查、不过滤、不限制。
"""
import os
import re
import uuid
import httpx
from pathlib import Path
from typing import List, Optional
from datetime import datetime

from ..config import settings
from ..models.conversation import Character, Message


# ===== 图片请求关键词检测 =====

IMAGE_REQUEST_KEYWORDS = [
    "照片", "图片", "发图", "发张图", "拍一张", "拍张", "拍个照",
    "看看你", "长什么样", "长啥样", "自拍", "自拍照", "全身照",
    "半身照", "正面照", "侧面照", "背影", "照片给我", "图片给我",
    "画你", "画一张", "生成图片", "生成照片", "你的样子", "你的照片",
    "你的图片", "照张相", "照一张", "露个脸", "露脸", "颜值",
    "穿什么", "穿的什么", "现在在哪", "在干嘛", "在做什么",
]


def detect_image_request(message: str) -> bool:
    """
    检测用户消息是否包含明确的图片请求意图。
    只有明确要求才触发，普通对话不生成图片。
    """
    if not message:
        return False
    msg_lower = message.lower()
    for kw in IMAGE_REQUEST_KEYWORDS:
        if kw in msg_lower:
            return True
    return False


# ===== 图片 Prompt 构建 =====

def _extract_appearance_from_persona(persona: str) -> str:
    """
    从角色人格描述中提取外貌相关信息。
    简单策略：查找包含外貌关键词的句子。
    """
    appearance_keywords = [
        "头发", "发型", "发色", "眼睛", "肤色", "身高", "身材", "穿着",
        "服装", "衣服", "裙子", "裤子", "衬衫", "外套", "鞋子", "饰品",
        "项链", "耳环", "眼镜", "帽子", "围巾", "手套", "纹身", "疤痕",
        "年龄", "长相", "外貌", "面容", "五官", "气质", "颜值", "美丽",
        "帅气", "可爱", "性感", "优雅", "阳光", "冷酷", "温柔",
        "hair", "eye", "skin", "wear", "dress", "height", "build",
        "appearance", "face", "look",
    ]
    sentences = re.split(r'[。！？\n.!?]', persona)
    appearance_parts = []
    for s in sentences:
        s = s.strip()
        if not s:
            continue
        for kw in appearance_keywords:
            if kw in s.lower():
                appearance_parts.append(s)
                break
    return "；".join(appearance_parts) if appearance_parts else persona[:200]


def _extract_scene_from_history(history: List[Message], character_id: int) -> str:
    """
    从最近对话历史中提取场景/动作/情绪信息。
    """
    recent = history[-6:] if len(history) > 6 else history
    scene_parts = []
    for msg in recent:
        if msg.role == "assistant" and msg.character_id == character_id:
            content = msg.content.strip()
            if content:
                # 取角色最近发言的前100字作为场景参考
                scene_parts.append(content[:100])
        elif msg.role == "user":
            content = msg.content.strip()
            if content and not detect_image_request(content):
                scene_parts.append(f"用户说：{content[:80]}")
    return "；".join(scene_parts[-3:]) if scene_parts else ""


def build_image_prompt(
    character: Character,
    history: List[Message],
    user_message: str,
) -> str:
    """
    构建图片生成 Prompt。

    综合参考：
    - 角色外貌设定（从 persona 提取）
    - 当前对话场景（最近历史）
    - 用户的具体请求（自拍、全身照等）
    - 当前时间（白天/夜晚）

    输出英文 Prompt（图片模型对英文理解更好），附中文描述辅助。
    """
    appearance = _extract_appearance_from_persona(character.persona)
    scene = _extract_scene_from_history(history, character.id)

    # 判断用户请求的图片类型
    photo_type = "a natural candid photo"
    if any(w in user_message for w in ["自拍", "自拍照"]):
        photo_type = "a selfie photo taken from arm's length"
    elif any(w in user_message for w in ["全身", "全身照"]):
        photo_type = "a full-body photo"
    elif any(w in user_message for w in ["半身", "上半身"]):
        photo_type = "a half-body portrait photo"
    elif any(w in user_message for w in ["正面", "正面照"]):
        photo_type = "a front-facing portrait photo"
    elif any(w in user_message for w in ["侧面", "侧面照"]):
        photo_type = "a side profile photo"
    elif any(w in user_message for w in ["背影", "背面"]):
        photo_type = "a back view photo"

    # 当前时间
    hour = datetime.now().hour
    if 6 <= hour < 12:
        time_desc = "morning, soft natural light"
    elif 12 <= hour < 18:
        time_desc = "afternoon, bright daylight"
    elif 18 <= hour < 22:
        time_desc = "evening, warm ambient lighting"
    else:
        time_desc = "night, dim atmospheric lighting"

    # 构建英文 Prompt
    prompt_parts = [
        f"{photo_type} of {character.name},",
        f"Character appearance: {appearance}",
    ]
    if scene:
        prompt_parts.append(f"Scene context: {scene}")
    prompt_parts.append(f"Time: {time_desc}")
    prompt_parts.append("High quality, detailed, realistic, photorealistic, 8k resolution")
    prompt_parts.append(f"The person in the photo is {character.name}, maintaining consistent appearance")

    full_prompt = "\n".join(prompt_parts)

    # 限制长度，避免超出模型限制
    if len(full_prompt) > 2000:
        full_prompt = full_prompt[:2000]

    return full_prompt


# ===== 图片生成 API 调用 =====

class ImageGenerationError(Exception):
    """图片生成异常，携带用户可读消息。"""
    def __init__(self, message: str, status_code: int = 500):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def _get_image_output_dir() -> Path:
    """获取图片输出目录，不存在则创建。"""
    output_dir = Path(settings.IMAGE_OUTPUT_DIR)
    if not output_dir.is_absolute():
        output_dir = Path(__file__).resolve().parent.parent.parent / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


async def _download_image(url: str, output_dir: Path) -> str:
    """
    从 URL 下载图片到本地，返回文件名。
    """
    filename = f"{uuid.uuid4().hex}.png"
    filepath = output_dir / filename

    async with httpx.AsyncClient(timeout=settings.IMAGE_TIMEOUT, follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        filepath.write_bytes(resp.content)

    return filename


async def generate_image(prompt: str) -> str:
    """
    调用火山方舟图片生成 API，生成图片并保存到本地。

    返回图片的相对访问路径，如 "/static/images/xxx.png"。
    前端通过后端静态文件服务访问。

    异常：ImageGenerationError
    """
    if not settings.DOUBAO_VISION_API_KEY:
        raise ImageGenerationError("未配置 DOUBAO_VISION_API_KEY，图片生成功能暂不可用。", 500)
    if not settings.DOUBAO_VISION_MODEL:
        raise ImageGenerationError("未配置 DOUBAO_VISION_MODEL（火山方舟推理接入点 ID），图片生成功能暂不可用。", 500)

    api_url = f"{settings.DOUBAO_VISION_BASE_URL.rstrip('/')}/images/generations"
    headers = {
        "Authorization": f"Bearer {settings.DOUBAO_VISION_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.DOUBAO_VISION_MODEL,
        "prompt": prompt,
        "size": "1024x1024",
        "n": 1,
        "response_format": "url",
    }

    try:
        async with httpx.AsyncClient(timeout=settings.IMAGE_TIMEOUT) as client:
            resp = await client.post(api_url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
    except httpx.TimeoutException:
        raise ImageGenerationError("图片生成超时，请稍后重试。", 504)
    except httpx.HTTPStatusError as e:
        status = e.response.status_code
        detail = ""
        try:
            err_body = e.response.json()
            detail = err_body.get("error", {}).get("message", str(err_body))
        except Exception:
            detail = e.response.text[:200]
        if status == 401:
            raise ImageGenerationError("图片生成 API Key 无效，请检查 DOUBAO_VISION_API_KEY 配置。", 401)
        if status == 403:
            raise ImageGenerationError("图片生成 API 访问被拒绝（403），请检查接入点权限。", 403)
        if status == 429:
            raise ImageGenerationError("图片生成请求频率过高，请稍后再试。", 429)
        raise ImageGenerationError(f"图片生成失败（{status}）：{detail[:200]}", status)
    except Exception as e:
        raise ImageGenerationError(f"图片生成网络错误：{str(e)[:200]}", 502)

    # 解析返回结果
    try:
        image_data = data.get("data", [])
        if not image_data:
            raise ImageGenerationError("图片生成 API 未返回图片数据。", 500)
        image_url = image_data[0].get("url") or image_data[0].get("b64_json")
        if not image_url:
            raise ImageGenerationError("图片生成 API 返回数据中没有图片 URL。", 500)
    except ImageGenerationError:
        raise
    except Exception as e:
        raise ImageGenerationError(f"解析图片生成结果失败：{str(e)[:200]}", 500)

    # 处理 base64 格式
    if image_url.startswith("data:image") or len(image_url) > 1000 and not image_url.startswith("http"):
        # base64 内嵌图片
        import base64
        output_dir = _get_image_output_dir()
        filename = f"{uuid.uuid4().hex}.png"
        filepath = output_dir / filename
        b64_data = image_url.split(",")[-1] if "," in image_url else image_url
        filepath.write_bytes(base64.b64decode(b64_data))
        return f"/static/images/{filename}"

    # URL 格式：下载到本地
    output_dir = _get_image_output_dir()
    try:
        filename = await _download_image(image_url, output_dir)
    except Exception as e:
        raise ImageGenerationError(f"下载生成的图片失败：{str(e)[:200]}", 502)

    return f"/static/images/{filename}"
