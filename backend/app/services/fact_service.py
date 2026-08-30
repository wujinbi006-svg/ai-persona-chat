"""
Phase 4: Canonical Facts（规范事实）服务。

核心原则：事实与假设分离。
- Fact: 已确认的客观事实（如"案件纸条时间为18:45"）
- Hypothesis: 角色的推测（如"林探长认为凶手可能从窗户逃离"）
- 假设不能自动成为事实，除非用户或系统确认。

Fact 状态：
- confirmed: 已确认
- uncertain: 不确定
- conflicted: 存在冲突
- superseded: 已被新事实取代
"""
from typing import Optional, List
from sqlalchemy.orm import Session
from ..models.conversation import Fact


def create_fact(
    db: Session,
    user_id: str,
    subject: str,
    content: str,
    conversation_id: Optional[int] = None,
    character_id: Optional[int] = None,
    fact_type: str = "fact",
    status: str = "confirmed",
    confidence: int = 100,
    source_message_id: Optional[int] = None,
) -> Fact:
    """创建新事实。"""
    fact = Fact(
        user_id=user_id,
        conversation_id=conversation_id,
        character_id=character_id,
        subject=subject,
        content=content,
        fact_type=fact_type,
        status=status,
        confidence=confidence,
        source_message_id=source_message_id,
    )
    db.add(fact)
    db.commit()
    db.refresh(fact)
    return fact


def get_facts(
    db: Session,
    user_id: str,
    conversation_id: Optional[int] = None,
    status_filter: Optional[List[str]] = None,
    fact_type_filter: Optional[List[str]] = None,
) -> List[Fact]:
    """获取事实列表。"""
    q = db.query(Fact).filter(Fact.user_id == user_id)

    if conversation_id is not None:
        q = q.filter(Fact.conversation_id == conversation_id)

    if status_filter:
        q = q.filter(Fact.status.in_(status_filter))

    if fact_type_filter:
        q = q.filter(Fact.fact_type.in_(fact_type_filter))

    return q.order_by(Fact.created_at.desc()).all()


def get_confirmed_facts(
    db: Session,
    user_id: str,
    conversation_id: Optional[int] = None,
) -> List[Fact]:
    """获取已确认的事实（用于注入上下文）。"""
    return get_facts(
        db, user_id, conversation_id,
        status_filter=["confirmed"],
        fact_type_filter=["fact"],
    )


def get_hypotheses(
    db: Session,
    user_id: str,
    conversation_id: Optional[int] = None,
    character_id: Optional[int] = None,
) -> List[Fact]:
    """获取角色假设（标记为 hypothesis，不能当作事实）。"""
    q = db.query(Fact).filter(
        Fact.user_id == user_id,
        Fact.fact_type == "hypothesis",
    )
    if conversation_id is not None:
        q = q.filter(Fact.conversation_id == conversation_id)
    if character_id is not None:
        q = q.filter(Fact.character_id == character_id)
    return q.order_by(Fact.created_at.desc()).all()


def update_fact_status(
    db: Session,
    fact_id: int,
    status: str,
    confidence: Optional[int] = None,
) -> Optional[Fact]:
    """更新事实状态。"""
    fact = db.query(Fact).filter(Fact.id == fact_id).first()
    if not fact:
        return None

    fact.status = status
    if confidence is not None:
        fact.confidence = confidence
    db.commit()
    db.refresh(fact)
    return fact


def supersede_fact(
    db: Session,
    old_fact_id: int,
    new_subject: str,
    new_content: str,
    user_id: str,
) -> Optional[Fact]:
    """用新事实取代旧事实。

    旧事实标记为 superseded，新事实标记为 confirmed。
    不删除旧事实，保留历史。
    """
    old_fact = db.query(Fact).filter(Fact.id == old_fact_id).first()
    if not old_fact:
        return None

    old_fact.status = "superseded"

    new_fact = Fact(
        user_id=user_id,
        conversation_id=old_fact.conversation_id,
        character_id=old_fact.character_id,
        subject=new_subject,
        content=new_content,
        fact_type="fact",
        status="confirmed",
        confidence=100,
        superseded_by=None,  # 新事实的 ID 会在 commit 后回填
    )
    db.add(new_fact)
    db.flush()
    old_fact.superseded_by = new_fact.id
    db.commit()
    db.refresh(new_fact)
    return new_fact


def mark_conflict(
    db: Session,
    fact_id: int,
) -> Optional[Fact]:
    """标记事实存在冲突。"""
    return update_fact_status(db, fact_id, "conflicted", confidence=50)


def delete_fact(db: Session, fact_id: int) -> bool:
    """删除事实（谨慎使用，通常用 supersede 代替）。"""
    fact = db.query(Fact).filter(Fact.id == fact_id).first()
    if not fact:
        return False
    db.delete(fact)
    db.commit()
    return True


def format_facts_for_context(facts: List[Fact]) -> str:
    """将事实格式化为上下文注入文本。"""
    if not facts:
        return ""
    lines = []
    for fact in facts:
        status_tag = ""
        if fact.status == "uncertain":
            status_tag = "（待确认）"
        elif fact.status == "conflicted":
            status_tag = "（存在冲突）"
        lines.append(f"- {fact.subject}: {fact.content}{status_tag}")
    return "\n".join(lines)


def format_hypotheses_for_context(hypotheses: List[Fact]) -> str:
    """将假设格式化为上下文注入文本（明确标记为假设，不能当作事实）。"""
    if not hypotheses:
        return ""
    lines = ["以下是角色提出的假设，尚未确认，不能当作事实："]
    for h in hypotheses:
        lines.append(f"- [假设] {h.subject}: {h.content}")
    return "\n".join(lines)
