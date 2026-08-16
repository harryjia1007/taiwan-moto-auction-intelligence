# UI Specification

The UI uses `zh-TW`, a compact vehicle-marketplace visual language, high-contrast status badges, and strong source attribution. It avoids decorative gradients and excessive rounded surfaces.

The visual system follows a premium editorial-utility direction: warm neutral paper, ink green, restrained copper, square information surfaces, strong Traditional Chinese typography, and minimal shadow. Marketplace browsing follows the 2.0 decision-first sequence: choose lifecycle, search a known clue, apply a familiar preset or always-visible region/source/sort controls, then open advanced filters only when needed. Search is the first mobile task; secondary filters collapse below 640 px and the primary official-notice action remains reachable at the bottom of a mobile detail page. The reusable external design brief lives in `docs/design-handoff/`.

## Routes

- `/login`: owner magic-link sign-in
- `/motorcycles`: searchable car-and-motorcycle cards and URL-backed filters (legacy route retained)
- `/motorcycles/[id]`: evidence-rich vehicle and auction detail
- `/sources`: adapter status, automation level, health, and run history

## Rules

- Default to the `進行中` view and sort by the nearest auction deadline. `已結束紀錄`, `我的收藏`, and the isolated `報廢／回收專區` remain one click away.
- Display the most recent successful production sync and a prominent warning when it is older than 36 hours. A failed run preserves prior listings and must never appear as a legitimate zero-result refresh.
- Normal marketplace views always exclude scrap-only, cannot-relicense, and licensed-recycler records. A query parameter cannot accidentally mix these records back into general shopping.
- Let the user choose all vehicles, motorcycles, cars, or inseparable mixed batches before applying type-specific filters. Motorcycle class/CC and car category are independent controls and never cross-apply.
- Show official motorcycle class for motorcycles and official car category for cars. `UNKNOWN` and `HEAVY_UNSPECIFIED` remain visible rather than inferred from displacement.
- Treat a passed deadline as an archived record, not a sold vehicle. Only an explicit official result can produce `SOLD`.
- Keep all search, lifecycle, source, location, eligibility, road-registration, photo, lot-size, price, date, and sort state in the URL.
- Cards must support an initial purchase decision without opening the detail page: official photo count, deadline, price type, auction round, year/month, displacement, plate, lot size, eligibility, registration, condition facts, location, risks, and completeness.
- Show `未確認` rather than hiding unknown facts.
- Show eligibility and registration status near price and deadline.
- Never label a missing/disappeared record as sold.
- A fact badge opens or links to its official evidence on the detail page.
- Mobile layouts preserve the 30-second summary and primary risks before secondary metadata.
- Cards rank decision facts P0–P3: eligibility/registration/price/deadline first, identity and media second, condition and risks third, provenance metadata last.
- Desktop and tablet result grids prefer readable one- or two-column cards over a dense three-column layout. Between 641 and 980 px, each result becomes a horizontal image-plus-decision card; mobile returns to a single vertical card.
- Region, official source, and result ordering are always visible. Vehicle class, legal eligibility, registration, price, media, lot size, and deadline remain in a disclosed precision-filter section. Active URL-backed filters are individually removable.
- Quick presets describe their actual predicate and never imply road legality from eligibility alone: public bidding, normal transfer, cached official photos/single lot, and a seven-day deadline are independent choices.
- Every identified vehicle listing, including judicial-auction vehicles without photos, shows a top-right favorite control on its marketplace card and an inline control on detail pages. The control persists to `我的收藏`; inseparable bulk lots remain unsupported until favorites have an explicit lot identity rather than an invented vehicle.
- Favorite controls expose busy and failure feedback; focus styles and reduced-motion behavior are mandatory.
- Cards and detail pages expose every privately cached official photo in source order. When multiple photos exist, show 44 px previous/next controls, a position counter, keyboard left/right navigation, and detail thumbnails.
- Do not substitute a generic motorcycle icon or silhouette when an official source has no image. Show a neutral textual `官方未提供照片` state with source/vehicle context. Keep `官方未提供` separate from `照片暫時無法載入`, because absence and delivery failure are different facts.
- A no-photo marketplace card uses a compact textual evidence notice instead of reserving the full image aspect ratio. It never carries an overlaid deadline badge; the deadline remains once in the auction decision block. Detail pages retain the larger no-photo explanation and source context.
- Marketplace controls and evidence states use natural Traditional Chinese. Decorative English section labels are not shown in the owner workflow.

## Find-a-vehicle flow

1. Choose `進行中`, `已結束紀錄`, or `我的收藏`.
2. Choose car, motorcycle, or mixed lot. Search by brand, vehicle class/category, plate, case number, or agency; narrow by location and official source. Placeholder examples stay generic and do not promote a specific brand or real plate.
3. Apply decision filters such as general-public eligibility, road-registration status, official photos, single-vehicle lots, price, and deadline.
4. Compare cards in deadline order, then open a candidate's decision summary, missing facts, evidence, documents, photos, and history.
5. Use `查看官方完整公告` to return to the publisher's exact motorcycle notice or court PDF before bidding. Public document actions always use the official external URL; a private evidence copy never silently replaces it.
