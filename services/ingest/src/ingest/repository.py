from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

import psycopg
from psycopg.rows import dict_row

from ingest import PARSER_VERSION
from ingest.models import DiscoveredItem, ParsedAuctionRecord, RawArtifact, SyncResult
from ingest.storage import ArtifactStorage

SOURCE_IDS = {
    "shwoo": "20000000-0000-0000-0000-000000000001",
    "judicial": "20000000-0000-0000-0000-000000000002",
    "pcc": "20000000-0000-0000-0000-000000000004",
}


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


class DatabaseRepository:
    def __init__(self, database_url: str, storage: ArtifactStorage, source: str) -> None:
        if source not in SOURCE_IDS:
            raise ValueError(f"Unknown repository source: {source}")
        self.database_url = database_url
        self.storage = storage
        self.source = source
        self.source_id = SOURCE_IDS[source]

    def _connect(self) -> psycopg.Connection[dict[str, Any]]:
        return psycopg.connect(self.database_url, row_factory=dict_row)

    def start_run(self) -> str:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "insert into sync_runs (source_id,status,parser_version) values (%s,'RUNNING',%s) returning id",
                (self.source_id, PARSER_VERSION),
            )
            run_id = str(cur.fetchone()["id"])
            cur.execute("update sources set last_attempted_at=now(),parser_version=%s where id=%s", (PARSER_VERSION, self.source_id))
            return run_id

    async def load_reprocessable(self, from_parser_version: str | None = None, limit: int | None = None) -> list[tuple[DiscoveredItem, list[RawArtifact]]]:
        where_version = "and ra.parser_version = %s" if from_parser_version else ""
        limit_sql = "limit %s" if limit is not None else ""
        parameters: list[Any] = []
        if from_parser_version:
            parameters.append(from_parser_version)
        parameters.append(self.source_id)
        if limit is not None:
            parameters.append(limit)
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                f"""
                select sr.source_record_id, sr.official_url, sr.original_title,
                       ra.official_url as artifact_url, ra.fetched_at, ra.http_status,
                       ra.http_headers, ra.mime_type, ra.filename, ra.checksum_sha256, ra.storage_path,
                       coalesce(latest.normalized_payload->>'eligibility', 'UNKNOWN') as eligibility
                from source_records sr
                join lateral (
                  select * from raw_artifacts ra
                  where ra.source_record_id = sr.id and ra.mime_type in ('text/html','application/json') {where_version}
                  order by ra.fetched_at desc,
                           case when ra.mime_type = 'application/json' then 0 else 1 end
                  limit 1
                ) ra on true
                left join lateral (
                  select normalized_payload from snapshots where source_record_id = sr.id
                  order by observed_at desc limit 1
                ) latest on true
                where sr.source_id = %s
                order by sr.source_record_id
                {limit_sql}
                """,
                tuple(parameters),
            )
            rows = cur.fetchall()
        loaded: list[tuple[DiscoveredItem, list[RawArtifact]]] = []
        for row in rows:
            content = await self.storage.get(row["storage_path"])
            item = DiscoveredItem(
                source_record_id=row["source_record_id"], official_url=row["official_url"],
                title=row["original_title"] or row["source_record_id"], discovery_url=row["official_url"],
                recycler_only=row["eligibility"] == "LICENSED_RECYCLER_ONLY",
            )
            artifact = RawArtifact(
                official_url=row["artifact_url"], fetched_at=row["fetched_at"], mime_type=row["mime_type"],
                filename=row["filename"], content=content, http_status=row["http_status"] or 200,
                http_headers=row["http_headers"] or {}, checksum_sha256=row["checksum_sha256"],
            )
            loaded.append((item, [artifact]))
        return loaded

    async def save(self, run_id: str, item: DiscoveredItem, artifacts: list[RawArtifact], record: ParsedAuctionRecord) -> bool:
        paths = [await self.storage.put(artifact) for artifact in artifacts]
        payload = record.model_dump(mode="json")
        payload_json = _json(payload)
        payload_checksum = hashlib.sha256(payload_json.encode()).hexdigest()
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                insert into organizations (canonical_name,organization_type,jurisdiction)
                values (%s,'GOVERNMENT_AGENCY',%s)
                on conflict (canonical_name,jurisdiction) do update set canonical_name=excluded.canonical_name
                returning id
                """,
                (record.organization, record.location[:3] if record.location else "臺灣"),
            )
            organization_id = cur.fetchone()["id"]
            cur.execute(
                """
                insert into source_records (source_id,source_record_id,official_url,original_title,last_content_checksum)
                values (%s,%s,%s,%s,%s)
                on conflict (source_id,source_record_id) do update
                set official_url=excluded.official_url, original_title=excluded.original_title,
                    last_seen_at=now(), last_content_checksum=excluded.last_content_checksum, active=true
                returning id, (xmax = 0) as inserted
                """,
                (self.source_id, item.source_record_id, str(item.official_url), record.official_title, artifacts[0].checksum_sha256),
            )
            source_row = cur.fetchone()
            source_record_uuid = source_row["id"]
            artifact_ids: list[str] = []
            for artifact, path in zip(artifacts, paths, strict=True):
                cur.execute(
                    """
                    insert into raw_artifacts
                    (source_record_id,sync_run_id,official_url,fetched_at,http_status,http_headers,mime_type,filename,checksum_sha256,content_length,storage_path,extraction_status,parser_version)
                    values (%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s,'PARSED',%s)
                    on conflict (checksum_sha256,storage_path) do nothing returning id
                    """,
                    (source_record_uuid, run_id, str(artifact.official_url), artifact.fetched_at, artifact.http_status,
                     _json(artifact.http_headers), artifact.mime_type, artifact.filename, artifact.checksum_sha256,
                     len(artifact.content), path, PARSER_VERSION),
                )
                row = cur.fetchone()
                if row:
                    artifact_ids.append(str(row["id"]))
                else:
                    cur.execute("select id from raw_artifacts where checksum_sha256=%s and storage_path=%s", (artifact.checksum_sha256, path))
                    artifact_ids.append(str(cur.fetchone()["id"]))
            artifacts_by_url = {
                str(artifact.official_url): (artifact, artifact_id, path)
                for artifact, artifact_id, path in zip(artifacts, artifact_ids, paths, strict=True)
            }
            primary_artifact_id = artifact_ids[0]
            for artifact, artifact_id in zip(artifacts, artifact_ids, strict=True):
                if artifact.mime_type == "application/pdf":
                    cur.execute(
                        """insert into documents (source_record_id,artifact_id,title,document_type,official_url)
                           values (%s,%s,%s,'OFFICIAL_AUCTION_NOTICE',%s)
                           on conflict (source_record_id,artifact_id) do update
                           set title=excluded.title,official_url=excluded.official_url""",
                        (source_record_uuid, artifact_id, f"{record.title}－官方拍賣公告", str(artifact.official_url)),
                    )
            cur.execute(
                """insert into snapshots (source_record_id,artifact_id,normalized_payload,payload_checksum,parser_version)
                   values (%s,%s,%s::jsonb,%s,%s) on conflict (source_record_id,payload_checksum,parser_version) do nothing returning id""",
                (source_record_uuid, primary_artifact_id, payload_json, payload_checksum, PARSER_VERSION),
            )
            snapshot_row = cur.fetchone()
            changed = snapshot_row is not None
            if snapshot_row:
                snapshot_id = snapshot_row["id"]
            else:
                cur.execute("select id from snapshots where source_record_id=%s and payload_checksum=%s and parser_version=%s", (source_record_uuid, payload_checksum, PARSER_VERSION))
                snapshot_id = cur.fetchone()["id"]

            case_number = record.official_case_number or f"{self.source.upper()}-{item.source_record_id}"
            cur.execute(
                """
                insert into auction_cases (source_id,organization_id,official_case_number,title,disposal_origin)
                values (%s,%s,%s,%s,%s)
                on conflict (source_id,official_case_number) do update
                set organization_id=excluded.organization_id,title=excluded.title,disposal_origin=excluded.disposal_origin
                returning id
                """,
                (self.source_id, organization_id, case_number, record.title, record.disposal_origin),
            )
            case_id = cur.fetchone()["id"]
            cur.execute(
                """
                insert into auction_events
                (auction_case_id,source_record_id,round_number,status,starts_at,ends_at,reserve_price,current_price,sold_price,
                 deposit,payment_deadline,pickup_deadline)
                values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                on conflict (source_record_id,round_number) do update
                set status=excluded.status,starts_at=excluded.starts_at,ends_at=excluded.ends_at,
                    reserve_price=excluded.reserve_price,current_price=excluded.current_price,sold_price=excluded.sold_price,
                    deposit=excluded.deposit,payment_deadline=excluded.payment_deadline,pickup_deadline=excluded.pickup_deadline
                returning id
                """,
                (case_id, source_record_uuid, record.auction_round, record.status.value, record.starts_at, record.ends_at,
                 record.reserve_price, record.current_price, record.sold_price, record.deposit,
                 record.payment_deadline, record.pickup_deadline),
            )
            event_id = cur.fetchone()["id"]
            cur.execute(
                """
                insert into lots
                (auction_event_id,lot_number,title,lot_size,bulk_lot,eligibility,storage_location,original_description,fee_notes,
                 registration_status,has_key,can_start,can_test,condition_summary,completeness,completeness_groups)
                values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
                on conflict (auction_event_id,(coalesce(lot_number,''))) do update
                set title=excluded.title,lot_size=excluded.lot_size,bulk_lot=excluded.bulk_lot,
                    eligibility=excluded.eligibility,storage_location=excluded.storage_location,
                    original_description=excluded.original_description,fee_notes=excluded.fee_notes,
                    registration_status=excluded.registration_status,has_key=excluded.has_key,
                    can_start=excluded.can_start,can_test=excluded.can_test,
                    condition_summary=excluded.condition_summary,completeness=excluded.completeness,
                    completeness_groups=excluded.completeness_groups
                returning id
                """,
                (event_id, "1", record.title, record.lot_size, record.bulk_lot, record.eligibility.value,
                 record.location, record.description, record.fee_notes, record.registration_status.value,
                 record.has_key.value, record.can_start.value, record.can_test.value,
                 record.condition_summary, record.completeness, _json(record.completeness_groups)),
            )
            lot_id = cur.fetchone()["id"]

            # An inseparable bulk description is a real lot, not evidence of N
            # individually identified vehicles. Preserve it at lot level only.
            if record.bulk_lot and not record.vehicle_units:
                for order, url in enumerate(record.photo_urls):
                    matched = artifacts_by_url.get(str(url))
                    artifact, artifact_id, storage_path = matched if matched else (None, None, None)
                    cur.execute(
                        """insert into photos (lot_id,source_record_id,artifact_id,source_url,storage_path,checksum_sha256,sort_order)
                           values (%s,%s,%s,%s,%s,%s,%s) on conflict (source_record_id,source_url)
                           do update set lot_id=excluded.lot_id,vehicle_id=null,
                             artifact_id=coalesce(excluded.artifact_id,photos.artifact_id),
                             storage_path=coalesce(excluded.storage_path,photos.storage_path),
                             checksum_sha256=coalesce(excluded.checksum_sha256,photos.checksum_sha256),
                             sort_order=excluded.sort_order,last_seen_at=now(),availability_status='AVAILABLE'""",
                        (lot_id, source_record_uuid, artifact_id, str(url), storage_path,
                         artifact.checksum_sha256 if artifact else None, order),
                    )
                for evidence in record.evidence:
                    cur.execute(
                        """insert into field_evidence
                           (entity_type,entity_id,field_name,normalized_value,source_record_id,artifact_id,source_text,table_row,
                            parser_name,parser_version,extraction_method,trust,confidence)
                           values ('lot',%s,%s,%s::jsonb,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                           on conflict do nothing""",
                        (lot_id, evidence.field_name, _json(evidence.normalized_value), source_record_uuid, primary_artifact_id,
                         evidence.source_text, evidence.table_row, self.source, PARSER_VERSION, evidence.extraction_method,
                         evidence.trust, evidence.confidence),
                    )
                return changed or bool(source_row["inserted"])

            brand_id = None
            if record.brand:
                cur.execute("select id from vehicle_brands where %s = any(aliases) or canonical_name=%s limit 1", (record.brand, record.brand))
                row = cur.fetchone()
                brand_id = row["id"] if row else None
            model_id = None
            if brand_id and record.model:
                cur.execute("select id from vehicle_models where brand_id=%s and (canonical_name=%s or model_code=%s) limit 1", (brand_id, record.model, record.model))
                row = cur.fetchone()
                model_id = row["id"] if row else None
            cur.execute(
                """
                insert into vehicles
                (lot_id,source_vehicle_key,brand_id,model_id,original_brand,original_model,model_code,manufacture_year,manufacture_month,
                 displacement_cc,color,mileage_km,has_key,can_start,can_test,registration_status,condition_summary,visible_damage,
                 tax_arrears,fine_arrears,fuel_fee_arrears,completeness,completeness_groups)
                values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
                on conflict (lot_id,source_vehicle_key) do update set
                 brand_id=excluded.brand_id,model_id=excluded.model_id,original_brand=excluded.original_brand,original_model=excluded.original_model,
                 manufacture_year=excluded.manufacture_year,manufacture_month=excluded.manufacture_month,displacement_cc=excluded.displacement_cc,
                 color=excluded.color,mileage_km=excluded.mileage_km,has_key=excluded.has_key,can_start=excluded.can_start,can_test=excluded.can_test,
                 registration_status=excluded.registration_status,condition_summary=excluded.condition_summary,visible_damage=excluded.visible_damage,
                 tax_arrears=excluded.tax_arrears,fine_arrears=excluded.fine_arrears,fuel_fee_arrears=excluded.fuel_fee_arrears,
                 completeness=excluded.completeness,completeness_groups=excluded.completeness_groups
                returning id
                """,
                (lot_id, record.vehicle_units[0].source_vehicle_key if record.vehicle_units else "primary",
                 brand_id, model_id, record.brand, record.model, record.model, record.manufacture_year, record.manufacture_month,
                 record.displacement_cc, record.color, record.mileage_km, record.has_key.value, record.can_start.value, record.can_test.value,
                 record.registration_status.value, record.condition_summary, record.visible_damage, record.tax_arrears.value,
                 record.fine_arrears.value, record.fuel_fee_arrears.value, record.completeness, _json(record.completeness_groups)),
            )
            vehicle_id = cur.fetchone()["id"]
            for identifier in record.identifiers:
                cur.execute(
                    """insert into vehicle_identifiers (vehicle_id,identifier_type,normalized_value,original_value)
                       values (%s,%s,%s,%s) on conflict (vehicle_id,identifier_type,normalized_value)
                       do update set original_value=excluded.original_value""",
                    (vehicle_id, identifier.identifier_type, identifier.normalized_value, identifier.original_value),
                )
            for unit in record.vehicle_units[1:]:
                cur.execute(
                    """
                    insert into vehicles
                    (lot_id,source_vehicle_key,brand_id,model_id,original_brand,original_model,model_code,manufacture_year,manufacture_month,
                     displacement_cc,color,mileage_km,has_key,can_start,can_test,registration_status,condition_summary,visible_damage,
                     tax_arrears,fine_arrears,fuel_fee_arrears,completeness,completeness_groups)
                    values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
                    on conflict (lot_id,source_vehicle_key) do update set updated_at=now() returning id
                    """,
                    (lot_id, unit.source_vehicle_key, brand_id, model_id, record.brand, record.model, record.model,
                     record.manufacture_year, record.manufacture_month, record.displacement_cc, record.color, record.mileage_km,
                     record.has_key.value, record.can_start.value, record.can_test.value, record.registration_status.value,
                     record.condition_summary, record.visible_damage, record.tax_arrears.value, record.fine_arrears.value,
                     record.fuel_fee_arrears.value, record.completeness, _json(record.completeness_groups)),
                )
                unit_vehicle_id = cur.fetchone()["id"]
                for identifier in unit.identifiers:
                    cur.execute(
                        """insert into vehicle_identifiers (vehicle_id,identifier_type,normalized_value,original_value)
                           values (%s,%s,%s,%s) on conflict (vehicle_id,identifier_type,normalized_value)
                           do update set original_value=excluded.original_value""",
                        (unit_vehicle_id, identifier.identifier_type, identifier.normalized_value, identifier.original_value),
                    )
            cur.execute(
                """insert into vehicle_observations (vehicle_id,snapshot_id,observed_at,payload)
                   values (%s,%s,now(),%s::jsonb) on conflict (vehicle_id,snapshot_id) do nothing""",
                (vehicle_id, snapshot_id, payload_json),
            )
            for order, url in enumerate(record.photo_urls):
                matched = artifacts_by_url.get(str(url))
                artifact, artifact_id, storage_path = matched if matched else (None, None, None)
                cur.execute(
                    """insert into photos (vehicle_id,source_record_id,artifact_id,source_url,storage_path,checksum_sha256,sort_order)
                       values (%s,%s,%s,%s,%s,%s,%s) on conflict (source_record_id,source_url)
                       do update set vehicle_id=excluded.vehicle_id,lot_id=null,
                         artifact_id=coalesce(excluded.artifact_id,photos.artifact_id),
                         storage_path=coalesce(excluded.storage_path,photos.storage_path),
                         checksum_sha256=coalesce(excluded.checksum_sha256,photos.checksum_sha256),
                         sort_order=excluded.sort_order,last_seen_at=now(),availability_status='AVAILABLE'""",
                    (vehicle_id, source_record_uuid, artifact_id, str(url), storage_path,
                     artifact.checksum_sha256 if artifact else None, order),
                )
            for evidence in record.evidence:
                cur.execute(
                    """insert into field_evidence
                       (entity_type,entity_id,field_name,normalized_value,source_record_id,artifact_id,source_text,table_row,
                        parser_name,parser_version,extraction_method,trust,confidence)
                       values ('vehicle',%s,%s,%s::jsonb,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                       on conflict do nothing""",
                    (vehicle_id, evidence.field_name, _json(evidence.normalized_value), source_record_uuid, primary_artifact_id,
                     evidence.source_text, evidence.table_row, self.source, PARSER_VERSION, evidence.extraction_method, evidence.trust, evidence.confidence),
                )
            return changed or bool(source_row["inserted"])

    def finish_run(self, run_id: str, result: SyncResult) -> None:
        status = "FAILED" if result.parsed == 0 and result.failed > 0 else "PARTIAL" if result.discovered == 0 or result.failed else "SUCCEEDED"
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """update sync_runs set completed_at=now(),status=%s,discovered_count=%s,fetched_count=%s,
                   changed_count=%s,parsed_count=%s,failed_count=%s,warnings=%s::jsonb where id=%s""",
                (status, result.discovered, result.fetched, result.changed, result.parsed, result.failed, _json(result.warnings), run_id),
            )
            if status == "SUCCEEDED":
                cur.execute("update sources set status='ACTIVE',last_successful_at=now() where id=%s", (self.source_id,))
            elif status == "FAILED":
                cur.execute("update sources set status='DEGRADED' where id=%s", (self.source_id,))
