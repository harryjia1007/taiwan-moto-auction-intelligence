from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any
import psycopg
from psycopg.rows import dict_row

from ingest import PARSER_VERSION
from ingest.models import (
    CarCategory,
    DiscoveredItem,
    EvidenceRef,
    FourState,
    ParsedAuctionRecord,
    ParsedVehicleUnit,
    RawArtifact,
    RegistrationStatus,
    SyncResult,
    VehicleClass,
    VehicleType,
)
from ingest.official_documents import official_document_urls
from ingest.storage import ArtifactStorage
from ingest.source_policy import AccessDecision, SourceAccessBlocked

SOURCE_IDS = {
    "shwoo": "20000000-0000-0000-0000-000000000001",
    "judicial": "20000000-0000-0000-0000-000000000002",
    "pcc": "20000000-0000-0000-0000-000000000004",
    "moj_auction": "20000000-0000-0000-0000-000000000005",
    "moj_enforcement": "20000000-0000-0000-0000-000000000003",
    "customs": "20000000-0000-0000-0000-000000000007",
    "moj_enforcement_cms": "20000000-0000-0000-0000-000000000008",
    "judicial_notices": "20000000-0000-0000-0000-000000000009",
}

def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def source_status_after_run(access: AccessDecision, run_status: str) -> str:
    """Resolve readiness without allowing a run to override access policy."""
    if access == AccessDecision.DISABLED:
        return "DISABLED"
    if access == AccessDecision.REVIEW_REQUIRED:
        return "DEGRADED"
    if access == AccessDecision.MANUAL_ONLY:
        return "DEGRADED" if run_status == "FAILED" else "PARTIAL"
    if run_status == "SUCCEEDED":
        return "ACTIVE"
    if run_status == "PARTIAL":
        return "PARTIAL"
    return "DEGRADED"


def evidence_artifact_id(
    evidence: EvidenceRef,
    *,
    primary_artifact_id: str,
    artifacts_by_checksum: dict[str, str],
) -> str:
    """Resolve an evidence row to the exact immutable artifact it quotes."""
    checksum = evidence.artifact_checksum_sha256
    if checksum is None:
        return primary_artifact_id
    artifact_id = artifacts_by_checksum.get(checksum)
    if artifact_id is None:
        raise ValueError(
            f"Evidence for {evidence.field_name!r} references an artifact checksum "
            "that was not saved with this record"
        )
    return artifact_id


def validate_artifact_evidence(
    artifacts: list[RawArtifact],
    evidence_rows: list[EvidenceRef],
) -> None:
    """Reject forged checksums and evidence references before writing bytes."""
    if not artifacts:
        raise ValueError("At least one raw artifact is required")
    available: set[str] = set()
    for artifact in artifacts:
        actual_checksum = hashlib.sha256(artifact.content).hexdigest()
        if artifact.checksum_sha256 != actual_checksum:
            raise ValueError("Raw artifact checksum does not match its immutable content")
        available.add(actual_checksum)
    for evidence in evidence_rows:
        checksum = evidence.artifact_checksum_sha256
        if checksum is None and len(artifacts) > 1:
            raise ValueError(
                f"Evidence for {evidence.field_name!r} must name its artifact checksum "
                "when more than one raw artifact was fetched"
            )
        if checksum is not None and checksum not in available:
            raise ValueError(
                f"Evidence for {evidence.field_name!r} references an artifact checksum "
                "that was not saved with this record"
            )


_COMPLETENESS_WEIGHTS = {
    "identity": .20,
    "auction": .25,
    "condition": .15,
    "registration": .20,
    "fees": .10,
    "media": .10,
}


def vehicle_facts_for_unit(record: ParsedAuctionRecord, unit: ParsedVehicleUnit) -> ParsedAuctionRecord:
    """Keep lot-level prose from becoming unverified facts about each vehicle.

    ParsedVehicleUnit currently carries identifiers only. When a lot has
    multiple units, its record-level brand, specifications and condition have
    no proven unit association. The original record, snapshot and lot retain
    those facts and their exact evidence; current vehicle rows remain honest.
    """
    if len(record.vehicle_units) <= 1:
        return record
    groups = dict(record.completeness_groups)
    groups.update({
        "identity": 25 if unit.identifiers else 0,
        "condition": 0,
        "registration": 0,
        "media": 0,
    })
    completeness = round(sum(groups.get(name, 0) * weight for name, weight in _COMPLETENESS_WEIGHTS.items()))
    return record.model_copy(update={
        "brand": None,
        "model": None,
        "manufacture_year": None,
        "manufacture_month": None,
        "displacement_cc": None,
        "color": None,
        "mileage_km": None,
        "vehicle_type": VehicleType.UNKNOWN if record.vehicle_type == VehicleType.MIXED else record.vehicle_type,
        "vehicle_class": VehicleClass.UNKNOWN,
        "car_category": CarCategory.UNKNOWN,
        "has_key": FourState.UNKNOWN,
        "can_start": FourState.UNKNOWN,
        "can_test": FourState.UNKNOWN,
        "registration_status": RegistrationStatus.UNKNOWN,
        "condition_summary": None,
        "visible_damage": None,
        "tax_arrears": FourState.UNKNOWN,
        "fine_arrears": FourState.UNKNOWN,
        "fuel_fee_arrears": FourState.UNKNOWN,
        "completeness": completeness,
        "completeness_groups": groups,
    })


def retain_as_bulk_lot(record: ParsedAuctionRecord) -> bool:
    """Keep a whole lot visible until every officially counted unit is identified."""
    return record.bulk_lot and len(record.vehicle_units) < record.lot_size


def validate_vehicle_unit_cardinality(record: ParsedAuctionRecord) -> None:
    """Reject contradictory current-vehicle counts before any artifact write."""
    unit_count = len(record.vehicle_units)
    if unit_count > record.lot_size or (record.lot_size > 1 and not record.bulk_lot):
        raise ValueError("Parsed vehicle-unit count conflicts with the official lot count")


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

    def require_access(
        self,
        allowed_decisions: set[AccessDecision] | frozenset[AccessDecision],
    ) -> AccessDecision:
        """Require the persisted policy before creating a run or discovering data."""
        if not allowed_decisions:
            raise ValueError("At least one source-access decision must be allowed")
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "select decision from source_access_policies where source_id=%s",
                (self.source_id,),
            )
            policy_row = cur.fetchone()
        if policy_row is None:
            raise SourceAccessBlocked(
                f"Database source-access policy is missing for {self.source}; discovery was blocked"
            )
        try:
            decision = AccessDecision(policy_row["decision"])
        except (KeyError, ValueError, TypeError) as exc:
            raise SourceAccessBlocked(
                f"Database source-access policy is invalid for {self.source}; discovery was blocked"
            ) from exc
        if decision not in allowed_decisions:
            expected = ", ".join(sorted(value.value for value in allowed_decisions))
            raise SourceAccessBlocked(
                f"Database source-access policy for {self.source} is {decision.value}; "
                f"this operation requires {expected}"
            )
        return decision

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
        validate_vehicle_unit_cardinality(record)
        validate_artifact_evidence(artifacts, record.evidence)
        checksums = [artifact.checksum_sha256 for artifact in artifacts]
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """select distinct ra.checksum_sha256
                   from raw_artifacts ra
                   join artifact_tombstones tombstone on tombstone.artifact_id=ra.id
                   where ra.checksum_sha256 = any(%s)""",
                (checksums,),
            )
            tombstoned = [str(row["checksum_sha256"]) for row in cur.fetchall()]
        if tombstoned:
            raise ValueError(
                "A previously purged artifact checksum was fetched again; "
                "storage restoration requires an explicit audited artifact generation"
            )
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
                    (source_record_id,sync_run_id,official_url,fetched_at,http_status,http_headers,mime_type,filename,checksum_sha256,content_length,storage_path,extraction_status,parser_version,retention_until)
                    values (%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s,'PARSED',%s,%s + interval '12 months')
                    on conflict (checksum_sha256,storage_path) do nothing returning id
                    """,
                    (source_record_uuid, run_id, str(artifact.official_url), artifact.fetched_at, artifact.http_status,
                     _json(artifact.http_headers), artifact.mime_type, artifact.filename, artifact.checksum_sha256,
                     len(artifact.content), path, PARSER_VERSION, record.ends_at or artifact.fetched_at),
                )
                row = cur.fetchone()
                if row:
                    artifact_ids.append(str(row["id"]))
                else:
                    cur.execute("select id from raw_artifacts where checksum_sha256=%s and storage_path=%s", (artifact.checksum_sha256, path))
                    artifact_ids.append(str(cur.fetchone()["id"]))
            for order, artifact_id in enumerate(artifact_ids):
                cur.execute(
                    """insert into source_record_artifacts
                       (source_record_id,artifact_id,first_sync_run_id,last_sync_run_id,
                        artifact_role,sort_order,first_seen_at,last_seen_at)
                       values (%s,%s,%s,%s,%s,%s,now(),now())
                       on conflict (source_record_id,artifact_id) do update
                       set last_sync_run_id=excluded.last_sync_run_id,
                           artifact_role=case
                             when source_record_artifacts.artifact_role='PRIMARY' then 'PRIMARY'
                             else excluded.artifact_role
                           end,
                           sort_order=least(source_record_artifacts.sort_order,excluded.sort_order),
                           last_seen_at=now()""",
                    (
                        source_record_uuid,
                        artifact_id,
                        run_id,
                        run_id,
                        "PRIMARY" if order == 0 else "SUPPORTING",
                        order,
                    ),
                )
            artifacts_by_url = {
                str(artifact.official_url): (artifact, artifact_id, path)
                for artifact, artifact_id, path in zip(artifacts, artifact_ids, paths, strict=True)
            }
            artifacts_by_checksum = {
                artifact.checksum_sha256: artifact_id
                for artifact, artifact_id in zip(artifacts, artifact_ids, strict=True)
            }
            primary_artifact_id = artifact_ids[0]
            cached_documents = {
                str(artifact.official_url): artifact_id
                for artifact, artifact_id in zip(artifacts, artifact_ids, strict=True)
                if artifact.mime_type == "application/pdf"
            }
            document_urls = official_document_urls(
                record,
                self.source,
                artifact_urls=cached_documents,
            )
            for official_url in document_urls:
                cached_artifact_id = cached_documents.get(official_url)
                if cached_artifact_id is not None:
                    cur.execute(
                        """insert into documents
                           (source_record_id,artifact_id,title,document_type,official_url)
                           values (%s,%s,%s,'OFFICIAL_AUCTION_NOTICE',%s)
                           on conflict (source_record_id,official_url) do update
                           set artifact_id=excluded.artifact_id,title=excluded.title,
                               document_type=excluded.document_type""",
                        (
                            source_record_uuid,
                            cached_artifact_id,
                            f"{record.title}－官方拍賣公告",
                            official_url,
                        ),
                    )
                else:
                    cur.execute(
                        """insert into documents
                           (source_record_id,artifact_id,title,document_type,official_url)
                           values (%s,null,%s,'OFFICIAL_LINK_ONLY',%s)
                           on conflict (source_record_id,official_url) do nothing""",
                        (source_record_uuid, f"{record.title}－官方完整全文", official_url),
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
                (auction_event_id,lot_number,title,lot_size,bulk_lot,eligibility,vehicle_type,vehicle_category,car_category,storage_location,original_description,fee_notes,
                 registration_status,has_key,can_start,can_test,condition_summary,completeness,completeness_groups)
                values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
                on conflict (auction_event_id,(coalesce(lot_number,''))) do update
                set title=excluded.title,lot_size=excluded.lot_size,bulk_lot=excluded.bulk_lot,
                    eligibility=excluded.eligibility,vehicle_type=excluded.vehicle_type,vehicle_category=excluded.vehicle_category,
                    car_category=excluded.car_category,storage_location=excluded.storage_location,
                    original_description=excluded.original_description,fee_notes=excluded.fee_notes,
                    registration_status=excluded.registration_status,has_key=excluded.has_key,
                    can_start=excluded.can_start,can_test=excluded.can_test,
                    condition_summary=excluded.condition_summary,completeness=excluded.completeness,
                    completeness_groups=excluded.completeness_groups
                returning id
                """,
                (event_id, "1", record.title, record.lot_size, record.bulk_lot, record.eligibility.value,
                 record.vehicle_type.value, record.vehicle_class.value, record.car_category.value,
                 record.location, record.description, record.fee_notes, record.registration_status.value,
                 record.has_key.value, record.can_start.value, record.can_test.value,
                 record.condition_summary, record.completeness, _json(record.completeness_groups)),
            )
            lot_id = cur.fetchone()["id"]

            # An inseparable or only partly identified bulk description is a
            # real lot, not evidence of N individually identified vehicles.
            # A single known plate must not make the remaining vehicles vanish
            # from the current marketplace projection.
            if retain_as_bulk_lot(record):
                cur.execute(
                    """update vehicles
                       set projection_active=false,projection_retired_at=now(),
                           projection_retired_reason=%s,updated_at=now()
                       where lot_id=%s and projection_active""",
                    (f"Parser {PARSER_VERSION} retained an incompletely identified official bulk lot", lot_id),
                )
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
                    artifact_id = evidence_artifact_id(
                        evidence,
                        primary_artifact_id=primary_artifact_id,
                        artifacts_by_checksum=artifacts_by_checksum,
                    )
                    cur.execute(
                        """insert into field_evidence
                           (entity_type,entity_id,field_name,normalized_value,source_record_id,artifact_id,source_text,table_row,
                            parser_name,parser_version,extraction_method,trust,confidence)
                           values ('lot',%s,%s,%s::jsonb,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                           on conflict do nothing""",
                        (lot_id, evidence.field_name, _json(evidence.normalized_value), source_record_uuid, artifact_id,
                         evidence.source_text, evidence.table_row, self.source, PARSER_VERSION, evidence.extraction_method,
                         evidence.trust, evidence.confidence),
                    )
                return changed or bool(source_row["inserted"])

            # A newer snapshot is authoritative only for the current projection,
            # never for history. Retire earlier rows first, then reactivate only
            # vehicle identities explicitly present in this parse.
            cur.execute(
                """update vehicles
                   set projection_active=false,projection_retired_at=now(),
                       projection_retired_reason=%s,updated_at=now()
                   where lot_id=%s and projection_active""",
                (f"Superseded by parser {PARSER_VERSION}", lot_id),
            )
            primary_unit = record.vehicle_units[0] if record.vehicle_units else None
            primary_facts = vehicle_facts_for_unit(record, primary_unit) if primary_unit else record
            brand_id = None
            if primary_facts.brand:
                cur.execute("select id from vehicle_brands where %s = any(aliases) or canonical_name=%s limit 1", (primary_facts.brand, primary_facts.brand))
                row = cur.fetchone()
                brand_id = row["id"] if row else None
            model_id = None
            if brand_id and primary_facts.model:
                cur.execute("select id from vehicle_models where brand_id=%s and (canonical_name=%s or model_code=%s) limit 1", (brand_id, primary_facts.model, primary_facts.model))
                row = cur.fetchone()
                model_id = row["id"] if row else None
            cur.execute(
                """
                insert into vehicles
                (lot_id,source_vehicle_key,brand_id,model_id,original_brand,original_model,model_code,vehicle_type,vehicle_category,car_category,manufacture_year,manufacture_month,
                 displacement_cc,color,mileage_km,has_key,can_start,can_test,registration_status,condition_summary,visible_damage,
                 tax_arrears,fine_arrears,fuel_fee_arrears,completeness,completeness_groups,
                 projection_active,projection_retired_at,projection_retired_reason)
                values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,true,null,null)
                on conflict (lot_id,source_vehicle_key) do update set
                 brand_id=excluded.brand_id,model_id=excluded.model_id,original_brand=excluded.original_brand,original_model=excluded.original_model,
                 vehicle_type=excluded.vehicle_type,vehicle_category=excluded.vehicle_category,car_category=excluded.car_category,
                 manufacture_year=excluded.manufacture_year,manufacture_month=excluded.manufacture_month,displacement_cc=excluded.displacement_cc,
                 color=excluded.color,mileage_km=excluded.mileage_km,has_key=excluded.has_key,can_start=excluded.can_start,can_test=excluded.can_test,
                 registration_status=excluded.registration_status,condition_summary=excluded.condition_summary,visible_damage=excluded.visible_damage,
                 tax_arrears=excluded.tax_arrears,fine_arrears=excluded.fine_arrears,fuel_fee_arrears=excluded.fuel_fee_arrears,
                 completeness=excluded.completeness,completeness_groups=excluded.completeness_groups,
                 projection_active=true,projection_retired_at=null,projection_retired_reason=null
                returning id
                """,
                (lot_id, primary_unit.source_vehicle_key if primary_unit else "primary",
                 brand_id, model_id, primary_facts.brand, primary_facts.model, primary_facts.model, primary_facts.vehicle_type.value,
                 primary_facts.vehicle_class.value, primary_facts.car_category.value, primary_facts.manufacture_year, primary_facts.manufacture_month,
                 primary_facts.displacement_cc, primary_facts.color, primary_facts.mileage_km, primary_facts.has_key.value,
                 primary_facts.can_start.value, primary_facts.can_test.value,
                 primary_facts.registration_status.value, primary_facts.condition_summary, primary_facts.visible_damage,
                 primary_facts.tax_arrears.value, primary_facts.fine_arrears.value, primary_facts.fuel_fee_arrears.value,
                 primary_facts.completeness, _json(primary_facts.completeness_groups)),
            )
            vehicle_id = cur.fetchone()["id"]
            primary_identifiers = record.vehicle_units[0].identifiers if record.vehicle_units else record.identifiers
            cur.execute(
                "update vehicle_identifiers set projection_active=false where vehicle_id=%s and projection_active",
                (vehicle_id,),
            )
            for identifier in primary_identifiers:
                cur.execute(
                    """insert into vehicle_identifiers
                       (vehicle_id,identifier_type,normalized_value,original_value,projection_active)
                       values (%s,%s,%s,%s,true) on conflict (vehicle_id,identifier_type,normalized_value)
                       do update set original_value=excluded.original_value,projection_active=true""",
                    (vehicle_id, identifier.identifier_type, identifier.normalized_value, identifier.original_value),
                )
            for unit in record.vehicle_units[1:]:
                unit_facts = vehicle_facts_for_unit(record, unit)
                cur.execute(
                    """
                    insert into vehicles
                    (lot_id,source_vehicle_key,brand_id,model_id,original_brand,original_model,model_code,vehicle_type,vehicle_category,car_category,manufacture_year,manufacture_month,
                     displacement_cc,color,mileage_km,has_key,can_start,can_test,registration_status,condition_summary,visible_damage,
                     tax_arrears,fine_arrears,fuel_fee_arrears,completeness,completeness_groups,
                     projection_active,projection_retired_at,projection_retired_reason)
                    values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,true,null,null)
                    on conflict (lot_id,source_vehicle_key) do update set
                      brand_id=excluded.brand_id,model_id=excluded.model_id,
                      original_brand=excluded.original_brand,original_model=excluded.original_model,
                      model_code=excluded.model_code,vehicle_type=excluded.vehicle_type,
                      vehicle_category=excluded.vehicle_category,car_category=excluded.car_category,
                      manufacture_year=excluded.manufacture_year,manufacture_month=excluded.manufacture_month,
                      displacement_cc=excluded.displacement_cc,color=excluded.color,mileage_km=excluded.mileage_km,
                      has_key=excluded.has_key,can_start=excluded.can_start,can_test=excluded.can_test,
                      registration_status=excluded.registration_status,condition_summary=excluded.condition_summary,
                      visible_damage=excluded.visible_damage,tax_arrears=excluded.tax_arrears,
                      fine_arrears=excluded.fine_arrears,fuel_fee_arrears=excluded.fuel_fee_arrears,
                      completeness=excluded.completeness,completeness_groups=excluded.completeness_groups,
                      projection_active=true,projection_retired_at=null,
                      projection_retired_reason=null,updated_at=now()
                    returning id
                    """,
                    (lot_id, unit.source_vehicle_key, brand_id, model_id, unit_facts.brand, unit_facts.model, unit_facts.model,
                     unit_facts.vehicle_type.value, unit_facts.vehicle_class.value, unit_facts.car_category.value,
                     unit_facts.manufacture_year, unit_facts.manufacture_month, unit_facts.displacement_cc,
                     unit_facts.color, unit_facts.mileage_km,
                     unit_facts.has_key.value, unit_facts.can_start.value, unit_facts.can_test.value,
                     unit_facts.registration_status.value, unit_facts.condition_summary, unit_facts.visible_damage,
                     unit_facts.tax_arrears.value, unit_facts.fine_arrears.value, unit_facts.fuel_fee_arrears.value,
                     unit_facts.completeness, _json(unit_facts.completeness_groups)),
                )
                unit_vehicle_id = cur.fetchone()["id"]
                cur.execute(
                    "update vehicle_identifiers set projection_active=false where vehicle_id=%s and projection_active",
                    (unit_vehicle_id,),
                )
                for identifier in unit.identifiers:
                    cur.execute(
                        """insert into vehicle_identifiers
                           (vehicle_id,identifier_type,normalized_value,original_value,projection_active)
                           values (%s,%s,%s,%s,true) on conflict (vehicle_id,identifier_type,normalized_value)
                           do update set original_value=excluded.original_value,projection_active=true""",
                        (unit_vehicle_id, identifier.identifier_type, identifier.normalized_value, identifier.original_value),
                    )
                cur.execute(
                    """insert into vehicle_observations (vehicle_id,snapshot_id,observed_at,payload)
                       values (%s,%s,now(),%s::jsonb)
                       on conflict (vehicle_id,snapshot_id) do nothing""",
                    (unit_vehicle_id, snapshot_id, payload_json),
                )
            cur.execute(
                """insert into vehicle_observations (vehicle_id,snapshot_id,observed_at,payload)
                   values (%s,%s,now(),%s::jsonb) on conflict (vehicle_id,snapshot_id) do nothing""",
                (vehicle_id, snapshot_id, payload_json),
            )
            for order, url in enumerate(record.photo_urls):
                matched = artifacts_by_url.get(str(url))
                artifact, artifact_id, storage_path = matched if matched else (None, None, None)
                # A source image with no per-unit association documents the
                # whole lot, not the first plate in a multi-vehicle notice.
                photo_vehicle_id = vehicle_id if len(record.vehicle_units) <= 1 else None
                photo_lot_id = lot_id if len(record.vehicle_units) > 1 else None
                cur.execute(
                    """insert into photos (vehicle_id,lot_id,source_record_id,artifact_id,source_url,storage_path,checksum_sha256,sort_order)
                       values (%s,%s,%s,%s,%s,%s,%s,%s) on conflict (source_record_id,source_url)
                       do update set vehicle_id=excluded.vehicle_id,lot_id=excluded.lot_id,
                         artifact_id=coalesce(excluded.artifact_id,photos.artifact_id),
                         storage_path=coalesce(excluded.storage_path,photos.storage_path),
                         checksum_sha256=coalesce(excluded.checksum_sha256,photos.checksum_sha256),
                         sort_order=excluded.sort_order,last_seen_at=now(),availability_status='AVAILABLE'""",
                    (photo_vehicle_id, photo_lot_id, source_record_uuid, artifact_id, str(url), storage_path,
                     artifact.checksum_sha256 if artifact else None, order),
                )
            for evidence in record.evidence:
                artifact_id = evidence_artifact_id(
                    evidence,
                    primary_artifact_id=primary_artifact_id,
                    artifacts_by_checksum=artifacts_by_checksum,
                )
                cur.execute(
                    """insert into field_evidence
                       (entity_type,entity_id,field_name,normalized_value,source_record_id,artifact_id,source_text,table_row,
                        parser_name,parser_version,extraction_method,trust,confidence)
                       values (%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                       on conflict do nothing""",
                    ("lot" if len(record.vehicle_units) > 1 else "vehicle",
                     lot_id if len(record.vehicle_units) > 1 else vehicle_id,
                     evidence.field_name, _json(evidence.normalized_value), source_record_uuid, artifact_id,
                     evidence.source_text, evidence.table_row, self.source, PARSER_VERSION, evidence.extraction_method, evidence.trust, evidence.confidence),
                )
            return changed or bool(source_row["inserted"])

    async def purge_expired_artifacts(self, *, execute: bool = False) -> list[dict[str, Any]]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                with artifact_references as (
                  select link.artifact_id,link.source_record_id,link.last_seen_at as referenced_at
                  from source_record_artifacts link
                  union all
                  select snapshot.artifact_id,snapshot.source_record_id,snapshot.observed_at
                  from snapshots snapshot where snapshot.artifact_id is not null
                  union all
                  select document.artifact_id,document.source_record_id,document.created_at
                  from documents document where document.artifact_id is not null
                  union all
                  select photo.artifact_id,photo.source_record_id,
                         greatest(photo.first_seen_at,photo.last_seen_at)
                  from photos photo where photo.artifact_id is not null
                  union all
                  select evidence.artifact_id,evidence.source_record_id,evidence.created_at
                  from field_evidence evidence
                ),
                reference_deadlines as (
                  select reference.artifact_id,
                         max(
                           greatest(
                             reference.referenced_at,
                             coalesce(event.latest_end,reference.referenced_at)
                           ) + interval '12 months'
                         ) as retention_until
                  from artifact_references reference
                  left join lateral (
                    select max(auction_event.ends_at) as latest_end
                    from auction_events auction_event
                    where auction_event.source_record_id=reference.source_record_id
                  ) event on true
                  group by reference.artifact_id
                )
                select ra.id,ra.storage_path,ra.checksum_sha256,
                       greatest(ra.retention_until,
                                coalesce(deadline.retention_until,ra.retention_until)) as retention_until
                from raw_artifacts ra
                join source_records sr on sr.id=ra.source_record_id
                left join artifact_tombstones at on at.artifact_id=ra.id
                left join reference_deadlines deadline on deadline.artifact_id=ra.id
                where sr.source_id=%s and at.id is null
                  and greatest(ra.retention_until,
                               coalesce(deadline.retention_until,ra.retention_until)) <= now()
                order by retention_until,ra.id
                """,
                (self.source_id,),
            )
            rows = [dict(row) for row in cur.fetchall()]
        if not execute:
            return rows
        for row in rows:
            await self.storage.delete(row["storage_path"])
            with self._connect() as conn, conn.cursor() as cur:
                cur.execute(
                    """insert into artifact_tombstones (artifact_id,storage_path,checksum_sha256,reason)
                       values (%s,%s,%s,'12-month private artifact retention expired')
                       on conflict (artifact_id) do nothing""",
                    (row["id"], row["storage_path"], row["checksum_sha256"]),
                )
        return rows

    def finish_run(self, run_id: str, result: SyncResult) -> None:
        status = (
            "FAILED" if result.parsed == 0 and result.failed > 0
            else "PARTIAL" if result.discovered == 0 or result.failed or result.warnings
            else "SUCCEEDED"
        )
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """update sync_runs set completed_at=now(),status=%s,discovered_count=%s,fetched_count=%s,
                   changed_count=%s,parsed_count=%s,failed_count=%s,warnings=%s::jsonb where id=%s""",
                (status, result.discovered, result.fetched, result.changed, result.parsed, result.failed, _json(result.warnings), run_id),
            )
            cur.execute(
                "select decision from source_access_policies where source_id=%s",
                (self.source_id,),
            )
            policy_row = cur.fetchone()
            # Missing registry state is never permission to promote a source.
            access = (
                AccessDecision(policy_row["decision"])
                if policy_row is not None
                else AccessDecision.REVIEW_REQUIRED
            )
            source_status = source_status_after_run(access, status)
            if status == "SUCCEEDED":
                cur.execute(
                    "update sources set status=%s,last_successful_at=now() where id=%s",
                    (source_status, self.source_id),
                )
            else:
                cur.execute("update sources set status=%s where id=%s", (source_status, self.source_id))
