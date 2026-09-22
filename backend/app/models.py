from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)

    users: Mapped[list["User"]] = relationship(back_populates="role")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(50))
    profile_photo: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )

    role: Mapped[Role] = relationship(back_populates="users")
    client_profile: Mapped["ClientProfile | None"] = relationship(
        back_populates="user", cascade="all, delete-orphan", uselist=False
    )
    supplier_profile: Mapped["SupplierProfile | None"] = relationship(
        back_populates="user", cascade="all, delete-orphan", uselist=False
    )
    notifications: Mapped[list["Notification"]] = relationship(back_populates="user")


class ClientProfile(Base):
    __tablename__ = "client_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    company_name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )

    user: Mapped[User] = relationship(back_populates="client_profile")
    requirements: Mapped[list["ClientRequirement"]] = relationship(back_populates="client")


class SupplierProfile(Base):
    __tablename__ = "supplier_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    company_name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )

    user: Mapped[User] = relationship(back_populates="supplier_profile")
    offerings: Mapped[list["SupplierOffering"]] = relationship(back_populates="supplier")


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_predefined: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )


class ClientRequirement(Base):
    __tablename__ = "client_requirements"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(
        ForeignKey("client_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"), nullable=False, index=True)
    company_name: Mapped[str] = mapped_column(String(200), nullable=False)
    product_requirement: Mapped[str] = mapped_column(String(300), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity_unit: Mapped[str | None] = mapped_column(String(40))
    budget: Mapped[int] = mapped_column(Integer, nullable=False)
    budget_currency: Mapped[str | None] = mapped_column(String(8))
    budget_basis: Mapped[str | None] = mapped_column(String(16))
    custom_category: Mapped[str | None] = mapped_column(String(200))
    location: Mapped[str] = mapped_column(String(200), nullable=False)
    delivery_timeline: Mapped[str] = mapped_column(String(100), nullable=False)
    additional_notes: Mapped[str | None] = mapped_column(String(2000))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="DRAFT", index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )

    client: Mapped[ClientProfile] = relationship(back_populates="requirements")
    category: Mapped[Category] = relationship()
    documents: Mapped[list["RequirementDocument"]] = relationship(back_populates="requirement")
    matches: Mapped[list["Match"]] = relationship(back_populates="requirement", cascade="all, delete-orphan")


class SupplierOffering(Base):
    __tablename__ = "supplier_offerings"

    id: Mapped[int] = mapped_column(primary_key=True)
    supplier_id: Mapped[int] = mapped_column(
        ForeignKey("supplier_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"), nullable=False, index=True)
    supplier_name: Mapped[str] = mapped_column(String(200), nullable=False)
    product_offered: Mapped[str] = mapped_column(String(300), nullable=False)
    available_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity_unit: Mapped[str | None] = mapped_column(String(40))
    pricing_details: Mapped[str] = mapped_column(String(300), nullable=False)
    price_amount: Mapped[int | None] = mapped_column(Integer)
    price_currency: Mapped[str | None] = mapped_column(String(8))
    price_basis: Mapped[str | None] = mapped_column(String(16))
    custom_category: Mapped[str | None] = mapped_column(String(200))
    location: Mapped[str] = mapped_column(String(200), nullable=False)
    delivery_capability: Mapped[str] = mapped_column(String(200), nullable=False)
    additional_notes: Mapped[str | None] = mapped_column(String(2000))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="DRAFT", index=True)
    product_image_path: Mapped[str | None] = mapped_column(String(255))
    product_image_filename: Mapped[str | None] = mapped_column(String(255))
    product_image_mime_type: Mapped[str | None] = mapped_column(String(80))
    product_image_source: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )

    supplier: Mapped[SupplierProfile] = relationship(back_populates="offerings")
    category: Mapped[Category] = relationship()
    matches: Mapped[list["Match"]] = relationship(back_populates="offering", cascade="all, delete-orphan")
    image_embedding: Mapped["ProductImageEmbedding | None"] = relationship(
        back_populates="offering", cascade="all, delete-orphan", uselist=False
    )


class RequirementDocument(Base):
    __tablename__ = "requirement_documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    requirement_id: Mapped[int | None] = mapped_column(
        ForeignKey("client_requirements.id", ondelete="SET NULL"), index=True
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str] = mapped_column(String(20), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    processing_status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING")
    extracted_json: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )

    requirement: Mapped[ClientRequirement | None] = relationship(back_populates="documents")


class SupplierDocument(Base):
    __tablename__ = "supplier_documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    offering_id: Mapped[int | None] = mapped_column(
        ForeignKey("supplier_offerings.id", ondelete="SET NULL"), index=True
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str] = mapped_column(String(20), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    processing_status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING")
    extracted_json: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )


class Match(Base):
    __tablename__ = "matches"
    __table_args__ = (UniqueConstraint("requirement_id", "offering_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    requirement_id: Mapped[int] = mapped_column(
        ForeignKey("client_requirements.id", ondelete="CASCADE"), nullable=False, index=True
    )
    offering_id: Mapped[int] = mapped_column(
        ForeignKey("supplier_offerings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    semantic_score: Mapped[float | None] = mapped_column(Float)
    ml_score: Mapped[float | None] = mapped_column(Float)
    structured_score: Mapped[float | None] = mapped_column(Float)
    final_score: Mapped[float | None] = mapped_column(Float)
    match_status: Mapped[str] = mapped_column(String(32), nullable=False, default="NEW")
    explanation: Mapped[str | None] = mapped_column(Text)
    model_version: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )

    requirement: Mapped[ClientRequirement] = relationship(back_populates="matches")
    offering: Mapped[SupplierOffering] = relationship(back_populates="matches")
    rfqs: Mapped[list["Rfq"]] = relationship(back_populates="match")


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    message: Mapped[str] = mapped_column(String(1000), nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notification_type: Mapped[str] = mapped_column(String(40), nullable=False, default="INFO")
    related_type: Mapped[str | None] = mapped_column(String(80))
    related_id: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )

    user: Mapped[User] = relationship(back_populates="notifications")


class Rfq(Base):
    __tablename__ = "rfqs"
    __table_args__ = (UniqueConstraint("requirement_id", "offering_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    requirement_id: Mapped[int] = mapped_column(
        ForeignKey("client_requirements.id", ondelete="CASCADE"), nullable=False, index=True
    )
    offering_id: Mapped[int] = mapped_column(
        ForeignKey("supplier_offerings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    match_id: Mapped[int | None] = mapped_column(ForeignKey("matches.id", ondelete="SET NULL"), index=True)
    client_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    supplier_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    notes: Mapped[str | None] = mapped_column(String(2000))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="SENT")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )

    match: Mapped[Match | None] = relationship(back_populates="rfqs")
    quotations: Mapped[list["Quotation"]] = relationship(back_populates="rfq")
    track: Mapped["OrderTrack | None"] = relationship(back_populates="rfq", uselist=False)
    review: Mapped["SupplierReview | None"] = relationship(back_populates="rfq", uselist=False)


class Quotation(Base):
    __tablename__ = "quotations"

    id: Mapped[int] = mapped_column(primary_key=True)
    rfq_id: Mapped[int] = mapped_column(ForeignKey("rfqs.id", ondelete="CASCADE"), nullable=False, index=True)
    unit_price: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    shipping: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tax: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    additional_charges: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    subtotal: Mapped[int] = mapped_column(Integer, nullable=False)
    total: Mapped[int] = mapped_column(Integer, nullable=False)
    delivery: Mapped[str] = mapped_column(String(200), nullable=False)
    validity_days: Mapped[int] = mapped_column(Integer, nullable=False)
    payment_terms: Mapped[str] = mapped_column(String(200), nullable=False)
    notes: Mapped[str | None] = mapped_column(String(2000))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="SENT")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )

    rfq: Mapped[Rfq] = relationship(back_populates="quotations")


class OrderTrack(Base):
    __tablename__ = "order_tracks"

    id: Mapped[int] = mapped_column(primary_key=True)
    rfq_id: Mapped[int] = mapped_column(ForeignKey("rfqs.id", ondelete="CASCADE"), unique=True, nullable=False)
    client_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    supplier_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    current_status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACCEPTED")
    payment_status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING")
    shipment_status: Mapped[str] = mapped_column(String(32), nullable=False, default="NOT_SHIPPED")
    received_status: Mapped[str] = mapped_column(String(32), nullable=False, default="NOT_RECEIVED")
    completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    payment_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    shipped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    shipment_code: Mapped[str | None] = mapped_column(String(40))
    otp_hash: Mapped[str | None] = mapped_column(String(128))
    otp_code: Mapped[str | None] = mapped_column(String(6))
    otp_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    otp_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    otp_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )

    rfq: Mapped[Rfq] = relationship(back_populates="track")


class SupplierReview(Base):
    __tablename__ = "supplier_reviews"
    __table_args__ = (UniqueConstraint("rfq_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    rfq_id: Mapped[int] = mapped_column(ForeignKey("rfqs.id", ondelete="CASCADE"), unique=True, nullable=False)
    supplier_id: Mapped[int] = mapped_column(
        ForeignKey("supplier_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    client_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    feedback: Mapped[str | None] = mapped_column(String(2000))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )

    rfq: Mapped[Rfq] = relationship(back_populates="review")
    supplier: Mapped[SupplierProfile] = relationship()
    client: Mapped[User] = relationship()


class ProductImageEmbedding(Base):
    __tablename__ = "product_image_embeddings"
    __table_args__ = (UniqueConstraint("supplier_offering_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    supplier_offering_id: Mapped[int] = mapped_column(
        ForeignKey("supplier_offerings.id", ondelete="CASCADE"), unique=True, nullable=False, index=True
    )
    model_version: Mapped[str] = mapped_column(String(80), nullable=False)
    embedding: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )

    offering: Mapped[SupplierOffering] = relationship(back_populates="image_embedding")


class N8nEmittedEvent(Base):
    """App-side idempotency for outbound n8n POSTs. Not the n8n Data Table row id."""

    __tablename__ = "n8n_emitted_events"

    event_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    event_type: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(80))
    entity_id: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
