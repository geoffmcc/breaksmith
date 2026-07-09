from __future__ import annotations

import json
import re
import secrets
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import __version__


WINDOWS_RESERVED_NAMES = {
    "con", "prn", "aux", "nul",
    "com1", "com2", "com3", "com4", "com5", "com6", "com7", "com8", "com9",
    "lpt1", "lpt2", "lpt3", "lpt4", "lpt5", "lpt6", "lpt7", "lpt8", "lpt9",
}


@dataclass(slots=True)
class ArtifactRecord:
    artifact_type: str
    path: str
    created: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RunContext:
    command: str
    source: Path
    parent_dir: Path
    run_dir: Path
    created_at: str
    artifacts: list[ArtifactRecord] = field(default_factory=list)

    def path(self, relative_path: str) -> Path:
        return self.run_dir / relative_path

    def register(self, artifact_type: str, path: Path, **metadata: Any) -> None:
        self.artifacts.append(
            ArtifactRecord(
                artifact_type=artifact_type,
                path=path.relative_to(self.run_dir).as_posix(),
                created=path.exists(),
                metadata={key: value for key, value in metadata.items() if value is not None},
            )
        )

    def write_manifest(self, options: dict[str, Any]) -> Path:
        manifest_path = self.run_dir / "manifest.json"
        data = {
            "breaksmith_version": __version__,
            "command": self.command,
            "created_at": self.created_at,
            "source_filename": self.source.name,
            "source_path": str(self.source),
            "run_directory": str(self.run_dir),
            "options": options,
            "artifacts": [asdict(artifact) for artifact in self.artifacts],
        }
        manifest_path.write_text(json.dumps(data, indent=2, default=str) + "\n", encoding="utf-8")
        self.register("manifest", manifest_path, format="json")
        return manifest_path


def sanitize_run_component(value: str, *, fallback: str = "source", max_length: int = 48) -> str:
    normalized = value.strip().lower()
    normalized = re.sub(r"[^a-z0-9._-]+", "-", normalized)
    normalized = re.sub(r"[-_.]+", "-", normalized).strip("-. ")
    if not normalized or normalized in WINDOWS_RESERVED_NAMES:
        normalized = fallback
    if len(normalized) > max_length:
        normalized = normalized[:max_length].rstrip("-") or fallback
    return normalized


def build_run_name(
    *,
    source: Path,
    command: str,
    style: str | None = None,
    timestamp: datetime | None = None,
    suffix: str | None = None,
) -> str:
    when = timestamp or datetime.now(timezone.utc)
    parts = [sanitize_run_component(source.stem), sanitize_run_component(command, fallback="run")]
    if style:
        parts.append(sanitize_run_component(style, fallback="style", max_length=24))
    parts.append(when.strftime("%Y%m%d-%H%M%S-%f")[:-3])
    parts.append(suffix or secrets.token_hex(2))
    return "-".join(part for part in parts if part)


def allocate_run_context(
    *,
    command: str,
    source: Path,
    parent_dir: Path,
    style: str | None = None,
    timestamp: datetime | None = None,
    suffix: str | None = None,
) -> RunContext:
    parent_dir.mkdir(parents=True, exist_ok=True)
    created_at = (timestamp or datetime.now(timezone.utc)).isoformat()
    for attempt in range(100):
        attempt_suffix = suffix if attempt == 0 else f"{suffix or secrets.token_hex(2)}-{attempt}"
        run_name = build_run_name(
            source=source,
            command=command,
            style=style,
            timestamp=timestamp,
            suffix=attempt_suffix,
        )
        run_dir = parent_dir / run_name
        try:
            run_dir.mkdir(parents=False, exist_ok=False)
        except FileExistsError:
            continue
        return RunContext(
            command=command,
            source=source,
            parent_dir=parent_dir,
            run_dir=run_dir,
            created_at=created_at,
        )
    raise RuntimeError(f"Could not allocate a unique run directory under {parent_dir}")
