"""
上下文裁剪与构造服务（多角色版）。

核心原则：
- system = 当前角色 persona（原样，不改写）
- 历史消息格式化为"发言者：内容"，让模型知道谁说了什么
- 最后明确告知当前发言角色
- 不添加任何额外限制、安全规则、客服语气
"""
from typing import List, Dict, Optional
from ..config import settings
from ..models.conversation import Character, Message


def format_history(messages: List[Message], character_map: Dict[int, str]) -> str:
    """
    将消息列表格式化为带发言者的文本。
    character_map: {character_id: character_name}
    """
    lines = []
    for msg in messages:
        if msg.role == "user":
            speaker = "用户"
        elif msg.role == "assistant":
            speaker = character_map.get(msg.character_id, "AI") if msg.character_id else "AI"
        else:
            continue
        lines.append(f"{speaker}：{msg.content}")
    return "\n\n".join(lines)


def build_context(
    character: Character,
    history: List[Message],
    all_characters: List[Character],
    current_message: Optional[str] = None,
) -> List[Dict[str, str]]:
    """
    构造发送给 LLM 的 messages。

    system = 当前角色 persona（原样）
    user = 格式化的聊天室历史 + 当前发言提示

    不添加任何平台自定义规则。
    """
    character_map = {c.id: c.name for c in all_characters}

    # 裁剪历史：保留最近 N 条
    trimmed = history[-settings.MAX_CONTEXT_MESSAGES:] if settings.MAX_CONTEXT_MESSAGES > 0 else history

    history_text = format_history(trimmed, character_map)

    # 构造提示文本
    prompt_parts = []
    if history_text:
        prompt_parts.append(f"以下是当前聊天室历史：\n\n{history_text}")
    if current_message:
        if prompt_parts:
            prompt_parts.append(f"\n\n用户刚刚说：{current_message}")
        else:
            prompt_parts.append(f"用户说：{current_message}")
    prompt_parts.append(f"\n\n当前发言角色：{character.name}。请以该角色的身份自然回复。")

    user_content = "\n".join(prompt_parts)

    messages: List[Dict[str, str]] = [
        {"role": "system", "content": character.persona},
        {"role": "user", "content": user_content},
    ]
    return messages
