"""
LLM 客户端封装。
只负责调用 OpenAI-compatible Chat Completions API。
人格文本原样作为 system message 传入，不做任何改写。
"""
from typing import List, Dict, AsyncGenerator, Optional
from openai import AsyncOpenAI
from ..config import settings


class LLMError(Exception):
    """统一的 LLM 调用异常，携带用户可读消息。"""
    def __init__(self, message: str, status_code: int = 500):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def _get_client() -> AsyncOpenAI:
    if not settings.OPENAI_API_KEY:
        raise LLMError("未配置 OPENAI_API_KEY，请在项目根目录 .env 中填写。", 500)
    if not settings.OPENAI_MODEL:
        raise LLMError("未配置 OPENAI_MODEL，请在项目根目录 .env 中填写。", 500)

    kwargs = {
        "api_key": settings.OPENAI_API_KEY,
        "timeout": settings.LLM_TIMEOUT,
    }
    if settings.OPENAI_BASE_URL:
        kwargs["base_url"] = settings.OPENAI_BASE_URL
    return AsyncOpenAI(**kwargs)


async def chat_stream(messages: List[Dict[str, str]]) -> AsyncGenerator[str, None]:
    """
    流式调用，逐块 yield 文本内容。
    messages 结构：[{"role": "system"/"user"/"assistant", "content": "..."}]
    """
    client = _get_client()
    try:
        stream = await client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=messages,
            stream=True,
            temperature=0.7,
        )
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
    except Exception as e:
        # 统一转换为用户可读错误
        msg = str(e)
        if "401" in msg or "authentication" in msg.lower() or "invalid api key" in msg.lower():
            raise LLMError("API Key 无效，请检查配置。", 401)
        if "403" in msg or "forbidden" in msg.lower():
            raise LLMError("API 访问被拒绝（403），请检查权限或账户状态。", 403)
        if "429" in msg or "rate limit" in msg.lower():
            raise LLMError("API 请求频率过高，请稍后再试。", 429)
        if "404" in msg or "model not found" in msg.lower():
            raise LLMError("模型不存在或 Base URL 错误，请检查 OPENAI_MODEL 和 OPENAI_BASE_URL。", 404)
        if "502" in msg:
            raise LLMError("API 服务暂时不可用（502），请稍后重试。", 502)
        if "503" in msg:
            raise LLMError("API 服务暂时不可用（503），请稍后重试。", 503)
        if "timeout" in msg.lower():
            raise LLMError("API 请求超时，请检查网络或稍后重试。", 504)
        if "connection" in msg.lower() or "network" in msg.lower():
            raise LLMError("网络连接失败，请检查网络状态。", 502)
        raise LLMError(f"AI 服务调用失败：{msg[:200]}", 500)
    finally:
        await client.close()
