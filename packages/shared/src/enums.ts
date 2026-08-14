export const AUCTION_STATUSES = [
  "DISCOVERED", "ANNOUNCED", "SCHEDULED", "SOLD", "UNSOLD",
  "WITHDRAWN", "CANCELLED", "EXPIRED", "UNKNOWN",
] as const;
export type AuctionStatus = (typeof AUCTION_STATUSES)[number];

export const DISPOSAL_ORIGINS = [
  "JUDICIAL_EXECUTION", "ADMINISTRATIVE_ENFORCEMENT",
  "CRIMINAL_SEIZURE_OR_FORFEITURE", "IMPOUNDED_UNCLAIMED",
  "PUBLIC_ASSET_DISPOSAL", "CUSTOMS_FORFEITURE", "SCRAP_DISPOSAL",
  "OTHER", "UNKNOWN",
] as const;
export type DisposalOrigin = (typeof DISPOSAL_ORIGINS)[number];

export const BID_ELIGIBILITIES = [
  "PUBLIC", "NATURAL_PERSON_ALLOWED", "BUSINESS_ONLY",
  "LICENSED_RECYCLER_ONLY", "SPECIAL_QUALIFICATION",
  "BULK_PURCHASE_ONLY", "UNKNOWN",
] as const;
export type BidEligibility = (typeof BID_ELIGIBILITIES)[number];

export const REGISTRATION_STATUSES = [
  "NORMAL_TRANSFER", "RE_REGISTRATION_REQUIRED", "INSPECTION_REQUIRED",
  "REGISTRABILITY_UNKNOWN", "DEREGISTERED", "CANNOT_RELICENSE",
  "SCRAP_ONLY", "EXPORT_ONLY", "UNKNOWN",
] as const;
export type RegistrationStatus = (typeof REGISTRATION_STATUSES)[number];

export const MOTORCYCLE_CLASSES = [
  "ORDINARY_LIGHT", "ORDINARY_HEAVY", "LARGE_HEAVY",
  "ELECTRIC_MOTORCYCLE", "HEAVY_UNSPECIFIED", "UNKNOWN",
] as const;
export type MotorcycleClass = (typeof MOTORCYCLE_CLASSES)[number];

export const DISPLACEMENT_BANDS = [
  "LE_50", "CC_51_125", "CC_126_250", "CC_251_550", "GT_550", "UNKNOWN",
] as const;
export type DisplacementBand = (typeof DISPLACEMENT_BANDS)[number];

export const FOUR_STATES = ["YES", "NO", "UNKNOWN", "CONFLICTING"] as const;
export type FourState = (typeof FOUR_STATES)[number];

export const SOURCE_TRUSTS = [
  "OFFICIAL_EXPLICIT", "OFFICIAL_INFERRED", "CROSS_SOURCE_CONFIRMED",
  "SYSTEM_CALCULATED", "LLM_EXTRACTED", "THIRD_PARTY_REFERENCE", "UNKNOWN",
] as const;
export type SourceTrust = (typeof SOURCE_TRUSTS)[number];

export const ADAPTER_STATUSES = ["PLANNED", "PARTIAL", "ACTIVE", "DEGRADED", "DISABLED"] as const;
export type AdapterStatus = (typeof ADAPTER_STATUSES)[number];

export const EXTRACTION_METHODS = ["STRUCTURED", "HTML", "DOCUMENT_RULE", "OCR", "LLM"] as const;
export type ExtractionMethod = (typeof EXTRACTION_METHODS)[number];
