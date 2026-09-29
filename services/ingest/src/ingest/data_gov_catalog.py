from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, Iterable, Mapping
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

import httpx

from ingest.adapters.base import contact_user_agent


CATALOG_EXPORT_URL = "https://data.gov.tw/api/front/dataset/export?format=json"
CATALOG_METADATA_URL_PREFIX = "https://data.gov.tw/dataset/"
CATALOG_HOST = "data.gov.tw"
CATALOG_PATHS = frozenset({"/api/front/dataset/export", "/api/front/dataset/export/"})
DEFAULT_LOOKBACK_DAYS = 14
MAX_CATALOG_BYTES = 128 * 1024 * 1024
MAX_CATALOG_ENTRIES = 100_000
MIN_CATALOG_ENTRIES = 1_000
MAX_CANDIDATES = 200
MAX_SEMANTIC_FIELD_CHARACTERS = 16_000

_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
_JSON_CONTENT_TYPES = frozenset({"application/json"})
_DATASET_ID_PATTERN = re.compile(r"^[1-9][0-9]{0,11}$")
_AUCTION_PATTERN = re.compile(r"拍賣|法拍|標售|標賣|變賣|拍定|公開競價|競標|出售")
_VEHICLE_PATTERN = re.compile(
    r"汽機車|汽車|機車|重機|車輛|公務車|小客車|大客車|客貨車|貨車|曳引車|拖車|"
    r"電動車|遊覽車|巴士|車體|車籍"
)
_REAL_ESTATE_PATTERN = re.compile(r"不動產|房地|土地|建物|房屋")
_ADMINISTRATIVE_ENFORCEMENT_PATTERN = re.compile(r"行政執行(?:署|分署)")
_JUDICIAL_PATTERN = re.compile(r"司法院|司法機關|(?:地方|高等|最高|行政|智慧財產及商業)法院|地方法院|法院")
_GOVERNMENT_AGENCY_PATTERN = re.compile(
    r"政府|公所|法務部|財政部|交通部|司法院|法院|行政執行|檢察署|警察(?:署|局)|"
    r"關務署|海關|監理(?:所|站)|公路局|國有財產署|管理(?:處|局)|委員會|"
    r"(?:部|署|局|處|會|院)$|國立|公立|國營|公營"
)


class DataGovCatalogError(RuntimeError):
    """Base error for a bounded metadata-only catalog check."""


class DataGovCatalogNetworkError(DataGovCatalogError):
    """The official catalog could not be read safely."""


class DataGovCatalogValidationError(DataGovCatalogError):
    """The response did not validate as the documented official catalog."""


@dataclass(frozen=True)
class CatalogCandidate:
    dataset_id: int
    published_on: date | None
    scope: str

    @property
    def metadata_url(self) -> str:
        return f"{CATALOG_METADATA_URL_PREFIX}{self.dataset_id}"

    def as_dict(self) -> dict[str, str | int | None]:
        # Deliberately omit title, description, keywords and publisher contacts.
        # A reviewer follows the official metadata URL before approving a source.
        return {
            "dataset_id": self.dataset_id,
            "metadata_url": self.metadata_url,
            "published_on": self.published_on.isoformat() if self.published_on else None,
            "scope": self.scope,
        }


@dataclass(frozen=True)
class CatalogWatchResult:
    checked_at: datetime
    published_after: date
    scanned_entries: int
    recent_entries: int
    undated_matching_entries: int
    document_sha256: str
    candidates: tuple[CatalogCandidate, ...]

    @property
    def status(self) -> str:
        return "warning" if self.candidates else "success"

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "checked_at": self.checked_at.astimezone(UTC).isoformat(),
            "catalog_export_url": CATALOG_EXPORT_URL,
            "published_after": self.published_after.isoformat(),
            "scanned_entries": self.scanned_entries,
            "recent_entries": self.recent_entries,
            "undated_matching_entries": self.undated_matching_entries,
            "document_sha256": self.document_sha256,
            "candidate_count": len(self.candidates),
            "candidates": [candidate.as_dict() for candidate in self.candidates],
            "notice": "metadata candidate only; no auction case was created or published",
        }


def taipei_catalog_cutoff(*, lookback_days: int, now: datetime | None = None) -> date:
    if lookback_days < 1 or lookback_days > 90:
        raise ValueError("lookback_days must be between 1 and 90")
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    return current.astimezone(ZoneInfo("Asia/Taipei")).date() - timedelta(days=lookback_days)


def _validate_catalog_url(value: str | httpx.URL) -> httpx.URL:
    url = httpx.URL(value)
    if (
        url.scheme != "https"
        or url.host != CATALOG_HOST
        or url.port not in (None, 443)
        or url.userinfo
        or url.path not in CATALOG_PATHS
        or url.fragment
        or len(url.params.multi_items()) != 1
        or url.params.get_list("format") != ["json"]
    ):
        raise DataGovCatalogValidationError("Catalog redirect left the exact official HTTPS export endpoint")
    return url


def _validate_download_headers(headers: Mapping[str, str]) -> None:
    content_type = headers.get("content-type", "").split(";", 1)[0].strip().lower()
    disposition = headers.get("content-disposition", "").lower()
    filename_is_json = ".json" in disposition and "filename" in disposition
    if content_type in _JSON_CONTENT_TYPES:
        return
    # data.gov.tw currently labels the JSON attachment as text/html. Accept that
    # narrow exception only when the official attachment filename is explicitly JSON;
    # the body still has to pass JSON-array validation below.
    if content_type in {"text/html", "application/octet-stream"} and filename_is_json:
        return
    raise DataGovCatalogValidationError("Official catalog response did not declare a supported JSON download MIME")


async def download_official_catalog(
    *,
    client: httpx.AsyncClient | None = None,
    max_bytes: int = MAX_CATALOG_BYTES,
    max_redirects: int = 2,
) -> bytes:
    if max_bytes < 1 or max_bytes > MAX_CATALOG_BYTES:
        raise ValueError(f"max_bytes must be between 1 and {MAX_CATALOG_BYTES}")
    if max_redirects < 0 or max_redirects > 2:
        raise ValueError("max_redirects must be between 0 and 2")

    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient(
            follow_redirects=False,
            timeout=httpx.Timeout(connect=10, read=120, write=10, pool=10),
            limits=httpx.Limits(max_connections=1, max_keepalive_connections=1),
        )

    # The catalog is a public, stateless download. Never inherit a login/session
    # cookie from a caller-provided client or replay one after an official redirect.
    client.cookies.clear()
    client.headers.pop("cookie", None)
    current_url = _validate_catalog_url(CATALOG_EXPORT_URL)
    try:
        for redirect_number in range(max_redirects + 1):
            try:
                async with client.stream(
                    "GET",
                    current_url,
                    follow_redirects=False,
                    headers={
                        "Accept": "application/json, application/octet-stream;q=0.9",
                        "User-Agent": contact_user_agent("data-gov-catalog-watcher/1.0"),
                    },
                ) as response:
                    if response.status_code in _REDIRECT_STATUSES:
                        location = response.headers.get("location")
                        if location is None or redirect_number >= max_redirects:
                            raise DataGovCatalogValidationError("Official catalog redirect was missing or exceeded the limit")
                        current_url = _validate_catalog_url(urljoin(str(response.url), location))
                        client.cookies.clear()
                        continue

                    if response.status_code < 200 or response.status_code >= 300:
                        raise DataGovCatalogNetworkError(
                            f"Official catalog returned HTTP {response.status_code}; no metadata was accepted"
                        )
                    _validate_download_headers(response.headers)
                    declared_length = response.headers.get("content-length", "").strip()
                    if declared_length.isdigit() and int(declared_length) > max_bytes:
                        raise DataGovCatalogValidationError("Official catalog exceeded the declared response-size limit")

                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        body.extend(chunk)
                        if len(body) > max_bytes:
                            raise DataGovCatalogValidationError("Official catalog exceeded the response-size limit")
                    if not body:
                        raise DataGovCatalogValidationError("Official catalog response was empty")
                    if bytes(body).lstrip()[:1] != b"[":
                        raise DataGovCatalogValidationError("Official catalog response was not a JSON array")
                    return bytes(body)
            except DataGovCatalogError:
                raise
            except (httpx.HTTPError, OSError) as exc:
                raise DataGovCatalogNetworkError("Official catalog network request failed") from exc
    finally:
        if owns_client:
            await client.aclose()

    raise DataGovCatalogValidationError("Official catalog redirect processing did not complete")


def _semantic_text(entry: Mapping[str, Any]) -> str:
    values: list[str] = []
    for key in ("提供機關", "資料集名稱", "資料集描述", "關鍵字", "主要欄位說明"):
        value = entry.get(key)
        if isinstance(value, str):
            text = value
        elif isinstance(value, (list, tuple)):
            text = " ".join(part for part in value if isinstance(part, str))
        else:
            continue
        if len(text) > MAX_SEMANTIC_FIELD_CHARACTERS:
            half = MAX_SEMANTIC_FIELD_CHARACTERS // 2
            text = f"{text[:half]} {text[-half:]}"
        values.append(text)
    normalized = unicodedata.normalize("NFKC", " ".join(values))
    return " ".join(normalized.split())


def _publisher_text(entry: Mapping[str, Any]) -> str:
    value = entry.get("提供機關")
    if not isinstance(value, str):
        return ""
    return " ".join(unicodedata.normalize("NFKC", value).split())[:1_000]


def _scope_for(entry: Mapping[str, Any], semantic_text: str) -> str | None:
    publisher = _publisher_text(entry)
    if not publisher or not _GOVERNMENT_AGENCY_PATTERN.search(publisher):
        return None
    if _ADMINISTRATIVE_ENFORCEMENT_PATTERN.search(semantic_text):
        return "ADMINISTRATIVE_ENFORCEMENT"
    if _JUDICIAL_PATTERN.search(semantic_text):
        return "JUDICIAL"
    return "GOVERNMENT_VEHICLE_AUCTION"


def _published_on(entry: Mapping[str, Any]) -> date | None:
    value = entry.get("上架日期")
    if not isinstance(value, str) or len(value) < 10:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _dataset_id(entry: Mapping[str, Any]) -> int | None:
    value = entry.get("資料集識別碼")
    text = str(value).strip() if isinstance(value, (str, int)) and not isinstance(value, bool) else ""
    if not _DATASET_ID_PATTERN.fullmatch(text):
        return None
    return int(text)


def _candidate_scope(entry: Mapping[str, Any]) -> str | None:
    semantic_text = _semantic_text(entry)
    if not _AUCTION_PATTERN.search(semantic_text) or not _VEHICLE_PATTERN.search(semantic_text):
        return None
    # A property dataset is not relevant merely because the Chinese word
    # 「不動產」 contains 「動產」. Mixed datasets with explicit vehicle terms
    # remain review candidates; pure property datasets are excluded.
    if _REAL_ESTATE_PATTERN.search(semantic_text) and not _VEHICLE_PATTERN.search(semantic_text):
        return None
    return _scope_for(entry, semantic_text)


def candidate_from_entry(entry: Mapping[str, Any], *, published_after: date) -> CatalogCandidate | None:
    scope = _candidate_scope(entry)
    if scope is None:
        return None
    published_on = _published_on(entry)
    # Missing dates cannot prove that a dataset is newly published. Count them in
    # the aggregate watch result, but never emit them as a recurring new candidate.
    if published_on is None or published_on < published_after:
        return None
    dataset_id = _dataset_id(entry)
    if dataset_id is None:
        raise DataGovCatalogValidationError("A matching catalog entry had no valid dataset identifier")
    return CatalogCandidate(dataset_id=dataset_id, published_on=published_on, scope=scope)


def _decode_catalog(document: bytes, *, min_entries: int) -> list[Mapping[str, Any]]:
    try:
        decoded = json.loads(document.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DataGovCatalogValidationError("Official catalog was not valid UTF-8 JSON") from exc
    if not isinstance(decoded, list):
        raise DataGovCatalogValidationError("Official catalog root was not an array")
    if len(decoded) < min_entries:
        raise DataGovCatalogValidationError("Official catalog contained unexpectedly few entries")
    if len(decoded) > MAX_CATALOG_ENTRIES:
        raise DataGovCatalogValidationError("Official catalog exceeded the entry-count limit")
    if any(not isinstance(entry, dict) for entry in decoded):
        raise DataGovCatalogValidationError("Official catalog contained a non-object entry")
    return decoded


def evaluate_catalog(
    document: bytes,
    *,
    published_after: date,
    checked_at: datetime | None = None,
    min_entries: int = MIN_CATALOG_ENTRIES,
) -> CatalogWatchResult:
    if min_entries < 1 or min_entries > MIN_CATALOG_ENTRIES:
        raise ValueError(f"min_entries must be between 1 and {MIN_CATALOG_ENTRIES}")
    entries = _decode_catalog(document, min_entries=min_entries)
    recent_entries = sum(
        1 for entry in entries if (published_on := _published_on(entry)) is not None and published_on >= published_after
    )
    candidates_by_id: dict[int, CatalogCandidate] = {}
    undated_matching_entries = 0
    for entry in entries:
        scope = _candidate_scope(entry)
        if scope is None:
            continue
        published_on = _published_on(entry)
        if published_on is None:
            undated_matching_entries += 1
            continue
        if published_on < published_after:
            continue
        dataset_id = _dataset_id(entry)
        if dataset_id is None:
            raise DataGovCatalogValidationError("A matching catalog entry had no valid dataset identifier")
        candidates_by_id.setdefault(
            dataset_id,
            CatalogCandidate(dataset_id=dataset_id, published_on=published_on, scope=scope),
        )
    if len(candidates_by_id) > MAX_CANDIDATES:
        raise DataGovCatalogValidationError("Official catalog produced an implausible number of review candidates")
    current = checked_at or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    candidates = tuple(
        sorted(
            candidates_by_id.values(),
            key=lambda candidate: (candidate.published_on or date.max, candidate.dataset_id),
            reverse=True,
        )
    )
    return CatalogWatchResult(
        checked_at=current,
        published_after=published_after,
        scanned_entries=len(entries),
        recent_entries=recent_entries,
        undated_matching_entries=undated_matching_entries,
        document_sha256=hashlib.sha256(document).hexdigest(),
        candidates=candidates,
    )


async def watch_official_catalog(
    *,
    published_after: date,
    client: httpx.AsyncClient | None = None,
    checked_at: datetime | None = None,
    min_entries: int = MIN_CATALOG_ENTRIES,
) -> CatalogWatchResult:
    document = await download_official_catalog(client=client)
    return evaluate_catalog(
        document,
        published_after=published_after,
        checked_at=checked_at,
        min_entries=min_entries,
    )


def github_warning_lines(candidates: Iterable[CatalogCandidate]) -> list[str]:
    return [
        "::warning title=data.gov.tw 官方資料集候選::"
        f"資料集 {candidate.dataset_id} 需要人工審核：{candidate.metadata_url}"
        for candidate in candidates
    ]
