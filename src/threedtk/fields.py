"""Which fields a target's ``values --field`` accepts."""

from __future__ import annotations

from threedtk.query import available_value_fields, resolve_value_field


def value_field_rows(target: str) -> list[dict[str, str]]:
    """List every accepted field for ``target``, marking aliases."""
    rows = []
    for field in available_value_fields(target):
        resolved = resolve_value_field(target, field)
        rows.append(
            {
                "field": field,
                "type": "alias" if field != resolved else "field",
                "resolves_to": resolved,
            }
        )
    return rows
