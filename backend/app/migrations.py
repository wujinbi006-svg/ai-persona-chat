"""
数据库迁移。
1. 创建 characters 表
2. messages 表增加 character_id 列
3. 所有表增加 user_id 列（第三阶段）
4. 旧数据迁移
5. messages 表增加 image_url 列（图片消息支持）
"""
from sqlalchemy import text, inspect
from sqlalchemy.orm import Session
from .database import engine, Base
from .models.conversation import Conversation, Character, Message

DEFAULT_USER_ID = "local-user"


def run_migrations():
    Base.metadata.create_all(bind=engine)
    inspector = inspect(engine)

    # messages.character_id
    if "messages" in inspector.get_table_names():
        cols = [c["name"] for c in inspector.get_columns("messages")]
        if "character_id" not in cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE messages ADD COLUMN character_id INTEGER"))
            print("[Migration] messages.character_id added")

    # messages.image_url（图片消息支持）
    if "messages" in inspector.get_table_names():
        cols = [c["name"] for c in inspector.get_columns("messages")]
        if "image_url" not in cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE messages ADD COLUMN image_url VARCHAR(500)"))
            print("[Migration] messages.image_url added")

    # user_id 列（第三阶段）
    for table in ["conversations", "characters", "messages"]:
        if table in inspector.get_table_names():
            cols = [c["name"] for c in inspector.get_columns(table)]
            if "user_id" not in cols:
                with engine.begin() as conn:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN user_id TEXT"))
                print(f"[Migration] {table}.user_id added")

    # 回填本地模式 user_id（旧数据为 NULL）
    with engine.begin() as conn:
        for table in ["conversations", "characters", "messages"]:
            result = conn.execute(text(f"SELECT COUNT(*) FROM {table} WHERE user_id IS NULL"))
            null_count = result.scalar()
            if null_count > 0:
                conn.execute(text(f"UPDATE {table} SET user_id = :uid WHERE user_id IS NULL"), {"uid": DEFAULT_USER_ID})
                print(f"[Migration] {null_count} records in {table} backfilled with user_id")

    # 旧数据迁移：有 persona 的 conversation 创建默认角色
    with Session(engine) as db:
        old_convs = db.query(Conversation).filter(
            Conversation.persona.isnot(None),
            Conversation.persona != "",
        ).all()
        migrated = 0
        for conv in old_convs:
            existing = db.query(Character).filter(Character.conversation_id == conv.id).first()
            if existing:
                continue
            char = Character(conversation_id=conv.id, name="AI", persona=conv.persona, user_id=DEFAULT_USER_ID)
            db.add(char)
            db.flush()
            db.query(Message).filter(
                Message.conversation_id == conv.id,
                Message.role == "assistant",
                Message.character_id.is_(None),
            ).update({"character_id": char.id}, synchronize_session=False)
            migrated += 1
        db.commit()
        if migrated > 0:
            print(f"[Migration] {migrated} old conversations migrated")

    print("[Migration] All migrations completed")
