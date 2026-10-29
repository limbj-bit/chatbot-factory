from typing import List, Optional
from pathlib import Path
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Render stores "Secret Files" as real files (not env vars) under /etc/secrets/
# (or the app root). If ENCRYPTION_KEY isn't set as an env var, fall back to
# reading it from a secret file so Fernet encryption still works on Render.
_SECRET_FILE_CANDIDATES = [
    Path("/etc/secrets/ENCRYPTION_KEY"),
    Path(__file__).resolve().parents[2] / "ENCRYPTION_KEY",
]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application
    APP_ENV: str = "development"
    APP_NAME: str = "Fresh Food Claim AI SaaS"
    DEBUG: bool = True
    PORT: int = 8000
    HOST: str = "0.0.0.0"
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ]

    # Database & Cache
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/claims.db"
    REDIS_URL: str = "redis://localhost:6379/0"

    # Mock Mode Flags
    MOCK_AI: bool = True
    MOCK_CAFE24: bool = True

    # AI Provider Keys
    GROQ_API_KEY: Optional[str] = None
    NVIDIA_API_KEY: Optional[str] = None
    NVIDIA_NIM_API_KEY: Optional[str] = None
    GEMINI_API_KEY: Optional[str] = None
    MISTRAL_API_KEY: Optional[str] = None
    OPENROUTER_API_KEY: Optional[str] = None

    AI_DEFAULT_PROVIDER: str = "groq"
    AI_FALLBACK_PROVIDER: str = "nvidia"
    # Free vision preferred; Gemini remains last resort in get_vision_provider_chain()
    AI_VISION_PROVIDER: str = "nvidia"
    # Per-provider models (task-tuned). Override via env without code changes.
    GROQ_TEXT_MODEL: str = "qwen/qwen3.8-27b"  # fast KR-capable chat
    # NVIDIA: Nemotron Super + Llama 3.3 (CSV pool RR). Single NVIDIA_TEXT_MODEL is legacy fallback.
    NVIDIA_TEXT_MODELS: str = (
        "nvidia/llama-3.3-nemotron-super-49b-v1.5,meta/llama-3.3-70b-instruct"
    )
    NVIDIA_TEXT_MODEL: str = "nvidia/llama-3.3-nemotron-super-49b-v1.5"
    # Vision: Llama 3.2 VL pool RR (90B → 11B). Single NVIDIA_VISION_MODEL = legacy.
    NVIDIA_VISION_MODELS: str = (
        "meta/llama-3.2-90b-vision-instruct,meta/llama-3.2-11b-vision-instruct"
    )
    NVIDIA_VISION_MODEL: str = "meta/llama-3.2-90b-vision-instruct"
    MISTRAL_TEXT_MODEL: str = "mistral-large-latest"  # strong multilingual CS
    # OpenRouter: rotate strong chat models (not vision mini). CSV pool RR.
    OPENROUTER_TEXT_MODELS: str = (
        "qwen/qwen-2.5-72b-instruct,"
        "deepseek/deepseek-chat,"
        "meta-llama/llama-3.3-70b-instruct"
    )
    OPENROUTER_TEXT_MODEL: str = "qwen/qwen-2.5-72b-instruct"
    # Vision backup: Nemotron VL free → Llama VL → gpt-4o-mini
    OPENROUTER_VISION_MODELS: str = (
        "nvidia/nemotron-3.5-super-vl:free,"
        "meta-llama/llama-3.2-11b-vision-instruct,"
        "openai/gpt-4o-mini"
    )
    OPENROUTER_VISION_MODEL: str = "nvidia/nemotron-3.5-super-vl:free"
    GEMINI_TEXT_MODEL: str = "gemini-2.0-flash"  # paid last-resort chat+vision

    # Cafe24 Integration
    CAFE24_MALL_ID: str = "demo_mall"
    CAFE24_CLIENT_ID: Optional[str] = None
    CAFE24_CLIENT_SECRET: Optional[str] = None
    CAFE24_ACCESS_TOKEN: Optional[str] = None
    CAFE24_API_VERSION: str = "2024-06-01"

    # Refund Policy Thresholds
    POLICY_FULL_REFUND_DAMAGE_RATIO: int = 30
    POLICY_PARTIAL_REFUND_DAMAGE_RATIO: int = 10
    POLICY_MAX_CLAIM_DAYS: int = 2
    POLICY_MIN_VISION_CONFIDENCE: float = 0.70

    # Security & Uploads
    CLAIM_IMAGE_MAX_SIZE_MB: int = 10
    ADMIN_API_KEY: str = "admin-dev-secret-key-change-in-prod"
    UPLOAD_DIR: str = "./uploads"

    # Commerce OAuth secret/token encryption key (Render 환경변수 ENCRYPTION_KEY).
    # 32-byte url-safe base64 값. 없으면 카페24 연동(저장/사용) 자체를 차단합니다.
    ENCRYPTION_KEY: Optional[str] = None

    @model_validator(mode="after")
    def _load_encryption_key_from_secret_file(self):
        """Fallback: if ENCRYPTION_KEY env var is unset, read it from a Render
        Secret File so Fernet encryption works without duplicating the value."""
        if not self.ENCRYPTION_KEY:
            for path in _SECRET_FILE_CANDIDATES:
                try:
                    if path.is_file():
                        value = path.read_text(encoding="utf-8").strip()
                        if value:
                            self.ENCRYPTION_KEY = value
                            break
                except Exception:
                    continue
        # Production must not ship with DEBUG left on by accident.
        if (self.APP_ENV or "").lower() == "production":
            self.DEBUG = False
        return self

    # Static Outbound IPs for Coupang Wing / Cafe24 / SmartStore IP Whitelist
    # Render dashboard > Connect > Outbound (shared by Render services in the same region)
    STATIC_OUTBOUND_IPS: str = "74.220.49.0/24, 74.220.57.0/24"
    OUTBOUND_PROXY_URL: Optional[str] = None


settings = Settings()
