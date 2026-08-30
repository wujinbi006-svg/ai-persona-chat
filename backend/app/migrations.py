"""
数据库迁移。
1. 创建 characters 表
2. messages 表增加 character_id 列
3. 所有表增加 user_id 列
4. 旧数据迁移
5. messages 表增加 image_url 列
6. characters 表增加 sort_order 列
7. conversations 表增加 scene/scene_time/scene_context 列
8. 创建 memories 表
9. Phase 3: messages 增加 generation_id/sequence_number/parent_message_id/message_type
10. Phase 3: 创建 generation_sessions 表
11. Phase 4: 创建 facts 表（Canonical Facts）
"""
from sqlalchemy import text, inspect
from sqlalchemy.orm import Session
from .database import engine, Base
from .models.conversation import Conversation, Character, Message, GenerationSession, Fact

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

    # messages.image_url
    if "messages" in inspector.get_table_names():
        cols = [c["name"] for c in inspector.get_columns("messages")]
        if "image_url" not in cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE messages ADD COLUMN image_url VARCHAR(500)"))
            print("[Migration] messages.image_url added")

    # Phase 3: messages 数据一致性字段
    if "messages" in inspector.get_table_names():
        cols = [c["name"] for c in inspector.get_columns("messages")]
        phase3_fields = {
            "generation_id": "VARCHAR(64)",
            "sequence_number": "INTEGER",
            "parent_message_id": "INTEGER",
            "message_type": "VARCHAR(20) DEFAULT 'text'",
        }
        for field, field_type in phase3_fields.items():
            if field not in cols:
                with engine.begin() as conn:
                    conn.execute(text(f"ALTER TABLE messages ADD COLUMN {field} {field_type}"))
                print(f"[Migration] messages.{field} added (Phase 3)")

    # 为 generation_id 创建索引（如果不存在）
    try:
        with engine.begin() as conn:
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_messages_generation_id ON messages (generation_id)"))
    except Exception:
        pass

    # Phase 8: generation_sessions 表的数据库级唯一性约束
    # 保证同一个 conversation 同时只能有一个 active generation（running/paused/stopping）
    # 使用部分唯一索引（PostgreSQL 和 SQLite 都支持）
    if "generation_sessions" in inspector.get_table_names():
        try:
            with engine.begin() as conn:
                conn.execute(text("""
                    CREATE UNIQUE INDEX IF NOT EXISTS idx_active_generation_per_conversation
                    ON generation_sessions (conversation_id)
                    WHERE status IN ('running', 'paused', 'stopping')
                """))
            print("[Migration] generation_sessions active unique index added (Phase 8)")
        except Exception as e:
            print(f"[Migration] Warning: could not create active generation unique index: {e}")

    # characters.sort_order
    if "characters" in inspector.get_table_names():
        cols = [c["name"] for c in inspector.get_columns("characters")]
        if "sort_order" not in cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE characters ADD COLUMN sort_order INTEGER DEFAULT 0"))
            print("[Migration] characters.sort_order added")

    # conversations scene fields
    if "conversations" in inspector.get_table_names():
        cols = [c["name"] for c in inspector.get_columns("conversations")]
        if "scene" not in cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE conversations ADD COLUMN scene VARCHAR(500) DEFAULT ''"))
            print("[Migration] conversations.scene added")
        if "scene_time" not in cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE conversations ADD COLUMN scene_time VARCHAR(100) DEFAULT ''"))
            print("[Migration] conversations.scene_time added")
        if "scene_context" not in cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE conversations ADD COLUMN scene_context TEXT DEFAULT ''"))
            print("[Migration] conversations.scene_context added")

    # user_id 列
    for table in ["conversations", "characters", "messages", "memories"]:
        if table in inspector.get_table_names():
            cols = [c["name"] for c in inspector.get_columns(table)]
            if "user_id" not in cols:
                with engine.begin() as conn:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN user_id TEXT"))
                print(f"[Migration] {table}.user_id added")

    # 回填本地模式 user_id
    with engine.begin() as conn:
        for table in ["conversations", "characters", "messages", "memories"]:
            if table in inspector.get_table_names():
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
