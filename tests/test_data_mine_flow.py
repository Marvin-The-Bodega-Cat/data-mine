import json
from pathlib import Path

from data_mine.cli import main
from data_mine.models import Block, Record
from data_mine.miners import MinerRegistry
from data_mine.sources import SourceRegistry, build_block_from_sources


def test_source_pipeline_builds_ordered_block(tmp_path: Path):
    text = tmp_path / "notes.txt"
    text.write_text("Need wallet search.\nIgnore boring line.\nBuild artifact index.\n", encoding="utf-8")
    jsonl = tmp_path / "events.jsonl"
    jsonl.write_text('{"text":"Blocks need source order."}\n{"text":"Private record should skip."}\n', encoding="utf-8")
    config = tmp_path / "sources.json"
    config.write_text(json.dumps({
        "sources": [
            {"name": "notes", "adapter": "text-file", "location": str(text), "query": {"include_terms": ["wallet", "artifact"]}},
            {"name": "events", "adapter": "jsonl", "location": str(jsonl), "query": {"include_terms": ["blocks"], "exclude_terms": ["private"]}},
            {"name": "inline", "adapter": "inline", "metadata": {"items": ["Inline source can seed a block."]}},
        ]
    }), encoding="utf-8")
    block = build_block_from_sources("b-sources", "Source block", config)
    assert [r.record_id.split("-")[0] for r in block.records] == ["s01", "s01", "s02", "s03"]
    assert len(block.records) == 4
    assert SourceRegistry().names() == ["directory-text", "inline", "jsonl", "text-file"]


def test_repeated_requests_miner_finds_artifacts():
    block=Block(
        block_id="b1",
        title="T",
        source="test",
        records=[
            Record("r1", "We need a searchable wallet map."),
            Record("r2", "People keep asking for wallet search."),
        ],
    )
    artifacts=MinerRegistry().run("repeated-requests", block)
    assert artifacts
    assert any(a.kind == "repeated_request" for a in artifacts)


def test_cli_block_mine_search_seed(tmp_path: Path, capsys):
    text=tmp_path/"input.txt"
    text.write_text(
        "We need a data mine.\n"
        "People keep asking for a search tool.\n"
        "Build a search tool for artifacts.\n",
        encoding="utf-8",
    )
    store=tmp_path/"mine"
    main(["--store", str(store), "init"])
    main(["--store", str(store), "block", "create", "--block-id", "b1", "--title", "Block 1", "--source", "synthetic", "--text", str(text)])
    main(["--store", str(store), "mine", "--block-id", "b1", "--miner", "build-seeds"])
    artifacts=list((store/"artifacts").glob("*.json"))
    assert artifacts
    artifact_id=json.loads(artifacts[0].read_text())["artifact_id"]
    out=tmp_path/"seed.json"
    main(["--store", str(store), "start-build", "--artifact-id", artifact_id, "--output", str(out)])
    assert out.exists()
    seed=json.loads(out.read_text())
    assert seed["block_id"] == "b1"
    _=capsys.readouterr()


def test_cli_build_repo_produces_runnable_repo(tmp_path: Path, capsys):
    text=tmp_path/"input.txt"
    text.write_text(
        "People keep asking for a search tool.\n"
        "Build a search tool for artifacts.\n",
        encoding="utf-8",
    )
    store=tmp_path/"mine"
    main(["--store", str(store), "init"])
    main(["--store", str(store), "block", "create", "--block-id", "b2", "--title", "Block 2", "--source", "synthetic", "--text", str(text)])
    main(["--store", str(store), "mine", "--block-id", "b2", "--miner", "build-seeds"])
    artifact_id=json.loads(next((store/"artifacts").glob("*.json")).read_text())["artifact_id"]
    repo=tmp_path/"generated-repo"
    main(["--store", str(store), "build-repo", "--artifact-id", artifact_id, "--output-dir", str(repo)])
    assert (repo/"pyproject.toml").exists()
    assert (repo/"data"/"build_seed.json").exists()
    import subprocess, sys
    result=subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=repo, text=True, capture_output=True, check=True)
    assert "2 passed" in result.stdout
    _=capsys.readouterr()
