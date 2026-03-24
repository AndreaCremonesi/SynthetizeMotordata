"""Compatibility launcher for the modularized trajectory synthesizer GUI."""

from __future__ import annotations

try:
    from synth_gui_app import TrajectorySynthApp, main
except ModuleNotFoundError:
    from .synth_gui_app import TrajectorySynthApp, main  # type: ignore[no-redef]


if __name__ == "__main__":
    main()
