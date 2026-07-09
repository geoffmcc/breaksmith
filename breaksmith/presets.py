from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .app import GenerationRequest


PRESET_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class GenerationPreset:
    name: str
    request: GenerationRequest
    schema_version: int = PRESET_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["request"] = _request_to_dict(self.request)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GenerationPreset":
        version = int(data.get("schema_version", 0))
        if version > PRESET_SCHEMA_VERSION:
            raise ValueError(f"Unsupported future preset schema version: {version}")
        name = str(data.get("name") or "Untitled")
        request_data = dict(data.get("request") or {})
        return cls(name=name, request=_request_from_dict(request_data), schema_version=version or 1)


def user_data_dir() -> Path:
    if os.name == "nt":
        root = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(root) / "Breaksmith"
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "breaksmith"


def preset_dir() -> Path:
    return user_data_dir() / "presets"


def _request_to_dict(request: GenerationRequest) -> dict[str, Any]:
    data = asdict(request)
    for key in ("audio", "output"):
        data[key] = str(data[key])
    return data


def _request_from_dict(data: dict[str, Any]) -> GenerationRequest:
    if "audio" not in data:
        data["audio"] = Path("")
    data["audio"] = Path(data["audio"])
    data["output"] = Path(data.get("output") or "output")
    allowed = {field for field in GenerationRequest.__dataclass_fields__}
    return GenerationRequest(**{key: value for key, value in data.items() if key in allowed})


def save_preset(preset: GenerationPreset, directory: Path | None = None) -> Path:
    target_dir = directory or preset_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    safe_name = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in preset.name.lower()).strip("-") or "preset"
    path = target_dir / f"{safe_name}.json"
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(preset.to_dict(), indent=2, default=str) + "\n", encoding="utf-8")
    temp.replace(path)
    return path


def load_preset(path: Path) -> GenerationPreset:
    return GenerationPreset.from_dict(json.loads(path.read_text(encoding="utf-8")))


def list_presets(directory: Path | None = None) -> list[GenerationPreset]:
    target_dir = directory or preset_dir()
    if not target_dir.exists():
        return []
    presets: list[GenerationPreset] = []
    for path in sorted(target_dir.glob("*.json")):
        try:
            presets.append(load_preset(path))
        except Exception:
            continue
    return presets
