from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def stable_id(*parts: object, length: int = 16) -> str:
    raw = "|".join(str(p) for p in parts)
    return sha256(raw.encode("utf-8")).hexdigest()[:length]


@dataclass(frozen=True)
class Record:
    record_id: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Block:
    block_id: str
    title: str
    source: str
    records: list[Record]
    dimensions: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now)
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["records"] = [r.to_dict() for r in self.records]
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Block":
        rows = [r if isinstance(r, Record) else Record(**r) for r in data.get("records", [])]
        return cls(
            block_id=data["block_id"],
            title=data["title"],
            source=data["source"],
            records=rows,
            dimensions=data.get("dimensions", []),
            created_at=data.get("created_at", utc_now()),
            description=data.get("description", ""),
        )


@dataclass(frozen=True)
class Evidence:
    record_id: str
    snippet: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ArtifactScore:
    value: float
    reasons: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Artifact:
    artifact_id: str
    block_id: str
    kind: str
    title: str
    summary: str
    evidence: list[Evidence]
    score: ArtifactScore
    miner: str
    created_at: str = field(default_factory=utc_now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["evidence"] = [e.to_dict() for e in self.evidence]
        data["score"] = self.score.to_dict()
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Artifact":
        return cls(
            artifact_id=data["artifact_id"],
            block_id=data["block_id"],
            kind=data["kind"],
            title=data["title"],
            summary=data["summary"],
            evidence=[Evidence(**e) for e in data.get("evidence", [])],
            score=ArtifactScore(**data["score"]),
            miner=data["miner"],
            created_at=data.get("created_at", utc_now()),
            metadata=data.get("metadata", {}),
        )


@dataclass(frozen=True)
class BuildSeed:
    seed_id: str
    block_id: str
    artifact_id: str
    thesis: str
    evidence: list[Evidence]
    recommended_first_files: list[str]
    falsification_check: str
    created_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["evidence"] = [e.to_dict() for e in self.evidence]
        return data
