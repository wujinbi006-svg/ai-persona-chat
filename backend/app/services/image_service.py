"""
图片生成服务（GK Image 2.0 / 小羽毛AI聚合平台）。

职责：
1. 检测用户消息中的图片请求意图（关键词匹配）
2. 基于角色人格 + 对话上下文构建图片生成 Prompt
3. 调用 GK Image 2.0 异步任务 API（创建任务 → 轮询 → 获取结果）
4. 下载图片到本地，返回可访问的 URL

不做内容审查、不过滤、不限制。

Legacy: 旧的火山方舟/豆包视觉实现保留在 _generate_image_doubao_legacy() 中作为回滚备用。
"""
import os
import re
import uuid
import asyncio
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

def _extract_appearance_keywords(persona: str) -> str:
    """
    从角色人格描述中提取纯外貌关键词，只保留外貌相关，过滤人格/性格/关系。
    返回英文关键词列表形式的描述。
    """
    appearance_map = {
        "长发": "long hair", "短发": "short hair", "卷发": "curly hair",
        "直发": "straight hair", "双马尾": "twin tails", "马尾": "ponytail",
        "刘海": "bangs", "黑发": "black hair", "金发": "blonde hair",
        "棕发": "brown hair", "红发": "red hair", "白发": "silver hair",
        "蓝发": "blue hair", "粉发": "pink hair", "紫发": "purple hair",
        "大眼睛": "big eyes", "蓝眼睛": "blue eyes", "绿眼睛": "green eyes",
        "棕眼睛": "brown eyes", "黑眼睛": "dark eyes", "皮肤白": "fair skin",
        "白皙": "fair skin", "小麦色": "tan skin", "高": "tall", "矮": "short",
        "苗条": "slim", "瘦": "slim", "丰满": "curvy", "运动型": "athletic build",
        "肌肉": "muscular", "裙子": "wearing a dress", "连衣裙": "wearing a dress",
        "校服": "wearing school uniform", "制服": "wearing uniform",
        "西装": "wearing a suit", "衬衫": "wearing a shirt", "T恤": "wearing a t-shirt",
        "毛衣": "wearing a sweater", "外套": "wearing a jacket", "牛仔裤": "wearing jeans",
        "眼镜": "wearing glasses", "耳环": "wearing earrings", "项链": "wearing necklace",
        "帽子": "wearing a hat", "围巾": "wearing a scarf", "年轻": "young",
        "少女": "young girl", "少年": "young boy", "女性": "young woman",
        "男性": "young man", "女孩": "young girl", "男孩": "young boy",
        "女人": "woman", "男人": "man", "美丽": "beautiful", "漂亮": "beautiful",
        "可爱": "cute", "帅气": "handsome", "优雅": "elegant", "阳光": "cheerful looking",
        "温柔": "gentle expression", "冷酷": "cool expression", "微笑": "smiling",
        "笑容": "smiling",
    }

    found = []
    for cn_keyword, en_desc in appearance_map.items():
        if cn_keyword in persona:
            if en_desc not in found:
                found.append(en_desc)

    if not found:
        if any(w in persona for w in ["女", "她", "女孩", "女生", "少女"]):
            found.append("young woman")
        elif any(w in persona for w in ["男", "他", "男孩", "男生", "少年"]):
            found.append("young man")
        else:
            found.append("young person")
        found.append("natural appearance")

    return ", ".join(found[:15])


def build_image_prompt(
    character: Character,
    history: List[Message],
    user_message: str,
) -> str:
    """
    构建安全的图片生成 Prompt。
    只包含：照片类型、角色名、纯外貌关键词、时间光线、质量描述。
    不包含：角色人格/性格描述、对话历史内容、任何可能触发审核的敏感内容。
    """
    appearance = _extract_appearance_keywords(character.persona)

    photo_type = "a natural candid portrait photo"
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

    hour = datetime.now().hour
    if 6 <= hour < 12:
        time_desc = "morning soft natural light"
    elif 12 <= hour < 18:
        time_desc = "afternoon bright daylight"
    elif 18 <= hour < 22:
        time_desc = "evening warm ambient lighting"
    else:
        time_desc = "night dim atmospheric lighting"

    prompt_parts = [
        f"{photo_type} of {character.name},",
        f"appearance: {appearance},",
        f"lighting: {time_desc},",
        "high quality, detailed, realistic, photorealistic, sharp focus, professional photography",
    ]

    full_prompt = " ".join(prompt_parts)
    if len(full_prompt) > 1000:
        full_prompt = full_prompt[:1000]

    return full_prompt


def build_fallback_image_prompt(character: Character) -> str:
    """
    最简降级 Prompt：当正常 prompt 触发审核时使用。
    """
    if any(w in character.persona for w in ["女", "她", "女孩", "女生", "少女"]):
        gender = "young woman"
    elif any(w in character.persona for w in ["男", "他", "男孩", "男生", "少年"]):
        gender = "young man"
    else:
        gender = "person"

    return (
        f"a natural portrait photo of a {gender} named {character.name}, "
        f"high quality, realistic, photorealistic, professional photography, "
        f"soft natural lighting, sharp focus"
    )


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
    """从 URL 下载图片到本地，返回文件名。"""
    filename = f"{uuid.uuid4().hex}.png"
    filepath = output_dir / filename

    async with httpx.AsyncClient(timeout=settings.IMAGE_TIMEOUT, follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        filepath.write_bytes(resp.content)

    return filename


# ===== GK Image 2.0 异步任务模式（当前使用）=====

async def _gk_create_task(client: httpx.AsyncClient, prompt: str) -> str:
    """
    创建 GK Image 2.0 图片生成任务，返回 task_id。
    """
    api_url = f"{settings.IMAGE_API_BASE_URL.rstrip('/')}/v1/media/generate"
    headers = {
        "Authorization": f"Bearer {settings.IMAGE_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.IMAGE_MODEL,
        "prompt": prompt,
        "params": {
            "aspect_ratio": "1:1",
            "resolution": "1k",
        },
    }
    resp = await client.post(api_url, headers=headers, json=payload)
    resp.raise_for_status()
    data = resp.json()

    if data.get("code") != 200:
        raise ImageGenerationError(f"创建图片任务失败：{data.get('msg', '未知错误')}", 502)

    task_id = data.get("data", {}).get("task_id")
    if not task_id:
        raise ImageGenerationError("创建图片任务失败：未返回 task_id", 502)

    return str(task_id)


async def _gk_poll_task(client: httpx.AsyncClient, task_id: str, timeout: float = 180.0) -> str:
    """
    轮询 GK Image 2.0 任务状态，直到完成，返回 result_url。
    轮询间隔 4 秒，超时时间默认 180 秒（3分钟）。
    """
    api_url = f"{settings.IMAGE_API_BASE_URL.rstrip('/')}/v1/media/status"
    headers = {
        "Authorization": f"Bearer {settings.IMAGE_API_KEY}",
        "Accept": "application/json",
    }

    start_time = asyncio.get_event_loop().time()
    poll_interval = 4.0  # 4秒轮询一次

    while True:
        elapsed = asyncio.get_event_loop().time() - start_time
        if elapsed > timeout:
            raise ImageGenerationError(f"图片生成超时（{timeout:.0f}秒），任务ID: {task_id}", 504)

        resp = await client.get(api_url, headers=headers, params={"task_id": task_id})
        resp.raise_for_status()
        data = resp.json()

        is_final = data.get("is_final", False)
        state = data.get("state", "")
        progress = data.get("progress", "")
        error = data.get("error", "")

        if is_final:
            if state == "success":
                result_url = data.get("result_url", "")
                if not result_url:
                    raise ImageGenerationError("图片生成完成但未返回 result_url", 502)
                return result_url
            elif state == "failed":
                raise ImageGenerationError(f"图片生成失败：{error or '未知错误'}（任务ID: {task_id}）", 502)
            else:
                raise ImageGenerationError(f"图片生成异常状态：{state}（任务ID: {task_id}）", 502)

        # 未完成，等待后继续轮询
        await asyncio.sleep(poll_interval)


async def generate_image(prompt: str, fallback_prompt: str = None) -> str:
    """
    调用 GK Image 2.0 图片生成 API（异步任务模式），生成图片并保存到本地。

    流程：POST 创建任务 → 轮询状态 → 获取 result_url → 下载到本地

    返回图片的相对访问路径，如 "/static/images/xxx.png"。
    前端通过后端静态文件服务访问。

    支持降级重试：当创建任务或生成失败时，自动用 fallback_prompt 重试一次。

    异常：ImageGenerationError
    """
    if not settings.IMAGE_API_KEY:
        raise ImageGenerationError("未配置 IMAGE_API_KEY（小羽毛AI聚合平台），图片生成功能暂不可用。", 500)

    async def _call_gk(current_prompt: str) -> str:
        """调用 GK Image 2.0 完整流程，返回本地图片路径或远程URL。"""
        async with httpx.AsyncClient(timeout=settings.IMAGE_TIMEOUT) as client:
            # 1. 创建任务
            task_id = await _gk_create_task(client, current_prompt)
            # 2. 轮询状态
            result_url = await _gk_poll_task(client, task_id, timeout=settings.IMAGE_TIMEOUT)
            # 3. 尝试下载到本地，失败则直接返回远程URL
            try:
                output_dir = _get_image_output_dir()
                filename = await _download_image(result_url, output_dir)
                return f"/static/images/{filename}"
            except Exception:
                return result_url

    try:
        return await _call_gk(prompt)
    except ImageGenerationError as e:
        # 如果有 fallback_prompt 且不是超时，自动降级重试一次
        if fallback_prompt and fallback_prompt != prompt and e.status_code != 504:
            try:
                return await _call_gk(fallback_prompt)
            except Exception:
                raise e
        raise
    except httpx.TimeoutException:
        raise ImageGenerationError("图片生成超时，请稍后重试。", 504)
    except httpx.HTTPStatusError as e:
        status = e.response.status_code
        detail = ""
        try:
            err_body = e.response.json()
            detail = err_body.get("msg", str(err_body))
        except Exception:
            detail = e.response.text[:200]
        if status == 401:
            raise ImageGenerationError("图片生成 API Key 无效，请检查 IMAGE_API_KEY 配置。", 401)
        if status == 403:
            raise ImageGenerationError("图片生成 API 访问被拒绝（403）。", 403)
        if status == 429:
            raise ImageGenerationError("图片生成请求频率过高，请稍后再试。", 429)
        raise ImageGenerationError(f"图片生成失败（{status}）：{detail[:200]}", status)
    except Exception as e:
        raise ImageGenerationError(f"图片生成网络错误：{str(e)[:200]}", 502)


# ===== Legacy: 火山方舟/豆包视觉实现（保留作为回滚备用）=====

async def _generate_image_doubao_legacy(prompt: str, fallback_prompt: str = None) -> str:
    """
    [LEGACY] 旧的火山方舟/豆包视觉图片生成实现。
    保留作为回滚备用，当前不使用。如需回滚，将 generate_image 重命名为 _generate_image_gk，
    然后将此函数重命名为 generate_image。
    """
    if not settings.DOUBAO_VISION_API_KEY:
        raise ImageGenerationError("未配置 DOUBAO_VISION_API_KEY，图片生成功能暂不可用。", 500)
    if not settings.DOUBAO_VISION_MODEL:
        raise ImageGenerationError("未配置 DOUBAO_VISION_MODEL，图片生成功能暂不可用。", 500)

    api_url = f"{settings.DOUBAO_VISION_BASE_URL.rstrip('/')}/images/generations"
    headers = {
        "Authorization": f"Bearer {settings.DOUBAO_VISION_API_KEY}",
        "Content-Type": "application/json",
    }

    async def _call_api(current_prompt: str):
        payload = {
            "model": settings.DOUBAO_VISION_MODEL,
            "prompt": current_prompt,
            "size": "1024x1024",
            "n": 1,
            "response_format": "url",
        }
        async with httpx.AsyncClient(timeout=settings.IMAGE_TIMEOUT) as client:
            resp = await client.post(api_url, headers=headers, json=payload)
            resp.raise_for_status()
            return resp.json()

    data = None
    try:
        data = await _call_api(prompt)
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
        if status == 400 and fallback_prompt and fallback_prompt != prompt:
            try:
                data = await _call_api(fallback_prompt)
            except Exception:
                raise ImageGenerationError(f"图片生成失败（{status}）：{detail[:200]}", status)
        else:
            if status == 401:
                raise ImageGenerationError("图片生成 API Key 无效，请检查 DOUBAO_VISION_API_KEY 配置。", 401)
            if status == 403:
                raise ImageGenerationError("图片生成 API 访问被拒绝（403），请检查接入点权限。", 403)
            if status == 429:
                raise ImageGenerationError("图片生成请求频率过高，请稍后再试。", 429)
            raise ImageGenerationError(f"图片生成失败（{status}）：{detail[:200]}", status)
    except Exception as e:
        raise ImageGenerationError(f"图片生成网络错误：{str(e)[:200]}", 502)

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

    if image_url.startswith("data:image") or len(image_url) > 1000 and not image_url.startswith("http"):
        import base64
        output_dir = _get_image_output_dir()
        filename = f"{uuid.uuid4().hex}.png"
        filepath = output_dir / filename
        b64_data = image_url.split(",")[-1] if "," in image_url else image_url
        filepath.write_bytes(base64.b64decode(b64_data))
        return f"/static/images/{filename}"

    output_dir = _get_image_output_dir()
    try:
        filename = await _download_image(image_url, output_dir)
    except Exception as e:
        raise ImageGenerationError(f"下载生成的图片失败：{str(e)[:200]}", 502)

    return f"/static/images/{filename}"
