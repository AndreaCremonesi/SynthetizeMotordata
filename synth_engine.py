from __future__ import annotations

import csv
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np


SEQ_COL = "SeqNo"
DATE_COL = "Date"
TIME_COL = "UTC Time"
Y_COL = "mrk_hor_pos(m)"
Z_COL = "mrk_ver_pos(m)"

DEFAULT_HEADER = [
    "SeqNo",
    "Date",
    "UTC Time",
    "int_hor_pos(m)",
    "src_hor_pos(m)",
    "mrk_hor_pos(m)",
    "int_ver_pos(m)",
    "src_ver_pos(m)",
    "mrk_ver_pos(m)",
    "int_mas_trq(Nm)",
    "src_mas_trq(Nm)",
    "int_sla_trq(Nm)",
    "src_sla_trq(Nm)",
    "int_ver_trq(Nm)",
    "src_ver_trq(Nm)",
    "xray_active(-)",
    "error_code(-)",
    "rt_ts(ms)",
]

MODE_SINE = "sine"
MODE_SWEEP = "sweep"
MODE_RAMP = "ramp"
MODE_CONSTANT = "constant"
VALID_MODES = (MODE_SINE, MODE_SWEEP, MODE_RAMP, MODE_CONSTANT)

EAT_AWAY_LEFT = "left"
EAT_AWAY_RIGHT = "right"
EAT_AWAY_BOTH = "both"
VALID_EAT_AWAY_MODES = (EAT_AWAY_LEFT, EAT_AWAY_RIGHT, EAT_AWAY_BOTH)

TRANSITION_STATUS_ACTIVE = "active"
TRANSITION_STATUS_RESOLVED = "resolved"
VALID_TRANSITION_STATUSES = (TRANSITION_STATUS_ACTIVE, TRANSITION_STATUS_RESOLVED)

DEFAULT_TRANSITION_DURATION_S = 0.10


@dataclass
class AxisSectionParams:
    mode: str = MODE_SINE
    amplitude: float = 0.01
    offset: float = 0.0
    phase_deg: float = 0.0
    frequency_hz: float = 1.0
    sweep_start_hz: float = 0.5
    sweep_end_hz: float = 5.0
    ramp_start: float = 0.0
    ramp_end: float = 0.01
    constant_value: float = 0.0


@dataclass
class AxisMotionSection:
    duration_s: float = 5.0
    params: AxisSectionParams = field(default_factory=AxisSectionParams)
    is_auto_fill: bool = False


@dataclass
class AxisTransitionConfig:
    enabled: bool = False
    duration_s: float = DEFAULT_TRANSITION_DURATION_S
    eat_away_mode: str = EAT_AWAY_BOTH
    auto_added: bool = False
    status: str = TRANSITION_STATUS_RESOLVED


@dataclass
class AxisPipeline:
    sections: List[AxisMotionSection] = field(default_factory=list)
    transitions: List[AxisTransitionConfig] = field(default_factory=list)


@dataclass
class TrajectoryRecipe:
    sample_rate_hz: float = 500.0
    y_pipeline: AxisPipeline = field(default_factory=AxisPipeline)
    z_pipeline: AxisPipeline = field(default_factory=AxisPipeline)

    @property
    def y_sections(self) -> List[AxisMotionSection]:
        return self.y_pipeline.sections

    @y_sections.setter
    def y_sections(self, value: List[AxisMotionSection]) -> None:
        self.y_pipeline.sections = value
        ensure_pipeline_transitions(self.y_pipeline)

    @property
    def z_sections(self) -> List[AxisMotionSection]:
        return self.z_pipeline.sections

    @z_sections.setter
    def z_sections(self, value: List[AxisMotionSection]) -> None:
        self.z_pipeline.sections = value
        ensure_pipeline_transitions(self.z_pipeline)


@dataclass
class AxisLimits:
    enable_min_value: bool = False
    min_value: float = -1.0
    enable_max_value: bool = False
    max_value: float = 1.0
    enable_max_speed: bool = False
    max_speed: float = 1.0
    enable_max_acceleration: bool = False
    max_acceleration: float = 1.0
    enable_jump_threshold: bool = True
    max_jump: float = 0.01


@dataclass
class LimitsConfig:
    y: AxisLimits = field(default_factory=AxisLimits)
    z: AxisLimits = field(default_factory=AxisLimits)


@dataclass
class ValidationIssue:
    axis: str
    rule: str
    actual: float
    threshold: float
    message: str
    time_s: Optional[float] = None
    boundary_index: Optional[int] = None


@dataclass
class ValidationReport:
    issues: List[ValidationIssue] = field(default_factory=list)

    @property
    def has_violations(self) -> bool:
        return bool(self.issues)

    def summary_lines(self) -> List[str]:
        return [issue.message for issue in self.issues]

    def summary_text(self, max_lines: int | None = None) -> str:
        lines = self.summary_lines()
        if max_lines is not None and len(lines) > max_lines:
            shown = lines[:max_lines]
            shown.append(f"... {len(lines) - max_lines} more warning(s)")
            return "\n".join(shown)
        return "\n".join(lines)


def ensure_pipeline_transitions(pipeline: AxisPipeline) -> None:
    target_len = max(0, len(pipeline.sections) - 1)
    current = len(pipeline.transitions)
    if current < target_len:
        for _ in range(target_len - current):
            pipeline.transitions.append(AxisTransitionConfig())
    elif current > target_len:
        del pipeline.transitions[target_len:]


def create_default_recipe() -> TrajectoryRecipe:
    recipe = TrajectoryRecipe(
        sample_rate_hz=500.0,
        y_pipeline=AxisPipeline(sections=[AxisMotionSection(duration_s=5.0)]),
        z_pipeline=AxisPipeline(sections=[AxisMotionSection(duration_s=5.0)]),
    )
    ensure_pipeline_transitions(recipe.y_pipeline)
    ensure_pipeline_transitions(recipe.z_pipeline)
    return recipe


def load_csv_header(template_path: Path) -> List[str]:
    if template_path.exists():
        with template_path.open("r", newline="", encoding="utf-8") as file:
            reader = csv.reader(file)
            header = next(reader, None)
        if header:
            return header
    return DEFAULT_HEADER.copy()


def validate_header(header: Sequence[str]) -> None:
    required = {SEQ_COL, DATE_COL, TIME_COL, Y_COL, Z_COL}
    missing = required.difference(header)
    if missing:
        missing_text = ", ".join(sorted(missing))
        raise ValueError(f"CSV header missing required columns: {missing_text}")


def _validate_axis_params(axis_label: str, params: AxisSectionParams) -> None:
    if params.mode not in VALID_MODES:
        allowed = ", ".join(VALID_MODES)
        raise ValueError(f"{axis_label}: invalid mode '{params.mode}' (allowed: {allowed}).")
    if params.amplitude < 0:
        raise ValueError(f"{axis_label}: amplitude cannot be negative.")
    if params.frequency_hz < 0:
        raise ValueError(f"{axis_label}: frequency cannot be negative.")
    if params.sweep_start_hz < 0 or params.sweep_end_hz < 0:
        raise ValueError(f"{axis_label}: sweep frequencies cannot be negative.")


def _section_sample_count(duration_s: float, sample_rate_hz: float) -> int:
    return int(round(duration_s * sample_rate_hz))


def _validate_axis_sections(axis_label: str, sections: Sequence[AxisMotionSection], sample_rate_hz: float) -> None:
    if not sections:
        raise ValueError(f"{axis_label}: at least one section is required.")
    if sample_rate_hz <= 0:
        raise ValueError("Sample rate must be > 0.")

    for idx, section in enumerate(sections, start=1):
        if section.duration_s <= 0:
            raise ValueError(f"{axis_label} section {idx}: duration must be > 0.")
        n_samples = _section_sample_count(section.duration_s, sample_rate_hz)
        if n_samples <= 0:
            raise ValueError(
                f"{axis_label} section {idx}: duration too short for sample rate (needs at least 1 sample)."
            )
        _validate_axis_params(f"{axis_label} section {idx}", section.params)


def _validate_axis_transitions(axis_label: str, pipeline: AxisPipeline) -> None:
    ensure_pipeline_transitions(pipeline)
    for idx, transition in enumerate(pipeline.transitions, start=1):
        if transition.duration_s < 0:
            raise ValueError(f"{axis_label} transition {idx}: duration cannot be negative.")
        if transition.eat_away_mode not in VALID_EAT_AWAY_MODES:
            allowed = ", ".join(VALID_EAT_AWAY_MODES)
            raise ValueError(
                f"{axis_label} transition {idx}: invalid eat-away mode '{transition.eat_away_mode}' (allowed: {allowed})."
            )
        if transition.status not in VALID_TRANSITION_STATUSES:
            transition.status = TRANSITION_STATUS_RESOLVED


def validate_recipe(recipe: TrajectoryRecipe) -> None:
    if recipe.sample_rate_hz <= 0:
        raise ValueError("Sample rate must be > 0.")
    _validate_axis_sections("Y", recipe.y_pipeline.sections, recipe.sample_rate_hz)
    _validate_axis_sections("Z", recipe.z_pipeline.sections, recipe.sample_rate_hz)
    _validate_axis_transitions("Y", recipe.y_pipeline)
    _validate_axis_transitions("Z", recipe.z_pipeline)


def _generate_axis_section(t_local: np.ndarray, duration_s: float, params: AxisSectionParams) -> np.ndarray:
    phase_rad = math.radians(params.phase_deg)

    if params.mode == MODE_CONSTANT:
        return np.full_like(t_local, params.constant_value, dtype=float)

    if params.mode == MODE_RAMP:
        if duration_s <= 0:
            return np.full_like(t_local, params.ramp_start, dtype=float)
        ratio = t_local / duration_s
        return params.ramp_start + (params.ramp_end - params.ramp_start) * ratio

    if params.mode == MODE_SINE:
        phase = 2.0 * math.pi * params.frequency_hz * t_local + phase_rad
        return params.offset + params.amplitude * np.sin(phase)

    if params.mode == MODE_SWEEP:
        k = (params.sweep_end_hz - params.sweep_start_hz) / duration_s
        phase = 2.0 * math.pi * (params.sweep_start_hz * t_local + 0.5 * k * t_local * t_local) + phase_rad
        return params.offset + params.amplitude * np.sin(phase)

    raise ValueError(f"Unsupported mode: {params.mode}")


def _endpoint_derivatives(values: np.ndarray, dt: float, at_start: bool) -> Tuple[float, float]:
    n = len(values)
    if n <= 1:
        return 0.0, 0.0

    if at_start:
        v = float((values[1] - values[0]) / dt)
        if n >= 3:
            a = float((values[2] - 2.0 * values[1] + values[0]) / (dt * dt))
        else:
            a = 0.0
        return v, a

    v = float((values[-1] - values[-2]) / dt)
    if n >= 3:
        a = float((values[-1] - 2.0 * values[-2] + values[-3]) / (dt * dt))
    else:
        a = 0.0
    return v, a


def _c2_quintic_blend(
    start_value: float,
    start_velocity: float,
    start_acceleration: float,
    end_value: float,
    end_velocity: float,
    end_acceleration: float,
    n_samples: int,
    dt: float,
) -> np.ndarray:
    if n_samples <= 0:
        return np.array([], dtype=float)

    total_time = (n_samples + 1) * dt
    c0 = start_value
    c1 = start_velocity
    c2 = 0.5 * start_acceleration

    rhs = np.array(
        [
            end_value - (c0 + c1 * total_time + c2 * total_time * total_time),
            end_velocity - (c1 + 2.0 * c2 * total_time),
            end_acceleration - (2.0 * c2),
        ],
        dtype=float,
    )
    mat = np.array(
        [
            [total_time**3, total_time**4, total_time**5],
            [3.0 * total_time**2, 4.0 * total_time**3, 5.0 * total_time**4],
            [6.0 * total_time, 12.0 * total_time**2, 20.0 * total_time**3],
        ],
        dtype=float,
    )

    try:
        c3, c4, c5 = np.linalg.solve(mat, rhs)
    except np.linalg.LinAlgError:
        u = (np.arange(n_samples, dtype=float) + 1.0) / (n_samples + 1.0)
        return start_value + (end_value - start_value) * u

    t = dt * np.arange(1, n_samples + 1, dtype=float)
    return c0 + c1 * t + c2 * t**2 + c3 * t**3 + c4 * t**4 + c5 * t**5


def _allocate_removals(
    eat_away_mode: str,
    n_target: int,
    left_available: int,
    right_available: int,
) -> Tuple[int, int]:
    if n_target <= 0:
        return 0, 0

    if eat_away_mode == EAT_AWAY_LEFT:
        return min(n_target, left_available), 0

    if eat_away_mode == EAT_AWAY_RIGHT:
        return 0, min(n_target, right_available)

    # split on both sides
    remove_left = min(left_available, n_target // 2)
    remove_right = min(right_available, n_target - remove_left)
    assigned = remove_left + remove_right

    if assigned < n_target:
        remaining = n_target - assigned
        more_left = min(left_available - remove_left, remaining)
        remove_left += more_left
        remaining -= more_left
        if remaining > 0:
            more_right = min(right_available - remove_right, remaining)
            remove_right += more_right

    return remove_left, remove_right


def generate_axis_timeline(
    sections: Sequence[AxisMotionSection],
    sample_rate_hz: float,
    axis_label: str = "Axis",
    transitions: Optional[Sequence[AxisTransitionConfig]] = None,
) -> Tuple[np.ndarray, np.ndarray, List[float], List[ValidationIssue]]:
    _validate_axis_sections(axis_label, sections, sample_rate_hz)
    dt = 1.0 / sample_rate_hz

    section_arrays: List[np.ndarray] = []
    for section in sections:
        n_samples = _section_sample_count(section.duration_s, sample_rate_hz)
        t_local = np.arange(n_samples, dtype=float) / sample_rate_hz
        section_arrays.append(_generate_axis_section(t_local, section.duration_s, section.params))

    if transitions is None:
        transition_items = [AxisTransitionConfig() for _ in range(max(0, len(sections) - 1))]
    else:
        transition_items = list(transitions)
        if len(transition_items) < max(0, len(sections) - 1):
            transition_items.extend(
                AxisTransitionConfig() for _ in range(max(0, len(sections) - 1) - len(transition_items))
            )
        elif len(transition_items) > max(0, len(sections) - 1):
            transition_items = transition_items[: max(0, len(sections) - 1)]

    issues: List[ValidationIssue] = []

    for boundary_idx, transition in enumerate(transition_items):
        if not transition.enabled:
            continue

        left = section_arrays[boundary_idx]
        right = section_arrays[boundary_idx + 1]

        requested_samples = int(round(transition.duration_s * sample_rate_hz))
        if requested_samples <= 0:
            continue

        left_available = max(0, len(left) - 1)
        right_available = max(0, len(right) - 1)
        if transition.eat_away_mode == EAT_AWAY_LEFT:
            max_possible = left_available
        elif transition.eat_away_mode == EAT_AWAY_RIGHT:
            max_possible = right_available
        else:
            max_possible = left_available + right_available

        effective_target = min(requested_samples, max_possible)
        remove_left, remove_right = _allocate_removals(
            transition.eat_away_mode,
            effective_target,
            left_available,
            right_available,
        )
        effective_samples = remove_left + remove_right

        if effective_samples <= 0:
            boundary_time = sum(len(arr) for arr in section_arrays[: boundary_idx + 1]) / sample_rate_hz
            issues.append(
                ValidationIssue(
                    axis=axis_label,
                    rule="transition_clamped",
                    actual=0.0,
                    threshold=float(requested_samples),
                    message=(
                        f"{axis_label}: transition at boundary {boundary_idx + 1} clamped to 0 samples "
                        f"at t={boundary_time:.6g}s (neighbor sections too short)"
                    ),
                    time_s=boundary_time,
                    boundary_index=boundary_idx,
                )
            )
            continue

        if effective_samples < requested_samples:
            boundary_time = sum(len(arr) for arr in section_arrays[: boundary_idx + 1]) / sample_rate_hz
            issues.append(
                ValidationIssue(
                    axis=axis_label,
                    rule="transition_clamped",
                    actual=float(effective_samples),
                    threshold=float(requested_samples),
                    message=(
                        f"{axis_label}: transition at boundary {boundary_idx + 1} clamped from "
                        f"{requested_samples} to {effective_samples} samples at t={boundary_time:.6g}s"
                    ),
                    time_s=boundary_time,
                    boundary_index=boundary_idx,
                )
            )

        left_kept = left[:-remove_left] if remove_left > 0 else left
        right_kept = right[remove_right:] if remove_right > 0 else right

        start_value = float(left_kept[-1])
        end_value = float(right_kept[0])
        start_velocity, start_acceleration = _endpoint_derivatives(left_kept, dt, at_start=False)
        end_velocity, end_acceleration = _endpoint_derivatives(right_kept, dt, at_start=True)
        blend = _c2_quintic_blend(
            start_value=start_value,
            start_velocity=start_velocity,
            start_acceleration=start_acceleration,
            end_value=end_value,
            end_velocity=end_velocity,
            end_acceleration=end_acceleration,
            n_samples=effective_samples,
            dt=dt,
        )

        section_arrays[boundary_idx] = np.concatenate([left_kept, blend])
        section_arrays[boundary_idx + 1] = right_kept

    boundaries_s: List[float] = [0.0]
    elapsed_samples = 0
    for arr in section_arrays:
        elapsed_samples += len(arr)
        boundaries_s.append(elapsed_samples / sample_rate_hz)

    values = np.concatenate(section_arrays)
    t = np.arange(len(values), dtype=float) / sample_rate_hz
    return t, values, boundaries_s, issues


def generate_trajectory_detailed(
    recipe: TrajectoryRecipe,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, List[float], List[float], List[ValidationIssue]]:
    validate_recipe(recipe)
    sample_rate_hz = float(recipe.sample_rate_hz)

    _t_y, y_values, y_boundaries, y_issues = generate_axis_timeline(
        recipe.y_pipeline.sections,
        sample_rate_hz,
        axis_label="Y",
        transitions=recipe.y_pipeline.transitions,
    )
    _t_z, z_values, z_boundaries, z_issues = generate_axis_timeline(
        recipe.z_pipeline.sections,
        sample_rate_hz,
        axis_label="Z",
        transitions=recipe.z_pipeline.transitions,
    )

    if len(y_values) != len(z_values):
        raise ValueError(
            "Y and Z total samples mismatch after rounding. "
            f"Y={len(y_values)} samples, Z={len(z_values)} samples. "
            "Adjust section durations so totals match."
        )

    t = np.arange(len(y_values), dtype=float) / sample_rate_hz
    return t, y_values, z_values, y_boundaries, z_boundaries, (y_issues + z_issues)


def generate_trajectory(recipe: TrajectoryRecipe) -> Tuple[np.ndarray, np.ndarray, np.ndarray, List[float], List[float]]:
    t, y_values, z_values, y_boundaries, z_boundaries, _issues = generate_trajectory_detailed(recipe)
    return t, y_values, z_values, y_boundaries, z_boundaries


def _section_end_value(section: AxisMotionSection, sample_rate_hz: float) -> float:
    n_samples = _section_sample_count(section.duration_s, sample_rate_hz)
    t_local = np.arange(n_samples, dtype=float) / sample_rate_hz
    values = _generate_axis_section(t_local, section.duration_s, section.params)
    return float(values[-1])


def apply_easy_mode_continuity(sections: List[AxisMotionSection], sample_rate_hz: float) -> None:
    if len(sections) <= 1:
        return

    _validate_axis_sections("Axis", sections, sample_rate_hz)
    for idx in range(1, len(sections)):
        prev_end = _section_end_value(sections[idx - 1], sample_rate_hz)
        params = sections[idx].params
        if params.mode == MODE_CONSTANT:
            params.constant_value = prev_end
        elif params.mode == MODE_RAMP:
            params.ramp_start = prev_end
        elif params.mode in (MODE_SINE, MODE_SWEEP):
            params.offset = prev_end - (params.amplitude * math.sin(math.radians(params.phase_deg)))


def compute_velocity_acceleration(
    y_values: np.ndarray, z_values: np.ndarray, sample_rate_hz: float
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    dt = 1.0 / sample_rate_hz
    vy = np.gradient(y_values, dt)
    vz = np.gradient(z_values, dt)
    ay = np.gradient(vy, dt)
    az = np.gradient(vz, dt)
    return vy, vz, ay, az


def _boundary_jumps(
    values: np.ndarray, boundaries_s: Sequence[float], sample_rate_hz: float
) -> List[Tuple[int, float, float, float, float]]:
    jumps: List[Tuple[int, float, float, float, float]] = []
    for boundary_index, boundary_s in enumerate(boundaries_s[1:-1]):
        idx = int(round(boundary_s * sample_rate_hz))
        if idx <= 0 or idx >= len(values):
            continue
        jump = float(abs(values[idx] - values[idx - 1]))

        left_step = jump
        if idx >= 2:
            left_step = float(abs(values[idx - 1] - values[idx - 2]))
        right_step = jump
        if idx + 1 < len(values):
            right_step = float(abs(values[idx + 1] - values[idx]))

        local_baseline = max(left_step, right_step)
        jump_excess = max(0.0, jump - local_baseline)
        jumps.append((boundary_index, boundary_s, jump, local_baseline, jump_excess))
    return jumps


def _evaluate_axis_limits(
    axis_label: str,
    values: np.ndarray,
    velocity: np.ndarray,
    acceleration: np.ndarray,
    boundaries_s: Sequence[float],
    sample_rate_hz: float,
    limits: AxisLimits,
) -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []

    if limits.enable_min_value:
        idx = int(np.argmin(values))
        actual = float(values[idx])
        time_s = idx / sample_rate_hz
        if actual < limits.min_value:
            issues.append(
                ValidationIssue(
                    axis=axis_label,
                    rule="min_value",
                    actual=actual,
                    threshold=limits.min_value,
                    message=(
                        f"{axis_label}: min value {actual:.6g} at t={time_s:.6g}s "
                        f"is below limit {limits.min_value:.6g}"
                    ),
                    time_s=time_s,
                )
            )

    if limits.enable_max_value:
        idx = int(np.argmax(values))
        actual = float(values[idx])
        time_s = idx / sample_rate_hz
        if actual > limits.max_value:
            issues.append(
                ValidationIssue(
                    axis=axis_label,
                    rule="max_value",
                    actual=actual,
                    threshold=limits.max_value,
                    message=(
                        f"{axis_label}: max value {actual:.6g} at t={time_s:.6g}s "
                        f"exceeds limit {limits.max_value:.6g}"
                    ),
                    time_s=time_s,
                )
            )

    if limits.enable_max_speed:
        idx = int(np.argmax(np.abs(velocity)))
        actual = float(abs(velocity[idx]))
        time_s = idx / sample_rate_hz
        if actual > limits.max_speed:
            issues.append(
                ValidationIssue(
                    axis=axis_label,
                    rule="max_speed",
                    actual=actual,
                    threshold=limits.max_speed,
                    message=(
                        f"{axis_label}: |speed| {actual:.6g} at t={time_s:.6g}s "
                        f"exceeds limit {limits.max_speed:.6g}"
                    ),
                    time_s=time_s,
                )
            )

    if limits.enable_max_acceleration:
        idx = int(np.argmax(np.abs(acceleration)))
        actual = float(abs(acceleration[idx]))
        time_s = idx / sample_rate_hz
        if actual > limits.max_acceleration:
            issues.append(
                ValidationIssue(
                    axis=axis_label,
                    rule="max_acceleration",
                    actual=actual,
                    threshold=limits.max_acceleration,
                    message=(
                        f"{axis_label}: |acceleration| {actual:.6g} at t={time_s:.6g}s "
                        f"exceeds limit {limits.max_acceleration:.6g}"
                    ),
                    time_s=time_s,
                )
            )

    if limits.enable_jump_threshold:
        for boundary_index, boundary_s, jump, baseline, jump_excess in _boundary_jumps(
            values, boundaries_s, sample_rate_hz
        ):
            if jump_excess > limits.max_jump:
                issues.append(
                    ValidationIssue(
                        axis=axis_label,
                        rule="boundary_jump",
                        actual=jump_excess,
                        threshold=limits.max_jump,
                        message=(
                            f"{axis_label}: boundary jump excess {jump_excess:.6g} at t={boundary_s:.6g}s "
                            f"(raw={jump:.6g}, local baseline={baseline:.6g}) "
                            f"exceeds limit {limits.max_jump:.6g}"
                        ),
                        time_s=boundary_s,
                        boundary_index=boundary_index,
                    )
                )

    return issues


def evaluate_limits(
    y_values: np.ndarray,
    z_values: np.ndarray,
    sample_rate_hz: float,
    y_boundaries_s: Sequence[float],
    z_boundaries_s: Sequence[float],
    config: LimitsConfig,
    additional_issues: Optional[Sequence[ValidationIssue]] = None,
) -> ValidationReport:
    vy, vz, ay, az = compute_velocity_acceleration(y_values, z_values, sample_rate_hz)
    issues = _evaluate_axis_limits("Y", y_values, vy, ay, y_boundaries_s, sample_rate_hz, config.y)
    issues.extend(_evaluate_axis_limits("Z", z_values, vz, az, z_boundaries_s, sample_rate_hz, config.z))
    if additional_issues:
        issues.extend(additional_issues)
    return ValidationReport(issues=issues)


def resolve_non_overwriting_path(path: Path) -> Path:
    if not path.exists():
        return path

    parent = path.parent
    suffix = path.suffix
    stem = path.stem
    counter = 1
    while True:
        candidate = parent / f"{stem}_{counter:03d}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def build_csv_rows(
    header: Sequence[str],
    t: np.ndarray,
    y_values: np.ndarray,
    z_values: np.ndarray,
    start_utc: datetime,
) -> List[List[str]]:
    index: Dict[str, int] = {name: i for i, name in enumerate(header)}
    rows: List[List[str]] = []

    for seq, (time_s, y_value, z_value) in enumerate(zip(t, y_values, z_values), start=1):
        timestamp = start_utc + timedelta(seconds=float(time_s))
        row = ["0"] * len(header)
        row[index[SEQ_COL]] = str(seq)
        row[index[DATE_COL]] = timestamp.strftime("%Y-%m-%d")
        row[index[TIME_COL]] = timestamp.strftime("%H:%M:%S.%f")[:-3]
        row[index[Y_COL]] = f"{y_value:.6f}"
        row[index[Z_COL]] = f"{z_value:.6f}"
        rows.append(row)

    return rows


def write_output_csv(path: Path, header: Sequence[str], rows: Sequence[Sequence[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(header)
        writer.writerows(rows)
