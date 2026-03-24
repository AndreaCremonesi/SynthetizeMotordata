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
        if selected:
            iid = selected[0]
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
        ui["sweep_start_var"].set(f"{params.sweep_start_hz:.6f}")
        ui["sweep_end_var"].set(f"{params.sweep_end_hz:.6f}")
        ui["ramp_start_var"].set(f"{params.ramp_start:.6f}")
        ui["ramp_end_var"].set(f"{params.ramp_end:.6f}")
        ui["multisine_components_var"].set(str(params.multisine_components))
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
        rows: Dict[str, Dict[str, Any]] = ui["rows"]
        mode_combo: ttk.Combobox = ui["mode_combo"]

        visible_by_mode = {
            MODE_CONSTANT: {"constant_value"},
            MODE_RAMP: {"ramp_start", "ramp_end"},
            MODE_SINE: {"amplitude", "offset", "phase_deg", "frequency_hz"},
            MODE_SWEEP: {"amplitude", "offset", "phase_deg", "sweep_start_hz", "sweep_end_hz"},
            MODE_MULTISINE: {"offset", "multisine_components"},
        }
        visible = visible_by_mode.get(mode, set())

        sections = self._sections_for_axis(axis)
        selected_auto_fill = False
        for key, meta in rows.items():
            frame = meta["frame"]
            if key in visible:
                frame.grid()
            else:
                frame.grid_remove()

        lock_field = None
        row_type, row_index = self._selected_row_info(axis)
        if row_type == "section" and 0 <= row_index < len(sections):
            selected_auto_fill = sections[row_index].is_auto_fill
        if not selected_auto_fill and self.edit_mode_var.get() == EDIT_MODE_EASY and row_type == "section" and row_index > 0:
            if mode == MODE_CONSTANT:
                lock_field = "constant_value"
            elif mode == MODE_RAMP:
                lock_field = "ramp_start"
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
            entry.configure(state=state)
            if scale is not None:
                scale.configure(state="normal" if state == "normal" else "disabled")
            if selected_auto_fill:
                label.configure(foreground="#1f4e79")
            else:
                label.configure(foreground="#555555" if state == "readonly" else "black")

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

    def _read_section_editor(self, axis: str) -> AxisMotionSection:
        ui = self.axis_ui[axis]
        axis_label = axis.upper()

        duration_s = self._parse_float(f"{axis_label} duration", ui["duration_var"].get())
        if duration_s <= 0:
            raise ValueError(f"{axis_label}: duration must be > 0.")

        mode = str(ui["mode_var"].get()).strip().lower()
        params = AxisSectionParams(mode=mode)
        if mode == MODE_CONSTANT:
            params.constant_value = self._parse_float(f"{axis_label} constant value", ui["constant_var"].get())
        elif mode == MODE_RAMP:
            params.ramp_start = self._parse_float(f"{axis_label} ramp start", ui["ramp_start_var"].get())
            params.ramp_end = self._parse_float(f"{axis_label} ramp end", ui["ramp_end_var"].get())
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
            params.sweep_start_hz = self._parse_float(f"{axis_label} sweep start", ui["sweep_start_var"].get())
            params.sweep_end_hz = self._parse_float(f"{axis_label} sweep end", ui["sweep_end_var"].get())
            if params.amplitude < 0:
                raise ValueError(f"{axis_label}: amplitude cannot be negative.")
            if params.sweep_start_hz < 0 or params.sweep_end_hz < 0:
                raise ValueError(f"{axis_label}: sweep frequencies cannot be negative.")
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
        row_type, row_index = self._selected_row_info(axis)
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
        if params.mode == MODE_CONSTANT:
            ui["constant_var"].set(f"{params.constant_value:.6f}")
        elif params.mode == MODE_RAMP:
            ui["ramp_start_var"].set(f"{params.ramp_start:.6f}")
        elif params.mode in (MODE_SINE, MODE_SWEEP, MODE_MULTISINE):
            ui["offset_var"].set(f"{params.offset:.6f}")
        self._suspend_events = False

    def _on_axis_selection_changed(self, axis: str) -> None:
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

    def _on_axis_editor_changed(self, axis: str) -> None:
        if self._suspend_events:
            return
        row_type, _row_index = self._selected_row_info(axis)
        if row_type != "section":
            return
        if self._apply_axis_editor_to_model(axis, show_popup=False, refresh_ui=False):
            self._schedule_refresh()

    def _on_transition_editor_changed(self, axis: str) -> None:
        if self._suspend_events:
            return
        row_type, _row_index = self._selected_row_info(axis)
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
        value = max(0.05, min(30.0, value))
        self._suspend_events = True
        ui["duration_scale_var"].set(value)
        self._suspend_events = False
        self._on_axis_editor_changed(axis)

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
        value = max(0.0, min(0.5, value))
        self._suspend_events = True
        ui["amplitude_scale_var"].set(value)
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

