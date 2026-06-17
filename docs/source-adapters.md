# Source adapters

Sources are queryable inputs that can be composed into a block.

The shape is:

```text
SourceAdapter -> SourceQuery -> ordered records -> Block -> MinerFunction -> Artifact
```

A source is not a block. A source is live-ish infrastructure or a local file. A block is a frozen `t0` cut from one or more sources.

## Built-in adapters

- `text-file`: reads non-empty lines from one text file.
- `directory-text`: reads matching text files from a directory in sorted order.
- `jsonl`: reads JSONL and extracts a configured text field.
- `community-archive`: reads public X/Twitter archive tweets from Community Archive raw JSON.
- `inline`: takes literal strings from config for small hypotheses/tests.

## Query rules

Each source can specify:

- `include_terms`: keep records containing at least one term.
- `exclude_terms`: drop records containing any term.
- `limit`: max records from that source.

This is intentionally primitive. Primitive filters have the virtue of failing where you can see them.

## Community Archive adapter

Use `community-archive` when a source should be an archived public X/Twitter account.

Minimal remote config:

```json
{
  "name": "defender-feedback",
  "adapter": "community-archive",
  "location": "defenderofbasic",
  "query": {"include_terms": ["build", "feedback"], "limit": 50}
}
```

For deterministic tests or cached runs, pass a local raw archive file:

```json
{
  "name": "cached-account",
  "adapter": "community-archive",
  "location": "somehandle",
  "metadata": {"archive_path": "artifacts/community_archive/raw/somehandle.archive.json"}
}
```

To close the archive freshness gap, pass incremental capture files:

```json
{
  "name": "fresh-account",
  "adapter": "community-archive",
  "location": "somehandle",
  "metadata": {
    "archive_path": "artifacts/community_archive/raw/somehandle.archive.json",
    "incremental_path": "artifacts/community_archive/incremental/somehandle.after-upload.jsonl"
  }
}
```

`incremental_path` or `incremental_paths` may point to JSONL, a JSON array, or a JSON object with `tweets`, `records`, or `rows`. Rows may use Community Archive shape (`{"tweet": {...}}`), raw tweet fields (`id_str`, `full_text`), or normalized fields (`tweet_id`, `text`). The adapter appends archive rows first, then incremental rows, dedupes by tweet ID, and keeps the first row for overlap windows. That makes 1-7 day overlap pulls safe without double-counting.

Emitted metadata includes `username`, `tweet_id`, `url`, `created_at`, engagement counts, source label, hashtags, mentions, and `source_dataset`.

Freshness caveat: raw Community Archive JSON is only complete up to that user's archive upload. Incremental captures are explicit files for now; live API fetch belongs behind a separate credentialed fetch step, not a hidden network surprise inside block creation.

Create an API-backed incremental capture file with:

```bash
export COMMUNITY_ARCHIVE_ANON_KEY='...'
datamine community-archive capture-incremental \
  --username defenderofbasic \
  --since-tweet-id <last-seen-tweet-id> \
  --output artifacts/community_archive/incremental/defenderofbasic.incremental.jsonl
```

The command resolves `username -> account_id`, pages the PostgREST `tweets` table, normalizes rows to JSONL, and writes `source_dataset=api_incremental`. That file can then be listed under `incremental_path` or `incremental_paths` in any later block source config.

This makes the shape explicit:

```text
Community Archive API -> incremental JSONL capture -> source pipeline -> frozen block
```

The capture file is the receipt. The block is the cut. Mixing those together is how systems learn to lie with timestamps.

## Ordered source pipelines

`datamine block from-sources` preserves source order in record IDs and metadata:

```bash
datamine block from-sources \
  --store .mine \
  --block-id source-pilot \
  --title "Source pilot" \
  --config examples/source_pipeline.json
```

Record IDs look like:

```text
s01-cat-text-r0001
s02-source-notes-r0001
s03-inline-hypotheses-r0001
```

That lets a downstream artifact cite not just what evidence existed, but which source produced it and in what order.

## Future adapters

Good next adapters:

- GitHub issues/discussions
- Discord exports
- YouTube transcripts/comments
- Substack posts/comments
- local browser/social archive
- Fathom analytics
- onchain transaction windows

Rule: external/network adapters should prepare/query by default, not mutate or post.
