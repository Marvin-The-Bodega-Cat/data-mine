from __future__ import annotations

import html
import json
import os
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Callable, Protocol

from .miners import tokens
from .models import Block, Record, stable_id


@dataclass(frozen=True)
class SourceQuery:
    include_terms: list[str] = field(default_factory=list)
    exclude_terms: list[str] = field(default_factory=list)
    limit: int | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "SourceQuery":
        data = data or {}
        return cls(
            include_terms=list(data.get("include_terms", [])),
            exclude_terms=list(data.get("exclude_terms", [])),
            limit=data.get("limit"),
        )

    def matches(self, text: str) -> bool:
        tok = set(tokens(text))
        includes = {t.lower() for t in self.include_terms}
        excludes = {t.lower() for t in self.exclude_terms}
        if includes and not (includes & tok):
            return False
        if excludes and (excludes & tok):
            return False
        return True


@dataclass(frozen=True)
class SourceSpec:
    name: str
    adapter: str
    location: str = ""
    query: SourceQuery = field(default_factory=SourceQuery)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SourceSpec":
        return cls(
            name=data["name"],
            adapter=data["adapter"],
            location=data.get("location", ""),
            query=SourceQuery.from_dict(data.get("query")),
            metadata=dict(data.get("metadata", {})),
        )


class SourceAdapter(Protocol):
    def name(self) -> str: ...

    def query(self, spec: SourceSpec) -> list[Record]: ...


class TextFileSourceAdapter:
    def name(self) -> str:
        return "text-file"

    def query(self, spec: SourceSpec) -> list[Record]:
        path = Path(spec.location)
        lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
        return _records_from_lines(spec, [line for line in lines if line], source_file=str(path))


class DirectoryTextSourceAdapter:
    def name(self) -> str:
        return "directory-text"

    def query(self, spec: SourceSpec) -> list[Record]:
        root = Path(spec.location)
        pattern = spec.metadata.get("glob", "*.txt")
        lines: list[tuple[str, str]] = []
        for path in sorted(root.glob(pattern)):
            if not path.is_file():
                continue
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line:
                    lines.append((line, str(path)))
        return _records_from_lines(spec, [line for line, _ in lines], source_files=[src for _, src in lines])


class JsonlSourceAdapter:
    def name(self) -> str:
        return "jsonl"

    def query(self, spec: SourceSpec) -> list[Record]:
        path = Path(spec.location)
        text_field = spec.metadata.get("text_field", "text")
        rows: list[Record] = []
        count = 0
        with path.open("r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                text = str(obj.get(text_field, "")).strip()
                if not text or not spec.query.matches(text):
                    continue
                count += 1
                rows.append(
                    Record(
                        record_id=f"{spec.name}-r{count:04d}",
                        text=text,
                        metadata={
                            "source": spec.name,
                            "adapter": spec.adapter,
                            "location": str(path),
                            "line": line_no,
                            "raw": obj if spec.metadata.get("include_raw", False) else None,
                        },
                    )
                )
                if spec.query.limit and count >= spec.query.limit:
                    break
        return rows


class InlineSourceAdapter:
    def name(self) -> str:
        return "inline"

    def query(self, spec: SourceSpec) -> list[Record]:
        items = spec.metadata.get("items", [])
        if isinstance(items, str):
            items = [items]
        return _records_from_lines(spec, [str(item) for item in items if str(item).strip()])


class CommunityArchiveSourceAdapter:
    storage_base = "https://fabxmporizzqflnftavs.supabase.co/storage/v1/object/public/archives"

    def name(self) -> str:
        return "community-archive"

    def query(self, spec: SourceSpec) -> list[Record]:
        username = _normalize_username(spec.location or str(spec.metadata.get("username", "")))
        archive = _load_community_archive(spec, username)
        if not username:
            username = _username_from_archive(archive)
        records: list[Record] = []
        seen_tweet_ids: set[str] = set()
        for tweet, source_dataset in _iter_community_archive_rows(spec, archive):
            text = str(tweet.get("full_text") or tweet.get("text") or "").strip()
            if not text or not spec.query.matches(text):
                continue
            tweet_id = _tweet_id(tweet)
            if tweet_id and tweet_id in seen_tweet_ids:
                continue
            if tweet_id:
                seen_tweet_ids.add(tweet_id)
            record_id = f"{spec.name}-t{tweet_id}" if tweet_id else f"{spec.name}-r{len(records)+1:04d}"
            records.append(
                Record(
                    record_id=record_id,
                    text=text,
                    metadata={
                        "source": spec.name,
                        "adapter": spec.adapter,
                        "location": spec.location,
                        "source_dataset": str(tweet.get("source_dataset") or source_dataset),
                        "username": username,
                        "tweet_id": tweet_id or None,
                        "url": f"https://x.com/{username}/status/{tweet_id}" if username and tweet_id else None,
                        "created_at": _parse_twitter_date(tweet.get("created_at")),
                        "lang": tweet.get("lang"),
                        "favorite_count": _safe_int(tweet.get("favorite_count")),
                        "retweet_count": _safe_int(tweet.get("retweet_count")),
                        "source_label": _source_label(tweet.get("source")),
                        "hashtags": _hashtags(tweet),
                        "mentions": _mentions(tweet),
                    },
                )
            )
            if spec.query.limit and len(records) >= spec.query.limit:
                break
        return records


class SourceRegistry:
    def __init__(self) -> None:
        adapters: list[SourceAdapter] = [
            TextFileSourceAdapter(),
            DirectoryTextSourceAdapter(),
            JsonlSourceAdapter(),
            InlineSourceAdapter(),
            CommunityArchiveSourceAdapter(),
        ]
        self._adapters = {adapter.name(): adapter for adapter in adapters}

    def names(self) -> list[str]:
        return sorted(self._adapters)

    def get(self, name: str) -> SourceAdapter:
        if name not in self._adapters:
            raise KeyError(f"unknown source adapter: {name}")
        return self._adapters[name]

    def query(self, spec: SourceSpec) -> list[Record]:
        return self.get(spec.adapter).query(spec)


CommunityArchiveApiGet = Callable[[str, dict[str, str], str], list[dict[str, Any]]]
COMMUNITY_ARCHIVE_API_BASE = "https://fabxmporizzqflnftavs.supabase.co/rest/v1"


def capture_community_archive_incremental(
    username: str,
    output_path: str | Path,
    since_tweet_id: str | None = None,
    api_key: str | None = None,
    page_size: int = 1000,
    api_get: CommunityArchiveApiGet | None = None,
    fetched_at: str | None = None,
) -> dict[str, Any]:
    username = _normalize_username(username)
    api_key = api_key or os.environ.get("COMMUNITY_ARCHIVE_ANON_KEY") or os.environ.get("CA_SUPABASE_ANON_KEY")
    if not api_key:
        raise ValueError("Community Archive API capture requires api_key or COMMUNITY_ARCHIVE_ANON_KEY")
    api_get = api_get or _community_archive_api_get
    account_rows = api_get("account", {"username": f"eq.{username}", "select": "account_id,username", "limit": "1"}, api_key)
    if not account_rows:
        raise ValueError(f"Community Archive account not found: {username}")
    account = account_rows[0]
    account_id = str(account.get("account_id") or account.get("id") or "")
    if not account_id:
        raise ValueError(f"Community Archive account has no account_id: {username}")
    fetched_at = fetched_at or datetime.now(UTC).isoformat()
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        params = {
            "account_id": f"eq.{account_id}",
            "select": "*",
            "order": "tweet_id.asc",
            "limit": str(page_size),
            "offset": str(offset),
        }
        if since_tweet_id:
            params["tweet_id"] = f"gt.{since_tweet_id}"
        batch = api_get("tweets", params, api_key)
        for row in batch:
            rows.append(_normalize_api_incremental_row(row, username, account_id, fetched_at))
        if len(batch) < page_size:
            break
        offset += page_size
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True) + "\n")
    return {"username": username, "account_id": account_id, "rows": len(rows), "output": str(out)}


def _community_archive_api_get(path: str, params: dict[str, str], api_key: str) -> list[dict[str, Any]]:
    url = f"{COMMUNITY_ARCHIVE_API_BASE}/{path}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(
        url,
        headers={
            "apikey": api_key,
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        data = json.loads(response.read().decode("utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"Community Archive API returned non-list for {path}")
    return [row for row in data if isinstance(row, dict)]


def _normalize_api_incremental_row(row: dict[str, Any], username: str, account_id: str, fetched_at: str) -> dict[str, Any]:
    tweet = row.get("tweet", row)
    tweet_id = _tweet_id(tweet)
    return {
        "tweet_id": tweet_id,
        "id_str": tweet_id,
        "text": str(tweet.get("full_text") or tweet.get("text") or tweet.get("content") or ""),
        "full_text": str(tweet.get("full_text") or tweet.get("text") or tweet.get("content") or ""),
        "created_at": tweet.get("created_at"),
        "favorite_count": _safe_int(tweet.get("favorite_count") or tweet.get("like_count")),
        "retweet_count": _safe_int(tweet.get("retweet_count") or tweet.get("repost_count")),
        "lang": tweet.get("lang"),
        "entities": tweet.get("entities") or {},
        "source": tweet.get("source"),
        "username": username,
        "account_id": account_id,
        "source_dataset": "api_incremental",
        "api_fetched_at": fetched_at,
    }


def _load_community_archive(spec: SourceSpec, username: str) -> dict[str, Any]:
    archive_path = spec.metadata.get("archive_path")
    if archive_path:
        return json.loads(Path(str(archive_path)).read_text(encoding="utf-8"))
    archive_url = spec.metadata.get("archive_url")
    if not archive_url:
        if not username:
            raise ValueError("community-archive source requires location, metadata.username, archive_path, or archive_url")
        archive_url = f"{CommunityArchiveSourceAdapter.storage_base}/{username}/archive.json"
    with urllib.request.urlopen(str(archive_url), timeout=int(spec.metadata.get("timeout_seconds", 120))) as response:
        return json.loads(response.read().decode("utf-8"))


def _iter_community_archive_rows(spec: SourceSpec, archive: dict[str, Any]) -> list[tuple[dict[str, Any], str]]:
    rows: list[tuple[dict[str, Any], str]] = []
    for row in archive.get("tweets", []):
        rows.append((row.get("tweet", row), "community_archive_raw"))
    for path in _incremental_paths(spec):
        for row in _load_incremental_rows(path):
            rows.append((row.get("tweet", row), str(row.get("source_dataset") or "community_archive_incremental")))
    return rows


def _incremental_paths(spec: SourceSpec) -> list[Path]:
    paths: list[str] = []
    if spec.metadata.get("incremental_path"):
        paths.append(str(spec.metadata["incremental_path"]))
    paths.extend(str(path) for path in spec.metadata.get("incremental_paths", []))
    return [Path(path) for path in paths]


def _load_incremental_rows(path: Path) -> list[dict[str, Any]]:
    if path.suffix == ".jsonl":
        rows = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                rows.append(json.loads(line))
        return rows
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        values = data.get("tweets") or data.get("records") or data.get("rows") or []
        return [row for row in values if isinstance(row, dict)]
    return []


def _tweet_id(tweet: dict[str, Any]) -> str:
    return str(tweet.get("id_str") or tweet.get("tweet_id") or tweet.get("id") or "").strip()


def _normalize_username(value: str) -> str:
    return value.strip().lower().lstrip("@")


def _username_from_archive(archive: dict[str, Any]) -> str:
    for row in archive.get("account", []):
        account = row.get("account", row)
        username = account.get("username") or account.get("screen_name")
        if username:
            return _normalize_username(str(username))
    return ""


def _parse_twitter_date(value: Any) -> str | None:
    if not value:
        return None
    try:
        return parsedate_to_datetime(str(value)).isoformat()
    except (TypeError, ValueError):
        return str(value)


def _source_label(source_html: Any) -> str:
    text = re.sub(r"<[^>]+>", "", str(source_html or ""))
    return html.unescape(text).strip()


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _hashtags(tweet: dict[str, Any]) -> list[str]:
    return [str(item.get("text", "")) for item in tweet.get("entities", {}).get("hashtags", []) if item.get("text")]


def _mentions(tweet: dict[str, Any]) -> list[str]:
    return [str(item.get("screen_name", "")) for item in tweet.get("entities", {}).get("user_mentions", []) if item.get("screen_name")]


def _records_from_lines(
    spec: SourceSpec,
    lines: list[str],
    source_file: str | None = None,
    source_files: list[str] | None = None,
) -> list[Record]:
    records: list[Record] = []
    for i, line in enumerate(lines, start=1):
        if not spec.query.matches(line):
            continue
        records.append(
            Record(
                record_id=f"{spec.name}-r{len(records)+1:04d}",
                text=line,
                metadata={
                    "source": spec.name,
                    "adapter": spec.adapter,
                    "location": spec.location,
                    "source_file": source_file or (source_files[i - 1] if source_files else spec.location),
                    "ordinal": i,
                },
            )
        )
        if spec.query.limit and len(records) >= spec.query.limit:
            break
    return records


def load_source_specs(path: str | Path) -> list[SourceSpec]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [SourceSpec.from_dict(item) for item in data.get("sources", [])]


def build_block_from_sources(
    block_id: str,
    title: str,
    source_config_path: str | Path,
    description: str = "",
    dimensions: list[str] | None = None,
) -> Block:
    specs = load_source_specs(source_config_path)
    registry = SourceRegistry()
    records: list[Record] = []
    for source_index, spec in enumerate(specs, start=1):
        source_records = registry.query(spec)
        for record in source_records:
            new_id = f"s{source_index:02d}-{record.record_id}"
            metadata = dict(record.metadata)
            metadata["source_order"] = source_index
            records.append(Record(record_id=new_id, text=record.text, metadata=metadata))
    return Block(
        block_id=block_id,
        title=title,
        source=f"source-config:{Path(source_config_path).name}",
        records=records,
        dimensions=dimensions or [],
        description=description,
    )


def source_config_fingerprint(path: str | Path) -> str:
    return stable_id(Path(path).read_text(encoding="utf-8"), length=12)
