import json
from pathlib import Path

from data_mine.cli import main
from data_mine.models import Block, Record
from data_mine.miners import MinerRegistry


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
