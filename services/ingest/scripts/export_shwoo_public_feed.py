from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from ingest.adapters.shwoo import ShwooAdapter
from ingest.public_feed import public_listing_payload


async def export(output: Path, limit: int | None) -> None:
    adapter = ShwooAdapter()
    rows: list[dict[str, object]] = []
    failures: list[str] = []
    try:
        items = await adapter.discover()
        if limit is not None:
            items = items[:limit]
        for item in items:
            try:
                artifacts = await adapter.fetch(item)
                record = await adapter.parse(item, artifacts)
                rows.append(public_listing_payload(record))
            except Exception as exc:  # one bad record must not erase prior data
                failures.append(f"{item.source_record_id}: {str(exc).strip() or exc.__class__.__name__}")
    finally:
        await adapter.close()
    output.write_text(json.dumps({"rows": rows, "failures": failures}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"discovered": len(rows) + len(failures), "parsed": len(rows), "failed": len(failures)}, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(description="Export a publication-safe Shwoo live feed")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    asyncio.run(export(args.output, args.limit))


if __name__ == "__main__":
    main()
