from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from ..database import get_db
from ..schemas.conversation import (
    ConversationCreate, ConversationUpdate, ConversationOut, MessageOut
)
from ..services import conversation_service as svc
from ..services.auth import get_current_user

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


@router.post("", response_model=ConversationOut)
def create_conversation(body: ConversationCreate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    return svc.create_conversation(db, user_id=current_user["id"], title=body.title)


@router.get("", response_model=List[ConversationOut])
def list_conversations(db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    return svc.list_conversations(db, user_id=current_user["id"])


@router.get("/{conv_id}", response_model=ConversationOut)
def get_conversation(conv_id: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    conv = svc.get_conversation(db, conv_id, user_id=current_user["id"])
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")
    return conv


@router.patch("/{conv_id}", response_model=ConversationOut)
def update_conversation(conv_id: int, body: ConversationUpdate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    conv = svc.update_conversation(
        db, conv_id, user_id=current_user["id"],
        title=body.title,
        scene=body.scene,
        scene_time=body.scene_time,
        scene_context=body.scene_context,
    )
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")
    return conv


@router.delete("/{conv_id}")
def delete_conversation(conv_id: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    ok = svc.delete_conversation(db, conv_id, user_id=current_user["id"])
    if not ok:
        raise HTTPException(status_code=404, detail="会话不存在")
    return {"ok": True}


@router.get("/{conv_id}/messages", response_model=List[MessageOut])
def get_messages(conv_id: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    conv = svc.get_conversation(db, conv_id, user_id=current_user["id"])
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")
    msgs = svc.get_messages(db, conv_id, user_id=current_user["id"])
    return [svc.message_to_out(m, db) for m in msgs]


@router.delete("/{conv_id}/messages")
def clear_messages(conv_id: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    conv = svc.get_conversation(db, conv_id, user_id=current_user["id"])
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")
    count = svc.clear_messages(db, conv_id, user_id=current_user["id"])
    return {"ok": True, "deleted": count}
