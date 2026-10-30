from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class UserModel(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    username: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    role: Mapped[str] = mapped_column(String(32), default="customer")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class StoreModel(Base):
    __tablename__ = "stores"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    mall_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    store_name: Mapped[str] = mapped_column(String(128), index=True)
    industry: Mapped[str] = mapped_column(String(32), default="fresh_food")  # fresh_food, electronics, fashion, beauty, general
    as_type: Mapped[str] = mapped_column(String(64), default="refund_and_warranty")
    theme_color: Mapped[str] = mapped_column(String(16), default="#2E7D32")
    policy_config_json: Mapped[str] = mapped_column(Text, default="{}")
    welcome_message: Mapped[str] = mapped_column(Text, default="")
    plan_type: Mapped[str] = mapped_column(String(32), default="free_trial")  # free_trial, active, unlimited, suspended
    trial_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=30)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    webhook_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    allowed_domains: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)  # comma-separated domains or *
    daily_quota_limit: Mapped[int] = mapped_column(Integer, default=300)
    daily_quota_used: Mapped[int] = mapped_column(Integer, default=0)
    quota_reset_date: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    bot_icon_style: Mapped[str] = mapped_column(String(64), default="flaticon_cute_robot")
    launcher_shape: Mapped[str] = mapped_column(String(32), default="cosbot_badge")
    bot_label: Mapped[str] = mapped_column(String(32), default="코스봇 상담")
    bot_name: Mapped[str] = mapped_column(String(64), default="코스봇")
    brand_badge: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    header_title: Mapped[str] = mapped_column(String(64), default="고객상담센터")
    chat_template: Mapped[str] = mapped_column(String(32), default="cosraw_grid")
    quick_buttons_json: Mapped[str] = mapped_column(Text, default="[]")
    contact_email: Mapped[str] = mapped_column(String(128), default="help@store.co.kr")
    business_hours: Mapped[str] = mapped_column(String(64), default="365일 24시간")
    input_placeholder: Mapped[str] = mapped_column(
        String(128), default="궁금한 상품명이나 질문(또는 주문번호)을 입력하세요..."
    )
    bot_avatar_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    brand_logo_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class StoreKnowledgeModel(Base):
    __tablename__ = "store_knowledge"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    mall_id: Mapped[str] = mapped_column(String(64), index=True)
    doc_type: Mapped[str] = mapped_column(String(32), default="product")  # product, policy, faq, crawled_url
    title: Mapped[str] = mapped_column(String(256))
    content: Mapped[str] = mapped_column(Text)
    source_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    price: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    original_price: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    purchase_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    image_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    tags: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class WebhookAlertLogModel(Base):
    __tablename__ = "webhook_alert_logs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    mall_id: Mapped[str] = mapped_column(String(64), index=True)
    claim_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    alert_type: Mapped[str] = mapped_column(String(64))  # ESCALATE_TO_HUMAN, HIGH_VALUE_CLAIM, TRIAL_EXPIRING
    webhook_url: Mapped[str] = mapped_column(String(512))
    payload_json: Mapped[str] = mapped_column(Text)
    delivery_status: Mapped[str] = mapped_column(String(32))  # SENT, MOCK_LOGGED, FAILED
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class SessionModel(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    customer_id: Mapped[str] = mapped_column(String(64), index=True)
    mall_id: Mapped[str] = mapped_column(String(64), default="demo_mall", index=True)
    channel: Mapped[str] = mapped_column(String(32), default="web_widget")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    messages: Mapped[list["MessageModel"]] = relationship(
        "MessageModel", back_populates="session", cascade="all, delete-orphan"
    )


class MessageModel(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("sessions.id"), index=True
    )
    role: Mapped[str] = mapped_column(String(16))  # user, assistant, system
    content: Mapped[str] = mapped_column(Text)
    intent: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # Owner-side translation support (foreign customer messages)
    detected_language: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    translation_ko: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    session: Mapped["SessionModel"] = relationship("SessionModel", back_populates="messages")


class ProductModel(Base):
    __tablename__ = "products"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(256), index=True)
    category: Mapped[str] = mapped_column(String(64), default="fresh_food")
    price: Mapped[int] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(Text)
    storage_method: Mapped[str] = mapped_column(Text, default="")
    intake_guide: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class DocumentModel(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    doc_type: Mapped[str] = mapped_column(String(32), index=True)  # faq, policy, product
    title: Mapped[str] = mapped_column(String(256))
    content: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class OrderCacheModel(Base):
    __tablename__ = "orders_cache"

    order_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    customer_id: Mapped[str] = mapped_column(String(64), index=True)
    mall_id: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32))
    total_amount: Mapped[int] = mapped_column(Integer, default=0)
    payload_json: Mapped[str] = mapped_column(Text)
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class ClaimModel(Base):
    __tablename__ = "claims"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    mall_id: Mapped[str] = mapped_column(String(64), default="demo_mall", index=True)
    order_id: Mapped[str] = mapped_column(String(64), index=True)
    customer_id: Mapped[str] = mapped_column(String(64), index=True)
    claim_type: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), index=True)
    refund_amount: Mapped[int] = mapped_column(Integer, default=0)
    description: Mapped[str] = mapped_column(Text)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(128), unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    images: Mapped[list["ClaimImageModel"]] = relationship(
        "ClaimImageModel", back_populates="claim", cascade="all, delete-orphan"
    )
    events: Mapped[list["ClaimEventModel"]] = relationship(
        "ClaimEventModel", back_populates="claim", cascade="all, delete-orphan"
    )


class ClaimImageModel(Base):
    __tablename__ = "claim_images"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    claim_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("claims.id"), index=True
    )
    file_path: Mapped[str] = mapped_column(String(512))
    file_hash: Mapped[str] = mapped_column(String(64), index=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=True)
    defect_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    damage_ratio: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    evidence_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    image_quality: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    claim: Mapped["ClaimModel"] = relationship("ClaimModel", back_populates="images")


class ClaimEventModel(Base):
    __tablename__ = "claim_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    claim_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("claims.id"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(64))
    from_status: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    to_status: Mapped[str] = mapped_column(String(32))
    actor: Mapped[str] = mapped_column(String(64))
    reason: Mapped[str] = mapped_column(Text)
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    claim: Mapped["ClaimModel"] = relationship("ClaimModel", back_populates="events")


class RefundDecisionModel(Base):
    __tablename__ = "refund_decisions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    claim_id: Mapped[str] = mapped_column(String(64), index=True)
    decision: Mapped[str] = mapped_column(String(32))
    reason_code: Mapped[str] = mapped_column(String(64))
    refund_ratio: Mapped[int] = mapped_column(Integer, default=0)
    refund_amount: Mapped[int] = mapped_column(Integer, default=0)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    execution_status: Mapped[str] = mapped_column(String(32), default="PENDING")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class ProviderEventModel(Base):
    __tablename__ = "provider_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    provider: Mapped[str] = mapped_column(String(32), index=True)
    model: Mapped[str] = mapped_column(String(64))
    task_type: Mapped[str] = mapped_column(String(32))
    latency_ms: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32))  # success, error, rate_limited
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class CommerceConnectionModel(Base):
    """Per-mall live commerce (e.g. Cafe24) OAuth connection & token storage.

    Secrets and tokens are stored Fernet-encrypted. status:
      - pending:       keys saved but owner has not clicked "허용" (OAuth not completed)
      - connected:     OAuth completed, access+refresh tokens stored
      - refresh_expired: refresh token expired, owner must re-authorize
    """

    __tablename__ = "commerce_connections"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    mall_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    platform: Mapped[str] = mapped_column(String(32), default="cafe24")
    cafe24_mall_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    client_id: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    client_secret_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    client_secret_masked: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    access_token_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    refresh_token_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    access_token_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    refresh_token_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(String(32), default="pending")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
