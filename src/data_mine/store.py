from __future__ import annotations

import json
from pathlib import Path

from .models import Artifact, Block


class MineStore:
    def __init__(self, root: str | Path = ".mine") -> None:
        self.root = Path(root)
        self.blocks_dir = self.root / "blocks"
        self.artifacts_dir = self.root / "artifacts"
        self.blocks_dir.mkdir(parents=True, exist_ok=True)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)

    def init(self) -> None:
        (self.root / "README.txt").write_text(
            "Data Mine local store. Do not commit private blocks unless explicitly intended.\n",
            encoding="utf-8",
        )

    def save_block(self, block: Block) -> Path:
        path = self.blocks_dir / f"{block.block_id}.json"
        path.write_text(json.dumps(block.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
        return path

    def load_block(self, block_id: str) -> Block:
        path = self.blocks_dir / f"{block_id}.json"
        if not path.exists():
            raise FileNotFoundError(f"block not found: {block_id}")
        return Block.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def list_blocks(self) -> list[Block]:
        return [Block.from_dict(json.loads(p.read_text(encoding="utf-8"))) for p in sorted(self.blocks_dir.glob("*.json"))]

    def save_artifact(self, artifact: Artifact) -> Path:
        path = self.artifacts_dir / f"{artifact.artifact_id}.json"
        path.write_text(json.dumps(artifact.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
        return path

    def load_artifact(self, artifact_id: str) -> Artifact:
        path = self.artifacts_dir / f"{artifact_id}.json"
        if not path.exists():
            raise FileNotFoundError(f"artifact not found: {artifact_id}")
        return Artifact.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def list_artifacts(self) -> list[Artifact]:
        return [Artifact.from_dict(json.loads(p.read_text(encoding="utf-8"))) for p in sorted(self.artifacts_dir.glob("*.json"))]
