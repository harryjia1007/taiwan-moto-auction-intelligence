# 行政執行署動產拍賣

The official `https://www.tpkonsale.moj.gov.tw/Chattel` search requires CAPTCHA. The project does not read, solve, reuse, or bypass it. A human performs the official `汽機車` search and records only motorcycle detail URLs shaped as `https://www.tpkonsale.moj.gov.tw/Detail/Chattel?NO=<official-id>`.

Place a private local manifest at `.data/moj-enforcement-manifest.json`:

```json
[
  {
    "official_url": "https://www.tpkonsale.moj.gov.tw/Detail/Chattel?NO=00000000-0000-0000-0000-000000000000",
    "title": "官方頁面的機車標題或摘要",
    "organization": "法務部行政執行署○○分署",
    "auction_round": 1
  }
]
```

Then run `pnpm ingest:moj-enforcement`. The adapter validates the official host and detail path, rate-limits requests, preserves HTML, official PDF attachments, and every detail image, and parses only pages that explicitly identify a motorcycle. Manifest files are local operational inputs and must never be committed.

The four motorcycle classes are accepted only when the official detail text explicitly says ordinary light, ordinary heavy, large heavy, or electric motorcycle. Generic heavy-motorcycle wording remains `HEAVY_UNSPECIFIED`; displacement is never used to invent a legal class. Recycler-only, scrapped, or non-relicensable records are routed to the separate scrap/recycling view instead of the ordinary marketplace.

Because search discovery is human-assisted, this source remains `PARTIAL` even after successful imports. Its last-success time shows the most recent imported manifest, not continuous nationwide discovery.
