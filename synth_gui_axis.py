"""Axis editing, section/transition controls, and input parsing mixin."""

from __future__ import annotations

try:
    from synth_gui_shared import *
except ModuleNotFoundError:
    from .synth_gui_shared import *  # type: ignore[no-redef]


class AxisEditorMixin:
    """Owns pipeline tree interactions and axis editor callbacks."""

    def _pipeline_for_axis(self, axis: str):
        return self.recipe.y_pipeline if axis == "y" else self.recipe.z_pipeline

    def _sections_for_axis(self, axis: str) -> List[AxisMotionSection]:
        return self._pipeline_for_axis(axis).sections

    def _transitions_for_axis(self, axis: str) -> List[AxisTransitionConfig]:
        pipeline = self._pipeline_for_axis(axis)
        ensure_pipeline_transitions(pipeline)
        return pipeline.transitions

    def _selected_row_info(self, axis: str) -> Tuple[str, int]:
        ui = self.axis_ui[axis]
        tree: ttk.Treeview = ui["tree"]
        row_map: Dict[str, Tuple[str, int]] = ui["row_map"]
        selected = tree.selection()
        focused = tree.focus()
        if focused and focused in row_map:
            if not selected or focused in selected:
                return row_map[focused]
        if selected:
            for iid in selected:
                if iid in row_map:
                    return row_map[iid]

        stored_type = str(ui.get("selected_type", "none"))
        try:
            stored_index = int(ui.get("selected_index", -1))
        except (TypeError, ValueError):
            stored_index = -1

        if stored_type == "section":
            sections = self._sections_for_axis(axis)
            if 0 <= stored_index < len(sections):
                return "section", stored_index
        elif stored_type == "transition":
            transitions = self._transitions_for_axis(axis)
            if 0 <= stored_index < len(transitions):
                return "transition", stored_index

        return "none", -1

    def _editor_row_info(self, axis: str) -> Tuple[str, int]:
        ui = self.axis_ui[axis]
        stored_type = str(ui.get("selected_type", "none"))
        try:
            stored_index = int(ui.get("selected_index", -1))
        except (TypeError, ValueError):
            stored_index = -1

        if stored_type == "section":
            sections = self._sections_for_axis(axis)
            if 0 <= stored_index < len(sections):
                return "section", stored_index
        elif stored_type == "transition":
            transitions = self._transitions_for_axis(axis)
            if 0 <= stored_index < len(transitions):
                return "transition", stored_index
        return "none", -1

    def _consume_skip_focus_commit(self, axis: str) -> bool:
        ui = self.axis_ui[axis]
        if bool(ui.get("skip_focus_commit", False)):
            ui["skip_focus_commit"] = False
            return True
        return False

    def _clear_axis_selection(self, axis: str) -> None:
        ui = self.axis_ui[axis]
        tree: ttk.Treeview = ui["tree"]
        selected = tree.selection()
        if selected:
            tree.selection_remove(*selected)
        tree.focus("")
        ui["selected_type"] = "none"
        ui["selected_index"] = -1

    def _on_axis_tree_click(self, axis: str, event: tk.Event) -> Optional[str]:
        ui = self.axis_ui[axis]
        tree: ttk.Treeview = ui["tree"]
        clicked_iid = tree.identify_row(event.y)
        if clicked_iid:
            if not self._suspend_events:
                self._apply_axis_editor_to_model(axis, show_popup=False, refresh_ui=False)
            ui["skip_focus_commit"] = True
            return None

        self._clear_axis_selection(axis)
        self._load_selected_item_into_editor(axis)
        refresh_fn = getattr(self, "_refresh_selection_highlight", None)
        if callable(refresh_fn):
            refresh_fn()
        return "break"

    def _selected_section_index_for_actions(self, axis: str) -> int:
        row_type, index = self._selected_row_info(axis)
        sections = self._sections_for_axis(axis)
        if row_type == "none":
            return max(0, len(sections) - 1)
        if row_type == "section":
            idx = min(max(index, 0), max(0, len(sections) - 1))
            if sections and sections[idx].is_auto_fill:
                return max(0, idx - 1)
            return idx
        return min(max(index + 1, 0), max(0, len(sections) - 1))

    def _selected_section_indices(self, axis: str, include_auto_fill: bool = False) -> List[int]:
        ui = self.axis_ui[axis]
        tree: ttk.Treeview = ui["tree"]
        row_map: Dict[str, Tuple[str, int]] = ui["row_map"]
        sections = self._sections_for_axis(axis)

        selected_indices: List[int] = []
        for iid in tree.selection():
            row = row_map.get(iid)
            if not row:
                continue
            row_type, row_index = row
            if row_type != "section":
                continue
            if 0 <= row_index < len(sections):
                if include_auto_fill or not sections[row_index].is_auto_fill:
                    selected_indices.append(row_index)

        if not selected_indices:
            row_type, row_index = self._selected_row_info(axis)
            if row_type == "section" and 0 <= row_index < len(sections):
                if include_auto_fill or not sections[row_index].is_auto_fill:
                    selected_indices.append(row_index)

        return sorted(set(selected_indices))

    @staticmethod
    def _clone_section_without_auto_fill(section: AxisMotionSection) -> AxisMotionSection:
        return AxisMotionSection(
            duration_s=float(section.duration_s),
            params=AxisSectionParams(**vars(section.params)),
            is_auto_fill=False,
        )

    def _copy_axis_sections(self, axis: str) -> None:
        indices = self._selected_section_indices(axis, include_auto_fill=False)
        sections = self._sections_for_axis(axis)
        if not indices:
            self._set_status(f"{axis.upper()}: select one or more sections to copy.", is_error=False)
            return

        copied: List[AxisMotionSection] = []
        skipped_auto_fill = 0
        for idx in indices:
            if sections[idx].is_auto_fill:
                skipped_auto_fill += 1
                continue
            copied.append(self._clone_section_without_auto_fill(sections[idx]))

        if not copied:
            self._set_status(f"{axis.upper()}: auto-fill sections cannot be copied.", is_error=False)
            return

        self.section_clipboard = copied
        extra = f" (skipped {skipped_auto_fill} auto-fill)" if skipped_auto_fill else ""
        self._set_status(f"Copied {len(copied)} section(s) from {axis.upper()}{extra}.", is_error=False)

    def _paste_axis_sections(self, axis: str) -> None:
        clipboard = list(getattr(self, "section_clipboard", []))
        if not clipboard:
            self._set_status("Clipboard is empty. Copy section(s) first.", is_error=False)
            return

        sections = self._sections_for_axis(axis)
        if not sections:
            insert_index = 0
        else:
            insert_index = self._selected_section_index_for_actions(axis) + 1
            insert_index = min(max(insert_index, 0), len(sections))

        pasted = [self._clone_section_without_auto_fill(section) for section in clipboard]
        for offset, section in enumerate(pasted):
            sections.insert(insert_index + offset, section)

        ensure_pipeline_transitions(self._pipeline_for_axis(axis))
        if self.edit_mode_var.get() == EDIT_MODE_EASY:
            apply_easy_mode_continuity(sections, self.recipe.sample_rate_hz)

        self._refresh_axis_tree(axis, select=("section", insert_index))
        self._load_selected_item_into_editor(axis)
        self._schedule_refresh()
        self._set_status(f"Pasted {len(pasted)} section(s) into {axis.upper()}.", is_error=False)

    def _on_axis_copy_shortcut(self, axis: str) -> str:
        self._copy_axis_sections(axis)
        return "break"

    def _on_axis_paste_shortcut(self, axis: str) -> str:
        self._paste_axis_sections(axis)
        return "break"

    def _refresh_axis_tree(self, axis: str, select: Optional[Tuple[str, int]] = None) -> None:
        ui = self.axis_ui[axis]
        tree: ttk.Treeview = ui["tree"]
        sections = self._sections_for_axis(axis)
        transitions = self._transitions_for_axis(axis)
        row_map: Dict[str, Tuple[str, int]] = {}

        if select is None:
            select = self._selected_row_info(axis)

        for item in tree.get_children():
            tree.delete(item)

        for idx, section in enumerate(sections):
            sid = f"s{idx}"
            section_label = f"S{idx + 1}"
            section_details = section.params.mode
            section_tags: Tuple[str, ...] = ()
            if section.is_auto_fill:
                section_label = f"S{idx + 1} (auto)"
                section_details = f"{section.params.mode} (auto-fill suggestion)"
                section_tags = (TREE_TAG_AUTO_FILL_SECTION,)
            tree.insert(
                "",
                "end",
                iid=sid,
                values=(section_label, f"{section.duration_s:.4f}", section_details),
                tags=section_tags,
            )
            row_map[sid] = ("section", idx)

            if idx < len(transitions):
                transition = transitions[idx]
                tid = f"t{idx}"
                mark = "\u2611" if transition.enabled else "\u2610"
                details = f"{mark} smoothen transition [{transition.eat_away_mode}]"
                tag = TREE_TAG_TRANSITION_ACTIVE if transition.status == TRANSITION_STATUS_ACTIVE else TREE_TAG_TRANSITION_RESOLVED
                tree.insert(
                    "",
                    "end",
                    iid=tid,
                    values=("\u21b3", f"{transition.duration_s:.4f}", details),
                    tags=(tag,),
                )
                row_map[tid] = ("transition", idx)

        ui["row_map"] = row_map
        total_duration = sum(section.duration_s for section in sections)
        ui["total_var"].set(f"{total_duration:.4f} s ({len(sections)} sections)")

        if not row_map:
            ui["selected_type"] = "none"
            ui["selected_index"] = -1
            return

        target_iid: Optional[str] = None
        target_type, target_idx = select
        if target_type == "none":
            self._clear_axis_selection(axis)
            return
        for iid, (row_type, row_idx) in row_map.items():
            if row_type == target_type and row_idx == target_idx:
                target_iid = iid
                break
        if target_iid is None:
            target_iid = next(iter(row_map.keys()))

        tree.selection_set(target_iid)
        tree.focus(target_iid)
        ui["selected_type"], ui["selected_index"] = row_map[target_iid]

    def _show_section_editor(self, axis: str) -> None:
        ui = self.axis_ui[axis]
        ui["transition_editor"].grid_remove()
        ui["section_editor"].grid()

    def _show_transition_editor(self, axis: str) -> None:
        ui = self.axis_ui[axis]
        ui["section_editor"].grid_remove()
        ui["transition_editor"].grid()

    def _load_selected_item_into_editor(self, axis: str) -> None:
        row_type, row_index = self._selected_row_info(axis)
        ui = self.axis_ui[axis]
        ui["selected_type"] = row_type
        ui["selected_index"] = row_index

        if row_type == "none":
            return

        if row_type == "transition":
            self._show_transition_editor(axis)
            self._load_transition_into_editor(axis, row_index)
        else:
            self._show_section_editor(axis)
            self._load_section_into_editor(axis, row_index)

    def _load_section_into_editor(self, axis: str, section_index: int) -> None:
        sections = self._sections_for_axis(axis)
        if not sections:
            return
        section_index = min(max(section_index, 0), len(sections) - 1)
        section = sections[section_index]
        params = section.params
        ui = self.axis_ui[axis]

        self._suspend_events = True
        ui["duration_var"].set(f"{section.duration_s:.6f}")
        ui["duration_scale_var"].set(max(0.05, min(30.0, section.duration_s)))
        ui["mode_var"].set(params.mode)
        ui["constant_var"].set(f"{params.constant_value:.6f}")
        ui["amplitude_var"].set(f"{params.amplitude:.6f}")
        ui["amplitude_scale_var"].set(max(0.0, min(0.5, params.amplitude)))
        ui["offset_var"].set(f"{params.offset:.6f}")
        ui["phase_var"].set(f"{params.phase_deg:.6f}")
        ui["frequency_var"].set(f"{params.frequency_hz:.6f}")
        ui["sweep_type_var"].set(params.sweep_type)
        ui["sweep_start_var"].set(f"{params.sweep_start_hz:.6f}")
        ui["sweep_end_var"].set(f"{params.sweep_end_hz:.6f}")
        ui["sweep_accel_star_var"].set(f"{params.sweep_accel_star:.6f}")
        ui["s_curve_start_var"].set(f"{params.s_curve_start:.6f}")
        ui["s_curve_end_var"].set(f"{params.s_curve_end:.6f}")
        ui["s_curve_max_speed_var"].set(f"{params.s_curve_max_speed:.6f}")
        ui["s_curve_max_acceleration_var"].set(f"{params.s_curve_max_acceleration:.6f}")
        ui["s_curve_max_jerk_var"].set(f"{params.s_curve_max_jerk:.6f}")
        ui["ramp_start_var"].set(f"{params.ramp_start:.6f}")
        ui["ramp_end_var"].set(f"{params.ramp_end:.6f}")
        if section.duration_s > 0:
            ramp_speed = (params.ramp_end - params.ramp_start) / section.duration_s
        else:
            ramp_speed = params.ramp_speed_mps
        ui["ramp_speed_var"].set(f"{ramp_speed:.6f}")
        ui["ramp_lock_speed_var"].set(bool(params.ramp_lock_speed))
        ui["multisine_components_var"].set(str(params.multisine_components))
        ui["secondary_enabled_var"].set(bool(params.secondary_enabled))
        ui["secondary_mode_var"].set(params.secondary_mode)
        ui["secondary_constant_var"].set(f"{params.secondary_constant_value:.6f}")
        ui["secondary_amplitude_var"].set(f"{params.secondary_amplitude:.6f}")
        ui["secondary_offset_var"].set(f"{params.secondary_offset:.6f}")
        ui["secondary_phase_var"].set(f"{params.secondary_phase_deg:.6f}")
        ui["secondary_frequency_var"].set(f"{params.secondary_frequency_hz:.6f}")
        ui["secondary_sweep_type_var"].set(params.secondary_sweep_type)
        ui["secondary_sweep_start_var"].set(f"{params.secondary_sweep_start_hz:.6f}")
        ui["secondary_sweep_end_var"].set(f"{params.secondary_sweep_end_hz:.6f}")
        ui["secondary_sweep_accel_star_var"].set(f"{params.secondary_sweep_accel_star:.6f}")
        ui["secondary_s_curve_start_var"].set(f"{params.secondary_s_curve_start:.6f}")
        ui["secondary_s_curve_end_var"].set(f"{params.secondary_s_curve_end:.6f}")
        ui["secondary_s_curve_max_speed_var"].set(f"{params.secondary_s_curve_max_speed:.6f}")
        ui["secondary_s_curve_max_acceleration_var"].set(f"{params.secondary_s_curve_max_acceleration:.6f}")
        ui["secondary_s_curve_max_jerk_var"].set(f"{params.secondary_s_curve_max_jerk:.6f}")
        ui["secondary_ramp_start_var"].set(f"{params.secondary_ramp_start:.6f}")
        ui["secondary_ramp_end_var"].set(f"{params.secondary_ramp_end:.6f}")
        ui["secondary_multisine_components_var"].set(str(params.secondary_multisine_components))
        self._suspend_events = False

        self._update_axis_editor_visibility(axis)

    def _load_transition_into_editor(self, axis: str, transition_index: int) -> None:
        transitions = self._transitions_for_axis(axis)
        if not transitions:
            return
        transition_index = min(max(transition_index, 0), len(transitions) - 1)
        transition = transitions[transition_index]
        ui = self.axis_ui[axis]

        self._suspend_events = True
        ui["transition_enabled_var"].set(bool(transition.enabled))
        ui["transition_duration_var"].set(f"{transition.duration_s:.6f}")
        ui["transition_eat_var"].set(transition.eat_away_mode)
        ui["transition_info_var"].set(
            f"Boundary {transition_index + 1} - status: {transition.status}, auto_added: {transition.auto_added}"
        )
        self._suspend_events = False

        easy = self.edit_mode_var.get() == EDIT_MODE_EASY
        ui["transition_duration_entry"].configure(state="disabled" if easy else "normal")
        ui["transition_eat_combo"].configure(state="disabled" if easy else "readonly")
        ui["transition_check"].configure(state="normal")

    def _update_axis_editor_visibility(self, axis: str) -> None:
        ui = self.axis_ui[axis]
        mode = str(ui["mode_var"].get()).strip().lower()
        secondary_mode = str(ui["secondary_mode_var"].get()).strip().lower()
        secondary_enabled = bool(ui["secondary_enabled_var"].get())
        rows: Dict[str, Dict[str, Any]] = ui["rows"]
        mode_combo: ttk.Combobox = ui["mode_combo"]
        secondary_check: ttk.Checkbutton = ui["secondary_check"]
        secondary_mode_combo: ttk.Combobox = ui["secondary_mode_combo"]
        secondary_mode_row: ttk.Frame = ui["secondary_mode_row"]
        secondary_enabled_row: ttk.Frame = ui["secondary_enabled_row"]
        ramp_lock_row: ttk.Frame = ui["ramp_lock_row"]
        ramp_lock_check: ttk.Checkbutton = ui["ramp_lock_check"]

        visible_primary_by_mode = {
            MODE_CONSTANT: {"constant_value"},
            MODE_RAMP: {"ramp_start", "ramp_end", "ramp_speed"},
            MODE_SINE: {"amplitude", "offset", "phase_deg", "frequency_hz"},
            MODE_S_CURVE: {
                "s_curve_start",
                "s_curve_end",
                "s_curve_max_speed",
                "s_curve_max_acceleration",
                "s_curve_max_jerk",
            },
            MODE_SWEEP: {
                "amplitude",
                "offset",
                "phase_deg",
                "sweep_type",
                "sweep_start_hz",
                "sweep_end_hz",
                "sweep_accel_star",
            },
            MODE_MULTISINE: {"offset", "multisine_components"},
        }
        visible_secondary_by_mode = {
            MODE_CONSTANT: {"secondary_constant_value"},
            MODE_RAMP: {"secondary_ramp_start", "secondary_ramp_end"},
            MODE_SINE: {"secondary_amplitude", "secondary_offset", "secondary_phase_deg", "secondary_frequency_hz"},
            MODE_SWEEP: {
                "secondary_amplitude",
                "secondary_offset",
                "secondary_phase_deg",
                "secondary_sweep_type",
                "secondary_sweep_start_hz",
                "secondary_sweep_end_hz",
                "secondary_sweep_accel_star",
            },
            MODE_S_CURVE: {
                "secondary_s_curve_start",
                "secondary_s_curve_end",
                "secondary_s_curve_max_speed",
                "secondary_s_curve_max_acceleration",
                "secondary_s_curve_max_jerk",
            },
            MODE_MULTISINE: {"secondary_offset", "secondary_multisine_components"},
        }
        visible_primary = visible_primary_by_mode.get(mode, set())
        visible_secondary = visible_secondary_by_mode.get(secondary_mode, set()) if secondary_enabled else set()
        visible = visible_primary.union(visible_secondary)

        sections = self._sections_for_axis(axis)
        selected_auto_fill = False
        secondary_enabled_row.grid()
        if secondary_enabled:
            secondary_mode_row.grid()
        else:
            secondary_mode_row.grid_remove()
        if mode == MODE_RAMP:
            ramp_lock_row.grid()
        else:
            ramp_lock_row.grid_remove()
        for key, meta in rows.items():
            frame = meta["frame"]
            if key in visible:
                frame.grid()
            else:
                frame.grid_remove()

        lock_field = None
        row_type, row_index = self._editor_row_info(axis)
        if row_type == "section" and 0 <= row_index < len(sections):
            selected_auto_fill = sections[row_index].is_auto_fill
        if not selected_auto_fill and self.edit_mode_var.get() == EDIT_MODE_EASY and row_type == "section" and row_index > 0:
            if secondary_enabled:
                if secondary_mode == MODE_CONSTANT:
                    lock_field = "secondary_constant_value"
                elif secondary_mode == MODE_RAMP:
                    lock_field = "secondary_ramp_start"
                elif secondary_mode == MODE_S_CURVE:
                    lock_field = "secondary_s_curve_start"
                elif secondary_mode in (MODE_SINE, MODE_SWEEP, MODE_MULTISINE):
                    lock_field = "secondary_offset"
            else:
                if mode == MODE_CONSTANT:
                    lock_field = "constant_value"
                elif mode == MODE_RAMP:
                    lock_field = "ramp_start"
                elif mode == MODE_S_CURVE:
                    lock_field = "s_curve_start"
                elif mode in (MODE_SINE, MODE_SWEEP, MODE_MULTISINE):
                    lock_field = "offset"

        for key, meta in rows.items():
            entry: ttk.Entry = meta["entry"]
            label: ttk.Label = meta["label"]
            scale = meta["scale"]

            if key not in visible:
                entry.configure(state="disabled")
                if scale is not None:
                    scale.configure(state="disabled")
                label.configure(foreground="#777777")
                continue

            if selected_auto_fill:
                state = "readonly"
            else:
                state = "readonly" if key == lock_field else "normal"
            if key in {"sweep_type", "secondary_sweep_type"} and state == "normal":
                state = "readonly"
            entry.configure(state=state)
            if scale is not None:
                scale.configure(state="normal" if state == "normal" else "disabled")
            if selected_auto_fill:
                label.configure(foreground="#1f4e79")
            else:
                label.configure(foreground="#555555" if state == "readonly" else "black")

        secondary_check.configure(state="disabled" if selected_auto_fill else "normal")
        if mode == MODE_RAMP:
            ramp_lock_check.configure(state="disabled" if selected_auto_fill else "normal")
        else:
            ramp_lock_check.configure(state="disabled")
        if selected_auto_fill:
            secondary_mode_combo.configure(state="disabled")
        else:
            secondary_mode_combo.configure(state="readonly" if secondary_enabled else "disabled")
        ui["duration_entry"].configure(state="readonly" if selected_auto_fill else "normal")
        mode_combo.configure(state="disabled" if selected_auto_fill else "readonly")

    def _parse_float(self, label: str, text: str) -> float:
        try:
            value = float(text)
        except ValueError as exc:
            raise ValueError(f"{label} must be numeric.") from exc
        if not (value == value):
            raise ValueError(f"{label} cannot be NaN.")
        if value == float("inf") or value == float("-inf"):
            raise ValueError(f"{label} must be finite.")
        return value

    def _parse_sweep_type(self, label: str, text: str) -> str:
        value = str(text).strip().lower()
        if value not in (SWEEP_TYPE_LINEAR, SWEEP_TYPE_LOG):
            raise ValueError(
                f"{label} must be '{SWEEP_TYPE_LINEAR}' or '{SWEEP_TYPE_LOG}'."
            )
        return value

    def _apply_ramp_speed_coupling(self, axis: str, changed_field: str) -> None:
        ui = self.axis_ui[axis]
        mode = str(ui["mode_var"].get()).strip().lower()
        if mode != MODE_RAMP:
            return

        try:
            duration = float(str(ui["duration_var"].get()).strip())
            start = float(str(ui["ramp_start_var"].get()).strip())
            end = float(str(ui["ramp_end_var"].get()).strip())
            speed = float(str(ui["ramp_speed_var"].get()).strip())
        except ValueError:
            return

        if duration <= 0:
            return

        lock_speed = bool(ui["ramp_lock_speed_var"].get())

        if lock_speed:
            if changed_field == "ramp_end":
                if abs(speed) < 1e-12:
                    return
                auto_duration = (end - start) / speed
                if auto_duration <= 0:
                    return
                self._suspend_events = True
                ui["duration_var"].set(f"{auto_duration:.6f}")
                ui["duration_scale_var"].set(max(0.05, min(30.0, auto_duration)))
                self._suspend_events = False
                return

            adjusted_end = start + speed * duration
            self._suspend_events = True
            ui["ramp_end_var"].set(f"{adjusted_end:.6f}")
            self._suspend_events = False
            return

        if changed_field != "ramp_speed":
            computed_speed = (end - start) / duration
            self._suspend_events = True
            ui["ramp_speed_var"].set(f"{computed_speed:.6f}")
            self._suspend_events = False

    def _read_section_editor(self, axis: str) -> AxisMotionSection:
        ui = self.axis_ui[axis]
        axis_label = axis.upper()

        duration_s = self._parse_float(f"{axis_label} duration", ui["duration_var"].get())
        if duration_s <= 0:
            raise ValueError(f"{axis_label}: duration must be > 0.")

        mode = str(ui["mode_var"].get()).strip().lower()
        row_type, row_index = self._editor_row_info(axis)
        sections = self._sections_for_axis(axis)
        if row_type == "section" and 0 <= row_index < len(sections):
            params = AxisSectionParams(**vars(sections[row_index].params))
        else:
            params = AxisSectionParams()
        params.mode = mode
        if mode == MODE_CONSTANT:
            params.constant_value = self._parse_float(f"{axis_label} constant value", ui["constant_var"].get())
        elif mode == MODE_RAMP:
            params.ramp_start = self._parse_float(f"{axis_label} ramp start", ui["ramp_start_var"].get())
            params.ramp_end = self._parse_float(f"{axis_label} ramp end", ui["ramp_end_var"].get())
            params.ramp_speed_mps = self._parse_float(f"{axis_label} ramp speed", ui["ramp_speed_var"].get())
            params.ramp_lock_speed = bool(ui["ramp_lock_speed_var"].get())
            if not params.ramp_lock_speed and duration_s > 0:
                params.ramp_speed_mps = (params.ramp_end - params.ramp_start) / duration_s
            if params.ramp_lock_speed and abs(params.ramp_speed_mps) < 1e-12 and abs(params.ramp_end - params.ramp_start) > 1e-12:
                raise ValueError(f"{axis_label}: with locked speed = 0, ramp start and end must be equal.")
        elif mode == MODE_SINE:
            params.amplitude = self._parse_float(f"{axis_label} amplitude", ui["amplitude_var"].get())
            params.offset = self._parse_float(f"{axis_label} offset", ui["offset_var"].get())
            params.phase_deg = self._parse_float(f"{axis_label} phase", ui["phase_var"].get())
            params.frequency_hz = self._parse_float(f"{axis_label} frequency", ui["frequency_var"].get())
            if params.amplitude < 0:
                raise ValueError(f"{axis_label}: amplitude cannot be negative.")
            if params.frequency_hz < 0:
                raise ValueError(f"{axis_label}: frequency cannot be negative.")
        elif mode == MODE_SWEEP:
            params.amplitude = self._parse_float(f"{axis_label} amplitude", ui["amplitude_var"].get())
            params.offset = self._parse_float(f"{axis_label} offset", ui["offset_var"].get())
            params.phase_deg = self._parse_float(f"{axis_label} phase", ui["phase_var"].get())
            params.sweep_type = self._parse_sweep_type(f"{axis_label} sweep type", ui["sweep_type_var"].get())
            params.sweep_start_hz = self._parse_float(f"{axis_label} sweep start", ui["sweep_start_var"].get())
            params.sweep_end_hz = self._parse_float(f"{axis_label} sweep end", ui["sweep_end_var"].get())
            params.sweep_accel_star = self._parse_float(f"{axis_label} sweep a*", ui["sweep_accel_star_var"].get())
            if params.amplitude < 0:
                raise ValueError(f"{axis_label}: amplitude cannot be negative.")
            if params.sweep_start_hz < 0 or params.sweep_end_hz < 0:
                raise ValueError(f"{axis_label}: sweep frequencies cannot be negative.")
            if params.sweep_accel_star < 0:
                raise ValueError(f"{axis_label}: sweep a* cannot be negative.")
            if params.sweep_type == SWEEP_TYPE_LOG and (params.sweep_start_hz <= 0 or params.sweep_end_hz <= 0):
                raise ValueError(f"{axis_label}: logarithmic sweep requires start/end frequencies > 0.")
        elif mode == MODE_S_CURVE:
            params.s_curve_start = self._parse_float(f"{axis_label} S-curve start", ui["s_curve_start_var"].get())
            params.s_curve_end = self._parse_float(f"{axis_label} S-curve end", ui["s_curve_end_var"].get())
            params.s_curve_max_speed = self._parse_float(
                f"{axis_label} S-curve max speed",
                ui["s_curve_max_speed_var"].get(),
            )
            params.s_curve_max_acceleration = self._parse_float(
                f"{axis_label} S-curve max acceleration",
                ui["s_curve_max_acceleration_var"].get(),
            )
            params.s_curve_max_jerk = self._parse_float(
                f"{axis_label} S-curve max jerk",
                ui["s_curve_max_jerk_var"].get(),
            )
            if params.s_curve_max_speed <= 0:
                raise ValueError(f"{axis_label}: S-curve max speed must be > 0.")
            if params.s_curve_max_acceleration <= 0:
                raise ValueError(f"{axis_label}: S-curve max acceleration must be > 0.")
            if params.s_curve_max_jerk <= 0:
                raise ValueError(f"{axis_label}: S-curve max jerk must be > 0.")
            delta = abs(params.s_curve_end - params.s_curve_start)
            required_speed = delta * 1.875 / duration_s
            required_acceleration = delta * 5.773502691896258 / (duration_s * duration_s)
            required_jerk = delta * 60.0 / (duration_s * duration_s * duration_s)
            if required_speed > params.s_curve_max_speed + 1e-12:
                raise ValueError(
                    f"{axis_label}: S-curve requires peak speed {required_speed:.6g} m/s "
                    f"(limit {params.s_curve_max_speed:.6g} m/s)."
                )
            if required_acceleration > params.s_curve_max_acceleration + 1e-12:
                raise ValueError(
                    f"{axis_label}: S-curve requires peak acceleration {required_acceleration:.6g} m/s^2 "
                    f"(limit {params.s_curve_max_acceleration:.6g} m/s^2)."
                )
            if required_jerk > params.s_curve_max_jerk + 1e-12:
                raise ValueError(
                    f"{axis_label}: S-curve requires peak jerk {required_jerk:.6g} m/s^3 "
                    f"(limit {params.s_curve_max_jerk:.6g} m/s^3)."
                )
        elif mode == MODE_MULTISINE:
            params.offset = self._parse_float(f"{axis_label} offset", ui["offset_var"].get())
            params.multisine_components = str(ui["multisine_components_var"].get()).strip()
            if not params.multisine_components:
                raise ValueError(
                    f"{axis_label}: multisine components cannot be empty "
                    "(format: amplitude,frequency_hz,phase_deg; ...)."
                )
        else:
            raise ValueError(f"{axis_label}: invalid mode '{mode}'.")

        params.secondary_enabled = bool(ui["secondary_enabled_var"].get())
        params.secondary_mode = str(ui["secondary_mode_var"].get()).strip().lower()
        if params.secondary_enabled:
            secondary_mode = params.secondary_mode
            if secondary_mode == MODE_CONSTANT:
                params.secondary_constant_value = self._parse_float(
                    f"{axis_label} secondary constant value",
                    ui["secondary_constant_var"].get(),
                )
            elif secondary_mode == MODE_RAMP:
                params.secondary_ramp_start = self._parse_float(
                    f"{axis_label} secondary ramp start",
                    ui["secondary_ramp_start_var"].get(),
                )
                params.secondary_ramp_end = self._parse_float(
                    f"{axis_label} secondary ramp end",
                    ui["secondary_ramp_end_var"].get(),
                )
            elif secondary_mode == MODE_SINE:
                params.secondary_amplitude = self._parse_float(
                    f"{axis_label} secondary amplitude",
                    ui["secondary_amplitude_var"].get(),
                )
                params.secondary_offset = self._parse_float(
                    f"{axis_label} secondary offset",
                    ui["secondary_offset_var"].get(),
                )
                params.secondary_phase_deg = self._parse_float(
                    f"{axis_label} secondary phase",
                    ui["secondary_phase_var"].get(),
                )
                params.secondary_frequency_hz = self._parse_float(
                    f"{axis_label} secondary frequency",
                    ui["secondary_frequency_var"].get(),
                )
                if params.secondary_amplitude < 0:
                    raise ValueError(f"{axis_label}: secondary amplitude cannot be negative.")
                if params.secondary_frequency_hz < 0:
                    raise ValueError(f"{axis_label}: secondary frequency cannot be negative.")
            elif secondary_mode == MODE_SWEEP:
                params.secondary_amplitude = self._parse_float(
                    f"{axis_label} secondary amplitude",
                    ui["secondary_amplitude_var"].get(),
                )
                params.secondary_offset = self._parse_float(
                    f"{axis_label} secondary offset",
                    ui["secondary_offset_var"].get(),
                )
                params.secondary_phase_deg = self._parse_float(
                    f"{axis_label} secondary phase",
                    ui["secondary_phase_var"].get(),
                )
                params.secondary_sweep_type = self._parse_sweep_type(
                    f"{axis_label} secondary sweep type",
                    ui["secondary_sweep_type_var"].get(),
                )
                params.secondary_sweep_start_hz = self._parse_float(
                    f"{axis_label} secondary sweep start",
                    ui["secondary_sweep_start_var"].get(),
                )
                params.secondary_sweep_end_hz = self._parse_float(
                    f"{axis_label} secondary sweep end",
                    ui["secondary_sweep_end_var"].get(),
                )
                params.secondary_sweep_accel_star = self._parse_float(
                    f"{axis_label} secondary sweep a*",
                    ui["secondary_sweep_accel_star_var"].get(),
                )
                if params.secondary_amplitude < 0:
                    raise ValueError(f"{axis_label}: secondary amplitude cannot be negative.")
                if params.secondary_sweep_start_hz < 0 or params.secondary_sweep_end_hz < 0:
                    raise ValueError(f"{axis_label}: secondary sweep frequencies cannot be negative.")
                if params.secondary_sweep_accel_star < 0:
                    raise ValueError(f"{axis_label}: secondary sweep a* cannot be negative.")
                if params.secondary_sweep_type == SWEEP_TYPE_LOG and (
                    params.secondary_sweep_start_hz <= 0 or params.secondary_sweep_end_hz <= 0
                ):
                    raise ValueError(f"{axis_label}: secondary logarithmic sweep requires start/end frequencies > 0.")
            elif secondary_mode == MODE_S_CURVE:
                params.secondary_s_curve_start = self._parse_float(
                    f"{axis_label} secondary S-curve start",
                    ui["secondary_s_curve_start_var"].get(),
                )
                params.secondary_s_curve_end = self._parse_float(
                    f"{axis_label} secondary S-curve end",
                    ui["secondary_s_curve_end_var"].get(),
                )
                params.secondary_s_curve_max_speed = self._parse_float(
                    f"{axis_label} secondary S-curve max speed",
                    ui["secondary_s_curve_max_speed_var"].get(),
                )
                params.secondary_s_curve_max_acceleration = self._parse_float(
                    f"{axis_label} secondary S-curve max acceleration",
                    ui["secondary_s_curve_max_acceleration_var"].get(),
                )
                params.secondary_s_curve_max_jerk = self._parse_float(
                    f"{axis_label} secondary S-curve max jerk",
                    ui["secondary_s_curve_max_jerk_var"].get(),
                )
                if params.secondary_s_curve_max_speed <= 0:
                    raise ValueError(f"{axis_label}: secondary S-curve max speed must be > 0.")
                if params.secondary_s_curve_max_acceleration <= 0:
                    raise ValueError(f"{axis_label}: secondary S-curve max acceleration must be > 0.")
                if params.secondary_s_curve_max_jerk <= 0:
                    raise ValueError(f"{axis_label}: secondary S-curve max jerk must be > 0.")
                secondary_delta = abs(params.secondary_s_curve_end - params.secondary_s_curve_start)
                required_secondary_speed = secondary_delta * 1.875 / duration_s
                required_secondary_acceleration = secondary_delta * 5.773502691896258 / (duration_s * duration_s)
                required_secondary_jerk = secondary_delta * 60.0 / (duration_s * duration_s * duration_s)
                if required_secondary_speed > params.secondary_s_curve_max_speed + 1e-12:
                    raise ValueError(
                        f"{axis_label}: secondary S-curve requires peak speed {required_secondary_speed:.6g} m/s "
                        f"(limit {params.secondary_s_curve_max_speed:.6g} m/s)."
                    )
                if required_secondary_acceleration > params.secondary_s_curve_max_acceleration + 1e-12:
                    raise ValueError(
                        f"{axis_label}: secondary S-curve requires peak acceleration {required_secondary_acceleration:.6g} m/s^2 "
                        f"(limit {params.secondary_s_curve_max_acceleration:.6g} m/s^2)."
                    )
                if required_secondary_jerk > params.secondary_s_curve_max_jerk + 1e-12:
                    raise ValueError(
                        f"{axis_label}: secondary S-curve requires peak jerk {required_secondary_jerk:.6g} m/s^3 "
                        f"(limit {params.secondary_s_curve_max_jerk:.6g} m/s^3)."
                    )
            elif secondary_mode == MODE_MULTISINE:
                params.secondary_offset = self._parse_float(
                    f"{axis_label} secondary offset",
                    ui["secondary_offset_var"].get(),
                )
                params.secondary_multisine_components = str(ui["secondary_multisine_components_var"].get()).strip()
                if not params.secondary_multisine_components:
                    raise ValueError(
                        f"{axis_label}: secondary multisine components cannot be empty "
                        "(format: amplitude,frequency_hz,phase_deg; ...)."
                    )
            else:
                raise ValueError(f"{axis_label}: invalid secondary mode '{secondary_mode}'.")

        return AxisMotionSection(duration_s=duration_s, params=params)

    def _read_transition_editor(self, axis: str) -> AxisTransitionConfig:
        ui = self.axis_ui[axis]
        axis_label = axis.upper()
        duration = self._parse_float(f"{axis_label} transition duration", ui["transition_duration_var"].get())
        if duration < 0:
            raise ValueError(f"{axis_label}: transition duration cannot be negative.")
        eat_mode = str(ui["transition_eat_var"].get()).strip().lower()
        if eat_mode not in (EAT_AWAY_LEFT, EAT_AWAY_RIGHT, EAT_AWAY_BOTH):
            raise ValueError(f"{axis_label}: invalid eat-away mode '{eat_mode}'.")
        return AxisTransitionConfig(
            enabled=bool(ui["transition_enabled_var"].get()),
            duration_s=duration,
            eat_away_mode=eat_mode,
        )

    def _apply_axis_editor_to_model(
        self,
        axis: str,
        show_popup: bool = False,
        refresh_ui: bool = True,
    ) -> bool:
        row_type, row_index = self._editor_row_info(axis)
        sections = self._sections_for_axis(axis)
        transitions = self._transitions_for_axis(axis)

        if row_type == "none":
            return True

        try:
            if row_type == "transition":
                if not (0 <= row_index < len(transitions)):
                    return False
                edited = self._read_transition_editor(axis)
                current = transitions[row_index]
                current.enabled = edited.enabled
                current.duration_s = edited.duration_s
                current.eat_away_mode = edited.eat_away_mode
                if self.edit_mode_var.get() == EDIT_MODE_EXPERT:
                    current.auto_added = False
            else:
                if not sections:
                    return False
                row_index = min(max(row_index, 0), len(sections) - 1)
                if sections[row_index].is_auto_fill:
                    return True
                sections[row_index] = self._read_section_editor(axis)
                if self.edit_mode_var.get() == EDIT_MODE_EASY:
                    apply_easy_mode_continuity(sections, self.recipe.sample_rate_hz)
                    self._update_easy_locked_field_from_model(axis, row_index)
        except ValueError as exc:
            self._set_status(f"Input error: {exc}", is_error=True)
            if show_popup:
                messagebox.showerror("Invalid Input", str(exc))
            return False

        if refresh_ui:
            self._refresh_axis_tree(axis, select=(row_type, row_index))
            self._load_selected_item_into_editor(axis)
        return True

    def _update_easy_locked_field_from_model(self, axis: str, section_index: int) -> None:
        if self.edit_mode_var.get() != EDIT_MODE_EASY or section_index <= 0:
            return

        sections = self._sections_for_axis(axis)
        if not (0 <= section_index < len(sections)):
            return

        params = sections[section_index].params
        ui = self.axis_ui[axis]

        self._suspend_events = True
        if params.secondary_enabled:
            if params.secondary_mode == MODE_CONSTANT:
                ui["secondary_constant_var"].set(f"{params.secondary_constant_value:.6f}")
            elif params.secondary_mode == MODE_RAMP:
                ui["secondary_ramp_start_var"].set(f"{params.secondary_ramp_start:.6f}")
            elif params.secondary_mode == MODE_S_CURVE:
                ui["secondary_s_curve_start_var"].set(f"{params.secondary_s_curve_start:.6f}")
            elif params.secondary_mode in (MODE_SINE, MODE_SWEEP, MODE_MULTISINE):
                ui["secondary_offset_var"].set(f"{params.secondary_offset:.6f}")
        else:
            if params.mode == MODE_CONSTANT:
                ui["constant_var"].set(f"{params.constant_value:.6f}")
            elif params.mode == MODE_RAMP:
                ui["ramp_start_var"].set(f"{params.ramp_start:.6f}")
                self._apply_ramp_speed_coupling(axis, changed_field="ramp_start")
            elif params.mode == MODE_S_CURVE:
                ui["s_curve_start_var"].set(f"{params.s_curve_start:.6f}")
            elif params.mode in (MODE_SINE, MODE_SWEEP, MODE_MULTISINE):
                ui["offset_var"].set(f"{params.offset:.6f}")
        self._suspend_events = False

    def _on_axis_selection_changed(self, axis: str) -> None:
        self.axis_ui[axis]["skip_focus_commit"] = False
        if self._suspend_events:
            return
        self._load_selected_item_into_editor(axis)
        refresh_fn = getattr(self, "_refresh_selection_highlight", None)
        if callable(refresh_fn):
            refresh_fn()

    def _on_axis_mode_changed(self, axis: str) -> None:
        if self._suspend_events:
            return
        self._update_axis_editor_visibility(axis)
        if self._apply_axis_editor_to_model(axis, show_popup=False, refresh_ui=False):
            self._schedule_refresh()

    def _on_axis_secondary_toggled(self, axis: str) -> None:
        if self._suspend_events:
            return
        self._update_axis_editor_visibility(axis)
        if self._apply_axis_editor_to_model(axis, show_popup=False, refresh_ui=False):
            self._schedule_refresh()

    def _on_axis_secondary_mode_changed(self, axis: str) -> None:
        if self._suspend_events:
            return
        self._update_axis_editor_visibility(axis)
        if self._apply_axis_editor_to_model(axis, show_popup=False, refresh_ui=False):
            self._schedule_refresh()

    def _on_axis_editor_changed(self, axis: str) -> None:
        if self._suspend_events:
            return
        if self._consume_skip_focus_commit(axis):
            return
        row_type, _row_index = self._editor_row_info(axis)
        if row_type != "section":
            return
        if self._apply_axis_editor_to_model(axis, show_popup=False, refresh_ui=False):
            self._schedule_refresh()

    def _on_transition_editor_changed(self, axis: str) -> None:
        if self._suspend_events:
            return
        if self._consume_skip_focus_commit(axis):
            return
        row_type, _row_index = self._editor_row_info(axis)
        if row_type != "transition":
            return
        if self._apply_axis_editor_to_model(axis, show_popup=False, refresh_ui=False):
            self._schedule_refresh()

    def _on_duration_scale(self, axis: str, value: str) -> None:
        if self._suspend_events:
            return
        try:
            parsed = float(value)
        except ValueError:
            return
        ui = self.axis_ui[axis]
        self._suspend_events = True
        ui["duration_var"].set(f"{parsed:.6f}")
        self._suspend_events = False
        self._apply_ramp_speed_coupling(axis, changed_field="duration")
        self._on_axis_editor_changed(axis)

    def _on_duration_entry(self, axis: str) -> None:
        if self._suspend_events:
            return
        ui = self.axis_ui[axis]
        text = str(ui["duration_var"].get()).strip()
        if not text:
            return
        try:
            value = float(text)
        except ValueError:
            return
        self._suspend_events = True
        ui["duration_scale_var"].set(max(0.05, min(30.0, value)))
        self._suspend_events = False
        self._apply_ramp_speed_coupling(axis, changed_field="duration")
        self._on_axis_editor_changed(axis)

    def _on_ramp_value_entry(self, axis: str, field_key: str) -> None:
        if self._suspend_events:
            return
        self._apply_ramp_speed_coupling(axis, changed_field=field_key)
        self._on_axis_editor_changed(axis)

    def _on_ramp_lock_toggled(self, axis: str) -> None:
        if self._suspend_events:
            return
        self._apply_ramp_speed_coupling(axis, changed_field="lock_toggle")
        if self._apply_axis_editor_to_model(axis, show_popup=False, refresh_ui=False):
            self._schedule_refresh()

    def _on_amplitude_scale(self, axis: str, value: str) -> None:
        if self._suspend_events:
            return
        try:
            parsed = float(value)
        except ValueError:
            return
        ui = self.axis_ui[axis]
        self._suspend_events = True
        ui["amplitude_var"].set(f"{parsed:.6f}")
        self._suspend_events = False
        self._on_axis_editor_changed(axis)

    def _on_amplitude_entry(self, axis: str) -> None:
        if self._suspend_events:
            return
        ui = self.axis_ui[axis]
        text = str(ui["amplitude_var"].get()).strip()
        if not text:
            return
        try:
            value = float(text)
        except ValueError:
            return
        self._suspend_events = True
        ui["amplitude_scale_var"].set(max(0.0, min(0.5, value)))
        self._suspend_events = False
        self._on_axis_editor_changed(axis)

    def _on_sample_rate_scale(self, value: str) -> None:
        if self._suspend_events:
            return
        try:
            parsed = float(value)
        except ValueError:
            return
        self._suspend_events = True
        self.sample_rate_var.set(f"{parsed:.3f}")
        self._suspend_events = False
        if self._apply_sample_rate_from_ui(show_popup=False):
            self._schedule_refresh()

    def _on_sample_rate_entry(self) -> None:
        if self._suspend_events:
            return
        text = self.sample_rate_var.get().strip()
        if not text:
            return
        try:
            parsed = float(text)
        except ValueError:
            return

        self._suspend_events = True
        self.sample_rate_scale_var.set(max(20.0, min(5000.0, parsed)))
        self._suspend_events = False
        if self._apply_sample_rate_from_ui(show_popup=False):
            self._schedule_refresh()

    def _on_edit_mode_changed(self) -> None:
        self._apply_easy_mode_if_needed()
        self._load_selected_item_into_editor("y")
        self._load_selected_item_into_editor("z")
        self._schedule_refresh()

    def _add_axis_section(self, axis: str) -> None:
        sections = self._sections_for_axis(axis)
        if not sections:
            sections.append(AxisMotionSection(duration_s=1.0, params=AxisSectionParams()))
            ensure_pipeline_transitions(self._pipeline_for_axis(axis))
            self._refresh_axis_tree(axis, select=("section", 0))
            self._load_selected_item_into_editor(axis)
            self._schedule_refresh()
            return

        insert_index = self._selected_section_index_for_actions(axis) + 1
        insert_index = min(max(insert_index, 0), len(sections))
        sections.insert(insert_index, AxisMotionSection(duration_s=1.0, params=AxisSectionParams()))
        ensure_pipeline_transitions(self._pipeline_for_axis(axis))

        if self.edit_mode_var.get() == EDIT_MODE_EASY:
            apply_easy_mode_continuity(sections, self.recipe.sample_rate_hz)

        self._refresh_axis_tree(axis, select=("section", insert_index))
        self._load_selected_item_into_editor(axis)
        self._schedule_refresh()

    def _delete_axis_section(self, axis: str) -> None:
        row_type, _row_index = self._selected_row_info(axis)
        if row_type == "none":
            self._set_status(f"{axis.upper()}: select a section to delete.", is_error=False)
            return

        sections = self._sections_for_axis(axis)
        if len(sections) <= 1:
            messagebox.showerror("Cannot Delete", f"{axis.upper()} must keep at least one section.")
            return

        idx = self._selected_section_index_for_actions(axis)
        idx = min(max(idx, 0), len(sections) - 1)
        if sections[idx].is_auto_fill:
            self._set_status(
                f"{axis.upper()}: auto-fill section cannot be deleted directly. Change durations to remove it.",
                is_error=False,
            )
            return
        del sections[idx]
        ensure_pipeline_transitions(self._pipeline_for_axis(axis))

        if self.edit_mode_var.get() == EDIT_MODE_EASY:
            apply_easy_mode_continuity(sections, self.recipe.sample_rate_hz)

        new_idx = min(idx, len(sections) - 1)
        self._refresh_axis_tree(axis, select=("section", new_idx))
        self._load_selected_item_into_editor(axis)
        self._schedule_refresh()

    def _move_axis_section(self, axis: str, direction: int) -> None:
        row_type, _row_index = self._selected_row_info(axis)
        if row_type == "none":
            self._set_status(f"{axis.upper()}: select a section to move.", is_error=False)
            return

        sections = self._sections_for_axis(axis)
        if len(sections) <= 1:
            return
        idx = self._selected_section_index_for_actions(axis)
        if sections[idx].is_auto_fill:
            self._set_status(
                f"{axis.upper()}: auto-fill section cannot be moved.",
                is_error=False,
            )
            return
        new_idx = idx + direction
        if new_idx < 0 or new_idx >= len(sections):
            return

        section = sections.pop(idx)
        sections.insert(new_idx, section)
        ensure_pipeline_transitions(self._pipeline_for_axis(axis))

        if self.edit_mode_var.get() == EDIT_MODE_EASY:
            apply_easy_mode_continuity(sections, self.recipe.sample_rate_hz)

        self._refresh_axis_tree(axis, select=("section", new_idx))
        self._load_selected_item_into_editor(axis)
        self._schedule_refresh()

    def _apply_easy_mode_if_needed(self) -> None:
        if self.edit_mode_var.get() != EDIT_MODE_EASY:
            return
        apply_easy_mode_continuity(self.recipe.y_pipeline.sections, self.recipe.sample_rate_hz)
        apply_easy_mode_continuity(self.recipe.z_pipeline.sections, self.recipe.sample_rate_hz)

    def _apply_sample_rate_from_ui(self, show_popup: bool = False) -> bool:
        try:
            sample_rate = self._parse_float("Sample rate", self.sample_rate_var.get())
            if sample_rate <= 0:
                raise ValueError("Sample rate must be > 0.")
        except ValueError as exc:
            self._set_status(f"Input error: {exc}", is_error=True)
            if show_popup:
                messagebox.showerror("Invalid Input", str(exc))
            return False

        self.recipe.sample_rate_hz = sample_rate
        if self.edit_mode_var.get() == EDIT_MODE_EASY:
            self._apply_easy_mode_if_needed()
        return True

