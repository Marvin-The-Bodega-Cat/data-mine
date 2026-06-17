import json
from pathlib import Path

from data_mine.cli import main
from data_mine.models import Block, Record
from data_mine.miners import MinerRegistry
from data_mine.sources import SourceRegistry, SourceSpec, build_block_from_sources
import data_mine.sources as source_mod


def test_community_archive_source_reads_tweets_from_archive_fixture(tmp_path: Path):
    archive = tmp_path / "archive.json"
    archive.write_text(json.dumps({
        "account": [{"account": {"username": "BodegaCat"}}],
        "tweets": [
            {"tweet": {
                "id_str": "111",
                "created_at": "Tue Nov 19 18:15:48 +0000 2024",
                "full_text": "Launch the wallet feedback game. https://t.co/x",
                "favorite_count": "3",
                "retweet_count": "2",
                "lang": "en",
                "source": "<a href=\"http://twitter.com/download/iphone\">Twitter for iPhone</a>",
                "entities": {"hashtags": [{"text": "pyramid"}], "user_mentions": [{"screen_name": "alice"}]},
            }},
            {"tweet": {
                "id_str": "222",
                "created_at": "Wed Nov 20 18:15:48 +0000 2024",
                "full_text": "Private draft should not enter the block.",
                "favorite_count": "0",
                "retweet_count": "0",
                "lang": "en",
                "entities": {},
            }},
        ],
    }), encoding="utf-8")
    spec = SourceSpec.from_dict({
        "name": "bodega-archive",
        "adapter": "community-archive",
        "location": "BodegaCat",
        "query": {"include_terms": ["wallet"], "exclude_terms": ["private"]},
        "metadata": {"archive_path": str(archive)},
    })

    records = SourceRegistry().query(spec)

    assert len(records) == 1
    assert records[0].record_id == "bodega-archive-t111"
    assert records[0].text == "Launch the wallet feedback game. https://t.co/x"
    assert records[0].metadata["tweet_id"] == "111"
    assert records[0].metadata["username"] == "bodegacat"
    assert records[0].metadata["url"] == "https://x.com/bodegacat/status/111"
    assert records[0].metadata["created_at"] == "2024-11-19T18:15:48+00:00"
    assert records[0].metadata["favorite_count"] == 3
    assert records[0].metadata["retweet_count"] == 2
    assert records[0].metadata["source_label"] == "Twitter for iPhone"
    assert records[0].metadata["hashtags"] == ["pyramid"]
    assert records[0].metadata["mentions"] == ["alice"]


def test_community_archive_source_merges_incremental_rows_and_dedupes(tmp_path: Path):
    archive = tmp_path / "archive.json"
    archive.write_text(json.dumps({
        "account": [{"account": {"username": "BodegaCat"}}],
        "tweets": [
            {"tweet": {
                "id_str": "111",
                "created_at": "Tue Nov 19 18:15:48 +0000 2024",
                "full_text": "Build the wallet feedback archive base.",
                "favorite_count": "3",
                "retweet_count": "2",
                "lang": "en",
                "entities": {},
            }},
        ],
    }), encoding="utf-8")
    incremental = tmp_path / "incremental.jsonl"
    incremental.write_text(
        json.dumps({
            "id_str": "111",
            "created_at": "Tue Nov 19 18:15:48 +0000 2024",
            "full_text": "Duplicate overlap row should not appear twice.",
            "favorite_count": "4",
            "retweet_count": "2",
            "lang": "en",
            "entities": {},
        }) + "\n" +
        json.dumps({
            "tweet_id": "333",
            "created_at": "Thu Nov 21 18:15:48 +0000 2024",
            "text": "Fresh wallet feedback after the archive upload.",
            "favorite_count": 7,
            "retweet_count": 1,
            "lang": "en",
            "source_dataset": "api_incremental",
            "entities": {"hashtags": [{"text": "fresh"}]},
        }) + "\n",
        encoding="utf-8",
    )
    spec = SourceSpec.from_dict({
        "name": "bodega-fresh",
        "adapter": "community-archive",
        "location": "BodegaCat",
        "query": {"include_terms": ["wallet"]},
        "metadata": {"archive_path": str(archive), "incremental_path": str(incremental)},
    })

    records = SourceRegistry().query(spec)

    assert [record.metadata["tweet_id"] for record in records] == ["111", "333"]
    assert records[0].metadata["source_dataset"] == "community_archive_raw"
    assert records[0].text == "Build the wallet feedback archive base."
    assert records[1].metadata["source_dataset"] == "api_incremental"
    assert records[1].metadata["url"] == "https://x.com/bodegacat/status/333"
    assert records[1].metadata["created_at"] == "2024-11-21T18:15:48+00:00"
    assert records[1].metadata["hashtags"] == ["fresh"]


def test_community_archive_api_capture_writes_incremental_jsonl(tmp_path: Path):
    calls = []

    def fake_api_get(path, params, api_key):
        calls.append((path, params, api_key))
        if path == "account":
            return [{"account_id": "acct-1", "username": "BodegaCat"}]
        if path == "tweets":
            return [
                {
                    "tweet_id": "333",
                    "created_at": "2024-11-21T18:15:48+00:00",
                    "full_text": "Fresh wallet feedback from the Community Archive API.",
                    "favorite_count": 7,
                    "retweet_count": 1,
                    "lang": "en",
                }
            ]
        raise AssertionError(path)

    output = tmp_path / "bodegacat.incremental.jsonl"

    receipt = source_mod.capture_community_archive_incremental(
        username="BodegaCat",
        output_path=output,
        since_tweet_id="111",
        api_key="unit-test-placeholder",  # git-secret-ignore
        page_size=100,
        api_get=fake_api_get,
        fetched_at="2026-06-17T00:00:00+00:00",
    )

    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert receipt == {"username": "bodegacat", "account_id": "acct-1", "rows": 1, "output": str(output)}
    assert calls[0] == ("account", {"username": "eq.bodegacat", "select": "account_id,username", "limit": "1"}, "unit-test-placeholder")
    assert calls[1][0] == "tweets"
    assert calls[1][1]["account_id"] == "eq.acct-1"
    assert calls[1][1]["tweet_id"] == "gt.111"
    assert rows[0]["tweet_id"] == "333"
    assert rows[0]["text"] == "Fresh wallet feedback from the Community Archive API."
    assert rows[0]["username"] == "bodegacat"
    assert rows[0]["account_id"] == "acct-1"
    assert rows[0]["source_dataset"] == "api_incremental"
    assert rows[0]["api_fetched_at"] == "2026-06-17T00:00:00+00:00"


def test_community_archive_capture_plan_uses_latest_archive_and_incremental_checkpoint(tmp_path: Path):
    archive = tmp_path / "archive.json"
    archive.write_text(json.dumps({
        "account": [{"account": {"username": "BodegaCat"}}],
        "tweets": [
            {"tweet": {"id_str": "111", "created_at": "Tue Nov 19 18:15:48 +0000 2024", "full_text": "Base one"}},
            {"tweet": {"id_str": "222", "created_at": "Wed Nov 20 18:15:48 +0000 2024", "full_text": "Base two"}},
        ],
    }), encoding="utf-8")
    incremental = tmp_path / "incremental.jsonl"
    incremental.write_text(json.dumps({
        "tweet_id": "333",
        "created_at": "2024-11-21T18:15:48+00:00",
        "text": "Latest captured row.",
    }) + "\n", encoding="utf-8")

    plan = source_mod.plan_community_archive_incremental_capture(
        username="BodegaCat",
        archive_path=archive,
        incremental_paths=[incremental],
        output_dir=tmp_path / "captures",
    )

    assert plan["username"] == "bodegacat"
    assert plan["since_tweet_id"] == "333"
    assert plan["latest_created_at"] == "2024-11-21T18:15:48+00:00"
    assert plan["output"] == str(tmp_path / "captures" / "bodegacat.after-333.jsonl")


def test_cli_community_archive_capture_incremental_writes_file(tmp_path: Path, monkeypatch):
    def fake_api_get(path, params, api_key):
        if path == "account":
            return [{"account_id": "acct-1", "username": "BodegaCat"}]
        if path == "tweets":
            return [{"tweet_id": "444", "text": "API capture file can become a source block."}]
        return []

    monkeypatch.setattr(source_mod, "_community_archive_api_get", fake_api_get)
    output = tmp_path / "capture.jsonl"

    main([
        "community-archive",
        "capture-incremental",
        "--username", "BodegaCat",
        "--since-tweet-id", "333",
        "--output", str(output),
        "--api-key", "unit-test-placeholder",  # git-secret-ignore
    ])

    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["tweet_id"] == "444"
    assert rows[0]["source_dataset"] == "api_incremental"


def test_cli_community_archive_capture_can_plan_checkpoint_and_output(tmp_path: Path, monkeypatch):
    calls = []

    def fake_api_get(path, params, api_key):
        calls.append((path, params, api_key))
        if path == "account":
            return [{"account_id": "acct-1", "username": "BodegaCat"}]
        if path == "tweets":
            return []
        return []

    monkeypatch.setattr(source_mod, "_community_archive_api_get", fake_api_get)
    archive = tmp_path / "archive.json"
    archive.write_text(json.dumps({
        "account": [{"account": {"username": "BodegaCat"}}],
        "tweets": [{"tweet": {"id_str": "222", "created_at": "Wed Nov 20 18:15:48 +0000 2024", "full_text": "Base"}}],
    }), encoding="utf-8")
    output_dir = tmp_path / "captures"

    main([
        "community-archive",
        "capture-incremental",
        "--username", "BodegaCat",
        "--archive-path", str(archive),
        "--output-dir", str(output_dir),
        "--api-key", "unit-test-placeholder",  # git-secret-ignore
    ])

    output = output_dir / "bodegacat.after-222.jsonl"
    assert output.exists()
    assert calls[1][1]["tweet_id"] == "gt.222"


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
    assert SourceRegistry().names() == ["community-archive", "directory-text", "inline", "jsonl", "text-file"]


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
