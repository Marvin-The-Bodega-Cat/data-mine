from __future__ import annotations

import argparse
import json
from pathlib import Path

from .models import Block, BuildSeed, Record, stable_id
from .miners import MinerRegistry
from .search import search_artifacts, search_blocks
from .store import MineStore


def store(args: argparse.Namespace) -> MineStore:
    return MineStore(args.store)


def cmd_init(args: argparse.Namespace) -> None:
    s=store(args)
    s.init()
    print(json.dumps({"store": str(s.root), "status": "initialized"}, indent=2))


def records_from_text(path: str) -> list[Record]:
    text=Path(path).read_text(encoding="utf-8")
    rows=[]
    for i,line in enumerate([ln.strip() for ln in text.splitlines() if ln.strip()], start=1):
        rows.append(Record(record_id=f"r{i:04d}", text=line, metadata={"line": i, "source_file": path}))
    return rows


def cmd_block_create(args: argparse.Namespace) -> None:
    s=store(args)
    records=records_from_text(args.text)
    block=Block(
        block_id=args.block_id,
        title=args.title,
        source=args.source,
        records=records,
        dimensions=args.dimension,
        description=args.description or "",
    )
    path=s.save_block(block)
    print(json.dumps({"block_id": block.block_id, "records": len(records), "path": str(path)}, indent=2))


def cmd_mine(args: argparse.Namespace) -> None:
    s=store(args)
    block=s.load_block(args.block_id)
    kwargs={}
    if args.query:
        kwargs["query"]=args.query
    artifacts=MinerRegistry().run(args.miner, block, **kwargs)
    for artifact in artifacts:
        s.save_artifact(artifact)
    print(json.dumps([a.to_dict() for a in artifacts], indent=2, sort_keys=True))


def cmd_search(args: argparse.Namespace) -> None:
    s=store(args)
    hits=search_artifacts(s.list_artifacts(), args.query)+search_blocks(s.list_blocks(), args.query)
    hits=sorted(hits, key=lambda h: -h["score"])
    print(json.dumps(hits[:args.limit], indent=2, sort_keys=True))


def cmd_start_build(args: argparse.Namespace) -> None:
    s=store(args)
    artifact=s.load_artifact(args.artifact_id)
    seed=BuildSeed(
        seed_id=stable_id("seed", artifact.artifact_id),
        block_id=artifact.block_id,
        artifact_id=artifact.artifact_id,
        thesis=f"Build from artifact: {artifact.title}",
        evidence=artifact.evidence,
        recommended_first_files=["README.md", "docs/architecture.md", "schemas/artifact.schema.json", "src/", "tests/"],
        falsification_check="If this artifact cannot produce a working CLI/API smoke test from its evidence, demote it back to research.",
    )
    out=Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(seed.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    print(str(out))


def cmd_list_miners(args: argparse.Namespace) -> None:
    print(json.dumps(MinerRegistry().names(), indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser=argparse.ArgumentParser(prog="datamine")
    parser.add_argument("--store", default=".mine")
    sub=parser.add_subparsers(required=True)

    p=sub.add_parser("init")
    p.set_defaults(func=cmd_init)

    block=sub.add_parser("block")
    bsub=block.add_subparsers(required=True)
    create=bsub.add_parser("create")
    create.add_argument("--block-id", required=True)
    create.add_argument("--title", required=True)
    create.add_argument("--source", required=True)
    create.add_argument("--text", required=True)
    create.add_argument("--dimension", action="append", default=[])
    create.add_argument("--description")
    create.set_defaults(func=cmd_block_create)

    mine=sub.add_parser("mine")
    mine.add_argument("--block-id", required=True)
    mine.add_argument("--miner", required=True)
    mine.add_argument("--query")
    mine.set_defaults(func=cmd_mine)

    search=sub.add_parser("search")
    search.add_argument("--query", required=True)
    search.add_argument("--limit", type=int, default=10)
    search.set_defaults(func=cmd_search)

    seed=sub.add_parser("start-build")
    seed.add_argument("--artifact-id", required=True)
    seed.add_argument("--output", required=True)
    seed.set_defaults(func=cmd_start_build)

    miners=sub.add_parser("miners")
    miners.set_defaults(func=cmd_list_miners)
    return parser


def main(argv: list[str] | None = None) -> None:
    args=build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
