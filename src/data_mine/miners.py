from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Callable

from .models import Artifact, ArtifactScore, Block, Evidence, stable_id, utc_now

TOKEN_RE = re.compile(r"[a-zA-Z0-9_'-]+")
REQUEST_TERMS = {"need", "needs", "want", "wants", "asking", "asked", "request", "should", "could", "would"}
BUILD_TERMS = {"build", "create", "make", "tool", "repo", "function", "pipeline", "system", "search", "mine"}
TENSION_TERMS = {"but", "however", "although", "risk", "scammy", "fails", "might", "accidentally", "unclear"}


def tokens(text: str) -> list[str]:
    return [m.group(0).lower() for m in TOKEN_RE.finditer(text)]


def snippet(text: str, limit: int = 180) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


class MinerRegistry:
    def __init__(self) -> None:
        self._miners: dict[str, Callable[..., list[Artifact]]] = {
            "keyword": keyword_miner,
            "repeated-requests": repeated_requests_miner,
            "contradictions": contradictions_miner,
            "build-seeds": build_seed_miner,
        }

    def names(self) -> list[str]:
        return sorted(self._miners)

    def run(self, name: str, block: Block, **kwargs: object) -> list[Artifact]:
        if name not in self._miners:
            raise KeyError(f"unknown miner: {name}")
        return self._miners[name](block, **kwargs)


def keyword_miner(block: Block, query: str = "") -> list[Artifact]:
    wanted = set(tokens(query))
    if not wanted:
        return []
    evidence=[]
    for record in block.records:
        hit = wanted & set(tokens(record.text))
        if hit:
            evidence.append(Evidence(record.record_id, snippet(record.text), f"matched:{','.join(sorted(hit))}"))
    if not evidence:
        return []
    artifact_id=stable_id(block.block_id, "keyword", query)
    return [Artifact(
        artifact_id=artifact_id,
        block_id=block.block_id,
        kind="keyword_cluster",
        title=f"Keyword cluster: {query}",
        summary=f"{len(evidence)} records matched query terms: {query}",
        evidence=evidence,
        score=ArtifactScore(value=float(len(evidence)), reasons=[f"matched_records={len(evidence)}"]),
        miner="keyword",
    )]


def repeated_requests_miner(block: Block, **_: object) -> list[Artifact]:
    candidates=[]
    phrase_counts: Counter[str] = Counter()
    phrase_records: defaultdict[str, list[Evidence]] = defaultdict(list)
    for record in block.records:
        toks=tokens(record.text)
        if not (REQUEST_TERMS & set(toks)):
            continue
        important=[t for t in toks if t not in REQUEST_TERMS and len(t) > 3]
        for t in important:
            phrase_counts[t]+=1
            phrase_records[t].append(Evidence(record.record_id, snippet(record.text), f"request_term:{t}"))
    for term,count in phrase_counts.items():
        if count >= 2:
            ev=phrase_records[term][:5]
            candidates.append(Artifact(
                artifact_id=stable_id(block.block_id, "repeated", term),
                block_id=block.block_id,
                kind="repeated_request",
                title=f"Repeated request: {term}",
                summary=f"The term '{term}' appeared in {count} request-like records.",
                evidence=ev,
                score=ArtifactScore(value=float(count * 10), reasons=[f"request_like_records={count}", "threshold>=2"]),
                miner="repeated-requests",
                metadata={"term": term, "count": count},
            ))
    return sorted(candidates, key=lambda a: (-a.score.value, a.title))


def contradictions_miner(block: Block, **_: object) -> list[Artifact]:
    evidence=[]
    for record in block.records:
        toks=set(tokens(record.text))
        hit=TENSION_TERMS & toks
        if hit:
            evidence.append(Evidence(record.record_id, snippet(record.text), f"tension:{','.join(sorted(hit))}"))
    if not evidence:
        return []
    return [Artifact(
        artifact_id=stable_id(block.block_id, "contradictions", len(evidence)),
        block_id=block.block_id,
        kind="contradiction_cluster",
        title="Tension / contradiction cluster",
        summary=f"Found {len(evidence)} records with tension markers worth resolving before build.",
        evidence=evidence,
        score=ArtifactScore(value=float(len(evidence) * 8), reasons=[f"tension_records={len(evidence)}"]),
        miner="contradictions",
    )]


def build_seed_miner(block: Block, **_: object) -> list[Artifact]:
    evidence=[]
    for record in block.records:
        toks=set(tokens(record.text))
        hit=BUILD_TERMS & toks
        if len(hit) >= 2:
            evidence.append(Evidence(record.record_id, snippet(record.text), f"build_terms:{','.join(sorted(hit))}"))
    if not evidence:
        return []
    return [Artifact(
        artifact_id=stable_id(block.block_id, "build-seeds", len(evidence)),
        block_id=block.block_id,
        kind="build_seed_candidate",
        title="Build seed candidate cluster",
        summary=f"Found {len(evidence)} records with build/tool/search language.",
        evidence=evidence,
        score=ArtifactScore(value=float(len(evidence) * 12), reasons=[f"build_language_records={len(evidence)}"]),
        miner="build-seeds",
        created_at=utc_now(),
    )]
