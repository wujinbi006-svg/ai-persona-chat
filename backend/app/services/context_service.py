"""
上下文裁剪与构造服务（多角色 + 记忆 + 场景 + 叙事 + Canonical Facts 版）。

核心原则：
- system = 当前角色 persona（原样，不改写）+ 极短叙事能力提示（不超过30字）
- Canonical Facts 注入：已确认事实 + 假设 + 冲突事实（事实与假设分离）
- 记忆注入：相关长期记忆（角色私有 + 共享）
- 场景注入：当前场景/时间/背景
- 历史消息格式化为"发言者：内容"
- 最后明确告知当前发言角色
- 不添加任何额外限制、安全规则、客服语气

上下文优先级：角色 Persona → Canonical Facts → 相关长期记忆 → 当前场景 → 最近聊天 → 当前用户消息
"""
from typing import List, Dict, Optional
from ..config import settings
from ..models.conversation import Character, Message, Conversation, Memory, Fact


# 极短的叙事能力提示（不超过30字，不改变人格，不增加限制）
NARRATIVE_HINT = "可自然加入动作、神态、环境描写。"


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


def format_scene(conversation: Optional[Conversation]) -> str:
    """格式化场景信息。"""
    if not conversation:
        return ""
    parts = []
    if conversation.scene:
        parts.append(f"地点：{conversation.scene}")
    if conversation.scene_time:
        parts.append(f"时间：{conversation.scene_time}")
    if conversation.scene_context:
        parts.append(f"背景：{conversation.scene_context}")
    return "\n".join(parts)


def format_memories(memories: List[Memory]) -> str:
    """格式化记忆列表。"""
    if not memories:
        return ""
    type_labels = {
        "user": "用户信息",
        "character": "角色信息",
        "relationship": "关系",
        "event": "事件",
        "preference": "偏好",
        "fact": "事实",
    }
    lines = []
    for mem in memories:
        label = type_labels.get(mem.memory_type, "记忆")
        lines.append(f"- [{label}] {mem.content}")
    return "\n".join(lines)


def format_facts(facts: List[Fact]) -> str:
    """格式化 Canonical Facts（规范事实）。

    事实与假设分离：
    - confirmed fact: 已确认的客观事实
    - hypothesis: 角色的推测，不能自动成为事实
    - conflicted: 存在冲突的事实
    - superseded: 已被新事实取代
    """
    if not facts:
        return ""

    confirmed = [f for f in facts if f.status == "confirmed" and f.fact_type == "fact"]
    hypotheses = [f for f in facts if f.fact_type == "hypothesis" and f.status in ("uncertain", "confirmed")]
    conflicted = [f for f in facts if f.status == "conflicted"]
    superseded = [f for f in facts if f.status == "superseded"]

    lines = []

    if confirmed:
        lines.append("【已确认事实】")
        for f in confirmed:
            subject = f"（{f.subject}）" if f.subject else ""
            lines.append(f"- {subject}{f.content}")

    if hypotheses:
        lines.append("\n【角色假设（未确认，仅供参考）】")
        for f in hypotheses:
            subject = f"（{f.subject}）" if f.subject else ""
            confidence = f" [置信度 {f.confidence}%]" if f.confidence else ""
            lines.append(f"- {subject}{f.content}{confidence}")

    if conflicted:
        lines.append("\n【存在冲突的事实】")
        for f in conflicted:
            subject = f"（{f.subject}）" if f.subject else ""
            lines.append(f"- {subject}{f.content}（注意：存在多个版本，需确认）")

    if superseded:
        # 只显示最近被取代的，避免上下文过长
        for f in superseded[:3]:
            subject = f"（{f.subject}）" if f.subject else ""
            lines.append(f"- [已更新] {subject}{f.content}")

    return "\n".join(lines) if lines else ""


def build_context(
    character: Character,
    history: List[Message],
    all_characters: List[Character],
    current_message: Optional[str] = None,
    conversation: Optional[Conversation] = None,
    memories: Optional[List[Memory]] = None,
    facts: Optional[List[Fact]] = None,
) -> List[Dict[str, str]]:
    """
    构造发送给 LLM 的 messages。

    system = 当前角色 persona（原样）+ 叙事提示
    user = Canonical Facts → 记忆 → 场景 → 格式化历史 → 当前发言提示

    上下文优先级：角色 Persona → Canonical Facts → 相关长期记忆 → 当前场景 → 最近聊天 → 当前用户消息

    不添加任何平台自定义规则。
    """
    character_map = {c.id: c.name for c in all_characters}

    # 裁剪历史：保留最近 N 条
    trimmed = history[-settings.MAX_CONTEXT_MESSAGES:] if settings.MAX_CONTEXT_MESSAGES > 0 else history

    history_text = format_history(trimmed, character_map)
    scene_text = format_scene(conversation)
    memories_text = format_memories(memories) if memories else ""
    facts_text = format_facts(facts) if facts else ""

    # 构造提示文本（按优先级：Canonical Facts → 记忆 → 场景 → 历史 → 当前消息）
    prompt_parts = []

    if facts_text:
        prompt_parts.append(facts_text)

    if memories_text:
        prompt_parts.append(f"【相关记忆】\n{memories_text}")

    if scene_text:
        prompt_parts.append(f"【当前场景】\n{scene_text}")

    if history_text:
        prompt_parts.append(f"【聊天室历史】\n{history_text}")

    if current_message:
        if prompt_parts:
            prompt_parts.append(f"\n用户刚刚说：{current_message}")
        else:
            prompt_parts.append(f"用户说：{current_message}")

    prompt_parts.append(f"\n当前发言角色：{character.name}。请以该角色的身份自然回复。")

    user_content = "\n".join(prompt_parts)

    # system = persona（原样）+ 极短叙事提示
    system_content = character.persona
    if system_content and not system_content.endswith("\n"):
        system_content += "\n"
    system_content += NARRATIVE_HINT

    messages: List[Dict[str, str]] = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_content},
    ]
    return messages
