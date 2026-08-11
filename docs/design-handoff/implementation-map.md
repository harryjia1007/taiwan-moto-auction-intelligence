# Engineering implementation map

## Existing surfaces

| Surface | Current implementation | Contract to preserve |
| --- | --- | --- |
| App shell | `apps/web/app/layout.tsx` | Owner-only navigation and zh-TW metadata. |
| Marketplace | `apps/web/app/motorcycles/page.tsx` | Server-rendered, URL-backed search state. |
| Filters | `apps/web/components/filter-panel.tsx` | Native GET form; every decision filter remains bookmarkable. |
| Listing card | `apps/web/components/motorcycle-card.tsx` | P0 decision facts remain visible before opening detail. |
| Official media | `apps/web/components/photo-gallery.tsx` | Ordered photo carousel, keyboard controls, detail thumbnails, and distinct no-photo/load-failure states. |
| Detail | `apps/web/app/motorcycles/[id]/page.tsx` | Exact evidence, immutable history, documents and official action. |
| Source health | `apps/web/app/sources/page.tsx` | Never present `PLANNED` as active coverage. |
| Visual system | `apps/web/app/globals.css` | WCAG focus, reduced motion, 640/980/1180 breakpoints. |

## Data interfaces

- `GET /api/motorcycles`: `{ items, nextCursor, total }`; exact count and opaque sort-aware keyset cursor.
- `GET /api/motorcycles/[id]`: normalized listing with evidence, history, documents and duplicate candidates.
- `POST|DELETE /api/favorites/[id]`: idempotent owner favorite mutation.
- `GET /api/sources`: source states, sync metrics and deterministic warnings.

Do not make official-source requests from React components or route handlers. The frontend consumes PostgreSQL/Supabase data and privately cached media only.

## Recommended component boundaries for generated design

- `AppHeader`, `MobileNavigation`
- `MarketViewTabs`, `SearchWorkspace`, `QuickFilterChips`, `AdvancedFilters`
- `MotorcycleCard`, `AuctionDeadline`, `PriceFact`, `DecisionBadge`, `CompletenessMeter`
- `PhotoGallery`, `PhotoAbsence`, `DecisionBrief`, `MissingFacts`, `AuctionTerms`, `EvidenceList`, `PriceHistory`
- `RiskSidebar`, `OfficialNoticeAction`, `SourceHealthTable`

Generated components may be split further, but domain decisions should remain in shared deterministic helpers rather than duplicated inside visual components.
