# Architecture

## Flow

```text
raw material -> SourceAdapter(s) -> SourceQuery -> Block -> MinerFunction(s) -> Artifact(s) -> BuildSeed -> repo/project t0
```

## Design rules

- Blocks are immutable enough to cite. If source material changes, create a new block revision.
- Miners are pure functions over a block where possible.
- Artifacts must carry evidence snippets and scoring reasons.
- Search must work locally without a hosted vector database.
- Real/private data stays out of git.

## t0 semantics

A block is a starting point for a build because it freezes a context window:

- what was known,
- what evidence existed,
- what artifact was detected,
- what was not yet built.

That lets downstream projects say: this repo started from block X, artifact Y. Accountability, the unpopular cousin of creativity.
