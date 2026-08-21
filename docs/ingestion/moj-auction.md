# 法務部查扣物集中拍賣

Official discovery uses the public `汽、機車類` list at `https://auction.moj.gov.tw/1724/1726/searchList`. The adapter requests at most ten pages with a one-second minimum interval, keeps rows whose official title explicitly identifies a car or motorcycle, then preserves the announcement HTML, registered-domain attachments, and official images before parsing.

Official ZIP attachments are preserved as immutable artifacts but are not treated as authoritative parsed text. Every redirect target is validated before contact. A redirect does not grant access to its destination: the reviewed allowlist remains exactly `https://auction.moj.gov.tw` on the default HTTPS port, without URL credentials. Artifact metadata retains only reproducibility headers and never stores response cookies or authorization headers.

Some historical central rows redirect to prosecutor-office subdomains whose automated-access policy is not yet usable or separately approved. The adapter never contacts those targets. Instead, it checksum-stores the exact `<tr>` byte slice returned by the approved central list, parses only its official title and organization, leaves detail-only fields unknown, and records the detail fetch as a partial failure. Thus the central record remains discoverable without inventing facts or silently upgrading an unreviewed host. If the central row cannot be retained because markup changed, the item fails explicitly.

The source represents criminal seizure, forfeiture, or pre-judgment conversion; it is not Judicial Yuan civil execution and not ordinary public-asset disposal. A record is `SOLD` only when the official text explicitly states a completed sale or sale price. A past auction time alone becomes an ended record without inventing a sale outcome.

Some announcements use generic “vehicle” titles and scanned PDF tables. If neither the public list title nor machine-readable official text explicitly identifies a car or motorcycle, the adapter does not create a vehicle row. The artifact format is documented as a coverage warning for future OCR work; OCR, if added, must remain evidence-linked and non-authoritative until reviewed.

Supported motorcycle classes are ordinary light, ordinary heavy, large heavy, and electric motorcycle; generic `重型機車` remains `HEAVY_UNSPECIFIED`. Supported car categories are passenger car, SUV, van, truck, bus, other, and unknown. Inseparable announcements containing both become `MIXED`.

The hosted scheduler runs this source twice daily at 09:30 and 21:30 Asia/Taipei with `python -m ingest publish-public --source moj_auction`. A successful run privately preserves official HTML, attachments and images, records source/run metrics and snapshots, and updates only the sanitized public projection. A zero-result run is retained as an explicit coverage warning and never deletes prior listings. A run containing central-summary fallbacks is `PARTIAL`; it does not advance `last_successful_at` or claim full detail coverage.
