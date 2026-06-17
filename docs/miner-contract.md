# Miner function contract

A miner function receives a `Block` and returns zero or more `Artifact` objects.

Required fields for every artifact:

- `artifact_id`
- `block_id`
- `kind`
- `title`
- `summary`
- `evidence`
- `score`
- `miner`
- `created_at`

Rules:

- Evidence snippets must be traceable to record IDs.
- Scores must include reasons, not just numbers wearing a tie.
- Miners must not mutate blocks.
- Miners that call external APIs should be adapters, not core defaults.

Built-in miners:

- `keyword`: finds records matching query terms.
- `repeated-requests`: detects repeated request/action language.
- `contradictions`: detects records that contain tension markers.
- `build-seeds`: detects buildable verbs and missing-tool language.
