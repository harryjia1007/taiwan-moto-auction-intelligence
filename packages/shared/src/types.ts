import type {
  AdapterStatus, AuctionStatus, BidEligibility, DisposalOrigin, DisplacementBand,
  FourState, MotorcycleClass, RegistrationStatus, SourceTrust,
} from "./enums";

export interface Evidence {
  id: string;
  fieldName: string;
  sourceText: string;
  officialUrl: string;
  trust: SourceTrust;
  confidence: number;
  artifactId?: string;
}

export interface PricePoint {
  observedAt: string;
  round: number | null;
  reservePrice: number | null;
  currentPrice: number | null;
  soldPrice: number | null;
  status: AuctionStatus;
}

export interface DuplicateCandidate {
  id: string;
  counterpartVehicleId: string;
  score: number;
  reviewStatus: "PENDING" | "CONFIRMED" | "REJECTED";
  matchingSignals: Record<string, unknown>;
}

export interface AuctionDocument {
  id: string;
  title: string;
  documentType: string | null;
  url: string;
  cached: boolean;
}

export interface Motorcycle {
  id: string;
  source: string;
  sourceName: string;
  sourceFamily: string;
  favoriteSupported: boolean;
  sourceRecordId: string;
  sourceAuid: string;
  officialUrl: string;
  officialTitle: string;
  name: string;
  brand: string | null;
  model: string | null;
  manufactureYear: number | null;
  manufactureMonth: number | null;
  displacementCc: number | null;
  vehicleClass: MotorcycleClass;
  plateNumber: string | null;
  color: string | null;
  organization: string;
  location: string | null;
  county: string | null;
  disposalOrigin: DisposalOrigin;
  auctionStatus: AuctionStatus;
  auctionRound: number | null;
  auctionAt: string | null;
  auctionDatePrecision?: "DATE" | "DATETIME";
  reservePrice: number | null;
  currentPrice: number | null;
  soldPrice: number | null;
  deposit: number | null;
  paymentDeadline: string | null;
  pickupDeadline: string | null;
  feeNotes: string[];
  bidEligibility: BidEligibility;
  registrationStatus: RegistrationStatus;
  hasKey: FourState;
  canStart: FourState;
  canTest: FourState;
  mileageKm: number | null;
  lotSize: number;
  bulkLot: boolean;
  conditionSummary: string | null;
  riskBadges: string[];
  imageUrl: string | null;
  imageUrls?: string[];
  mediaNote?: string;
  completeness: number;
  completenessGroups: Record<string, number>;
  favorite: boolean;
  evidence: Evidence[];
  history: PricePoint[];
  duplicateCandidates: DuplicateCandidate[];
  documents?: AuctionDocument[];
}

export interface SourceSummary {
  id: string;
  name: string;
  adapter: string;
  status: AdapterStatus;
  automationLevel: string;
  lastAttemptedAt: string | null;
  lastSuccessfulAt: string | null;
  discoveredCount: number;
  changedCount: number;
  parseSuccessRate: number | null;
  warnings: string[];
}

export interface MotorcycleFilters {
  keyword?: string;
  source?: string;
  disposalOrigin?: DisposalOrigin;
  county?: string;
  brand?: string;
  eligibility?: BidEligibility;
  registration?: RegistrationStatus;
  vehicleClass?: MotorcycleClass;
  displacementBands?: DisplacementBand[];
  hasPhotos?: boolean;
  singleVehicle?: boolean;
  excludeScrap?: boolean;
  auctionWithinDays?: number;
  minPrice?: number;
  maxPrice?: number;
  marketView?: "active" | "ended" | "favorites" | "scrap" | "all";
  sort?: "auction_asc" | "auction_desc" | "price_asc" | "price_desc" | "completeness_desc";
}
