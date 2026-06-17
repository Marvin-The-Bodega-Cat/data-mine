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
- `inline`: takes literal strings from config for small hypotheses/tests.

## Query rules

Each source can specify:

- `include_terms`: keep records containing at least one term.
- `exclude_terms`: drop records containing any term.
- `limit`: max records from that source.

This is intentionally primitive. Primitive filters have the virtue of failing where you can see them.

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
