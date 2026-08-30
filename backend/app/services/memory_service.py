"""
长期记忆服务。

职责：
1. 记忆 CRUD（用户可手动管理）
2. 自动提取：每N条消息批量提取，不保存无意义内容
3. 记忆检索：基于角色+关键词+重要性，注入相关记忆
4. 角色私有记忆隔离

不做内容审查、不过滤。
"""
import re
import json
from datetime import datetime
from typing import List, Optional, Dict
from sqlalchemy.orm import Session
from sqlalchemy import or_

from ..models.conversation import Memory, Character, Message
from ..config import settings

# 每N条用户消息触发一次记忆提取
MEMORY_EXTRACT_INTERVAL = 5

# 无意义内容过滤（不保存这些）
MEANINGLESS_PATTERNS = [
    r'^[哈哈嗯哦啊呀哇嘿嘻呵]+$',
    r'^(好的|好|行|可以|嗯|哦|啊|呀|哈哈|嗯嗯|哦哦)$',
    r'^[\s\W]+$',
]

# 记忆类型关键词映射
TYPE_KEYWORDS = {
    "preference": ["喜欢", "讨厌", "偏好", "爱", "不爱", "想要", "不想要", "习惯", "口味"],
    "event": ["发生了", "昨天", "今天", "刚才", "之前", "后来", "然后", "经历", "事情"],
    "fact": ["是", "叫", "住在", "工作", "年龄", "身高", "体重", "职业", "身份"],
    "relationship": ["朋友", "恋人", "家人", "爸爸", "妈妈", "哥哥", "姐姐", "弟弟", "妹妹", "关系"],
}


def is_meaningless(text: str) -> bool:
    """判断文本是否无意义，不值得保存为记忆。"""
    text = text.strip()
    if len(text) < 2:
        return True
    for pattern in MEANINGLESS_PATTERNS:
        if re.match(pattern, text):
            return True
    return False


def classify_memory_type(text: str) -> str:
    """根据内容关键词分类记忆类型。"""
    text_lower = text.lower()
    for mem_type, keywords in TYPE_KEYWORDS.items():
        for kw in keywords:
            if kw in text_lower:
                return mem_type
    return "fact"


def estimate_importance(text: str) -> int:
    """估算记忆重要性 1-5。"""
    score = 3
    if len(text) > 50:
        score += 1
    if any(w in text for w in ["永远", "一直", "从来", "最重要", "绝对", "必须"]):
        score += 1
    if any(w in text for w in ["也许", "可能", "大概", "似乎", "好像"]):
        score -= 1
    return max(1, min(5, score))


# ===== CRUD =====

def create_memory(
    db: Session,
    user_id: str,
    conversation_id: int,
    content: str,
    memory_type: str = "fact",
    importance: int = 3,
    character_id: Optional[int] = None,
) -> Memory:
    mem = Memory(
        user_id=user_id,
        conversation_id=conversation_id,
        character_id=character_id,
        content=content,
        memory_type=memory_type,
        importance=importance,
        is_active=True,
    )
    db.add(mem)
    db.commit()
    db.refresh(mem)
    return mem


def get_memory(db: Session, memory_id: int, user_id: str) -> Optional[Memory]:
    return db.query(Memory).filter(
        Memory.id == memory_id,
        Memory.user_id == user_id,
    ).first()


def list_memories(
    db: Session,
    user_id: str,
    conversation_id: Optional[int] = None,
    character_id: Optional[int] = None,
    include_inactive: bool = True,
) -> List[Memory]:
    q = db.query(Memory).filter(Memory.user_id == user_id)
    if conversation_id:
        q = q.filter(Memory.conversation_id == conversation_id)
    if character_id is not None:
        q = q.filter(Memory.character_id == character_id)
    if not include_inactive:
        q = q.filter(Memory.is_active == True)
    return q.order_by(Memory.importance.desc(), Memory.updated_at.desc()).all()


def update_memory(
    db: Session,
    memory_id: int,
    user_id: str,
    content: Optional[str] = None,
    memory_type: Optional[str] = None,
    importance: Optional[int] = None,
    is_active: Optional[bool] = None,
) -> Optional[Memory]:
    mem = get_memory(db, memory_id, user_id)
    if not mem:
        return None
    if content is not None:
        mem.content = content
    if memory_type is not None:
        mem.memory_type = memory_type
    if importance is not None:
        mem.importance = importance
    if is_active is not None:
        mem.is_active = is_active
    mem.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(mem)
    return mem


def delete_memory(db: Session, memory_id: int, user_id: str) -> bool:
    mem = get_memory(db, memory_id, user_id)
    if not mem:
        return False
    db.delete(mem)
    db.commit()
    return True


# ===== 检索 =====

def retrieve_relevant_memories(
    db: Session,
    user_id: str,
    conversation_id: int,
    character_id: Optional[int] = None,
    query_text: str = "",
    limit: int = 10,
) -> List[Memory]:
    """
    检索与当前角色和上下文相关的记忆。

    规则：
    - 角色私有记忆（character_id=当前角色）优先
    - 会话级共享记忆（character_id=None）也可用
    - 其他角色的私有记忆不注入
    - 按关键词匹配 + 重要性排序
    """
    q = db.query(Memory).filter(
        Memory.user_id == user_id,
        Memory.conversation_id == conversation_id,
        Memory.is_active == True,
    )

    # 角色隔离：只取当前角色的私有记忆 + 无角色归属的共享记忆
    if character_id is not None:
        q = q.filter(
            or_(
                Memory.character_id == character_id,
                Memory.character_id.is_(None),
            )
        )

    memories = q.all()

    if not memories:
        return []

    # 如果有查询文本，做简单关键词匹配排序
    if query_text and query_text.strip():
        query_words = set(re.findall(r'[\u4e00-\u9fff\w]+', query_text.lower()))
        scored = []
        for mem in memories:
            mem_words = set(re.findall(r'[\u4e00-\u9fff\w]+', mem.content.lower()))
            overlap = len(query_words & mem_words)
            # 重要性也作为分数
            score = overlap * 2 + mem.importance
            scored.append((score, mem))
        scored.sort(key=lambda x: x[0], reverse=True)
        result = [m for _, m in scored if _ > 0][:limit]
        # 如果没有匹配的，返回最重要的几条
        if not result:
            result = sorted(memories, key=lambda m: m.importance, reverse=True)[:limit]
        return result

    # 无查询文本，按重要性+最近使用排序
    return sorted(memories, key=lambda m: (m.importance, m.last_used_at or m.updated_at), reverse=True)[:limit]


def mark_memories_used(db: Session, memory_ids: List[int]):
    """标记记忆为已使用，更新 last_used_at。"""
    if not memory_ids:
        return
    db.query(Memory).filter(Memory.id.in_(memory_ids)).update(
        {"last_used_at": datetime.utcnow()}, synchronize_session=False
    )
    db.commit()


# ===== 自动提取 =====

def should_extract(db: Session, conversation_id: int, user_id: str) -> bool:
    """判断是否应该触发记忆提取（每N条用户消息）。"""
    count = db.query(Message).filter(
        Message.conversation_id == conversation_id,
        Message.user_id == user_id,
        Message.role == "user",
    ).count()
    return count > 0 and count % MEMORY_EXTRACT_INTERVAL == 0


async def extract_memories_from_batch(
    db: Session,
    user_id: str,
    conversation_id: int,
    messages: List[Message],
    all_characters: List[Character],
) -> int:
    """
    从一批消息中提取记忆。

    使用 LLM 批量提取，避免每条消息都调用模型。
    过滤无意义内容。
    返回新创建的记忆数量。
    """
    from ..services.llm_client import chat_stream, LLMError

    # 只取有实质内容的消息
    meaningful = [
        m for m in messages
        if m.role in ("user", "assistant") and not is_meaningless(m.content)
    ]
    if len(meaningful) < 2:
        return 0

    # 构建角色名映射
    char_map = {c.id: c.name for c in all_characters}

    # 格式化消息
    lines = []
    for m in meaningful[-15:]:  # 最多取最近15条
        if m.role == "user":
            speaker = "用户"
        else:
            speaker = char_map.get(m.character_id, "AI") if m.character_id else "AI"
        lines.append(f"{speaker}：{m.content[:200]}")

    dialogue = "\n".join(lines)

    # 构建提取提示
    extract_prompt = f"""请从以下对话中提取值得长期记住的关键信息，每条记忆一行，格式为：
类型|内容
类型可选：preference(偏好)、event(事件)、fact(事实)、relationship(关系)
只提取有实质意义的信息，不要提取寒暄、感叹、无意义内容。
如果没有值得记住的信息，只回复"无"。

对话：
{dialogue}

提取结果："""

    messages_for_llm = [
        {"role": "system", "content": "你是一个记忆提取助手，擅长从对话中提取关键信息。"},
        {"role": "user", "content": extract_prompt},
    ]

    try:
        full_response = ""
        async for chunk in chat_stream(messages_for_llm):
            full_response += chunk

        if not full_response.strip() or full_response.strip() == "无":
            return 0

        # 解析提取结果
        created = 0
        for line in full_response.strip().split("\n"):
            line = line.strip()
            if not line or line == "无":
                continue
            # 解析 类型|内容 格式
            if "|" in line:
                parts = line.split("|", 1)
                mem_type = parts[0].strip().lower()
                content = parts[1].strip()
            else:
                mem_type = "fact"
                content = line.strip(" -•*\t")

            # 验证
            if mem_type not in ("preference", "event", "fact", "relationship", "user", "character"):
                mem_type = "fact"
            if not content or is_meaningless(content) or len(content) < 3:
                continue
            if len(content) > 500:
                content = content[:500]

            # 检查是否已存在相似记忆（简单去重）
            existing = db.query(Memory).filter(
                Memory.user_id == user_id,
                Memory.conversation_id == conversation_id,
                Memory.content == content,
            ).first()
            if existing:
                continue

            create_memory(
                db, user_id, conversation_id, content,
                memory_type=mem_type,
                importance=estimate_importance(content),
            )
            created += 1

        return created

    except LLMError:
        return 0
    except Exception:
        return 0


def format_memories_for_context(memories: List[Memory]) -> str:
    """将记忆列表格式化为注入上下文的文本。"""
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
