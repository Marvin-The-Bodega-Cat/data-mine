import json
from pathlib import Path

from data_mine.cli import main
from data_mine.extension_enrichment import enrich_extension_capture_file


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def test_extension_enrichment_splits_receipt_into_queues_and_subrecords(tmp_path: Path):
    source = tmp_path / "captures.jsonl"
    write_jsonl(source, [
        {
            "schema_version": "trial-extension-capture/v0.2",
            "tweet_id": "100",
            "url": "https://x.com/i/web/status/100",
            "author": "alice",
            "text": "Brent Dill thread visible text Show more",
            "participant_role": "jury",
            "suggested_lane": "prosecution",
            "admission": "unreviewed",
            "dom_features": {
                "image_urls": ["https://pbs.twimg.com/media/a.jpg"],
                "quoted_status_urls": ["https://x.com/bob/status/200"],
                "visible_has_show_more": True,
                "has_quote_card": True,
            },
        },
        {
            "schema_version": "trial-extension-capture/v0.1",
            "tweet_id": None,
            "url": "https://x.com/search?q=brent%20dill",
            "author": None,
            "text": "Search context capture without tweet id",
            "participant_role": "jury",
            "suggested_lane": "jury",
            "admission": "unreviewed",
        },
    ])

    receipt = enrich_extension_capture_file(source, tmp_path / "out", run_id="unit-run")

    assert receipt["input_rows"] == 2
    assert receipt["unique_tweets"] == 1
    assert receipt["normalized_records"] == 2
    assert receipt["evidence_subrecords"] == 5
    assert receipt["queues"] == {
        "needs_ocr": 1,
        "needs_quote_fetch": 1,
        "needs_expanded_text": 1,
        "missing_tweet_id": 1,
    }

    normalized = [json.loads(line) for line in Path(receipt["outputs"]["normalized"]).read_text(encoding="utf-8").splitlines()]
    subrecords = [json.loads(line) for line in Path(receipt["outputs"]["evidence_subrecords"]).read_text(encoding="utf-8").splitlines()]
    needs_ocr = [json.loads(line) for line in Path(receipt["outputs"]["needs_ocr"]).read_text(encoding="utf-8").splitlines()]

    assert normalized[0]["canonical_id"] == "tweet:100"
    assert normalized[1]["canonical_id"].startswith("text-sha256:")
    assert [record["evidence_type"] for record in subrecords] == [
        "visible_text",
        "quoted_status_url",
        "image_url",
        "show_more_truncation",
        "visible_text",
    ]
    assert needs_ocr[0]["image_url"] == "https://pbs.twimg.com/media/a.jpg"
    assert needs_ocr[0]["parent_tweet_id"] == "100"


def test_extension_enrichment_dedupes_duplicate_tweet_ids_without_losing_evidence(tmp_path: Path):
    source = tmp_path / "captures.jsonl"
    write_jsonl(source, [
        {
            "schema_version": "trial-extension-capture/v0.2",
            "tweet_id": "100",
            "url": "https://x.com/i/web/status/100",
            "author": "alice",
            "text": "Short text",
            "dom_features": {"image_urls": ["https://pbs.twimg.com/media/a.jpg"]},
        },
        {
            "schema_version": "trial-extension-capture/v0.2",
            "tweet_id": "100",
            "url": "https://x.com/i/web/status/100",
            "author": "alice",
            "text": "Longer expanded text with more context",
            "dom_features": {"image_urls": ["https://pbs.twimg.com/media/a.jpg", "https://pbs.twimg.com/media/b.jpg"]},
        },
    ])

    receipt = enrich_extension_capture_file(source, tmp_path / "out")

    assert receipt["input_rows"] == 2
    assert receipt["duplicate_rows"] == 1
    assert receipt["normalized_records"] == 1
    assert receipt["queues"]["needs_ocr"] == 2
    normalized = [json.loads(line) for line in Path(receipt["outputs"]["normalized"]).read_text(encoding="utf-8").splitlines()]
    assert normalized[0]["text"] == "Longer expanded text with more context"
    assert normalized[0]["capture_count"] == 2


def test_cli_extension_enrich_writes_receipt_and_outputs(tmp_path: Path, capsys):
    source = tmp_path / "captures.jsonl"
    write_jsonl(source, [{
        "schema_version": "trial-extension-capture/v0.2",
        "tweet_id": "100",
        "text": "Brent Dill visible capture",
        "dom_features": {"visible_has_show_more": True},
    }])
    output_dir = tmp_path / "enriched"

    main(["extension", "enrich", "--input", str(source), "--output-dir", str(output_dir), "--run-id", "cli-unit"])

    printed = json.loads(capsys.readouterr().out)
    assert printed["run_id"] == "cli-unit"
    assert printed["queues"]["needs_expanded_text"] == 1
    assert (output_dir / "normalized.jsonl").exists()
    assert (output_dir / "queues" / "needs_expanded_text.jsonl").exists()
