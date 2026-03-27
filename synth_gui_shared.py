"""Shared imports, constants, and engine symbols for the synth GUI modules."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import tkinter as tk
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from tkinter import filedialog, messagebox, ttk

try:
    from synth_engine import (
        DEFAULT_TRANSITION_DURATION_S,
        EAT_AWAY_BOTH,
        EAT_AWAY_LEFT,
        EAT_AWAY_RIGHT,
        MODE_CONSTANT,
        MODE_MULTISINE,
        MODE_RAMP,
        MODE_SINE,
        MODE_SWEEP,
        SWEEP_TYPE_LINEAR,
        SWEEP_TYPE_LOG,
        TRANSITION_STATUS_ACTIVE,
        TRANSITION_STATUS_RESOLVED,
        Y_COL,
        Z_COL,
        AxisLimits,
        AxisMotionSection,
        AxisSectionParams,
        AxisTransitionConfig,
        LimitsConfig,
        TrajectoryRecipe,
        ValidationIssue,
        ValidationReport,
        apply_easy_mode_continuity,
        build_csv_rows,
        compute_velocity_acceleration,
        create_default_recipe,
        ensure_pipeline_transitions,
        evaluate_limits,
        generate_axis_timeline,
        generate_trajectory_detailed,
        load_csv_header,
        resolve_non_overwriting_path,
        validate_header,
        write_output_csv,
    )
except ModuleNotFoundError:
    from .synth_engine import (  # type: ignore[no-redef]
        DEFAULT_TRANSITION_DURATION_S,
        EAT_AWAY_BOTH,
        EAT_AWAY_LEFT,
        EAT_AWAY_RIGHT,
        MODE_CONSTANT,
        MODE_MULTISINE,
        MODE_RAMP,
        MODE_SINE,
        MODE_SWEEP,
        SWEEP_TYPE_LINEAR,
        SWEEP_TYPE_LOG,
        TRANSITION_STATUS_ACTIVE,
        TRANSITION_STATUS_RESOLVED,
        Y_COL,
        Z_COL,
        AxisLimits,
        AxisMotionSection,
        AxisSectionParams,
        AxisTransitionConfig,
        LimitsConfig,
        TrajectoryRecipe,
        ValidationIssue,
        ValidationReport,
        apply_easy_mode_continuity,
        build_csv_rows,
        compute_velocity_acceleration,
        create_default_recipe,
        ensure_pipeline_transitions,
        evaluate_limits,
        generate_axis_timeline,
        generate_trajectory_detailed,
        load_csv_header,
        resolve_non_overwriting_path,
        validate_header,
        write_output_csv,
    )


TEMPLATE_PATH = Path(__file__).with_name("MotordataExample.csv")
OUTPUT_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT_BASENAME = "synth_motordata.csv"

EDIT_MODE_EASY = "Easy"
EDIT_MODE_EXPERT = "Expert"

TREE_TAG_TRANSITION_ACTIVE = "transition_active"
TREE_TAG_TRANSITION_RESOLVED = "transition_resolved"
TREE_TAG_AUTO_FILL_SECTION = "auto_fill_section"


__all__ = [
    "Any",
    "DEFAULT_OUTPUT_BASENAME",
    "DEFAULT_TRANSITION_DURATION_S",
    "Dict",
    "EAT_AWAY_BOTH",
    "EAT_AWAY_LEFT",
    "EAT_AWAY_RIGHT",
    "EDIT_MODE_EASY",
    "EDIT_MODE_EXPERT",
    "Figure",
    "FigureCanvasTkAgg",
    "LimitsConfig",
    "List",
    "MODE_CONSTANT",
    "MODE_MULTISINE",
    "MODE_RAMP",
    "MODE_SINE",
    "MODE_SWEEP",
    "SWEEP_TYPE_LINEAR",
    "SWEEP_TYPE_LOG",
    "OUTPUT_DIR",
    "Optional",
    "Path",
    "TEMPLATE_PATH",
    "TRANSITION_STATUS_ACTIVE",
    "TRANSITION_STATUS_RESOLVED",
    "Y_COL",
    "Z_COL",
    "TREE_TAG_TRANSITION_ACTIVE",
    "TREE_TAG_TRANSITION_RESOLVED",
    "TREE_TAG_AUTO_FILL_SECTION",
    "TrajectoryRecipe",
    "Tuple",
    "ValidationIssue",
    "ValidationReport",
    "apply_easy_mode_continuity",
    "build_csv_rows",
    "compute_velocity_acceleration",
    "create_default_recipe",
    "datetime",
    "ensure_pipeline_transitions",
    "evaluate_limits",
    "filedialog",
    "generate_trajectory_detailed",
    "generate_axis_timeline",
    "load_csv_header",
    "messagebox",
    "resolve_non_overwriting_path",
    "tk",
    "timezone",
    "ttk",
    "validate_header",
    "write_output_csv",
    "AxisLimits",
    "AxisMotionSection",
    "AxisSectionParams",
    "AxisTransitionConfig",
]
