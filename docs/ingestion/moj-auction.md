# 法務部查扣物集中拍賣

Official discovery uses the public `汽、機車類` list at `https://auction.moj.gov.tw/1724/1726/searchList`. The adapter requests at most ten pages with a one-second minimum interval, keeps only rows whose official title explicitly mentions a motorcycle, then preserves the announcement HTML, registered-domain attachments, and official images before parsing.

Official ZIP attachments are preserved as immutable artifacts but are not treated as authoritative parsed text. Every redirect target is validated before contact; legacy links that leave the HTTPS `auction.moj.gov.tw` allowlist are recorded as failures instead of being followed.

The source represents criminal seizure, forfeiture, or pre-judgment conversion; it is not Judicial Yuan civil execution and not ordinary public-asset disposal. A record is `SOLD` only when the official text explicitly states a completed sale or sale price. A past auction time alone becomes an ended record without inventing a sale outcome.

Some announcements use generic “vehicle” titles and scanned PDF tables. If neither the public list title nor machine-readable official text explicitly identifies a motorcycle, the adapter does not create a vehicle row. The artifact format is documented as a coverage warning for future OCR work; OCR, if added, must remain evidence-linked and non-authoritative until reviewed.

Supported explicit classes are ordinary light, ordinary heavy, large heavy, and electric motorcycle. Generic `重型機車` remains `HEAVY_UNSPECIFIED`.

The hosted scheduler runs this source four times daily after Taipei Shwoo with `python -m ingest publish-public --source moj_auction`. A successful run privately preserves official HTML, attachments and images, records source/run metrics and snapshots, and updates only the sanitized public projection. A zero-result run is retained as an explicit coverage warning and never deletes prior listings.
