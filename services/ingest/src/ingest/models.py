from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, HttpUrl


class FourState(StrEnum):
    YES = "YES"
    NO = "NO"
    UNKNOWN = "UNKNOWN"
    CONFLICTING = "CONFLICTING"


class BidEligibility(StrEnum):
    PUBLIC = "PUBLIC"
    NATURAL_PERSON_ALLOWED = "NATURAL_PERSON_ALLOWED"
    BUSINESS_ONLY = "BUSINESS_ONLY"
    LICENSED_RECYCLER_ONLY = "LICENSED_RECYCLER_ONLY"
    SPECIAL_QUALIFICATION = "SPECIAL_QUALIFICATION"
    BULK_PURCHASE_ONLY = "BULK_PURCHASE_ONLY"
    UNKNOWN = "UNKNOWN"


class RegistrationStatus(StrEnum):
    NORMAL_TRANSFER = "NORMAL_TRANSFER"
    RE_REGISTRATION_REQUIRED = "RE_REGISTRATION_REQUIRED"
    INSPECTION_REQUIRED = "INSPECTION_REQUIRED"
    REGISTRABILITY_UNKNOWN = "REGISTRABILITY_UNKNOWN"
    DEREGISTERED = "DEREGISTERED"
    CANNOT_RELICENSE = "CANNOT_RELICENSE"
    SCRAP_ONLY = "SCRAP_ONLY"
    EXPORT_ONLY = "EXPORT_ONLY"
    UNKNOWN = "UNKNOWN"


class AuctionStatus(StrEnum):
    DISCOVERED = "DISCOVERED"
    ANNOUNCED = "ANNOUNCED"
    SCHEDULED = "SCHEDULED"
    SOLD = "SOLD"
    UNSOLD = "UNSOLD"
    WITHDRAWN = "WITHDRAWN"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"
    UNKNOWN = "UNKNOWN"


class DiscoveredItem(BaseModel):
    source_record_id: str
    official_url: HttpUrl
    title: str
    discovery_url: HttpUrl
    recycler_only: bool = False
    result_record: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class RawArtifact(BaseModel):
    official_url: HttpUrl
    fetched_at: datetime
    mime_type: str
    filename: str | None = None
    content: bytes = Field(repr=False)
    http_status: int = 200
    http_headers: dict[str, str] = Field(default_factory=dict)
    checksum_sha256: str


class EvidenceRef(BaseModel):
    field_name: str
    normalized_value: Any
    source_text: str
    extraction_method: str = "HTML"
    trust: str = "OFFICIAL_EXPLICIT"
    confidence: float = Field(default=1.0, ge=0, le=1)
    table_row: str | None = None


class VehicleIdentifier(BaseModel):
    identifier_type: str
    normalized_value: str
    original_value: str


class ParsedVehicleUnit(BaseModel):
    source_vehicle_key: str
    identifiers: list[VehicleIdentifier] = Field(default_factory=list)


class ParsedAuctionRecord(BaseModel):
    source_record_id: str
    official_url: HttpUrl
    official_title: str
    official_case_number: str | None = None
    organization: str
    disposal_origin: str = "PUBLIC_ASSET_DISPOSAL"
    status: AuctionStatus = AuctionStatus.UNKNOWN
    auction_round: int | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    reserve_price: int | None = None
    current_price: int | None = None
    sold_price: int | None = None
    deposit: int | None = None
    payment_deadline: datetime | None = None
    pickup_deadline: datetime | None = None
    fee_notes: list[str] = Field(default_factory=list)
    title: str
    lot_size: int = 1
    bulk_lot: bool = False
    eligibility: BidEligibility = BidEligibility.UNKNOWN
    location: str | None = None
    description: str | None = None
    brand: str | None = None
    model: str | None = None
    manufacture_year: int | None = None
    manufacture_month: int | None = None
    displacement_cc: int | None = None
    color: str | None = None
    mileage_km: int | None = None
    has_key: FourState = FourState.UNKNOWN
    can_start: FourState = FourState.UNKNOWN
    can_test: FourState = FourState.UNKNOWN
    registration_status: RegistrationStatus = RegistrationStatus.UNKNOWN
    condition_summary: str | None = None
    visible_damage: str | None = None
    tax_arrears: FourState = FourState.UNKNOWN
    fine_arrears: FourState = FourState.UNKNOWN
    fuel_fee_arrears: FourState = FourState.UNKNOWN
    identifiers: list[VehicleIdentifier] = Field(default_factory=list)
    vehicle_units: list[ParsedVehicleUnit] = Field(default_factory=list)
    photo_urls: list[HttpUrl] = Field(default_factory=list)
    evidence: list[EvidenceRef] = Field(default_factory=list)
    completeness: int = Field(default=0, ge=0, le=100)
    completeness_groups: dict[str, int] = Field(default_factory=dict)


class SourceHealth(BaseModel):
    source: str
    status: str
    checked_at: datetime
    response_ms: int | None = None
    message: str
    warnings: list[str] = Field(default_factory=list)


class SyncResult(BaseModel):
    source: str
    discovered: int
    fetched: int
    parsed: int
    changed: int
    failed: int
    warnings: list[str] = Field(default_factory=list)
