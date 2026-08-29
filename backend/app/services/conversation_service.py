"""
会话与角色服务（支持多用户 user_id）。
"""
from datetime import datetime
from typing import List, Optional
from sqlalchemy.orm import Session
from ..models.conversation import Conversation, Character, Message


# ===== Conversation =====

def create_conversation(db: Session, user_id: str, title: Optional[str] = None) -> Conversation:
    conv = Conversation(title=title or "新对话", persona="", user_id=user_id)
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv


def get_conversation(db: Session, conv_id: int, user_id: Optional[str] = None) -> Optional[Conversation]:
    q = db.query(Conversation).filter(Conversation.id == conv_id)
    if user_id:
        q = q.filter(Conversation.user_id == user_id)
    return q.first()


def list_conversations(db: Session, user_id: Optional[str] = None) -> List[Conversation]:
    q = db.query(Conversation)
    if user_id:
        q = q.filter(Conversation.user_id == user_id)
    return q.order_by(Conversation.updated_at.desc()).all()


def update_conversation(db: Session, conv_id: int, user_id: Optional[str] = None, title: Optional[str] = None) -> Optional[Conversation]:
    conv = get_conversation(db, conv_id, user_id)
    if not conv:
        return None
    if title is not None:
        conv.title = title
    conv.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(conv)
    return conv


def delete_conversation(db: Session, conv_id: int, user_id: Optional[str] = None) -> bool:
    conv = get_conversation(db, conv_id, user_id)
    if not conv:
        return False
    db.delete(conv)
    db.commit()
    return True


def touch_conversation(db: Session, conv_id: int):
    conv = db.query(Conversation).filter(Conversation.id == conv_id).first()
    if conv:
        conv.updated_at = datetime.utcnow()
        db.commit()


# ===== Character =====

def create_character(db: Session, conversation_id: int, user_id: str, name: str, persona: str = "", avatar: Optional[str] = None) -> Character:
    char = Character(conversation_id=conversation_id, user_id=user_id, name=name, persona=persona, avatar=avatar)
    db.add(char)
    touch_conversation(db, conversation_id)
    db.refresh(char)
    return char


def get_character(db: Session, char_id: int, user_id: Optional[str] = None) -> Optional[Character]:
    q = db.query(Character).filter(Character.id == char_id)
    if user_id:
        q = q.filter(Character.user_id == user_id)
    return q.first()


def list_characters(db: Session, conversation_id: int, user_id: Optional[str] = None) -> List[Character]:
    q = db.query(Character).filter(Character.conversation_id == conversation_id)
    if user_id:
        q = q.filter(Character.user_id == user_id)
    return q.order_by(Character.id).all()


def update_character(db: Session, char_id: int, user_id: Optional[str] = None, name: Optional[str] = None, persona: Optional[str] = None, avatar: Optional[str] = None) -> Optional[Character]:
    char = get_character(db, char_id, user_id)
    if not char:
        return None
    if name is not None:
        char.name = name
    if persona is not None:
        char.persona = persona
    if avatar is not None:
        char.avatar = avatar
    char.updated_at = datetime.utcnow()
    touch_conversation(db, char.conversation_id)
    db.refresh(char)
    return char


def delete_character(db: Session, char_id: int, user_id: Optional[str] = None) -> bool:
    char = get_character(db, char_id, user_id)
    if not char:
        return False
    conv_id = char.conversation_id
    db.delete(char)
    touch_conversation(db, conv_id)
    return True


# ===== Message =====

def get_messages(db: Session, conversation_id: int, user_id: Optional[str] = None) -> List[Message]:
    q = db.query(Message).filter(Message.conversation_id == conversation_id)
    return q.order_by(Message.id).all()


def add_message(
    db: Session,
    conversation_id: int,
    user_id: str,
    role: str,
    content: str,
    character_id: Optional[int] = None,
    image_url: Optional[str] = None,
) -> Message:
    """
    添加消息。支持图片消息：image_url 非空时为图片消息。
    图片消息的 content 可以是图片说明文字或空字符串。
    """
    msg = Message(
        conversation_id=conversation_id,
        user_id=user_id,
        role=role,
        content=content,
        character_id=character_id,
        image_url=image_url,
    )
    db.add(msg)
    touch_conversation(db, conversation_id)
    db.refresh(msg)
    return msg


def clear_messages(db: Session, conversation_id: int, user_id: Optional[str] = None) -> int:
    q = db.query(Message).filter(Message.conversation_id == conversation_id)
    if user_id:
        q = q.filter(Message.user_id == user_id)
    count = q.delete()
    touch_conversation(db, conversation_id)
    return count


def generate_title_from_message(message: str, max_len: int = 25) -> str:
    cleaned = message.strip().replace("\n", " ")
    if not cleaned:
        return "新对话"
    if len(cleaned) > max_len:
        return cleaned[:max_len] + "…"
    return cleaned


def message_to_out(msg: Message, db: Session) -> dict:
    char_name = None
    if msg.character_id:
        char = db.query(Character).filter(Character.id == msg.character_id).first()
        char_name = char.name if char else "已删除角色"
    return {
        "id": msg.id,
        "conversation_id": msg.conversation_id,
        "character_id": msg.character_id,
        "character_name": char_name,
        "role": msg.role,
        "content": msg.content,
        "image_url": msg.image_url,
        "created_at": msg.created_at,
    }
