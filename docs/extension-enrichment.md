# Extension capture enrichment

The browser extension export is a scroll receipt, not a finished corpus. `datamine extension enrich` turns the exported JSONL into normalized records, evidence subrecords, and explicit follow-up queues.

## Command

```bash
PYTHONPATH=src python -m data_mine.cli extension enrich \
  --input /path/to/brent-dill-trial-captures.jsonl \
  --output-dir /path/to/enriched/week-00/run-id \
  --run-id week-00-scroll-001
```

Outputs:

```text
enrichment_receipt.json
normalized.jsonl
evidence_subrecords.jsonl
queues/needs_ocr.jsonl
queues/needs_quote_fetch.jsonl
queues/needs_expanded_text.jsonl
queues/missing_tweet_id.jsonl
```

## What gets normalized

Rows are grouped by:

- `tweet:<tweet_id>` when a tweet id exists;
- `text-sha256:<hash>` when the extension could not extract a tweet id.

Duplicate captures for the same tweet are merged. The longest visible text wins, and DOM features such as image URLs, quote URLs, status URLs, and link URLs are unioned.

## Evidence subrecords

Each normalized capture becomes one or more evidence subrecords:

- `visible_text` — the browser-visible tweet/card text;
- `quoted_status_url` — a status/photo URL visible inside a quote card;
- `image_url` — an X-hosted image URL that likely needs OCR;
- `video_presence` — video count when visible;
- `show_more_truncation` — a marker that the visible text was probably incomplete.

These subrecords are the bridge from scroll capture to a corpus that can be audited. The raw capture is preserved; enrichment appends structure instead of overwriting the receipt.

## Queues

`needs_ocr.jsonl`
: one row per captured image URL. Later pass should fetch media and attach OCR text as separate evidence records.

`needs_quote_fetch.jsonl`
: one row per quoted status URL. Later pass should fetch or capture the quoted tweet as its own normalized record.

`needs_expanded_text.jsonl`
: tweets where X showed `Show more`. Later pass should open/fetch expanded text.

`missing_tweet_id.jsonl`
: captures without a tweet id. Later pass should resolve the URL/DOM shape or manually review.

## Corpus rule

Do not describe a browser export as comprehensive until these queue counts are known. A screenshot-heavy thread can look captured while the actual evidentiary content is still hidden in pixels. The receipt should say that. The receipt is annoying. This is its chief virtue.
