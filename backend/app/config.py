import os
from pathlib import Path
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(ROOT_DIR / ".env")


class Settings:
    # 模式切换
    USE_SUPABASE: bool = os.getenv("USE_SUPABASE", "false").lower() == "true"

    # Supabase
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
    SUPABASE_ANON_KEY: str = os.getenv("SUPABASE_ANON_KEY", "")
    SUPABASE_SERVICE_ROLE_KEY: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

    # 数据库
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./data/app.db")

    # LLM
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_BASE_URL: str = os.getenv("OPENAI_BASE_URL", "")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "")

    # CORS
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "")

    # 上下文
    MAX_CONTEXT_MESSAGES: int = int(os.getenv("MAX_CONTEXT_MESSAGES", "40"))
    LLM_TIMEOUT: float = float(os.getenv("LLM_TIMEOUT", "120"))

    # 限流
    RATE_LIMIT_PER_MINUTE: int = int(os.getenv("RATE_LIMIT_PER_MINUTE", "60"))

    # 图片生成（GK Image 2.0 / 小羽毛AI聚合平台 - 当前使用）
    IMAGE_API_BASE_URL: str = os.getenv("IMAGE_API_BASE_URL", "https://api.lk888.ai")
    IMAGE_API_KEY: str = os.getenv("IMAGE_API_KEY", "")
    IMAGE_MODEL: str = os.getenv("IMAGE_MODEL", "gk-image-2.0")
    IMAGE_OUTPUT_DIR: str = os.getenv("IMAGE_OUTPUT_DIR", "data/generated_images")
    IMAGE_TIMEOUT: float = float(os.getenv("IMAGE_TIMEOUT", "180"))

    # 图片生成（豆包视觉 / 火山方舟 - 保留作为回滚备用）
    DOUBAO_VISION_API_KEY: str = os.getenv("DOUBAO_VISION_API_KEY", "")
    DOUBAO_VISION_BASE_URL: str = os.getenv("DOUBAO_VISION_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
    DOUBAO_VISION_MODEL: str = os.getenv("DOUBAO_VISION_MODEL", "")


settings = Settings()
