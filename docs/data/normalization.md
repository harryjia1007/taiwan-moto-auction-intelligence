# Normalization

Canonical values never replace the original source text. Brand aliases begin with `YAMAHA/山葉/台灣山葉`, `SYM/三陽/三陽工業/SANYANG`, and `KYMCO/光陽` and expand only with evidence.

Boolean-like facts use `YES`, `NO`, `UNKNOWN`, or `CONFLICTING`. Inability to test produces `can_test=NO` only when explicitly stated and does not imply `can_start=NO`.

Completeness is measured independently of confidence across identity, auction, condition, registration, fees, and media groups. The overall score weights those groups 20%, 25%, 15%, 20%, 10%, and 10% respectively.

PCC asset-sale titles sometimes contain CJK compatibility glyphs (`⾞` rather than `車`). The parser applies Unicode NFKC only to classification and quantity matching; it retains the official original in the title and evidence. An explicit title such as `報廢警用汽⾞3輛、機⾞10輛` is a scrap/mixed lot of 13 vehicles, not a regular single-car listing. Quantity is summed only where the title enumerates vehicle types with their own counts; the parser does not invent identities for the 13 vehicles. The public marketplace also treats an explicit official scrap-vehicle title as scrap when an older already-published row lacks that normalized classification, pending a verified republish.

For PCC titles, an explicit `機車0輛` alongside a positive enumerated car count is evidence of zero motorcycles in that lot, not a motorcycle listing. The reverse holds for `汽車0輛`. An additional uncounted vehicle group in the title leaves the total unknown and prevents the zero-count override; generic keywords never prove the absence of an unspecified group. An exhaustive all-zero breakdown fails closed. Existing published rows require reprocessing and republishing before their old classification changes.
