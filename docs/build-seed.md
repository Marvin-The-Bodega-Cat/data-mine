# BuildSeed

A BuildSeed is an artifact promoted into a downstream t0 build input.

It contains:

- source block ID,
- artifact ID,
- build thesis,
- evidence snippets,
- recommended first files,
- falsification check.

A good BuildSeed is small enough to start a repo and sharp enough to be wrong.

## Runnable repo production

`datamine build-repo` turns an artifact into a minimal Python repository with:

- `data/build_seed.json`
- README and architecture docs
- a package CLI with `status`
- smoke tests
- an initial git commit

This is not the final product. It is a falsification harness: if the generated repo cannot run from the artifact evidence, the artifact is not ready to become a build.
