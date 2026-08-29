"""
SQLite → Supabase PostgreSQL 数据迁移脚本。

用法：
  python scripts/migrate_sqlite_to_supabase.py --dry-run
  python scripts/migrate_sqlite_to_supabase.py --target-user-id <uuid>

功能：
- 读取本地 SQLite 数据库
- 转换 conversations / characters / messages 到 Supabase
- 旧 conversation.persona → 创建默认 character "AI"
- 旧 assistant messages → 绑定到默认 character
- 支持 dry-run（只打印不写入）
- 幂等（通过 migration_meta 表防止重复迁移）
- 迁移前自动备份 SQLite
"""
import argparse
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

# 项目根目录
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")


def get_sqlite_data(db_path: Path):
    """从 SQLite 读取所有数据。"""
    import sqlite3
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    data = {"conversations": [], "characters": [], "messages": []}

    # conversations
    try:
        rows = conn.execute("SELECT * FROM conversations ORDER BY id").fetchall()
        data["conversations"] = [dict(r) for r in rows]
    except Exception as e:
        print(f"  读取 conversations 失败: {e}")

    # characters
    try:
        rows = conn.execute("SELECT * FROM characters ORDER BY id").fetchall()
        data["characters"] = [dict(r) for r in rows]
    except Exception:
        data["characters"] = []  # 旧版本可能没有 characters 表

    # messages
    try:
        rows = conn.execute("SELECT * FROM messages ORDER BY id").fetchall()
        data["messages"] = [dict(r) for r in rows]
    except Exception as e:
        print(f"  读取 messages 失败: {e}")

    conn.close()
    return data


def migrate(data, target_user_id, dry_run, supabase_url, supabase_key):
    """执行迁移。"""
    from supabase import create_client
    client = create_client(supabase_url, supabase_key)

    id_mapping = {"conversations": {}, "characters": {}}
    stats = {"conversations": 0, "characters": 0, "messages": 0, "skipped": 0}

    # 1. 迁移 conversations
    print("\n--- 迁移 conversations ---")
    for conv in data["conversations"]:
        old_id = conv["id"]
        # 检查是否已迁移
        existing = client.table("migration_meta").select("target_id").eq("source", "sqlite").eq("source_id", str(old_id)).eq("target_table", "conversations").execute()
        if existing.data:
            id_mapping["conversations"][old_id] = existing.data[0]["target_id"]
            stats["skipped"] += 1
            print(f"  会话 {old_id} 已迁移，跳过")
            continue

        if dry_run:
            print(f"  [DRY] 会话 {old_id}: {conv.get('title', '')[:30]}")
            continue

        result = client.table("conversations").insert({
            "user_id": target_user_id,
            "title": conv.get("title", "新对话"),
            "persona": conv.get("persona", ""),
        }).execute()
        new_id = result.data[0]["id"]
        id_mapping["conversations"][old_id] = new_id

        # 记录迁移
        client.table("migration_meta").insert({
            "source": "sqlite", "source_id": str(old_id),
            "target_table": "conversations", "target_id": new_id,
        }).execute()
        stats["conversations"] += 1
        print(f"  会话 {old_id} → {new_id}")

    # 2. 为有 persona 的旧会话创建默认 character
    print("\n--- 迁移/创建 characters ---")
    for conv in data["conversations"]:
        old_id = conv["id"]
        new_conv_id = id_mapping["conversations"].get(old_id)
        if not new_conv_id:
            continue

        # 检查该会话是否已有角色
        existing_chars = [c for c in data["characters"] if c["conversation_id"] == old_id]

        if not existing_chars and conv.get("persona"):
            # 创建默认角色 "AI"
            if dry_run:
                print(f"  [DRY] 为会话 {old_id} 创建默认角色 AI")
                continue
            result = client.table("characters").insert({
                "conversation_id": new_conv_id,
                "user_id": target_user_id,
                "name": "AI",
                "persona": conv["persona"],
            }).execute()
            char_id = result.data[0]["id"]
            # 记录映射（用负数 old_id 避免冲突）
            id_mapping["characters"][f"default_{old_id}"] = char_id
            stats["characters"] += 1
            print(f"  为会话 {old_id} 创建默认角色 AI → {char_id}")

        for char in existing_chars:
            old_char_id = char["id"]
            # 检查已迁移
            existing = client.table("migration_meta").select("target_id").eq("source", "sqlite").eq("source_id", str(old_char_id)).eq("target_table", "characters").execute()
            if existing.data:
                id_mapping["characters"][old_char_id] = existing.data[0]["target_id"]
                continue
            if dry_run:
                print(f"  [DRY] 角色 {old_char_id}: {char['name']}")
                continue
            result = client.table("characters").insert({
                "conversation_id": new_conv_id,
                "user_id": target_user_id,
                "name": char["name"],
                "persona": char.get("persona", ""),
                "avatar": char.get("avatar"),
            }).execute()
            new_char_id = result.data[0]["id"]
            id_mapping["characters"][old_char_id] = new_char_id
            client.table("migration_meta").insert({
                "source": "sqlite", "source_id": str(old_char_id),
                "target_table": "characters", "target_id": new_char_id,
            }).execute()
            stats["characters"] += 1
            print(f"  角色 {old_char_id} → {new_char_id}")

    # 3. 迁移 messages
    print("\n--- 迁移 messages ---")
    for msg in data["messages"]:
        old_msg_id = msg["id"]
        old_conv_id = msg["conversation_id"]
        new_conv_id = id_mapping["conversations"].get(old_conv_id)
        if not new_conv_id:
            continue

        # 检查已迁移
        existing = client.table("migration_meta").select("target_id").eq("source", "sqlite").eq("source_id", str(old_msg_id)).eq("target_table", "messages").execute()
        if existing.data:
            stats["skipped"] += 1
            continue

        # 映射 character_id
        new_char_id = None
        old_char_id = msg.get("character_id")
        if old_char_id:
            new_char_id = id_mapping["characters"].get(old_char_id)
            if not new_char_id:
                # 可能是默认角色
                new_char_id = id_mapping["characters"].get(f"default_{old_conv_id}")

        if dry_run:
            print(f"  [DRY] 消息 {old_msg_id}: role={msg['role']} char={new_char_id}")
            continue

        result = client.table("messages").insert({
            "conversation_id": new_conv_id,
            "user_id": target_user_id,
            "character_id": new_char_id,
            "role": msg["role"],
            "content": msg["content"],
        }).execute()
        new_msg_id = result.data[0]["id"]
        client.table("migration_meta").insert({
            "source": "sqlite", "source_id": str(old_msg_id),
            "target_table": "messages", "target_id": new_msg_id,
        }).execute()
        stats["messages"] += 1

    print(f"\n=== 迁移完成 ===")
    print(f"  会话: {stats['conversations']} 新建, {stats['skipped']} 跳过")
    print(f"  角色: {stats['characters']} 新建")
    print(f"  消息: {stats['messages']} 新建")
    if dry_run:
        print("  (DRY RUN 模式，未实际写入)")


def main():
    parser = argparse.ArgumentParser(description="SQLite → Supabase 数据迁移")
    parser.add_argument("--sqlite", default=str(ROOT / "data" / "app.db"), help="SQLite 数据库路径")
    parser.add_argument("--target-user-id", help="目标 Supabase 用户 UUID")
    parser.add_argument("--dry-run", action="store_true", help="只打印不写入")
    args = parser.parse_args()

    db_path = Path(args.sqlite)
    if not db_path.exists():
        print(f"错误: SQLite 数据库不存在: {db_path}")
        sys.exit(1)

    # 备份
    backup_path = db_path.parent / f"app.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    shutil.copy2(db_path, backup_path)
    print(f"已备份数据库到: {backup_path}")

    # 读取数据
    print(f"\n读取 SQLite 数据: {db_path}")
    data = get_sqlite_data(db_path)
    print(f"  会话: {len(data['conversations'])}")
    print(f"  角色: {len(data['characters'])}")
    print(f"  消息: {len(data['messages'])}")

    if args.dry_run:
        migrate(data, None, True, "", "")
        return

    # 生产模式需要 Supabase 配置
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    target_user_id = args.target_user_id

    if not supabase_url or not supabase_key:
        print("错误: 请在 .env 中配置 SUPABASE_URL 和 SUPABASE_SERVICE_ROLE_KEY")
        sys.exit(1)
    if not target_user_id:
        print("错误: 请使用 --target-user-id 指定目标用户 UUID")
        sys.exit(1)

    migrate(data, target_user_id, False, supabase_url, supabase_key)


if __name__ == "__main__":
    main()
