"""
LLM 客户端封装。
性能优化 Phase2: 应用生命周期共享 AsyncOpenAI + httpx 连接池 + keep-alive
消除每次请求 ~400ms DNS+TLS+connection 建立开销
"""
from typing import List, Dict, AsyncGenerator, Optional, TYPE_CHECKING
from openai import AsyncOpenAI
from ..config import settings

if TYPE_CHECKING:
    from .trace import RequestTrace


class LLMError(Exception):
    def __init__(self, message: str, status_code: int = 500):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


# 共享客户端 + 连接池（应用生命周期单例）
_shared_client: Optional[AsyncOpenAI] = None


def _get_shared_client() -> AsyncOpenAI:
    global _shared_client
    if _shared_client is None:
        if not settings.OPENAI_API_KEY:
            raise LLMError("未配置 OPENAI_API_KEY", 500)
        if not settings.OPENAI_MODEL:
            raise LLMError("未配置 OPENAI_MODEL", 500)
        kwargs = {
            "api_key": settings.OPENAI_API_KEY,
            "timeout": settings.LLM_TIMEOUT,
        }
        if settings.OPENAI_BASE_URL:
            kwargs["base_url"] = settings.OPENAI_BASE_URL
        _shared_client = AsyncOpenAI(**kwargs)
    return _shared_client


async def close_shared_client():
    global _shared_client
    if _shared_client:
        await _shared_client.close()
        _shared_client = None


def _get_client() -> AsyncOpenAI:
    return _get_shared_client()


async def chat_stream(
    messages: List[Dict[str, str]],
    trace: Optional["RequestTrace"] = None,
) -> AsyncGenerator[str, None]:
    if trace:
        trace.mark("t10_llm_request_sent")
        trace.mark_speaker_point("llm_request_sent")
        trace.increment_llm_request()

    client = _get_shared_client()
    try:
        stream = await client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=messages,
            stream=True,
            temperature=0.7,
        )
        if trace:
            trace.mark("t11_llm_connection")
            trace.mark_speaker_point("llm_connection")
        if trace:
            trace.mark("t12_llm_streaming_start")
            trace.mark_speaker_point("llm_streaming_start")

        first_token = False
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                content = chunk.choices[0].delta.content
                if not first_token and trace:
                    first_token = True
                    trace.mark("t13_first_token_backend")
                    trace.mark_speaker_point("first_token_backend")
                yield content
    except Exception as e:
        msg = str(e)
        if "401" in msg or "authentication" in msg.lower() or "invalid api key" in msg.lower():
            raise LLMError("API Key invalid", 401)
        if "403" in msg or "forbidden" in msg.lower():
            raise LLMError("API access denied (403)", 403)
        if "429" in msg or "rate limit" in msg.lower():
            raise LLMError("Rate limit exceeded", 429)
        if "404" in msg or "model not found" in msg.lower():
            raise LLMError("Model not found or base URL error", 404)
        if "502" in msg:
            raise LLMError("API temporarily unavailable (502)", 502)
        if "503" in msg:
            raise LLMError("API temporarily unavailable (503)", 503)
        if "timeout" in msg.lower():
            raise LLMError("API request timeout", 504)
        if "connection" in msg.lower() or "network" in msg.lower():
            raise LLMError("Network connection failed", 502)
        raise LLMError(f"LLM call failed: {msg[:200]}", 500)
    # 注意：不关闭共享客户端！连接池在应用生命周期内保持复用。
    # stream 对象在异步迭代完成后由 OpenAI SDK 自动清理。
