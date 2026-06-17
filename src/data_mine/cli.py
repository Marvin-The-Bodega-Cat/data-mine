from __future__ import annotations

import argparse
import json
from pathlib import Path

from .models import Block, Record
from .miners import MinerRegistry
from .repo_builder import build_seed_from_artifact, render_repo
from .search import search_artifacts, search_blocks
from .sources import SourceRegistry, build_block_from_sources, load_source_specs, source_config_fingerprint
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


def cmd_block_from_sources(args: argparse.Namespace) -> None:
    s=store(args)
    block=build_block_from_sources(
        block_id=args.block_id,
        title=args.title,
        source_config_path=args.config,
        description=args.description or "",
        dimensions=args.dimension,
    )
    path=s.save_block(block)
    source_count=len(load_source_specs(args.config))
    print(json.dumps({
        "block_id": block.block_id,
        "records": len(block.records),
        "sources": source_count,
        "source_config_fingerprint": source_config_fingerprint(args.config),
        "path": str(path),
    }, indent=2, sort_keys=True))


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
    seed=build_seed_from_artifact(artifact)
    out=Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(seed.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    print(str(out))


def cmd_build_repo(args: argparse.Namespace) -> None:
    s=store(args)
    artifact=s.load_artifact(args.artifact_id)
    seed=build_seed_from_artifact(artifact)
    out=render_repo(seed, artifact, args.output_dir, force=args.force)
    print(json.dumps({"repo": str(out), "seed_id": seed.seed_id, "artifact_id": artifact.artifact_id}, indent=2, sort_keys=True))


def cmd_list_miners(args: argparse.Namespace) -> None:
    print(json.dumps(MinerRegistry().names(), indent=2))


def cmd_list_sources(args: argparse.Namespace) -> None:
    print(json.dumps(SourceRegistry().names(), indent=2))


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

    from_sources=bsub.add_parser("from-sources")
    from_sources.add_argument("--block-id", required=True)
    from_sources.add_argument("--title", required=True)
    from_sources.add_argument("--config", required=True)
    from_sources.add_argument("--dimension", action="append", default=[])
    from_sources.add_argument("--description")
    from_sources.set_defaults(func=cmd_block_from_sources)

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

    repo=sub.add_parser("build-repo")
    repo.add_argument("--artifact-id", required=True)
    repo.add_argument("--output-dir", required=True)
    repo.add_argument("--force", action="store_true")
    repo.set_defaults(func=cmd_build_repo)

    miners=sub.add_parser("miners")
    miners.set_defaults(func=cmd_list_miners)

    sources=sub.add_parser("sources")
    sources.set_defaults(func=cmd_list_sources)
    return parser


def main(argv: list[str] | None = None) -> None:
    args=build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
