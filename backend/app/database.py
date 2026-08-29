from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from pathlib import Path
from .config import settings
import logging

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

if settings.USE_SUPABASE and settings.DATABASE_URL and not settings.DATABASE_URL.startswith('sqlite'):
    # 生产模式：PostgreSQL
    logger.info(f"Using PostgreSQL database: {settings.DATABASE_URL[:50]}...")
    engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True, pool_size=5, max_overflow=10)
else:
    # 本地开发模式或未配置 PostgreSQL：SQLite
    if settings.USE_SUPABASE:
        logger.warning("USE_SUPABASE=true but DATABASE_URL is not configured or is SQLite. Falling back to SQLite.")
    raw_path = settings.DATABASE_URL.replace("sqlite:///", "")
    p = Path(raw_path)
    if not p.is_absolute():
        p = PROJECT_ROOT / p
    p.parent.mkdir(parents=True, exist_ok=True)
    db_url = f"sqlite:///{p.as_posix()}"
    logger.info(f"Using SQLite database: {db_url}")
    engine = create_engine(db_url, connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
