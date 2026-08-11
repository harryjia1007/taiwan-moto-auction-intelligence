# UI Specification

The UI uses `zh-TW`, a compact vehicle-marketplace visual language, high-contrast status badges, and strong source attribution. It avoids decorative gradients and excessive rounded surfaces.

The visual system follows a premium editorial-utility direction: warm neutral paper, ink green, restrained copper, square information surfaces, strong Traditional Chinese typography, and minimal shadow. Search is the first mobile task; secondary filters collapse below 640 px and the primary official-notice action remains reachable at the bottom of a mobile detail page. The reusable external design brief lives in `docs/design-handoff/`.

## Routes

- `/login`: owner magic-link sign-in
- `/motorcycles`: searchable cards and URL-backed filters
- `/motorcycles/[id]`: evidence-rich vehicle and auction detail
- `/sources`: adapter status, automation level, health, and run history

## Rules

- Default to the `進行中` view and sort by the nearest auction deadline. `已結束紀錄` and `我的收藏` remain one click away.
- Treat a passed deadline as an archived record, not a sold vehicle. Only an explicit official result can produce `SOLD`.
- Keep all search, lifecycle, source, location, eligibility, road-registration, photo, lot-size, price, date, and sort state in the URL.
- Cards must support an initial purchase decision without opening the detail page: official photo count, deadline, price type, auction round, year/month, displacement, plate, lot size, eligibility, registration, condition facts, location, risks, and completeness.
- Show `未確認` rather than hiding unknown facts.
- Show eligibility and registration status near price and deadline.
- Never label a missing/disappeared record as sold.
- A fact badge opens or links to its official evidence on the detail page.
- Mobile layouts preserve the 30-second summary and primary risks before secondary metadata.
- Cards rank decision facts P0–P3: eligibility/registration/price/deadline first, identity and media second, condition and risks third, provenance metadata last.
- Favorite controls expose busy and failure feedback; focus styles and reduced-motion behavior are mandatory.
- Cards and detail pages expose every privately cached official photo in source order. When multiple photos exist, show 44 px previous/next controls, a position counter, keyboard left/right navigation, and detail thumbnails.
- Do not substitute a generic motorcycle icon or silhouette when an official source has no image. Show a neutral textual `官方未提供照片` state with source/vehicle context. Keep `官方未提供` separate from `照片暫時無法載入`, because absence and delivery failure are different facts.

## Find-a-bike flow

1. Choose `進行中`, `已結束紀錄`, or `我的收藏`.
2. Search by model, plate, case number, or agency; narrow by location and official source.
3. Apply decision filters such as general-public eligibility, road-registration status, official photos, single-vehicle lots, price, and deadline.
4. Compare cards in deadline order, then open a candidate's decision summary, missing facts, evidence, documents, photos, and history.
5. Return to the exact official motorcycle notice or court PDF before bidding.
