# UI Specification

The UI uses `zh-TW`, a compact vehicle-marketplace visual language, high-contrast status badges, and strong source attribution. It avoids decorative gradients and excessive rounded surfaces.

The visual system follows a premium editorial-utility direction: warm neutral paper, ink green, restrained copper, square information surfaces, strong Traditional Chinese typography, and minimal shadow. Marketplace browsing follows the 2.0 decision-first sequence: choose lifecycle, search a known clue, apply a familiar preset or always-visible region/source/sort controls, then open advanced filters only when needed. Search is the first mobile task; secondary filters collapse below 640 px and the primary official-notice action remains reachable at the bottom of a mobile detail page. The reusable external design brief lives in `docs/design-handoff/`.

## Routes

- `/login`: owner magic-link sign-in
- `/motorcycles`: searchable car-and-motorcycle cards and URL-backed filters (legacy route retained)
- `/motorcycles/[id]`: evidence-rich vehicle and auction detail
- `/motorcycles/compare?ids=...`: owner-authenticated comparison for exactly two or three identified, single-vehicle listings
- `/sources`: adapter status, automation level, health, and run history

## Rules

- Default to the `進行中` view and sort by the nearest auction deadline. `已結束紀錄`, `我的收藏`, and the isolated `報廢／回收專區` remain one click away.
- Display the most recent successful production sync and a prominent warning when it is older than 36 hours. A failed run preserves prior listings and must never appear as a legitimate zero-result refresh.
- Normal marketplace views always exclude scrap-only, cannot-relicense, and licensed-recycler records. A query parameter cannot accidentally mix these records back into general shopping.
- Let the user choose all vehicles, motorcycles, cars, or inseparable mixed batches before applying type-specific filters. Motorcycle class/CC and car category are independent controls and never cross-apply.
- Show official motorcycle class for motorcycles and official car category for cars. `UNKNOWN` and `HEAVY_UNSPECIFIED` remain visible rather than inferred from displacement.
- Treat a passed deadline as an archived record, not a sold vehicle. Only an explicit official result can produce `SOLD`.
- Keep all search, lifecycle, source, location, eligibility, road-registration, photo, lot-size, price, date, and sort state in the URL.
- Result pagination uses the same URL-backed state and an opaque cursor. The interface exposes a next-batch action and a first-page action, while browser Back provides step-by-step return without maintaining hidden client state.
- Cards must support an initial purchase decision without opening the detail page: official photo count, deadline, price type, auction round, year/month, displacement, plate, lot size, eligibility, registration, condition facts, location, risks, and completeness. Owner-only screens may show the complete official plate; the public marketplace shows only a plate with its final two or three characters masked.
- Show `未確認` rather than hiding unknown facts.
- Show eligibility and registration status near price and deadline.
- Never label a missing/disappeared record as sold.
- A fact badge opens or links to its official evidence on the detail page.
- Mobile layouts preserve the 30-second summary and primary risks before secondary metadata.
- Cards rank decision facts P0–P3: eligibility/registration/price/deadline first, identity and media second, condition and risks third, provenance metadata last.
- Desktop and tablet result grids prefer readable one- or two-column cards over a dense three-column layout. Between 641 and 980 px, each result becomes a horizontal image-plus-decision card; mobile returns to a single vertical card.
- Region, official source, and result ordering are always visible. Vehicle class, legal eligibility, registration, price, media, lot size, and deadline remain in a disclosed precision-filter section. Active URL-backed filters are individually removable.
- Each fixed displacement band shows an exact matching count. Counts honor the current lifecycle, vehicle type, region, source, eligibility, registration, price, media, lot-size, deadline, and text filters while deliberately ignoring only the current displacement selection, so adding a second band remains understandable. Database mode uses exact count-only queries rather than inferring totals from the current page; `官方未提供` counts only rows where `displacement_cc IS NULL`.
- Quick presets describe their actual predicate and never imply road legality from eligibility alone: public bidding, normal transfer, single-lot status, and a seven-day deadline are independent choices. Cached-photo filtering is owner-only until a source has explicit anonymous image redistribution rights.
- Quick presets add predicates to the current source, region, vehicle type, search, and other compatible filters; selecting one clears pagination. The future seven-day preset is absent from ended records. Entering the scrap area clears bidding, registration, and exclusion filters that would conceal eligible scrap records, while leaving source and region intact. The ordinary-bidding and normal-transfer presets return from scrap to active browsing and visibly say so.
- The always-visible current-view summary names keyword, region, source, vehicle type, date window, selected displacement bands, price, non-default sort, and result count when present. On mobile it wraps naturally, so users can see what produced a zero-result state without reopening the filter controls.
- Every identified vehicle listing, including judicial-auction vehicles without photos, shows a compact favorite control in the card's top action row and an inline control on detail pages. The action row reserves its own width so the favorite never covers the auction status, source, or photo controls. The control persists to `我的收藏`; inseparable bulk lots remain unsupported until favorites have an explicit lot identity rather than an invented vehicle.
- Every identified single-vehicle card can join a local comparison list. The list is limited to three, survives reload in browser storage, never leaves the owner's browser, and exposes remove/clear controls. At two or three vehicles, the authenticated comparison page shows price, deadline, legal class, displacement, year/month, eligibility, registration, start/test facts, mileage, location, completeness, risks, and detail links without inferring unknown values. The fixed comparison tray reserves bottom space and its table scrolls inside its own container on narrow screens rather than widening the viewport.
- Favorite controls expose busy and failure feedback; focus styles and reduced-motion behavior are mandatory.
- A failed database subquery is never rendered as a legitimate empty fact set. Listing failures use a retryable page error; detail-only failures preserve available facts and show a visible partial-data warning.
- Owner-only cards and detail pages expose every privately cached official photo in source order. When multiple photos exist, show 44 px previous/next controls, a position counter, keyboard left/right navigation, and detail thumbnails. The anonymous projection currently exposes no source photos; its compact cards must not imply that a private cached image is publicly licensed.
- An owner-only single-vehicle detail keeps vehicle-specific photos and field evidence first. If the official lot has additional photos or evidence not assigned to any vehicle, show them separately as `整批共用`; when no vehicle-specific image exists, the shared gallery may fill the hero only with a prominent shared-lot warning. Never present a sibling vehicle's photo or lot-wide wording as this vehicle's own fact. These queries use the signed-in owner's Supabase client and existing RLS; they do not make the private assets public.
- Do not substitute a generic motorcycle icon, silhouette, or large placeholder when an official source has no image. Result cards omit the media block entirely and keep the favorite control beside the source line; the detail page uses only a compact `官方未附照片` fact label. Keep `官方未附` separate from `照片暫時無法載入`, because absence and delivery failure are different facts.
- A no-photo marketplace card omits the media block instead of reserving an image aspect ratio. It never carries an overlaid deadline badge; the deadline remains once in the auction decision block. Detail pages omit the gallery and show the compact `官方未附照片` fact label alongside the other decision badges.
- Marketplace controls and evidence states use natural Traditional Chinese. Decorative English section labels are not shown in the owner workflow.

## Find-a-vehicle flow

1. Choose `進行中`, `已結束紀錄`, or `我的收藏`.
2. Choose car, motorcycle, or mixed lot. Search by brand, vehicle class/category, plate, case number, or agency; narrow by location and official source. Placeholder examples stay generic and do not promote a specific brand or real plate.
3. Apply decision filters such as general-public eligibility, road-registration status, official photos, single-vehicle lots, price, and deadline.
4. Add two or three identified single vehicles to the local comparison tray and scan their decision facts side by side; inseparable bulk lots are not treated as individual vehicles.
5. Open a candidate's decision summary, missing facts, evidence, documents, photos, and history.
6. Use `查看官方完整公告` to return to the publisher's exact vehicle notice or court PDF before bidding. Public document actions always use the official external URL; a private evidence copy never silently replaces it.
