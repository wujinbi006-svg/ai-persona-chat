"""
智能发言路由服务。

根据用户当前消息 + 最近上下文 + 角色列表，判断谁最适合回答。
Router 只判断"谁应该说话"，真正回答仍然使用目标角色自己的 persona。
"""
import json
import re
from typing import List, Optional, Dict
from sqlalchemy.orm import Session

from ..models.conversation import Character, Message
from ..services.llm_client import chat_stream, LLMError


def _format_history_for_router(messages: List[Message], char_map: Dict[int, str]) -> str:
    """格式化最近历史供路由判断。"""
    lines = []
    for msg in messages[-10:]:
        if msg.role == "user":
            speaker = "用户"
        elif msg.role == "assistant":
            speaker = char_map.get(msg.character_id, "AI") if msg.character_id else "AI"
        else:
            continue
        content = msg.content[:150] if msg.content else ""
        lines.append(f"{speaker}：{content}")
    return "\n".join(lines)


def _keyword_match_route(message: str, characters: List[Character]) -> Optional[int]:
    """
    简单关键词匹配：如果消息中明确提到某个角色名字，直接路由到该角色。
    这是 Router 失败时的快速回退，也能减少 LLM 调用。
    """
    msg_lower = message.lower()
    for char in characters:
        if char.name and char.name.lower() in msg_lower:
            return char.id
    return None


async def route_speaker(
    db: Session,
    conversation_id: int,
    user_id: str,
    message: str,
    characters: List[Character],
    history: Optional[List[Message]] = None,
) -> List[int]:
    """
    智能路由：判断谁应该回复。

    返回 character_id 列表（可能多个角色都适合）。
    如果 Router 失败，回退到第一个角色。

    策略：
    1. 先尝试关键词匹配（零成本）
    2. 再用 LLM 做语义判断
    3. 失败回退到第一个角色
    """
    if not characters:
        return []

    # 1. 关键词快速匹配
    keyword_match = _keyword_match_route(message, characters)
    if keyword_match:
        return [keyword_match]

    # 只有一个角色时直接返回
    if len(characters) == 1:
        return [characters[0].id]

    # 2. LLM 语义路由
    char_map = {c.id: c.name for c in characters}
    char_list_text = "\n".join([
        f"{c.id}. {c.name}：{c.persona[:100]}" for c in characters
    ])

    if history is None:
        history = db.query(Message).filter(
            Message.conversation_id == conversation_id,
            Message.user_id == user_id,
        ).order_by(Message.id).all()

    history_text = _format_history_for_router(history, char_map)

    router_prompt = f"""根据以下信息，判断哪个角色最适合回复用户的最新消息。

角色列表：
{char_list_text}

对话历史：
{history_text}

用户最新消息：{message}

请只回复最适合的角色编号（一个数字），不要解释。如果多个角色都适合，按优先级用逗号分隔编号。
回复格式：数字 或 数字,数字"""

    messages_for_llm = [
        {"role": "system", "content": "你是一个对话路由助手，只负责判断哪个角色最适合回复。"},
        {"role": "user", "content": router_prompt},
    ]

    try:
        full_response = ""
        async for chunk in chat_stream(messages_for_llm):
            full_response += chunk

        # 解析回复中的数字
        numbers = re.findall(r'\d+', full_response.strip())
        if numbers:
            valid_ids = []
            for num_str in numbers:
                cid = int(num_str)
                if cid in char_map:
                    valid_ids.append(cid)
            if valid_ids:
                # 去重并保持顺序
                seen = set()
                result = []
                for cid in valid_ids:
                    if cid not in seen:
                        seen.add(cid)
                        result.append(cid)
                return result[:3]  # 最多3个角色

    except LLMError:
        pass
    except Exception:
        pass

    # 3. 回退到第一个角色
    return [characters[0].id]
