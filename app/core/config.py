from typing import List, Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    AI_DEFAULT_PROVIDER: str = "groq"
    AI_FALLBACK_PROVIDER: str = "nvidia"
    AI_VISION_PROVIDER: str = "gemini"

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

    # Static Outbound IPs for Coupang Wing / Cafe24 / SmartStore IP Whitelist
    # Render dashboard > Connect > Outbound (shared by Render services in the same region)
    STATIC_OUTBOUND_IPS: str = "74.220.49.0/24, 74.220.57.0/24"
    OUTBOUND_PROXY_URL: Optional[str] = None


settings = Settings()
