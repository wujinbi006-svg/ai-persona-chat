from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from typing import List
import logging
import time
import uuid
from ..database import get_db
from ..schemas.conversation import (
    ConversationCreate, ConversationUpdate, ConversationOut, MessageOut
)
from ..services import conversation_service as svc
from ..services.auth import get_current_user

router = APIRouter(prefix="/api/conversations", tags=["conversations"])
logger = logging.getLogger(__name__)


@router.post("", response_model=ConversationOut)
def create_conversation(
    body: ConversationCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    trace_id = uuid.uuid4().hex[:12]
    started = time.perf_counter()
    logger.info("CREATE_CONV_START trace=%s", trace_id)
    logger.info("CREATE_CONV_AUTH_DONE trace=%s user_present=%s", trace_id, bool(current_user.get("id")))
    logger.info("CREATE_CONV_DB_SESSION_ACQUIRED trace=%s", trace_id)
    logger.info("CREATE_CONV_DB_INSERT_START trace=%s", trace_id)
    conv = svc.create_conversation(db, user_id=current_user["id"], title=body.title)
    logger.info(
        "CREATE_CONV_DB_INSERT_COMMIT_REFRESH_DONE trace=%s elapsed_ms=%.1f",
        trace_id,
        (time.perf_counter() - started) * 1000,
    )
    logger.info("CREATE_CONV_RESPONSE_READY trace=%s", trace_id)
    return conv


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
