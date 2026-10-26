"""Streamlit wrapper for the drag-and-drop pitch component."""

from pathlib import Path

import streamlit.components.v1 as components

_COMPONENT_DIR = Path(__file__).resolve().parent / "frontend_dist"
_component = components.declare_component("lineup_builder", path=str(_COMPONENT_DIR))


def lineup_builder(players, xi, bench_out, bench_gk, version=0, key=None):
    """Render the interactive pitch.

    Args:
        players: 15 compact player dicts with GW cells.
        xi: 11 player IDs in the current XI.
        bench_out: 3 outfield bench IDs in substitution order.
        bench_gk: 1 goalkeeper ID.
        version: bump to force a fresh frontend state.
        key: stable Streamlit widget key.

    Returns:
        {"xi": [...], "bench_out": [...], "bench_gk": id} or None.
    """
    return _component(
        players=players,
        xi=[int(i) for i in xi],
        bench_out=[int(i) for i in bench_out],
        bench_gk=int(bench_gk) if bench_gk is not None else None,
        version=int(version),
        key=key,
        default=None,
    )
