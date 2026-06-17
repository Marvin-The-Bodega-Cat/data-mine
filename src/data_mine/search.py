from __future__ import annotations

from .miners import tokens
from .models import Artifact, Block


def search_blocks(blocks: list[Block], query: str) -> list[dict]:
    wanted=set(tokens(query))
    hits=[]
    for block in blocks:
        for record in block.records:
            overlap=wanted & set(tokens(record.text))
            if overlap:
                hits.append({
                    "type":"record",
                    "block_id":block.block_id,
                    "record_id":record.record_id,
                    "score":len(overlap),
                    "matched":sorted(overlap),
                    "text":record.text,
                })
    return sorted(hits, key=lambda h: -h["score"])


def search_artifacts(artifacts: list[Artifact], query: str) -> list[dict]:
    wanted=set(tokens(query))
    hits=[]
    for artifact in artifacts:
        haystack=" ".join([artifact.title, artifact.summary, artifact.kind, artifact.miner])
        overlap=wanted & set(tokens(haystack))
        if overlap:
            hits.append({
                "type":"artifact",
                "artifact_id":artifact.artifact_id,
                "block_id":artifact.block_id,
                "score":len(overlap)+artifact.score.value/100,
                "matched":sorted(overlap),
                "title":artifact.title,
                "summary":artifact.summary,
            })
    return sorted(hits, key=lambda h: -h["score"])
