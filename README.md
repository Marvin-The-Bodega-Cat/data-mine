# Data Mine

Data Mine turns raw material into searchable `Block`s. Each block is a `t0` starting point for a possible build.

The job is simple:

1. create a block of data,
2. run miner functions over it,
3. extract artifacts worth building,
4. export the artifact as a build brief for a downstream repo.

This is not a data lake. Lakes are where data goes to become sedimentary guilt.

## Core vocabulary

- `Block`: bounded data package with source, content records, dimensions, and t0 timestamp.
- `MinerFunction`: pluggable function that searches a block for a specific artifact type.
- `Artifact`: a mined signal: product idea, contradiction, repeated request, missing tool, quote cluster, workflow, dataset, lead, or build brief.
- `BuildSeed`: an artifact promoted to a t0 build input.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
pytest -q

datamine init --store .mine
datamine sources
datamine block create --store .mine --block-id cat-feedback --title "Cat feedback batch" --source synthetic --text examples/cat_feedback.txt
datamine block from-sources --store .mine --block-id source-pilot --title "Source pilot" --config examples/source_pipeline.json
datamine mine --store .mine --block-id cat-feedback --miner repeated-requests
datamine mine --store .mine --block-id cat-feedback --miner contradictions
datamine search --store .mine --query wallet
datamine start-build --store .mine --artifact-id <artifact-id> --output /tmp/build_seed.json
datamine build-repo --store .mine --artifact-id <artifact-id> --output-dir /tmp/generated-build
cd /tmp/generated-build && python -m pytest -q
```

## Public/private boundary

Commit synthetic examples only. Real client archives, DMs, wallets, screenshots, or proprietary data should be stored as `*.private.jsonl` or outside the repo.

## Relationship to Pyramid Payments

Pyramid Payments starts a creative project at `t=0` and coordinates feedback until `t=1`.

Data Mine creates the `t=0` blocks: the raw material, contradictions, requests, and overlooked artifacts that justify a build existing at all.
