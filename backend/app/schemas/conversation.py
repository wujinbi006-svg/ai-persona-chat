from datetime import datetime
from pydantic import BaseModel, Field
from typing import Optional, List


class ConversationCreate(BaseModel):
    title: Optional[str] = None


class ConversationUpdate(BaseModel):
    title: Optional[str] = None


class ConversationOut(BaseModel):
    id: int
    title: str
    persona: str  # 保留兼容
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CharacterCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    persona: str = ""
    avatar: Optional[str] = None


class CharacterUpdate(BaseModel):
    name: Optional[str] = None
    persona: Optional[str] = None
    avatar: Optional[str] = None


class CharacterOut(BaseModel):
    id: int
    conversation_id: int
    name: str
    persona: str
    avatar: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MessageOut(BaseModel):
    id: int
    conversation_id: int
    character_id: Optional[int] = None
    character_name: Optional[str] = None
    role: str
    content: str
    image_url: Optional[str] = None  # 图片消息的图片URL，文字消息为null
    created_at: datetime

    model_config = {"from_attributes": True}


class ChatRequest(BaseModel):
    conversation_id: int
    message: str = Field(..., min_length=1)
    character_id: Optional[int] = None  # 为空=只保存用户消息；有值=调用该角色生成回复


class ReplyAllRequest(BaseModel):
    conversation_id: int
    message: Optional[str] = None  # 可选：先发一条用户消息再让所有AI回复


class DiscussionRequest(BaseModel):
    conversation_id: int
    character_ids: List[int]
    rounds: int = Field(5, ge=1, le=20)
    message: Optional[str] = None  # 可选：先发一条用户消息作为讨论起点
