from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path


@dataclass(frozen=True)
class ManifestEntry:
    entry_type: str
    id_field: str
    id_value: str
    url: str | None
    path: str | None
    checksum: str | None
    status: str
    size: int | None = None

    def as_dict(self) -> dict[str, str | int | None]:
        payload: dict[str, str | int | None] = {
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "type": self.entry_type,
            "url": self.url,
            "path": self.path,
            "checksum": self.checksum,
            "bytes": self.size,
            "status": self.status,
        }
        payload[self.id_field] = self.id_value
        return payload


def append_manifest_entry(manifest_path: str | Path, entry: ManifestEntry) -> None:
    path = Path(manifest_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("a", encoding="utf-8") as handle:
        json.dump(entry.as_dict(), handle, ensure_ascii=True)
        handle.write("\n")
