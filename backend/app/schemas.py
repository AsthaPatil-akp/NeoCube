from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

PublicRole = Literal["CLIENT", "SUPPLIER"]


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    role: PublicRole
    full_name: str = Field(min_length=1, max_length=200)
    company_name: str = Field(min_length=1, max_length=200)
    phone: str | None = Field(default=None, max_length=50)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).lower()

    @field_validator("full_name", "company_name")
    @classmethod
    def strip_required(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be empty")
        return value

    @field_validator("phone")
    @classmethod
    def strip_phone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=72)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).lower()


class ProfileUpdateRequest(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=200)
    phone: str | None = Field(default=None, max_length=50)
    company_name: str | None = Field(default=None, min_length=1, max_length=200)

    @field_validator("full_name", "company_name")
    @classmethod
    def strip_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("must not be empty")
        return value

    @field_validator("phone")
    @classmethod
    def strip_phone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class UserResponse(BaseModel):
    id: int
    email: str
    role: str
    full_name: str
    phone: str | None
    company_name: str | None
    profile_photo_url: str | None = None
    is_active: bool
    created_at: datetime


class CategoryResponse(BaseModel):
    id: int
    name: str
    is_active: bool
    is_predefined: bool = True


class RequirementCreateRequest(BaseModel):
    company_name: str = Field(min_length=1, max_length=200)
    product_requirement: str = Field(min_length=1, max_length=300)
    category_id: int
    custom_category: str | None = Field(default=None, max_length=200)
    quantity: int = Field(gt=0)
    quantity_unit: str | None = Field(default=None, max_length=40)
    budget: int = Field(ge=0)
    budget_currency: str | None = Field(default=None, max_length=8)
    budget_basis: Literal["TOTAL", "PER_UNIT"] | None = None
    location: str = Field(min_length=1, max_length=200)
    delivery_timeline: str = Field(min_length=1, max_length=100)
    additional_notes: str | None = Field(default=None, max_length=2000)
    status: Literal["DRAFT", "SUBMITTED"] = "SUBMITTED"
    document_id: int | None = None

    @field_validator("company_name", "product_requirement", "location", "delivery_timeline")
    @classmethod
    def strip_required_fields(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be empty")
        return value

    @field_validator("additional_notes", "custom_category", "quantity_unit", "budget_currency")
    @classmethod
    def strip_notes(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class RequirementUpdateRequest(BaseModel):
    company_name: str | None = Field(default=None, min_length=1, max_length=200)
    product_requirement: str | None = Field(default=None, min_length=1, max_length=300)
    category_id: int | None = None
    custom_category: str | None = Field(default=None, max_length=200)
    quantity: int | None = Field(default=None, gt=0)
    quantity_unit: str | None = Field(default=None, max_length=40)
    budget: int | None = Field(default=None, ge=0)
    budget_currency: str | None = Field(default=None, max_length=8)
    budget_basis: Literal["TOTAL", "PER_UNIT"] | None = None
    location: str | None = Field(default=None, min_length=1, max_length=200)
    delivery_timeline: str | None = Field(default=None, min_length=1, max_length=100)
    additional_notes: str | None = Field(default=None, max_length=2000)
    status: str | None = None
    document_id: int | None = None

    @field_validator(
        "company_name",
        "product_requirement",
        "location",
        "delivery_timeline",
    )
    @classmethod
    def strip_optional_required(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("must not be empty")
        return value

    @field_validator("additional_notes", "custom_category", "quantity_unit", "budget_currency")
    @classmethod
    def strip_notes(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class MatchSummary(BaseModel):
    id: int
    offering_id: int
    product_offered: str
    supplier_name: str
    location: str
    category_name: str
    available_quantity: int | None = None
    quantity_unit: str | None = None
    pricing_details: str | None = None
    price_amount: int | None = None
    price_currency: str | None = None
    price_basis: str | None = None
    delivery_capability: str | None = None
    semantic_score: float | None = None
    ml_score: float | None = None
    structured_score: float | None = None
    final_score: float | None = None
    match_status: str = "NEW"
    explanation: list[str] = []
    model_version: str | None = None
    rfq_id: int | None = None
    rfq_status: str | None = None
    supplier_id: int | None = None


class RequirementResponse(BaseModel):
    id: int
    company_name: str
    product_requirement: str
    category_id: int
    category_name: str
    custom_category: str | None = None
    quantity: int
    quantity_unit: str | None = None
    budget: int
    budget_currency: str | None = None
    budget_basis: str | None = None
    location: str
    delivery_timeline: str
    additional_notes: str | None
    status: str
    match_count: int
    created_at: datetime
    updated_at: datetime
    matches: list[MatchSummary] = []


class OfferingCreateRequest(BaseModel):
    supplier_name: str = Field(min_length=1, max_length=200)
    product_offered: str = Field(min_length=1, max_length=300)
    category_id: int
    custom_category: str | None = Field(default=None, max_length=200)
    available_quantity: int = Field(gt=0)
    quantity_unit: str | None = Field(default=None, max_length=40)
    pricing_details: str | None = Field(default=None, max_length=300)
    price_amount: int | None = Field(default=None, ge=0)
    price_currency: str | None = Field(default=None, max_length=8)
    price_basis: Literal["TOTAL", "PER_UNIT"] | None = None
    location: str = Field(min_length=1, max_length=200)
    delivery_capability: str = Field(min_length=1, max_length=200)
    additional_notes: str | None = Field(default=None, max_length=2000)
    status: Literal["DRAFT", "ACTIVE"] = "ACTIVE"
    document_id: int | None = None

    @field_validator(
        "supplier_name",
        "product_offered",
        "location",
        "delivery_capability",
    )
    @classmethod
    def strip_required_fields(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be empty")
        return value

    @field_validator(
        "additional_notes",
        "custom_category",
        "quantity_unit",
        "price_currency",
        "pricing_details",
    )
    @classmethod
    def strip_notes(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @model_validator(mode="after")
    def require_price(self):
        if self.price_amount is None and not self.pricing_details:
            raise ValueError("price_amount or pricing_details is required")
        return self


class OfferingUpdateRequest(BaseModel):
    supplier_name: str | None = Field(default=None, min_length=1, max_length=200)
    product_offered: str | None = Field(default=None, min_length=1, max_length=300)
    category_id: int | None = None
    custom_category: str | None = Field(default=None, max_length=200)
    available_quantity: int | None = Field(default=None, gt=0)
    quantity_unit: str | None = Field(default=None, max_length=40)
    pricing_details: str | None = Field(default=None, min_length=1, max_length=300)
    price_amount: int | None = Field(default=None, ge=0)
    price_currency: str | None = Field(default=None, max_length=8)
    price_basis: Literal["TOTAL", "PER_UNIT"] | None = None
    location: str | None = Field(default=None, min_length=1, max_length=200)
    delivery_capability: str | None = Field(default=None, min_length=1, max_length=200)
    additional_notes: str | None = Field(default=None, max_length=2000)
    status: str | None = None

    @field_validator(
        "supplier_name",
        "product_offered",
        "location",
        "delivery_capability",
    )
    @classmethod
    def strip_optional_required(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("must not be empty")
        return value

    @field_validator(
        "additional_notes",
        "custom_category",
        "quantity_unit",
        "price_currency",
        "pricing_details",
    )
    @classmethod
    def strip_notes(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class RequirementMatchSummary(BaseModel):
    id: int
    requirement_id: int
    product_requirement: str
    company_name: str
    location: str
    quantity: int
    category_name: str
    status: str
    semantic_score: float | None = None
    ml_score: float | None = None
    final_score: float | None = None
    match_status: str = "NEW"
    explanation: list[str] = []


class OfferingResponse(BaseModel):
    id: int
    supplier_name: str
    product_offered: str
    category_id: int
    category_name: str
    custom_category: str | None = None
    available_quantity: int
    quantity_unit: str | None = None
    pricing_details: str
    price_amount: int | None = None
    price_currency: str | None = None
    price_basis: str | None = None
    location: str
    delivery_capability: str
    additional_notes: str | None
    status: str
    match_count: int
    created_at: datetime
    updated_at: datetime
    matches: list[RequirementMatchSummary] = []
    has_product_image: bool = False
    product_image_url: str | None = None
    product_image_indexed: bool = False
    product_image_source: str | None = None


class NotificationResponse(BaseModel):
    id: int
    title: str
    message: str
    is_read: bool
    notification_type: str = "INFO"
    related_type: str | None = None
    related_id: int | None = None
    created_at: datetime


class ClearNotificationsRequest(BaseModel):
    ids: list[int] = Field(min_length=1)


class RfqCreateRequest(BaseModel):
    match_id: int
    notes: str | None = Field(default=None, max_length=2000)


class QuotationCreateRequest(BaseModel):
    unit_price: int = Field(gt=0)
    quantity: int = Field(gt=0)
    shipping: int = Field(default=0, ge=0)
    tax: int = Field(default=0, ge=0)
    additional_charges: int = Field(default=0, ge=0)
    delivery: str = Field(min_length=1, max_length=200)
    validity_days: int = Field(gt=0, le=365)
    payment_terms: str = Field(min_length=1, max_length=200)
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("delivery", "payment_terms")
    @classmethod
    def strip_quote_fields(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be empty")
        return value


class QuotationResponse(BaseModel):
    id: int
    rfq_id: int
    unit_price: int
    quantity: int
    shipping: int
    tax: int
    additional_charges: int
    subtotal: int
    total: int
    delivery: str
    validity_days: int
    payment_terms: str
    notes: str | None
    status: str
    created_at: datetime


class OrderTrackingResponse(BaseModel):
    rfq_id: int
    current_status: str
    payment_status: str
    shipment_status: str
    received_status: str
    completed: bool
    payment_at: datetime | None = None
    shipped_at: datetime | None = None
    received_at: datetime | None = None
    completed_at: datetime | None = None
    shipment_code: str | None = None
    demo_otp: str | None = None
    otp_expires_at: datetime | None = None
    otp_verified: bool = False
    otp_expired: bool = False


class VerifyOtpRequest(BaseModel):
    otp: str


class ReviewCreateRequest(BaseModel):
    rating: int = Field(ge=1, le=5)
    feedback: str | None = Field(default=None, max_length=2000)

    @field_validator("feedback")
    @classmethod
    def strip_feedback(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class ReviewOwnResponse(BaseModel):
    id: int
    rfq_id: int
    rating: int
    feedback: str | None = None
    created_at: datetime


class ReviewPublicResponse(BaseModel):
    id: int
    rating: int
    feedback: str | None = None
    client_name: str
    verified: bool = True
    created_at: datetime


class SupplierOfferingPublic(BaseModel):
    id: int
    product_offered: str
    category_name: str
    custom_category: str | None = None
    available_quantity: int
    quantity_unit: str | None = None
    pricing_details: str | None = None
    price_amount: int | None = None
    price_currency: str | None = None
    price_basis: str | None = None
    location: str
    delivery_capability: str
    additional_notes: str | None = None
    status: str


class SupplierPublicProfile(BaseModel):
    id: int
    company_name: str
    categories: list[str] = []
    offerings: list[SupplierOfferingPublic] = []
    average_rating: float | None = None
    review_count: int = 0
    reviews: list[ReviewPublicResponse] = []


class RfqResponse(BaseModel):
    id: int
    requirement_id: int
    offering_id: int
    match_id: int | None
    client_user_id: int
    supplier_user_id: int
    notes: str | None
    status: str
    product_requirement: str | None = None
    product_offered: str | None = None
    client_name: str | None = None
    supplier_name: str | None = None
    category_name: str | None = None
    quantity: int | None = None
    budget: int | None = None
    budget_currency: str | None = None
    location: str | None = None
    delivery_timeline: str | None = None
    additional_notes: str | None = None
    match_score: float | None = None
    match_explanation: str | None = None
    created_at: datetime
    quotations: list[QuotationResponse] = []
    tracking: OrderTrackingResponse | None = None
    supplier_id: int | None = None
    can_review: bool = False
    review: ReviewOwnResponse | None = None


class AdminSummaryResponse(BaseModel):
    users: int
    clients: int
    suppliers: int
    requirements: int
    offerings: int
    matches: int
    rfqs: int
    quotations: int
    audit_logs: int = 0


class AuditLogResponse(BaseModel):
    id: int
    action: str
    entity_type: str | None
    entity_id: int | None
    created_at: datetime


class ExtractedFields(BaseModel):
    company_name: str | None = None
    product_requirement: str | None = None
    product: str | None = None
    category_id: int | None = None
    category_label: str | None = None
    custom_category: str | None = None
    quantity: int | None = None
    quantity_unit: str | None = None
    budget: int | None = None
    budget_amount: int | None = None
    budget_currency: str | None = None
    budget_basis: str | None = None
    price_amount: int | None = None
    price_currency: str | None = None
    price_basis: str | None = None
    location: str | None = None
    delivery_timeline: str | None = None
    delivery_days: int | None = None
    additional_notes: str | None = None


class DocumentExtractResponse(BaseModel):
    id: int
    original_filename: str
    file_type: str
    processing_status: str
    extracted: ExtractedFields
    error_message: str | None = None


class AiProductFinderStatus(BaseModel):
    enabled: bool = True
    model_available: bool
    model_version: str | None = None
    embedding_dimension: int | None = None
    number_of_indexed_supplier_images: int = 0
    message: str | None = None


class AiVisualMatchResult(BaseModel):
    supplier_id: int
    offering_id: int
    supplier_name: str
    product_offered: str
    category_name: str
    location: str
    available_quantity: int
    quantity_unit: str | None = None
    visual_similarity: float
    model_version: str
    product_image_url: str | None = None


class AiProductFinderSearchResponse(BaseModel):
    results: list[AiVisualMatchResult]
    result_count: int
    message: str | None = None


class ProductImageCandidate(BaseModel):
    candidate_id: str
    preview_url: str
    width: int
    height: int
    source_hint: str | None = None


class ExtractProductImagesResponse(BaseModel):
    offering_id: int | None = None
    document_id: int | None = None
    candidates: list[ProductImageCandidate]
    message: str | None = None


class SelectProductImageRequest(BaseModel):
    candidate_id: str
    document_id: int | None = None
