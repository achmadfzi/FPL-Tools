"""Streamlit wrapper for the JavaScript squad-builder component.

The component is a small vanilla-JS/HTML app (SortableJS) served from
``frontend_dist``. It is intentionally thin: Python remains the source of
truth for the squad and all FPL rules.
"""

from pathlib import Path

import streamlit.components.v1 as components

_COMPONENT_DIR = Path(__file__).resolve().parent / "frontend_dist"
_component = components.declare_component("squad_builder", path=str(_COMPONENT_DIR))


def squad_builder(players, selected, budget=1000, club_max=3, version=0, key=None):
    """Render the drag-and-drop squad builder.

    Args:
        players: list of compact player dicts (id, name, team, pos, price,
            proj, photo).
        selected: dict {pos: [player_id, ...]} for GK/DEF/MID/FWD.
        budget: available budget in tenths of a million.
        club_max: maximum players per club.
        version: bump from Python to force a fresh frontend state after an
            external squad change (load/sync/clear).
        key: stable Streamlit widget key.

    Returns:
        dict {pos: [player_id, ...]} or None until the user interacts.
    """
    return _component(
        players=players,
        selected=selected,
        budget=int(budget),
        club_max=int(club_max),
        version=int(version),
        key=key,
        default=None,
    )
