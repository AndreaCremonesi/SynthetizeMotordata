"""Preview generation, warning handling, plotting, and export mixin."""

from __future__ import annotations

import json

try:
    from synth_gui_shared import *
except ModuleNotFoundError:
    from .synth_gui_shared import *  # type: ignore[no-redef]

try:
    from synth_project_io import (
        PROJECT_FILE_EXTENSION,
        PROJECT_SCHEMA_VERSION,
        limits_from_dict,
        limits_to_dict,
        recipe_from_dict,
        recipe_to_dict,
    )
except ModuleNotFoundError:
    from .synth_project_io import (  # type: ignore[no-redef]
        PROJECT_FILE_EXTENSION,
        PROJECT_SCHEMA_VERSION,
        limits_from_dict,
        limits_to_dict,
        recipe_from_dict,
        recipe_to_dict,
    )


PREVIEW_MAX_POINTS = 4000


class RuntimeMixin:
    """Owns generation pipeline, diagnostics, and CSV export actions."""

    def _selected_section_index(self, axis: str) -> Optional[int]:
        row_type, row_index = self._selected_row_info(axis)
        if row_type != "section":
            return None
        sections = self._sections_for_axis(axis)
        if not (0 <= row_index < len(sections)):
            return None
        return row_index

    def _refresh_selection_highlight(self) -> None:
        result = self._last_generated
        if not result:
            return
        self._plot_preview(
            t=result["t"],
            y=result["y"],
            z=result["z"],
            y_boundaries=result["y_boundaries"],
            z_boundaries=result["z_boundaries"],
        )

    def _on_plot_tab_changed(self) -> None:
        result = self._last_generated
        if not result:
            return
        self._plot_preview(
            t=result["t"],
            y=result["y"],
            z=result["z"],
            y_boundaries=result["y_boundaries"],
            z_boundaries=result["z_boundaries"],
        )

    def _active_plot_tab_index(self) -> int:
        notebook = getattr(self, "plot_notebook", None)
        if notebook is None:
            return -1
        try:
            return int(notebook.index(notebook.select()))
        except Exception:
            return -1

    @staticmethod
    def _decimate_for_preview(*arrays: Any, max_points: int = PREVIEW_MAX_POINTS) -> Tuple[Any, ...]:
        if not arrays:
            return tuple()
        n = len(arrays[0])
        if n <= max_points or max_points <= 0:
            return tuple(arrays)
        for arr in arrays[1:]:
            if len(arr) != n:
                return tuple(arrays)
        step = max(1, int((n + max_points - 1) / max_points))
        return tuple(arr[::step] for arr in arrays)

    def _axis_section_sample_count(self, axis: str) -> int:
        sample_rate = float(self.recipe.sample_rate_hz)
        sections = self._sections_for_axis(axis)
        return sum(int(round(section.duration_s * sample_rate)) for section in sections)

    def _axis_auto_fill_intervals(self, axis: str) -> List[Tuple[float, float]]:
        sample_rate = float(self.recipe.sample_rate_hz)
        if sample_rate <= 0:
            return []
        elapsed = 0
        intervals: List[Tuple[float, float]] = []
        for section in self._sections_for_axis(axis):
            n_samples = int(round(section.duration_s * sample_rate))
            start_s = elapsed / sample_rate
            elapsed += n_samples
            end_s = elapsed / sample_rate
            if section.is_auto_fill:
                intervals.append((start_s, end_s))
        return intervals

    @staticmethod
    def _clone_transition_config(transition: AxisTransitionConfig) -> AxisTransitionConfig:
        return AxisTransitionConfig(
            enabled=bool(transition.enabled),
            duration_s=float(transition.duration_s),
            eat_away_mode=str(transition.eat_away_mode),
            auto_added=bool(transition.auto_added),
            status=str(transition.status),
        )

    def _trailing_auto_fill_transition(self, axis: str) -> Optional[AxisTransitionConfig]:
        pipeline = self._pipeline_for_axis(axis)
        if len(pipeline.sections) < 2:
            return None
        if not pipeline.sections[-1].is_auto_fill:
            return None
        ensure_pipeline_transitions(pipeline)
        if not pipeline.transitions:
            return None
        return self._clone_transition_config(pipeline.transitions[-1])

    def _strip_auto_fill_sections(self) -> bool:
        changed = False
        for axis in ("y", "z"):
            pipeline = self._pipeline_for_axis(axis)
            filtered = [section for section in pipeline.sections if not section.is_auto_fill]
            if len(filtered) != len(pipeline.sections):
                pipeline.sections = filtered
                ensure_pipeline_transitions(pipeline)
                changed = True
        return changed

    def _axis_last_value(self, axis: str) -> float:
        pipeline = self._pipeline_for_axis(axis)
        if not pipeline.sections:
            return 0.0
        _t, values, _boundaries, _issues = generate_axis_timeline(
            pipeline.sections,
            self.recipe.sample_rate_hz,
            axis_label=axis.upper(),
            transitions=pipeline.transitions,
        )
        if len(values) == 0:
            return 0.0
        return float(values[-1])

    def _sync_auto_fill_section(self) -> Optional[str]:
        preserved_transition = {
            "y": self._trailing_auto_fill_transition("y"),
            "z": self._trailing_auto_fill_transition("z"),
        }
        self._strip_auto_fill_sections()

        y_samples = self._axis_section_sample_count("y")
        z_samples = self._axis_section_sample_count("z")
        if y_samples == z_samples:
            return None

        shorter_axis = "y" if y_samples < z_samples else "z"
        longer_samples = z_samples if shorter_axis == "y" else y_samples
        shorter_samples = y_samples if shorter_axis == "y" else z_samples
        needed_samples = max(0, longer_samples - shorter_samples)
        if needed_samples <= 0:
            return None

        constant_value = self._axis_last_value(shorter_axis)
        duration_s = needed_samples / float(self.recipe.sample_rate_hz)
        auto_fill = AxisMotionSection(
            duration_s=duration_s,
            params=AxisSectionParams(mode=MODE_CONSTANT, constant_value=constant_value),
            is_auto_fill=True,
        )
        pipeline = self._pipeline_for_axis(shorter_axis)
        pipeline.sections.append(auto_fill)
        ensure_pipeline_transitions(pipeline)
        preserved = preserved_transition[shorter_axis]
        if preserved is not None and pipeline.transitions:
            transition = pipeline.transitions[-1]
            transition.enabled = preserved.enabled
            transition.duration_s = preserved.duration_s
            transition.eat_away_mode = preserved.eat_away_mode
            transition.auto_added = preserved.auto_added
            transition.status = preserved.status

        return (
            f"{shorter_axis.upper()} is shorter by {needed_samples} samples "
            f"({duration_s:.6g}s). Added auto-fill constant section."
        )

    def _read_axis_limits(self, axis: str) -> AxisLimits:
        vars_for_axis = self.limit_vars[axis]

        def parse_optional(enable_key: str, value_key: str, label: str, fallback: float) -> float:
            enabled = bool(vars_for_axis[enable_key].get())
            if not enabled:
                return fallback
            return self._parse_float(f"{axis.upper()} {label}", str(vars_for_axis[value_key].get()))

        return AxisLimits(
            enable_min_value=bool(vars_for_axis["enable_min_value"].get()),
            min_value=parse_optional("enable_min_value", "min_value", "min value", -1.0),
            enable_max_value=bool(vars_for_axis["enable_max_value"].get()),
            max_value=parse_optional("enable_max_value", "max_value", "max value", 1.0),
            enable_max_speed=bool(vars_for_axis["enable_max_speed"].get()),
            max_speed=parse_optional("enable_max_speed", "max_speed", "max speed", 1.0),
            enable_max_acceleration=bool(vars_for_axis["enable_max_acceleration"].get()),
            max_acceleration=parse_optional("enable_max_acceleration", "max_acceleration", "max acceleration", 1.0),
            enable_jump_threshold=bool(vars_for_axis["enable_jump_threshold"].get()),
            max_jump=parse_optional("enable_jump_threshold", "max_jump", "max jump", 0.01),
        )

    def _read_limits_config(self) -> LimitsConfig:
        return LimitsConfig(
            y=self._read_axis_limits("y"),
            z=self._read_axis_limits("z"),
        )

    def _update_transition_statuses_from_report(self, report: ValidationReport) -> bool:
        changed = False
        active_boundaries: Dict[str, set[int]] = {"y": set(), "z": set()}

        for issue in report.issues:
            if issue.rule != "boundary_jump" or issue.boundary_index is None:
                continue
            axis_label = str(issue.axis).strip().upper()
            axis = "y" if axis_label.startswith("Y") else "z" if axis_label.startswith("Z") else ""
            if axis:
                active_boundaries[axis].add(issue.boundary_index)

        for axis in ("y", "z"):
            transitions = self._transitions_for_axis(axis)
            for index, transition in enumerate(transitions):
                desired_status = (
                    TRANSITION_STATUS_ACTIVE if index in active_boundaries[axis] else TRANSITION_STATUS_RESOLVED
                )
                if transition.status != desired_status:
                    transition.status = desired_status
                    changed = True

                if (
                    desired_status == TRANSITION_STATUS_ACTIVE
                    and self.edit_mode_var.get() == EDIT_MODE_EASY
                    and not transition.enabled
                ):
                    if not transition.auto_added:
                        transition.duration_s = DEFAULT_TRANSITION_DURATION_S
                        transition.eat_away_mode = EAT_AWAY_BOTH
                        transition.auto_added = True
                    transition.enabled = True
                    changed = True

        return changed

    def _format_issue_line(self, issue: ValidationIssue) -> str:
        axis = str(issue.axis).strip().upper()
        details: List[str] = []
        if issue.boundary_index is not None:
            details.append(f"boundary {issue.boundary_index + 1}")
        if issue.time_s is not None:
            details.append(f"t={issue.time_s:.6g}s")
        prefix = f"{axis} [{issue.rule}]"
        if details:
            return f"- {prefix} ({', '.join(details)}): {issue.message}"
        return f"- {prefix}: {issue.message}"

    def _set_warning_text(self, text: str) -> None:
        if self.warning_text_widget is None:
            return
        widget = self.warning_text_widget
        widget.configure(state="normal")
        widget.delete("1.0", tk.END)
        widget.insert("1.0", text)
        widget.configure(state="disabled")

    def _set_warning_report(self, report: Optional[ValidationReport]) -> None:
        if report is None or not report.issues:
            self._set_warning_text("No warnings.")
            return
        lines = [self._format_issue_line(issue) for issue in report.issues]
        self._set_warning_text("\n".join(lines))

    def _set_status(self, text: str, is_error: bool = False) -> None:
        self.status_var.set(text)
        if self.status_label is not None:
            self.status_label.configure(foreground="#b00020" if is_error else "#1f2a44")

    def _plot_preview(
        self,
        t: Any,
        y: Any,
        z: Any,
        y_boundaries: List[float],
        z_boundaries: List[float],
    ) -> None:
        active_tab = self._active_plot_tab_index()
        render_position = active_tab in (-1, 0)
        render_dynamics = active_tab in (-1, 1)
        render_path = active_tab in (-1, 2)

        if render_position:
            t_plot, y_plot, z_plot = self._decimate_for_preview(t, y, z)
            self.ax_pos.clear()
            self.ax_pos.plot(t_plot, y_plot, label="Y position", color="#1f77b4", linewidth=1.4)
            self.ax_pos.plot(t_plot, z_plot, label="Z position", color="#2ca02c", linewidth=1.4)

            auto_fill_labels: List[Tuple[float, str]] = []
            for start_s, end_s in self._axis_auto_fill_intervals("y"):
                self.ax_pos.axvspan(start_s, end_s, color="#d9edf7", alpha=0.35, linewidth=0)
                auto_fill_labels.append(((start_s + end_s) * 0.5, "Y auto-fill"))
            for start_s, end_s in self._axis_auto_fill_intervals("z"):
                self.ax_pos.axvspan(start_s, end_s, color="#fde2e4", alpha=0.30, linewidth=0)
                auto_fill_labels.append(((start_s + end_s) * 0.5, "Z auto-fill"))

            for boundary in y_boundaries[1:-1]:
                self.ax_pos.axvline(boundary, color="#1f77b4", linestyle="--", alpha=0.25, linewidth=1.0)
            for boundary in z_boundaries[1:-1]:
                self.ax_pos.axvline(boundary, color="#2ca02c", linestyle=":", alpha=0.30, linewidth=1.0)

            def _overlay_selected_segment(
                axis: str,
                boundaries: List[float],
                values: Any,
                color: str,
                label: str,
            ) -> None:
                selected_idx = self._selected_section_index(axis)
                if selected_idx is None:
                    return
                if selected_idx + 1 >= len(boundaries):
                    return
                start_idx = int(round(boundaries[selected_idx] * self.recipe.sample_rate_hz))
                end_idx = int(round(boundaries[selected_idx + 1] * self.recipe.sample_rate_hz))
                n = len(values)
                if n <= 1:
                    return
                start_idx = max(0, min(start_idx, n - 1))
                end_idx = max(start_idx + 1, min(end_idx, n))
                if end_idx - start_idx < 2:
                    return
                seg_t = t[start_idx:end_idx]
                seg_v = values[start_idx:end_idx]
                seg_t_plot, seg_v_plot = self._decimate_for_preview(seg_t, seg_v, max_points=1200)
                self.ax_pos.axvspan(
                    float(seg_t[0]),
                    float(seg_t[-1]),
                    color=color,
                    alpha=0.12,
                    linewidth=0,
                    zorder=2,
                )
                self.ax_pos.plot(
                    seg_t_plot,
                    seg_v_plot,
                    color=color,
                    linewidth=3.6,
                    alpha=1.0,
                    zorder=6,
                    label=label,
                )

            _overlay_selected_segment("y", y_boundaries, y, "#1f77b4", "Y selected section")
            _overlay_selected_segment("z", z_boundaries, z, "#2ca02c", "Z selected section")

            self.ax_pos.set_xlabel("Time (s)")
            self.ax_pos.set_ylabel("Position (m)")
            self.ax_pos.set_title("Position vs Time")
            self.ax_pos.grid(True, alpha=0.25)
            self.ax_pos.legend(loc="upper right")
            for x_center, label in auto_fill_labels:
                self.ax_pos.text(
                    x_center,
                    0.98,
                    label,
                    transform=self.ax_pos.get_xaxis_transform(),
                    ha="center",
                    va="top",
                    fontsize=8,
                    color="#1f4e79",
                )
            self.canvas_pos.draw_idle()

        if render_dynamics:
            vy, vz, ay, az = compute_velocity_acceleration(y, z, self.recipe.sample_rate_hz)
            t_plot, vy_plot, vz_plot, ay_plot, az_plot = self._decimate_for_preview(t, vy, vz, ay, az)
            self.ax_vel.clear()
            self.ax_acc.clear()
            self.ax_vel.plot(t_plot, vy_plot, label="Y velocity", color="#1f77b4", linewidth=1.2)
            self.ax_vel.plot(t_plot, vz_plot, label="Z velocity", color="#2ca02c", linewidth=1.2)
            self.ax_vel.set_ylabel("Velocity (m/s)")
            self.ax_vel.grid(True, alpha=0.25)
            self.ax_vel.legend(loc="upper right")

            self.ax_acc.plot(t_plot, ay_plot, label="Y acceleration", color="#1f77b4", linewidth=1.2)
            self.ax_acc.plot(t_plot, az_plot, label="Z acceleration", color="#2ca02c", linewidth=1.2)
            self.ax_acc.set_xlabel("Time (s)")
            self.ax_acc.set_ylabel("Acceleration (m/s^2)")
            self.ax_acc.grid(True, alpha=0.25)
            self.ax_acc.legend(loc="upper right")
            self.canvas_dyn.draw_idle()

        if render_path:
            y_plot, z_plot = self._decimate_for_preview(y, z)
            self.ax_path.clear()
            self.ax_path.plot(y_plot, z_plot, color="#b2182b", linewidth=1.3, label="Y-Z path")
            self.ax_path.scatter([y[0]], [z[0]], color="#1f77b4", s=30, label="Start")
            self.ax_path.scatter([y[-1]], [z[-1]], color="#2ca02c", s=30, label="End")
            self.ax_path.set_xlabel("Y position (m)")
            self.ax_path.set_ylabel("Z position (m)")
            self.ax_path.set_title("Y-Z Trajectory")
            self.ax_path.grid(True, alpha=0.25)
            self.ax_path.legend(loc="best")
            self.canvas_path.draw_idle()

    def _clear_plots(self, reason: str = "") -> None:
        for ax in (self.ax_pos, self.ax_vel, self.ax_acc, self.ax_path):
            ax.clear()
            if reason:
                ax.text(0.5, 0.5, reason, transform=ax.transAxes, ha="center", va="center")
        self.canvas_pos.draw_idle()
        self.canvas_dyn.draw_idle()
        self.canvas_path.draw_idle()

    def _generate_current_result(self) -> Dict[str, Any]:
        t, y, z, y_boundaries, z_boundaries, generation_issues = generate_trajectory_detailed(self.recipe)
        limits = self._read_limits_config()
        report = evaluate_limits(
            y_values=y,
            z_values=z,
            sample_rate_hz=self.recipe.sample_rate_hz,
            y_boundaries_s=y_boundaries,
            z_boundaries_s=z_boundaries,
            config=limits,
            additional_issues=generation_issues,
        )

        status_changed = self._update_transition_statuses_from_report(report)
        if status_changed:
            t, y, z, y_boundaries, z_boundaries, generation_issues = generate_trajectory_detailed(self.recipe)
            report = evaluate_limits(
                y_values=y,
                z_values=z,
                sample_rate_hz=self.recipe.sample_rate_hz,
                y_boundaries_s=y_boundaries,
                z_boundaries_s=z_boundaries,
                config=limits,
                additional_issues=generation_issues,
            )
            self._update_transition_statuses_from_report(report)

        return {
            "t": t,
            "y": y,
            "z": z,
            "y_boundaries": y_boundaries,
            "z_boundaries": z_boundaries,
            "report": report,
        }

    def _schedule_refresh(self) -> None:
        if self._pending_refresh_id is not None:
            try:
                self.root.after_cancel(self._pending_refresh_id)
            except tk.TclError:
                pass
        self._pending_refresh_id = self.root.after(140, self._refresh_preview)

    def _refresh_preview(self) -> None:
        self._pending_refresh_id = None

        if not self._apply_sample_rate_from_ui(show_popup=False):
            self._last_generated = None
            self._set_warning_report(None)
            self._clear_plots("Invalid sample rate")
            return

        if not self._apply_axis_editor_to_model("y", show_popup=False, refresh_ui=False):
            self._last_generated = None
            self._set_warning_report(None)
            self._clear_plots("Invalid Y section parameters")
            return
        if not self._apply_axis_editor_to_model("z", show_popup=False, refresh_ui=False):
            self._last_generated = None
            self._set_warning_report(None)
            self._clear_plots("Invalid Z section parameters")
            return

        auto_fill_message = self._sync_auto_fill_section()

        try:
            result = self._generate_current_result()
        except ValueError as exc:
            self._last_generated = None
            self._set_warning_report(None)
            self._clear_plots("Preview unavailable")
            self._set_status(str(exc), is_error=True)
            return

        self._last_generated = result
        self._plot_preview(
            t=result["t"],
            y=result["y"],
            z=result["z"],
            y_boundaries=result["y_boundaries"],
            z_boundaries=result["z_boundaries"],
        )
        self._set_warning_report(result["report"])

        y_sel = self._selected_row_info("y")
        z_sel = self._selected_row_info("z")
        self._refresh_axis_tree("y", select=y_sel)
        self._refresh_axis_tree("z", select=z_sel)
        self._load_selected_item_into_editor("y")
        self._load_selected_item_into_editor("z")

        n = len(result["t"])
        duration = float(result["t"][-1]) if n > 1 else 0.0
        warning_count = len(result["report"].issues)
        extra = f" {auto_fill_message}" if auto_fill_message else ""
        if warning_count:
            self._set_status(
                f"Preview updated: {n} samples, duration {duration:.6g}s, warnings {warning_count}.{extra}",
                is_error=False,
            )
        else:
            self._set_status(f"Preview updated: {n} samples, duration {duration:.6g}s.{extra}", is_error=False)

    def _suggest_unique_output_path(self, preferred_name: Optional[str] = None, force_default_dir: bool = False) -> Path:
        name = (preferred_name or DEFAULT_OUTPUT_BASENAME).strip()
        if not name:
            name = DEFAULT_OUTPUT_BASENAME
        candidate = Path(name)
        if candidate.suffix.lower() != ".csv":
            candidate = candidate.with_suffix(".csv")
        if candidate.is_absolute() and not force_default_dir:
            target = candidate
        else:
            target = OUTPUT_DIR / candidate.name
        return resolve_non_overwriting_path(target)

    def _prepare_for_generation(self, show_popup: bool) -> bool:
        if not self._apply_sample_rate_from_ui(show_popup=show_popup):
            return False
        if not self._apply_axis_editor_to_model("y", show_popup=show_popup, refresh_ui=False):
            return False
        if not self._apply_axis_editor_to_model("z", show_popup=show_popup, refresh_ui=False):
            return False
        self._sync_auto_fill_section()
        return True

    def _confirm_warnings_for_export(self, report: ValidationReport) -> bool:
        if not report.issues:
            return True

        lines = [self._format_issue_line(issue) for issue in report.issues[:16]]
        if len(report.issues) > 16:
            lines.append(f"- ... {len(report.issues) - 16} more warning(s)")
        message = "Warnings detected before export:\n\n" + "\n".join(lines) + "\n\nExport anyway?"
        return messagebox.askyesno("Export With Warnings", message, icon="warning")

    def _perform_export(self, path: Path) -> bool:
        if not self._prepare_for_generation(show_popup=True):
            return False

        try:
            result = self._generate_current_result()
        except ValueError as exc:
            self._set_status(str(exc), is_error=True)
            messagebox.showerror("Export Error", str(exc))
            return False

        report: ValidationReport = result["report"]
        if not self._confirm_warnings_for_export(report):
            self._set_status("Export cancelled by user.", is_error=False)
            return False

        rows = build_csv_rows(
            header=self.header,
            t=result["t"],
            y_values=result["y"],
            z_values=result["z"],
            start_utc=datetime.now(timezone.utc),
        )
        write_output_csv(path, self.header, rows)

        self._last_generated = result
        self._set_warning_report(report)
        self._set_status(f"CSV exported: {path}", is_error=False)
        return True

    def _collect_sash_positions(self) -> Dict[str, int]:
        positions: Dict[str, int] = {}

        def read_sash(name: str, pane: Any) -> None:
            if pane is None:
                return
            try:
                positions[name] = int(pane.sashpos(0))
            except Exception:
                return

        read_sash("main", getattr(self, "main_pane", None))
        read_sash("controls", getattr(self, "controls_pane", None))
        read_sash("axes", getattr(self, "axes_pane", None))
        for axis in ("y", "z"):
            pane = self.axis_ui.get(axis, {}).get("axis_pane")
            read_sash(f"axis_{axis}", pane)
        return positions

    def _restore_sash_positions(self, positions: Dict[str, Any]) -> None:
        if not isinstance(positions, dict):
            return

        def set_sash(name: str, pane: Any) -> None:
            raw_value = positions.get(name)
            if pane is None or raw_value is None:
                return
            try:
                pane.sashpos(0, int(raw_value))
            except Exception:
                return

        self.root.update_idletasks()
        set_sash("main", getattr(self, "main_pane", None))
        set_sash("controls", getattr(self, "controls_pane", None))
        set_sash("axes", getattr(self, "axes_pane", None))
        set_sash("axis_y", self.axis_ui.get("y", {}).get("axis_pane"))
        set_sash("axis_z", self.axis_ui.get("z", {}).get("axis_pane"))

    def _suggest_project_path(self) -> Path:
        output_name = self.output_name_var.get().strip() or DEFAULT_OUTPUT_BASENAME
        base = Path(output_name)
        stem = base.stem if base.suffix else base.name
        if not stem:
            stem = "trajectory_project"
        candidate = OUTPUT_DIR / f"{stem}{PROJECT_FILE_EXTENSION}"
        return resolve_non_overwriting_path(candidate)

    @staticmethod
    def _coerce_saved_bool(value: Any) -> bool:
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
        return False

    def _project_payload(self) -> Dict[str, Any]:
        if not self._prepare_for_generation(show_popup=True):
            raise ValueError("Cannot save project because current inputs are invalid.")

        limits_cfg = self._read_limits_config()
        selected_rows = {
            "y": {"type": self._selected_row_info("y")[0], "index": self._selected_row_info("y")[1]},
            "z": {"type": self._selected_row_info("z")[0], "index": self._selected_row_info("z")[1]},
        }
        tab_index = 0
        if hasattr(self, "plot_notebook"):
            try:
                tab_index = int(self.plot_notebook.index(self.plot_notebook.select()))
            except Exception:
                tab_index = 0

        return {
            "schema_version": PROJECT_SCHEMA_VERSION,
            "saved_utc": datetime.now(timezone.utc).isoformat(),
            "recipe": recipe_to_dict(self.recipe),
            "limits": limits_to_dict(limits_cfg),
            "ui": {
                "edit_mode": self.edit_mode_var.get(),
                "sample_rate_text": self.sample_rate_var.get(),
                "output_name": self.output_name_var.get(),
                "window_geometry": self.root.winfo_geometry(),
                "selected_rows": selected_rows,
                "selected_plot_tab": tab_index,
                "sash_positions": self._collect_sash_positions(),
            },
        }

    def _apply_limits_config(self, limits_cfg: LimitsConfig) -> None:
        for axis in ("y", "z"):
            axis_limits = limits_cfg.y if axis == "y" else limits_cfg.z
            vars_for_axis = self.limit_vars[axis]
            vars_for_axis["enable_min_value"].set(axis_limits.enable_min_value)
            vars_for_axis["min_value"].set(f"{axis_limits.min_value:.6g}")
            vars_for_axis["enable_max_value"].set(axis_limits.enable_max_value)
            vars_for_axis["max_value"].set(f"{axis_limits.max_value:.6g}")
            vars_for_axis["enable_max_speed"].set(axis_limits.enable_max_speed)
            vars_for_axis["max_speed"].set(f"{axis_limits.max_speed:.6g}")
            vars_for_axis["enable_max_acceleration"].set(axis_limits.enable_max_acceleration)
            vars_for_axis["max_acceleration"].set(f"{axis_limits.max_acceleration:.6g}")
            vars_for_axis["enable_jump_threshold"].set(axis_limits.enable_jump_threshold)
            vars_for_axis["max_jump"].set(f"{axis_limits.max_jump:.6g}")

    def _apply_project_payload(self, payload: Dict[str, Any], source_path: Path) -> None:
        if not isinstance(payload, dict):
            raise ValueError("Project file root must be an object.")

        schema_version = int(payload.get("schema_version", -1))
        if schema_version != PROJECT_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported project schema_version={schema_version}. "
                f"Expected {PROJECT_SCHEMA_VERSION}."
            )

        recipe = recipe_from_dict(payload.get("recipe", {}))
        limits_cfg = limits_from_dict(payload.get("limits", {}))
        ui_state = payload.get("ui", {})
        if not isinstance(ui_state, dict):
            ui_state = {}

        edit_mode = str(ui_state.get("edit_mode", EDIT_MODE_EASY))
        if edit_mode not in (EDIT_MODE_EASY, EDIT_MODE_EXPERT):
            edit_mode = EDIT_MODE_EASY

        sample_rate_text = str(ui_state.get("sample_rate_text", f"{recipe.sample_rate_hz:.3f}"))
        try:
            float(sample_rate_text)
        except ValueError:
            sample_rate_text = f"{recipe.sample_rate_hz:.3f}"
        output_name = str(ui_state.get("output_name", self.output_name_var.get()))
        geometry = ui_state.get("window_geometry")
        selected_rows = ui_state.get("selected_rows", {})
        if not isinstance(selected_rows, dict):
            selected_rows = {}
        selected_tab_raw = ui_state.get("selected_plot_tab", 0)
        sash_positions = ui_state.get("sash_positions", {})

        self._suspend_events = True
        self.recipe = recipe
        self.edit_mode_var.set(edit_mode)
        self.sample_rate_var.set(sample_rate_text)
        self.sample_rate_scale_var.set(recipe.sample_rate_hz)
        self.output_name_var.set(output_name)
        self._apply_limits_config(limits_cfg)
        self._suspend_events = False

        self._refresh_axis_tree("y", select=("section", 0))
        self._refresh_axis_tree("z", select=("section", 0))

        for axis in ("y", "z"):
            axis_row = selected_rows.get(axis, {})
            if not isinstance(axis_row, dict):
                axis_row = {}
            row_type = str(axis_row.get("type", "section"))
            try:
                row_index = int(axis_row.get("index", 0))
            except (TypeError, ValueError):
                row_index = 0
            if row_type not in ("section", "transition"):
                row_type = "section"
            self._refresh_axis_tree(axis, select=(row_type, row_index))
            self._load_selected_item_into_editor(axis)

        if hasattr(self, "plot_notebook"):
            try:
                selected_tab = int(selected_tab_raw)
            except (TypeError, ValueError):
                selected_tab = 0
            try:
                tabs_count = len(self.plot_notebook.tabs())
                selected_tab = max(0, min(selected_tab, tabs_count - 1))
                self.plot_notebook.select(selected_tab)
            except Exception:
                pass

        if isinstance(geometry, str) and geometry.strip():
            try:
                self.root.geometry(geometry)
            except Exception:
                pass

        self._restore_sash_positions(sash_positions if isinstance(sash_positions, dict) else {})
        self._apply_easy_mode_if_needed()
        self._refresh_preview()

        self.project_path = source_path
        self.project_path_var.set(f"Project: {source_path}")

    def _on_save_project(self) -> None:
        if self.project_path is None:
            suggested = self._suggest_project_path()
            picked = filedialog.asksaveasfilename(
                parent=self.root,
                title="Save Synth Project",
                initialdir=str(suggested.parent),
                initialfile=suggested.name,
                defaultextension=PROJECT_FILE_EXTENSION,
                filetypes=[("Synth project", f"*{PROJECT_FILE_EXTENSION}"), ("JSON", "*.json"), ("All files", "*.*")],
            )
            if not picked:
                return
            target = Path(picked)
            if not str(target).lower().endswith(PROJECT_FILE_EXTENSION):
                target = target.with_name(target.name + PROJECT_FILE_EXTENSION)
            self.project_path = target

        try:
            payload = self._project_payload()
        except ValueError as exc:
            self._set_status(f"Project save failed: {exc}", is_error=True)
            messagebox.showerror("Save Project Error", str(exc))
            return

        assert self.project_path is not None
        self.project_path.parent.mkdir(parents=True, exist_ok=True)
        with self.project_path.open("w", encoding="utf-8") as file:
            json.dump(payload, file, indent=2)

        self.project_path_var.set(f"Project: {self.project_path}")
        self._set_status(f"Project saved: {self.project_path}", is_error=False)

    def _on_load_project(self) -> None:
        picked = filedialog.askopenfilename(
            parent=self.root,
            title="Load Synth Project",
            initialdir=str(OUTPUT_DIR),
            filetypes=[("Synth project", f"*{PROJECT_FILE_EXTENSION}"), ("JSON", "*.json"), ("All files", "*.*")],
        )
        if not picked:
            return

        path = Path(picked)
        try:
            with path.open("r", encoding="utf-8") as file:
                payload = json.load(file)
            self._apply_project_payload(payload, path)
        except Exception as exc:
            self._set_status(f"Project load failed: {exc}", is_error=True)
            messagebox.showerror("Load Project Error", str(exc))
            return

        self._set_status(f"Project loaded: {path}", is_error=False)

    def _on_save_inline(self) -> None:
        target = self._suggest_unique_output_path(self.output_name_var.get(), force_default_dir=True)
        if self._perform_export(target):
            self.output_name_var.set(target.name)

    def _on_save_as(self) -> None:
        suggested = self._suggest_unique_output_path(self.output_name_var.get())
        picked = filedialog.asksaveasfilename(
            parent=self.root,
            title="Save Synthesized MotorData CSV",
            initialdir=str(suggested.parent),
            initialfile=suggested.name,
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if not picked:
            return
        target = Path(picked)
        if target.suffix.lower() != ".csv":
            target = target.with_suffix(".csv")
        target = resolve_non_overwriting_path(target)
        if self._perform_export(target):
            self.output_name_var.set(target.name)

