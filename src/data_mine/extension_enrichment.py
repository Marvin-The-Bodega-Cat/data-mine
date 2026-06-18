from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

QUEUE_NAMES = ("needs_ocr", "needs_quote_fetch", "needs_expanded_text", "missing_tweet_id")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row, dict):
            raise ValueError(f"line {line_number} is not a JSON object")
        row["_input_line"] = line_number
        rows.append(row)
    return rows


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    materialized = list(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in materialized), encoding="utf-8")
    return len(materialized)


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _canonical_id(row: dict[str, Any]) -> str:
    tweet_id = row.get("tweet_id")
    if tweet_id:
        return f"tweet:{tweet_id}"
    basis = "\n".join(str(row.get(key) or "") for key in ("url", "author", "text"))
    return f"text-sha256:{_sha256_text(basis)}"


def _list_unique(values: Iterable[Any]) -> list[Any]:
    seen: set[str] = set()
    out: list[Any] = []
    for value in values:
        if value in (None, ""):
            continue
        key = json.dumps(value, sort_keys=True) if isinstance(value, (dict, list)) else str(value)
        if key in seen:
            continue
        seen.add(key)
        out.append(value)
    return out


def _merge_dom_features(rows: list[dict[str, Any]]) -> dict[str, Any]:
    merged: dict[str, Any] = {
        "status_urls": [],
        "quoted_status_urls": [],
        "image_urls": [],
        "link_urls": [],
        "video_count": 0,
        "image_count": 0,
        "has_media": False,
        "has_quote_card": False,
        "visible_has_show_more": False,
        "visible_has_replying_to": False,
    }
    for row in rows:
        dom = row.get("dom_features") or {}
        if not isinstance(dom, dict):
            continue
        for key in ("status_urls", "quoted_status_urls", "image_urls", "link_urls"):
            merged[key].extend(dom.get(key) or [])
        for key in ("has_media", "has_quote_card", "visible_has_show_more", "visible_has_replying_to"):
            merged[key] = bool(merged[key] or dom.get(key))
        merged["video_count"] = max(int(merged["video_count"]), int(dom.get("video_count") or 0))
    for key in ("status_urls", "quoted_status_urls", "image_urls", "link_urls"):
        merged[key] = _list_unique(merged[key])
    merged["image_count"] = len(merged["image_urls"])
    merged["has_media"] = bool(merged["has_media"] or merged["image_urls"] or merged["video_count"])
    return merged


def _pick_best_row(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return max(rows, key=lambda row: (len(str(row.get("text") or "")), int(row.get("_input_line") or 0)))


def _normalize_group(canonical_id: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    best = _pick_best_row(rows)
    dom_features = _merge_dom_features(rows)
    tweet_ids = _list_unique(row.get("tweet_id") for row in rows)
    urls = _list_unique(row.get("url") for row in rows)
    authors = _list_unique(row.get("author") for row in rows)
    schemas = _list_unique(row.get("schema_version") for row in rows)
    return {
        "record_type": "extension_capture_normalized",
        "canonical_id": canonical_id,
        "tweet_id": best.get("tweet_id"),
        "url": best.get("url"),
        "author": best.get("author"),
        "text": best.get("text") or "",
        "participant_roles": _list_unique(row.get("participant_role") for row in rows),
        "suggested_lanes": _list_unique(row.get("suggested_lane") for row in rows),
        "admissions": _list_unique(row.get("admission") for row in rows),
        "schema_versions": schemas,
        "dom_features": dom_features,
        "capture_count": len(rows),
        "input_lines": [row.get("_input_line") for row in rows],
        "all_tweet_ids": tweet_ids,
        "all_urls": urls,
        "all_authors": authors,
    }


def _evidence_subrecords(record: dict[str, Any]) -> list[dict[str, Any]]:
    dom = record.get("dom_features") or {}
    base = {
        "parent_canonical_id": record["canonical_id"],
        "parent_tweet_id": record.get("tweet_id"),
        "parent_url": record.get("url"),
        "author": record.get("author"),
    }
    subrecords: list[dict[str, Any]] = []
    text = record.get("text") or ""
    if text:
        subrecords.append({**base, "evidence_type": "visible_text", "text": text})
    for url in dom.get("quoted_status_urls") or []:
        subrecords.append({**base, "evidence_type": "quoted_status_url", "quoted_status_url": url})
    for url in dom.get("image_urls") or []:
        subrecords.append({**base, "evidence_type": "image_url", "image_url": url})
    if dom.get("video_count"):
        subrecords.append({**base, "evidence_type": "video_presence", "video_count": dom.get("video_count")})
    if dom.get("visible_has_show_more"):
        subrecords.append({**base, "evidence_type": "show_more_truncation", "reason": "visible Show more marker indicates truncated text"})
    return subrecords


def _queues_for(record: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    dom = record.get("dom_features") or {}
    base = {
        "parent_canonical_id": record["canonical_id"],
        "parent_tweet_id": record.get("tweet_id"),
        "parent_url": record.get("url"),
        "author": record.get("author"),
    }
    queues = {name: [] for name in QUEUE_NAMES}
    for image_url in dom.get("image_urls") or []:
        queues["needs_ocr"].append({**base, "image_url": image_url, "reason": "image URL captured; OCR text not yet extracted"})
    for quoted_status_url in dom.get("quoted_status_urls") or []:
        queues["needs_quote_fetch"].append({**base, "quoted_status_url": quoted_status_url, "reason": "quote/status URL captured; quoted tweet not yet fetched as its own record"})
    if dom.get("visible_has_show_more"):
        queues["needs_expanded_text"].append({**base, "reason": "visible Show more marker indicates truncated text"})
    if not record.get("tweet_id"):
        queues["missing_tweet_id"].append({**base, "text_sha256": _sha256_text(record.get("text") or ""), "reason": "capture lacked tweet_id"})
    return queues


def enrich_extension_capture_file(input_path: str | Path, output_dir: str | Path, run_id: str | None = None) -> dict[str, Any]:
    input_path = Path(input_path)
    output_dir = Path(output_dir)
    rows = _read_jsonl(input_path)
    run_id = run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault(_canonical_id(row), []).append(row)
    normalized = [_normalize_group(canonical_id, grouped) for canonical_id, grouped in groups.items()]

    evidence: list[dict[str, Any]] = []
    queues: dict[str, list[dict[str, Any]]] = {name: [] for name in QUEUE_NAMES}
    for record in normalized:
        evidence.extend(_evidence_subrecords(record))
        record_queues = _queues_for(record)
        for name, items in record_queues.items():
            queues[name].extend(items)

    output_dir.mkdir(parents=True, exist_ok=True)
    queue_dir = output_dir / "queues"
    outputs = {
        "normalized": str(output_dir / "normalized.jsonl"),
        "evidence_subrecords": str(output_dir / "evidence_subrecords.jsonl"),
        "needs_ocr": str(queue_dir / "needs_ocr.jsonl"),
        "needs_quote_fetch": str(queue_dir / "needs_quote_fetch.jsonl"),
        "needs_expanded_text": str(queue_dir / "needs_expanded_text.jsonl"),
        "missing_tweet_id": str(queue_dir / "missing_tweet_id.jsonl"),
        "receipt": str(output_dir / "enrichment_receipt.json"),
    }
    _write_jsonl(Path(outputs["normalized"]), normalized)
    _write_jsonl(Path(outputs["evidence_subrecords"]), evidence)
    for name in QUEUE_NAMES:
        _write_jsonl(Path(outputs[name]), queues[name])

    tweet_ids = {row.get("tweet_id") for row in rows if row.get("tweet_id")}
    duplicate_rows = len(rows) - len(groups)
    receipt = {
        "run_id": run_id,
        "input": str(input_path),
        "input_sha256": hashlib.sha256(input_path.read_bytes()).hexdigest(),
        "input_rows": len(rows),
        "unique_tweets": len(tweet_ids),
        "missing_tweet_id_rows": sum(1 for row in rows if not row.get("tweet_id")),
        "duplicate_rows": duplicate_rows,
        "normalized_records": len(normalized),
        "evidence_subrecords": len(evidence),
        "queues": {name: len(items) for name, items in queues.items()},
        "outputs": outputs,
        "notes": [
            "visible_text subrecords preserve the browser-visible receipt text",
            "image_url rows require a later OCR/media fetch pass",
            "quoted_status_url rows require a later quoted-status expansion pass",
            "show_more_truncation rows indicate likely incomplete visible text",
        ],
    }
    Path(outputs["receipt"]).write_text(json.dumps(receipt, indent=2, sort_keys=True), encoding="utf-8")
    return receipt
