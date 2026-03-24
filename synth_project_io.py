"""Project file serialization/deserialization helpers."""

from __future__ import annotations

import math
from typing import Any, Dict, Mapping

try:
    from synth_engine import (
        AxisLimits,
        AxisMotionSection,
        AxisPipeline,
        AxisSectionParams,
        AxisTransitionConfig,
        LimitsConfig,
        TrajectoryRecipe,
        validate_recipe,
    )
except ModuleNotFoundError:
    from .synth_engine import (  # type: ignore[no-redef]
        AxisLimits,
        AxisMotionSection,
        AxisPipeline,
        AxisSectionParams,
        AxisTransitionConfig,
        LimitsConfig,
        TrajectoryRecipe,
        validate_recipe,
    )


PROJECT_SCHEMA_VERSION = 1
PROJECT_FILE_EXTENSION = ".synthproj.json"


def _as_dict(name: str, value: Any) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object.")
    return dict(value)


def _as_float(name: str, value: Any) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric.") from exc
    if not math.isfinite(parsed):
        raise ValueError(f"{name} must be finite.")
    return parsed


def _as_bool(name: str, value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lower = value.strip().lower()
        if lower in {"true", "1", "yes", "y"}:
            return True
        if lower in {"false", "0", "no", "n"}:
            return False
    raise ValueError(f"{name} must be boolean.")


def _as_str(name: str, value: Any) -> str:
    if isinstance(value, str):
        return value
    raise ValueError(f"{name} must be string.")


def _params_to_dict(params: AxisSectionParams) -> Dict[str, Any]:
    return {
        "mode": params.mode,
        "amplitude": params.amplitude,
        "offset": params.offset,
        "phase_deg": params.phase_deg,
        "frequency_hz": params.frequency_hz,
        "sweep_start_hz": params.sweep_start_hz,
        "sweep_end_hz": params.sweep_end_hz,
        "ramp_start": params.ramp_start,
        "ramp_end": params.ramp_end,
        "constant_value": params.constant_value,
        "multisine_components": params.multisine_components,
    }


def _params_from_dict(data: Mapping[str, Any], prefix: str) -> AxisSectionParams:
    return AxisSectionParams(
        mode=_as_str(f"{prefix}.mode", data.get("mode")),
        amplitude=_as_float(f"{prefix}.amplitude", data.get("amplitude")),
        offset=_as_float(f"{prefix}.offset", data.get("offset")),
        phase_deg=_as_float(f"{prefix}.phase_deg", data.get("phase_deg")),
        frequency_hz=_as_float(f"{prefix}.frequency_hz", data.get("frequency_hz")),
        sweep_start_hz=_as_float(f"{prefix}.sweep_start_hz", data.get("sweep_start_hz")),
        sweep_end_hz=_as_float(f"{prefix}.sweep_end_hz", data.get("sweep_end_hz")),
        ramp_start=_as_float(f"{prefix}.ramp_start", data.get("ramp_start")),
        ramp_end=_as_float(f"{prefix}.ramp_end", data.get("ramp_end")),
        constant_value=_as_float(f"{prefix}.constant_value", data.get("constant_value")),
        multisine_components=_as_str(
            f"{prefix}.multisine_components",
            data.get("multisine_components", AxisSectionParams().multisine_components),
        ),
    )


def _section_to_dict(section: AxisMotionSection) -> Dict[str, Any]:
    return {
        "duration_s": section.duration_s,
        "params": _params_to_dict(section.params),
        "is_auto_fill": section.is_auto_fill,
    }


def _section_from_dict(data: Mapping[str, Any], prefix: str) -> AxisMotionSection:
    params_data = _as_dict(f"{prefix}.params", data.get("params"))
    is_auto_fill_raw = data.get("is_auto_fill", False)
    is_auto_fill = _as_bool(f"{prefix}.is_auto_fill", is_auto_fill_raw)
    return AxisMotionSection(
        duration_s=_as_float(f"{prefix}.duration_s", data.get("duration_s")),
        params=_params_from_dict(params_data, f"{prefix}.params"),
        is_auto_fill=is_auto_fill,
    )


def _transition_to_dict(transition: AxisTransitionConfig) -> Dict[str, Any]:
    return {
        "enabled": transition.enabled,
        "duration_s": transition.duration_s,
        "eat_away_mode": transition.eat_away_mode,
        "auto_added": transition.auto_added,
        "status": transition.status,
    }


def _transition_from_dict(data: Mapping[str, Any], prefix: str) -> AxisTransitionConfig:
    return AxisTransitionConfig(
        enabled=_as_bool(f"{prefix}.enabled", data.get("enabled")),
        duration_s=_as_float(f"{prefix}.duration_s", data.get("duration_s")),
        eat_away_mode=_as_str(f"{prefix}.eat_away_mode", data.get("eat_away_mode")),
        auto_added=_as_bool(f"{prefix}.auto_added", data.get("auto_added")),
        status=_as_str(f"{prefix}.status", data.get("status")),
    )


def _pipeline_to_dict(pipeline: AxisPipeline) -> Dict[str, Any]:
    return {
        "sections": [_section_to_dict(section) for section in pipeline.sections],
        "transitions": [_transition_to_dict(transition) for transition in pipeline.transitions],
    }


def _pipeline_from_dict(data: Mapping[str, Any], prefix: str) -> AxisPipeline:
    sections_raw = data.get("sections")
    transitions_raw = data.get("transitions")
    if not isinstance(sections_raw, list):
        raise ValueError(f"{prefix}.sections must be a list.")
    if not isinstance(transitions_raw, list):
        raise ValueError(f"{prefix}.transitions must be a list.")
    sections = [
        _section_from_dict(
            _as_dict(f"{prefix}.sections[{idx}]", item),
            f"{prefix}.sections[{idx}]",
        )
        for idx, item in enumerate(sections_raw)
    ]
    transitions = [
        _transition_from_dict(_as_dict(f"{prefix}.transitions[{idx}]", item), f"{prefix}.transitions[{idx}]")
        for idx, item in enumerate(transitions_raw)
    ]
    return AxisPipeline(sections=sections, transitions=transitions)


def recipe_to_dict(recipe: TrajectoryRecipe) -> Dict[str, Any]:
    return {
        "sample_rate_hz": recipe.sample_rate_hz,
        "y_pipeline": _pipeline_to_dict(recipe.y_pipeline),
        "z_pipeline": _pipeline_to_dict(recipe.z_pipeline),
    }


def recipe_from_dict(data: Mapping[str, Any]) -> TrajectoryRecipe:
    parsed = _as_dict("recipe", data)
    recipe = TrajectoryRecipe(
        sample_rate_hz=_as_float("recipe.sample_rate_hz", parsed.get("sample_rate_hz")),
        y_pipeline=_pipeline_from_dict(_as_dict("recipe.y_pipeline", parsed.get("y_pipeline")), "recipe.y_pipeline"),
        z_pipeline=_pipeline_from_dict(_as_dict("recipe.z_pipeline", parsed.get("z_pipeline")), "recipe.z_pipeline"),
    )
    validate_recipe(recipe)
    return recipe


def limits_to_dict(limits: LimitsConfig) -> Dict[str, Any]:
    def axis_to_dict(axis_limits: AxisLimits) -> Dict[str, Any]:
        return {
            "enable_min_value": axis_limits.enable_min_value,
            "min_value": axis_limits.min_value,
            "enable_max_value": axis_limits.enable_max_value,
            "max_value": axis_limits.max_value,
            "enable_max_speed": axis_limits.enable_max_speed,
            "max_speed": axis_limits.max_speed,
            "enable_max_acceleration": axis_limits.enable_max_acceleration,
            "max_acceleration": axis_limits.max_acceleration,
            "enable_jump_threshold": axis_limits.enable_jump_threshold,
            "max_jump": axis_limits.max_jump,
        }

    return {
        "y": axis_to_dict(limits.y),
        "z": axis_to_dict(limits.z),
    }


def limits_from_dict(data: Mapping[str, Any]) -> LimitsConfig:
    parsed = _as_dict("limits", data)

    def axis_from_dict(axis_data: Mapping[str, Any], prefix: str) -> AxisLimits:
        return AxisLimits(
            enable_min_value=_as_bool(f"{prefix}.enable_min_value", axis_data.get("enable_min_value")),
            min_value=_as_float(f"{prefix}.min_value", axis_data.get("min_value")),
            enable_max_value=_as_bool(f"{prefix}.enable_max_value", axis_data.get("enable_max_value")),
            max_value=_as_float(f"{prefix}.max_value", axis_data.get("max_value")),
            enable_max_speed=_as_bool(f"{prefix}.enable_max_speed", axis_data.get("enable_max_speed")),
            max_speed=_as_float(f"{prefix}.max_speed", axis_data.get("max_speed")),
            enable_max_acceleration=_as_bool(
                f"{prefix}.enable_max_acceleration",
                axis_data.get("enable_max_acceleration"),
            ),
            max_acceleration=_as_float(f"{prefix}.max_acceleration", axis_data.get("max_acceleration")),
            enable_jump_threshold=_as_bool(f"{prefix}.enable_jump_threshold", axis_data.get("enable_jump_threshold")),
            max_jump=_as_float(f"{prefix}.max_jump", axis_data.get("max_jump")),
        )

    y_data = _as_dict("limits.y", parsed.get("y"))
    z_data = _as_dict("limits.z", parsed.get("z"))
    return LimitsConfig(
        y=axis_from_dict(y_data, "limits.y"),
        z=axis_from_dict(z_data, "limits.z"),
    )
