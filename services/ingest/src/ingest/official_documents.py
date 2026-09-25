from __future__ import annotations

import re
from collections.abc import Iterable
from urllib.parse import parse_qs, unquote, urlparse
from uuid import UUID

from ingest.models import ParsedAuctionRecord


ENFORCEMENT_CMS_HOSTS = frozenset({
    "www.tpy.moj.gov.tw",
    "www.sly.moj.gov.tw",
    "www.pcy.moj.gov.tw",
    "www.tyy.moj.gov.tw",
    "www.scy.moj.gov.tw",
    "www.tcy.moj.gov.tw",
    "www.chy.moj.gov.tw",
    "www.cyy.moj.gov.tw",
    "www.tny.moj.gov.tw",
    "www.ksy.moj.gov.tw",
    "www.pty.moj.gov.tw",
    "www.hly.moj.gov.tw",
    "www.ily.moj.gov.tw",
})

MOJ_AUCTION_DOCUMENT_HOSTS = frozenset({
    "auction.moj.gov.tw",
    "www.tcc.moj.gov.tw",
    "www.qtc.moj.gov.tw",
    "www.ulc.moj.gov.tw",
})


def validated_official_document_url(source: str, value: str) -> str | None:
    """Validate an outbound document URL against the exact producing source.

    This validator is shared by the private normalized repository and the
    anonymous projection. It deliberately recognizes only reviewed document
    shapes; a safe-looking page elsewhere on the same government host is not an
    auction attachment.
    """
    candidate = value.strip()
    if not candidate or candidate != value or any(ord(character) < 32 or ord(character) == 127 for character in candidate):
        return None
    try:
        parsed = urlparse(candidate)
        port = parsed.port
    except ValueError:
        return None
    if (
        parsed.scheme != "https"
        or parsed.username is not None
        or parsed.password is not None
        or port not in {None, 443}
        or parsed.fragment
        or parsed.params
    ):
        return None
    host = (parsed.hostname or "").lower()
    decoded_path = unquote(parsed.path)
    if ".." in decoded_path.split("/"):
        return None
    query = parse_qs(parsed.query, keep_blank_values=True)

    if source == "judicial":
        filenames = query.get("filenm", [])
        if (
            host == "aomp109.judicial.gov.tw"
            and parsed.path == "/judbp/wkw/WHD1A02/DO_VIEWPDF.htm"
            and set(query) == {"filenm"}
            and len(filenames) == 1
            and filenames[0].lower().endswith(".pdf")
        ):
            return candidate
        return None

    if source == "judicial_notices":
        if (
            host == "www.judicial.gov.tw"
            and not parsed.query
            and re.fullmatch(r"/tw/dl-\d+-[A-Za-z0-9-]+\.html", decoded_path)
        ):
            return candidate
        return None

    if source == "moj_enforcement":
        if (
            host != "www.tpkonsale.moj.gov.tw"
            or parsed.path != "/File/Download"
            or not {"PATH", "NAME"}.issubset(query)
            or not set(query).issubset({"PATH", "NAME", "DOWNLOAD"})
            or any(len(values) != 1 for values in query.values())
        ):
            return None
        path_uuid = query["PATH"][0].lower()
        try:
            parsed_uuid = UUID(path_uuid)
        except (ValueError, AttributeError):
            return None
        if str(parsed_uuid) != path_uuid:
            return None
        filename = query["NAME"][0]
        if (
            not filename.lower().endswith(".pdf")
            or "/" in filename
            or "\\" in filename
            or (query.get("DOWNLOAD") and not query["DOWNLOAD"][0].lower().endswith(".pdf"))
        ):
            return None
        return candidate

    if source == "customs":
        return candidate if host == "web.customs.gov.tw" and decoded_path.lower().startswith("/download/") else None

    if source == "moj_enforcement_cms":
        path = decoded_path.lower()
        return candidate if host in ENFORCEMENT_CMS_HOSTS and path.startswith("/media/") and path.endswith(".pdf") else None

    if source == "moj_auction":
        return candidate if host in MOJ_AUCTION_DOCUMENT_HOSTS and decoded_path.lower().endswith(".pdf") else None

    return None


def official_document_urls(
    record: ParsedAuctionRecord,
    source: str,
    *,
    artifact_urls: Iterable[str] = (),
) -> list[str]:
    """Return de-duplicated, source-validated official document links."""
    candidates = [
        str(evidence.normalized_value)
        for evidence in record.evidence
        if evidence.field_name.strip().lower() == "official_attachment_url"
        and isinstance(evidence.normalized_value, str)
    ]
    if source == "judicial":
        candidates.append(str(record.official_url))
    candidates.extend(str(value) for value in artifact_urls)
    return list(dict.fromkeys(
        validated
        for candidate in candidates
        if (validated := validated_official_document_url(source, candidate)) is not None
    ))
