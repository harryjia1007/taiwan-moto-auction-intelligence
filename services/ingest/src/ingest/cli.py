from __future__ import annotations

import asyncio
import os

import typer

from ingest.adapters import JudicialMovableAdapter, PccAssetSaleAdapter, ShwooAdapter
from ingest.adapters.base import SourceAdapter
from ingest import PARSER_VERSION
from ingest.models import SyncResult
from ingest.repository import DatabaseRepository
from ingest.storage import LocalArtifactStorage, SupabaseArtifactStorage

app = typer.Typer(no_args_is_help=True, help="Read-only official motorcycle auction ingestion")


def adapter_for(source: str) -> SourceAdapter:
    if source == "shwoo":
        return ShwooAdapter(request_interval=float(os.getenv("SHWOO_REQUEST_INTERVAL_SECONDS", "1")))
    if source == "pcc":
        return PccAssetSaleAdapter(request_interval=float(os.getenv("PCC_REQUEST_INTERVAL_SECONDS", "1")))
    if source == "judicial":
        return JudicialMovableAdapter(request_interval=float(os.getenv("JUDICIAL_REQUEST_INTERVAL_SECONDS", "1")))
    raise typer.BadParameter("Implemented sources are: shwoo, pcc, judicial")


async def run_healthcheck(source: str) -> None:
    adapter = adapter_for(source)
    try:
        typer.echo((await adapter.healthcheck()).model_dump_json(indent=2))
    finally:
        await adapter.close()


async def run_sync(source: str, limit: int | None) -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is required for sync; run the local Supabase stack first")
    supabase_url = os.getenv("SUPABASE_URL")
    service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    storage = SupabaseArtifactStorage(supabase_url, service_key, os.getenv("RAW_ARTIFACT_BUCKET", "raw-artifacts")) if supabase_url and service_key else LocalArtifactStorage()
    repository = DatabaseRepository(database_url, storage, source)
    adapter = adapter_for(source)
    result = SyncResult(source=source, discovered=0, fetched=0, parsed=0, changed=0, failed=0)
    run_id = repository.start_run()
    try:
        items = await adapter.discover()
        if limit is not None:
            items = items[:limit]
        result.discovered = len(items)
        if not items:
            result.warnings.append("Discovery returned zero records; prior data was preserved")
        for item in items:
            try:
                artifacts = await adapter.fetch(item)
                result.fetched += 1
                record = await adapter.parse(item, artifacts)
                if await repository.save(run_id, item, artifacts, record):
                    result.changed += 1
                result.parsed += 1
            except Exception as exc:
                result.failed += 1
                result.warnings.append(f"{item.source_record_id}: {exc}")
        if result.fetched and (result.parsed / result.fetched) < 0.9:
            result.warnings.append("Parse success rate fell below 90%")
    finally:
        await adapter.close()
        repository.finish_run(run_id, result)
    typer.echo(result.model_dump_json(indent=2))


async def run_reprocess(source: str, from_parser_version: str | None, limit: int | None) -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is required for reprocessing; run the local Supabase stack first")
    supabase_url = os.getenv("SUPABASE_URL")
    service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    storage = SupabaseArtifactStorage(supabase_url, service_key, os.getenv("RAW_ARTIFACT_BUCKET", "raw-artifacts")) if supabase_url and service_key else LocalArtifactStorage()
    repository = DatabaseRepository(database_url, storage, source)
    adapter = adapter_for(source)
    run_id = repository.start_run()
    result = SyncResult(source=source, discovered=0, fetched=0, parsed=0, changed=0, failed=0)
    try:
        queued = await repository.load_reprocessable(from_parser_version, limit)
        result.discovered = len(queued)
        for item, artifacts in queued:
            try:
                record = await adapter.parse(item, artifacts)
                result.fetched += 1
                if await repository.save(run_id, item, artifacts, record):
                    result.changed += 1
                result.parsed += 1
            except Exception as exc:
                result.failed += 1
                result.warnings.append(f"{item.source_record_id}: {exc}")
        if not queued:
            result.warnings.append("No matching raw parse artifacts were available for reprocessing")
    finally:
        await adapter.close()
        repository.finish_run(run_id, result)
    typer.echo(f"Reprocessed with parser {PARSER_VERSION}")
    typer.echo(result.model_dump_json(indent=2))


@app.command()
def healthcheck(source: str = typer.Option("shwoo")) -> None:
    asyncio.run(run_healthcheck(source))


@app.command()
def sync(source: str = typer.Option("shwoo"), limit: int | None = typer.Option(None, min=1)) -> None:
    asyncio.run(run_sync(source, limit))


@app.command()
def reprocess(
    source: str = typer.Option("shwoo"),
    from_parser_version: str | None = typer.Option(None, help="Only raw artifacts first parsed by this version"),
    limit: int | None = typer.Option(None, min=1),
) -> None:
    """Re-run the current parser against checksum-addressed stored artifacts without live fetches."""
    asyncio.run(run_reprocess(source, from_parser_version, limit))
