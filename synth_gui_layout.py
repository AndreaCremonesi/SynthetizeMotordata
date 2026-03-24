"""GUI layout/building mixin for the trajectory synthesizer."""

from __future__ import annotations

try:
    from synth_gui_shared import *
except ModuleNotFoundError:
    from .synth_gui_shared import *  # type: ignore[no-redef]

MIN_TOP_CONTROLS_HEIGHT = 420
MIN_AXIS_WORKSPACE_HEIGHT = 920
MIN_LEFT_PANEL_HEIGHT = MIN_TOP_CONTROLS_HEIGHT + MIN_AXIS_WORKSPACE_HEIGHT
MIN_AXIS_SECTION_HEIGHT = 360
MIN_AXIS_EDITOR_HEIGHT = 300


class LayoutMixin:
    """Builds frames, panes, editors, and plots."""

    @staticmethod
    def _bind_numeric_entry_behavior(entry: ttk.Entry, on_commit=None) -> None:
        def _select_all_on_focus(event: tk.Event) -> None:
            widget = event.widget

            def _apply_selection() -> None:
                try:
                    widget.selection_range(0, tk.END)
                    widget.icursor(tk.END)
                except Exception:
                    return

            widget.after_idle(_apply_selection)

        def _select_all_shortcut(event: tk.Event) -> str:
            widget = event.widget
            try:
                widget.selection_range(0, tk.END)
                widget.icursor(tk.END)
            except Exception:
                pass
            return "break"

        def _commit(_event: tk.Event) -> None:
            if callable(on_commit):
                on_commit()

        entry.bind("<FocusIn>", _select_all_on_focus, add="+")
        entry.bind("<Control-a>", _select_all_shortcut, add="+")
        entry.bind("<Return>", _commit, add="+")
        entry.bind("<KP_Enter>", _commit, add="+")
        entry.bind("<FocusOut>", _commit, add="+")

    def _build_layout(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=0)
        self.root.rowconfigure(1, weight=1)

        window_header = ttk.Frame(self.root, padding=(8, 6))
        window_header.grid(row=0, column=0, sticky="ew")
        window_header.columnconfigure(1, weight=2)
        window_header.columnconfigure(3, weight=1)
        self._build_window_header(window_header)

        main_pane = ttk.Panedwindow(self.root, orient="horizontal")
        main_pane.grid(row=1, column=0, sticky="nsew")
        self.main_pane = main_pane

        controls_container = ttk.Frame(main_pane, padding=8)
        plots_container = ttk.Frame(main_pane, padding=8)
        controls_container.columnconfigure(0, weight=1)
        controls_container.rowconfigure(0, weight=1)
        plots_container.columnconfigure(0, weight=1)
        plots_container.rowconfigure(0, weight=1)

        main_pane.add(controls_container, weight=1)
        main_pane.add(plots_container, weight=2)

        controls_canvas = tk.Canvas(controls_container, highlightthickness=0, borderwidth=0)
        controls_scrollbar = ttk.Scrollbar(controls_container, orient="vertical", command=controls_canvas.yview)
        controls_canvas.configure(yscrollcommand=controls_scrollbar.set)
        controls_canvas.grid(row=0, column=0, sticky="nsew")
        controls_scrollbar.grid(row=0, column=1, sticky="ns")

        controls_content = ttk.Frame(controls_canvas)
        controls_content.columnconfigure(0, weight=1)
        controls_content.rowconfigure(0, weight=1)
        controls_window = controls_canvas.create_window((0, 0), window=controls_content, anchor="nw")

        def _sync_controls_scroll_region(_event: tk.Event) -> None:
            controls_canvas.configure(scrollregion=controls_canvas.bbox("all"))

        def _sync_controls_size(event: tk.Event) -> None:
            target_width = event.width
            target_height = max(event.height, controls_content.winfo_reqheight(), MIN_LEFT_PANEL_HEIGHT)
            controls_canvas.itemconfigure(controls_window, width=target_width, height=target_height)

        def _on_controls_mousewheel(event: tk.Event) -> None:
            delta = event.delta
            if delta == 0:
                return
            controls_canvas.yview_scroll(int(-delta / 120), "units")

        def _on_controls_scroll_up(_event: tk.Event) -> None:
            controls_canvas.yview_scroll(-1, "units")

        def _on_controls_scroll_down(_event: tk.Event) -> None:
            controls_canvas.yview_scroll(1, "units")

        controls_content.bind("<Configure>", _sync_controls_scroll_region)
        controls_canvas.bind("<Configure>", _sync_controls_size)
        controls_canvas.bind("<Enter>", lambda _e: controls_canvas.bind_all("<MouseWheel>", _on_controls_mousewheel))
        controls_canvas.bind("<Enter>", lambda _e: controls_canvas.bind_all("<Button-4>", _on_controls_scroll_up), add="+")
        controls_canvas.bind("<Enter>", lambda _e: controls_canvas.bind_all("<Button-5>", _on_controls_scroll_down), add="+")
        controls_canvas.bind("<Leave>", lambda _e: controls_canvas.unbind_all("<MouseWheel>"))
        controls_canvas.bind("<Leave>", lambda _e: controls_canvas.unbind_all("<Button-4>"), add="+")
        controls_canvas.bind("<Leave>", lambda _e: controls_canvas.unbind_all("<Button-5>"), add="+")

        self.controls_canvas = controls_canvas
        self.controls_scrollbar = controls_scrollbar

        controls_pane = ttk.Panedwindow(controls_content, orient="vertical")
        controls_pane.grid(row=0, column=0, sticky="nsew")
        self.controls_pane = controls_pane
        controls_pane.configure(height=MIN_LEFT_PANEL_HEIGHT)

        top_controls = ttk.Frame(controls_pane, padding=4)
        top_controls.columnconfigure(0, weight=1)
        top_controls.configure(height=MIN_TOP_CONTROLS_HEIGHT)

        axis_workspace = ttk.Frame(controls_pane, padding=4)
        axis_workspace.columnconfigure(0, weight=1)
        axis_workspace.rowconfigure(0, weight=1)
        axis_workspace.configure(height=MIN_AXIS_WORKSPACE_HEIGHT)

        controls_pane.add(top_controls, weight=0)
        controls_pane.add(axis_workspace, weight=1)

        self._build_top_controls(top_controls)
        self._build_axis_workspace(axis_workspace)
        self._build_plot_area(plots_container)
        self.root.after_idle(self._initialize_min_heights)

    def _initialize_min_heights(self) -> None:
        try:
            self.controls_pane.sashpos(0, MIN_TOP_CONTROLS_HEIGHT)
        except Exception:
            pass
        for axis in ("y", "z"):
            pane = self.axis_ui.get(axis, {}).get("axis_pane")
            if pane is None:
                continue
            try:
                pane.sashpos(0, MIN_AXIS_SECTION_HEIGHT)
            except Exception:
                continue

    def _build_window_header(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="Project").grid(row=0, column=0, sticky="w", padx=(0, 6))
        ttk.Label(
            parent,
            textvariable=self.project_path_var,
            justify="left",
        ).grid(row=0, column=1, sticky="ew", padx=(0, 10))

        ttk.Label(parent, text="Output").grid(row=0, column=2, sticky="w", padx=(0, 6))
        ttk.Entry(parent, textvariable=self.output_name_var, width=24).grid(
            row=0, column=3, sticky="ew", padx=(0, 8)
        )

        ttk.Button(parent, text="Save Project", command=self._on_save_project).grid(
            row=0, column=4, padx=(0, 4)
        )
        ttk.Button(parent, text="Load Project", command=self._on_load_project).grid(
            row=0, column=5, padx=(0, 4)
        )
        ttk.Button(parent, text="Export", command=self._on_save_inline).grid(
            row=0, column=6, padx=(0, 4)
        )
        ttk.Button(parent, text="Export As...", command=self._on_save_as).grid(row=0, column=7)

    def _build_top_controls(self, parent: ttk.Frame) -> None:
        general = ttk.LabelFrame(parent, text="Global Settings", padding=8)
        general.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        general.columnconfigure(1, weight=1)

        ttk.Label(general, text="Edit mode").grid(row=0, column=0, sticky="w", padx=(0, 6), pady=2)
        mode_combo = ttk.Combobox(
            general,
            state="readonly",
            values=[EDIT_MODE_EASY, EDIT_MODE_EXPERT],
            textvariable=self.edit_mode_var,
            width=12,
        )
        mode_combo.grid(row=0, column=1, sticky="ew", pady=2)
        mode_combo.bind("<<ComboboxSelected>>", lambda _event: self._on_edit_mode_changed())

        ttk.Label(general, text="Sample rate (Hz)").grid(row=1, column=0, sticky="w", padx=(0, 6), pady=2)
        sample_rate_entry = ttk.Entry(general, textvariable=self.sample_rate_var, width=14)
        sample_rate_entry.grid(row=1, column=1, sticky="ew", pady=2)
        self._bind_numeric_entry_behavior(sample_rate_entry, on_commit=self._on_sample_rate_entry)
        ttk.Scale(
            general,
            from_=20.0,
            to=5000.0,
            variable=self.sample_rate_scale_var,
            command=self._on_sample_rate_scale,
        ).grid(row=2, column=0, columnspan=2, sticky="ew", pady=(2, 2))

        self._build_limits_frame(parent, row_index=1)
        warning_frame = ttk.LabelFrame(parent, text="Warnings", padding=6)
        warning_frame.grid(row=2, column=0, sticky="nsew", pady=(0, 8))
        warning_frame.columnconfigure(0, weight=1)
        warning_frame.rowconfigure(0, weight=1)
        parent.rowconfigure(2, weight=1)

        warning_text = tk.Text(warning_frame, height=10, wrap="word")
        warning_text.grid(row=0, column=0, sticky="nsew")
        warning_scroll = ttk.Scrollbar(warning_frame, orient="vertical", command=warning_text.yview)
        warning_scroll.grid(row=0, column=1, sticky="ns")
        warning_text.configure(yscrollcommand=warning_scroll.set)
        warning_text.configure(state="disabled")
        self.warning_text_widget = warning_text

        status_frame = ttk.Frame(parent)
        status_frame.grid(row=3, column=0, sticky="ew")
        status_frame.columnconfigure(0, weight=1)
        self.status_label = ttk.Label(status_frame, textvariable=self.status_var, wraplength=720, justify="left")
        self.status_label.grid(row=0, column=0, sticky="ew")

    def _build_limits_frame(self, parent: ttk.Frame, row_index: int = 2) -> None:
        frame = ttk.LabelFrame(parent, text="Optional Limits", padding=8)
        frame.grid(row=row_index, column=0, sticky="ew", pady=(0, 8))
        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)

        self.limit_vars = {
            "y": {
                "enable_min_value": tk.BooleanVar(value=False),
                "min_value": tk.StringVar(value="-1.0"),
                "enable_max_value": tk.BooleanVar(value=False),
                "max_value": tk.StringVar(value="1.0"),
                "enable_max_speed": tk.BooleanVar(value=False),
                "max_speed": tk.StringVar(value="1.0"),
                "enable_max_acceleration": tk.BooleanVar(value=False),
                "max_acceleration": tk.StringVar(value="10.0"),
                "enable_jump_threshold": tk.BooleanVar(value=True),
                "max_jump": tk.StringVar(value="0.01"),
            },
            "z": {
                "enable_min_value": tk.BooleanVar(value=False),
                "min_value": tk.StringVar(value="-1.0"),
                "enable_max_value": tk.BooleanVar(value=False),
                "max_value": tk.StringVar(value="1.0"),
                "enable_max_speed": tk.BooleanVar(value=False),
                "max_speed": tk.StringVar(value="1.0"),
                "enable_max_acceleration": tk.BooleanVar(value=False),
                "max_acceleration": tk.StringVar(value="10.0"),
                "enable_jump_threshold": tk.BooleanVar(value=True),
                "max_jump": tk.StringVar(value="0.01"),
            },
        }

        definitions = [
            ("enable_min_value", "min_value", "Min value"),
            ("enable_max_value", "max_value", "Max value"),
            ("enable_max_speed", "max_speed", "Max speed"),
            ("enable_max_acceleration", "max_acceleration", "Max acceleration"),
            ("enable_jump_threshold", "max_jump", "Max jump"),
        ]

        for col, axis in enumerate(("y", "z")):
            axis_frame = ttk.LabelFrame(frame, text=f"{axis.upper()} limits", padding=6)
            axis_frame.grid(row=0, column=col, sticky="nsew", padx=4)
            axis_frame.columnconfigure(1, weight=1)

            for row, (enable_key, value_key, label) in enumerate(definitions):
                check = ttk.Checkbutton(
                    axis_frame,
                    text=label,
                    variable=self.limit_vars[axis][enable_key],
                    command=self._schedule_refresh,
                )
                check.grid(row=row, column=0, sticky="w", pady=1)
                entry = ttk.Entry(axis_frame, textvariable=self.limit_vars[axis][value_key], width=12)
                entry.grid(row=row, column=1, sticky="ew", pady=1, padx=(6, 0))
                self._bind_numeric_entry_behavior(entry, on_commit=self._schedule_refresh)

    def _build_axis_workspace(self, parent: ttk.Frame) -> None:
        axes_pane = ttk.Panedwindow(parent, orient="horizontal")
        axes_pane.grid(row=0, column=0, sticky="nsew")
        self.axes_pane = axes_pane

        y_frame = self._build_axis_panel(axes_pane, "y", "Y Axis Pipeline (mrk_hor_pos)")
        z_frame = self._build_axis_panel(axes_pane, "z", "Z Axis Pipeline (mrk_ver_pos)")
        axes_pane.add(y_frame, weight=1)
        axes_pane.add(z_frame, weight=1)

    def _build_axis_panel(self, parent: ttk.Panedwindow, axis: str, title: str) -> ttk.Frame:
        panel = ttk.Frame(parent, padding=2)
        panel.columnconfigure(0, weight=1)
        panel.rowconfigure(0, weight=1)

        axis_pane = ttk.Panedwindow(panel, orient="vertical")
        axis_pane.grid(row=0, column=0, sticky="nsew")

        section_frame = ttk.LabelFrame(axis_pane, text=f"{title} - Pipeline", padding=6)
        section_frame.columnconfigure(0, weight=1)
        section_frame.rowconfigure(1, weight=1)
        section_frame.configure(height=MIN_AXIS_SECTION_HEIGHT)
        editor_frame = ttk.LabelFrame(axis_pane, text=f"{title} - Editor", padding=6)
        editor_frame.columnconfigure(0, weight=1)
        editor_frame.configure(height=MIN_AXIS_EDITOR_HEIGHT)

        axis_pane.add(section_frame, weight=1)
        axis_pane.add(editor_frame, weight=1)

        total_var = tk.StringVar(value="0.0000 s (0 sections)")
        ttk.Label(section_frame, textvariable=total_var).grid(row=0, column=0, sticky="w", pady=(0, 4))

        tree = ttk.Treeview(
            section_frame,
            columns=("item", "duration", "details"),
            show="headings",
            selectmode="browse",
            height=10,
        )
        tree.heading("item", text="Item")
        tree.heading("duration", text="Duration (s)")
        tree.heading("details", text="Details")
        tree.column("item", width=72, anchor="center")
        tree.column("duration", width=98, anchor="center")
        tree.column("details", width=220, anchor="w")
        tree.grid(row=1, column=0, sticky="nsew")
        tree.bind("<<TreeviewSelect>>", lambda _event, a=axis: self._on_axis_selection_changed(a))
        tree.tag_configure(TREE_TAG_TRANSITION_ACTIVE, background="#ffe066")
        tree.tag_configure(TREE_TAG_TRANSITION_RESOLVED, background="#fff3b0")
        tree.tag_configure(TREE_TAG_AUTO_FILL_SECTION, background="#d9edf7")

        buttons = ttk.Frame(section_frame)
        buttons.grid(row=2, column=0, sticky="ew", pady=(4, 0))
        for i in range(4):
            buttons.columnconfigure(i, weight=1)
        ttk.Button(buttons, text="Add", command=lambda a=axis: self._add_axis_section(a)).grid(
            row=0, column=0, sticky="ew", padx=(0, 3)
        )
        ttk.Button(buttons, text="Delete", command=lambda a=axis: self._delete_axis_section(a)).grid(
            row=0, column=1, sticky="ew", padx=3
        )
        ttk.Button(buttons, text="Up", command=lambda a=axis: self._move_axis_section(a, -1)).grid(
            row=0, column=2, sticky="ew", padx=3
        )
        ttk.Button(buttons, text="Down", command=lambda a=axis: self._move_axis_section(a, 1)).grid(
            row=0, column=3, sticky="ew", padx=(3, 0)
        )

        section_editor = ttk.Frame(editor_frame)
        section_editor.grid(row=0, column=0, sticky="nsew")
        section_editor.columnconfigure(0, weight=1)

        transition_editor = ttk.Frame(editor_frame)
        transition_editor.grid(row=0, column=0, sticky="nsew")
        transition_editor.columnconfigure(0, weight=1)

        duration_var = tk.StringVar(value="5.0")
        duration_scale_var = tk.DoubleVar(value=5.0)
        mode_var = tk.StringVar(value=MODE_SINE)
        constant_var = tk.StringVar(value="0.0")
        amplitude_var = tk.StringVar(value="0.01")
        amplitude_scale_var = tk.DoubleVar(value=0.01)
        offset_var = tk.StringVar(value="0.0")
        phase_var = tk.StringVar(value="0.0")
        frequency_var = tk.StringVar(value="1.0")
        sweep_start_var = tk.StringVar(value="0.5")
        sweep_end_var = tk.StringVar(value="5.0")
        ramp_start_var = tk.StringVar(value="0.0")
        ramp_end_var = tk.StringVar(value="0.01")
        multisine_components_var = tk.StringVar(value="0.01,1.0,0.0; 0.005,3.0,90.0")

        duration_row = ttk.Frame(section_editor)
        duration_row.grid(row=0, column=0, sticky="ew", pady=1)
        duration_row.columnconfigure(1, weight=1)
        ttk.Label(duration_row, text="Duration (s)").grid(row=0, column=0, sticky="w", padx=(0, 6))
        duration_entry = ttk.Entry(duration_row, textvariable=duration_var, width=12)
        duration_entry.grid(row=0, column=1, sticky="ew")
        self._bind_numeric_entry_behavior(duration_entry, on_commit=lambda a=axis: self._on_duration_entry(a))
        ttk.Scale(
            duration_row,
            from_=0.05,
            to=30.0,
            variable=duration_scale_var,
            command=lambda value, a=axis: self._on_duration_scale(a, value),
        ).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(2, 4))

        mode_row = ttk.Frame(section_editor)
        mode_row.grid(row=1, column=0, sticky="ew", pady=1)
        mode_row.columnconfigure(1, weight=1)
        ttk.Label(mode_row, text="Mode").grid(row=0, column=0, sticky="w", padx=(0, 6))
        mode_combo = ttk.Combobox(
            mode_row,
            state="readonly",
            values=[MODE_SINE, MODE_SWEEP, MODE_RAMP, MODE_CONSTANT, MODE_MULTISINE],
            textvariable=mode_var,
            width=12,
        )
        mode_combo.grid(row=0, column=1, sticky="ew")
        mode_combo.bind("<<ComboboxSelected>>", lambda _event, a=axis: self._on_axis_mode_changed(a))

        row_meta: Dict[str, Dict[str, Any]] = {}

        def create_row(
            row_idx: int,
            field_key: str,
            label_text: str,
            variable: tk.StringVar,
            slider_var: Optional[tk.DoubleVar] = None,
            slider_cmd=None,
            slider_to: float = 1.0,
            entry_width: int = 12,
        ) -> None:
            row_frame = ttk.Frame(section_editor)
            row_frame.grid(row=row_idx, column=0, sticky="ew", pady=1)
            row_frame.columnconfigure(1, weight=1)
            label_widget = ttk.Label(row_frame, text=label_text)
            label_widget.grid(row=0, column=0, sticky="w", padx=(0, 6))
            entry_widget = ttk.Entry(row_frame, textvariable=variable, width=entry_width)
            entry_widget.grid(row=0, column=1, sticky="ew")
            if field_key == "amplitude":
                on_commit = lambda a=axis: self._on_amplitude_entry(a)
            else:
                on_commit = lambda a=axis: self._on_axis_editor_changed(a)
            self._bind_numeric_entry_behavior(entry_widget, on_commit=on_commit)
            scale_widget = None
            if slider_var is not None:
                row_frame.columnconfigure(2, weight=1)
                scale_widget = ttk.Scale(
                    row_frame,
                    from_=0.0,
                    to=slider_to,
                    variable=slider_var,
                    command=slider_cmd,
                )
                scale_widget.grid(row=0, column=2, sticky="ew", padx=(6, 0))
            row_meta[field_key] = {
                "frame": row_frame,
                "label": label_widget,
                "entry": entry_widget,
                "scale": scale_widget,
            }

        create_row(2, "constant_value", "Constant value (m)", constant_var)
        create_row(
            3,
            "amplitude",
            "Amplitude (m)",
            amplitude_var,
            slider_var=amplitude_scale_var,
            slider_cmd=lambda value, a=axis: self._on_amplitude_scale(a, value),
            slider_to=0.5,
        )
        create_row(4, "offset", "Offset (m)", offset_var)
        create_row(5, "phase_deg", "Start phase (deg)", phase_var)
        create_row(6, "frequency_hz", "Frequency (Hz)", frequency_var)
        create_row(7, "sweep_start_hz", "Sweep start (Hz)", sweep_start_var)
        create_row(8, "sweep_end_hz", "Sweep end (Hz)", sweep_end_var)
        create_row(9, "ramp_start", "Ramp start (m)", ramp_start_var)
        create_row(10, "ramp_end", "Ramp end (m)", ramp_end_var)
        create_row(
            11,
            "multisine_components",
            "Multisine terms (A,f,phi;...)",
            multisine_components_var,
            entry_width=38,
        )

        transition_enabled_var = tk.BooleanVar(value=False)
        transition_duration_var = tk.StringVar(value=f"{DEFAULT_TRANSITION_DURATION_S:.3f}")
        transition_eat_var = tk.StringVar(value=EAT_AWAY_BOTH)
        transition_info_var = tk.StringVar(value="")

        check = ttk.Checkbutton(
            transition_editor,
            text="smoothen transition",
            variable=transition_enabled_var,
            command=lambda a=axis: self._on_transition_editor_changed(a),
        )
        check.grid(row=0, column=0, sticky="w", pady=(0, 8))

        dur_row = ttk.Frame(transition_editor)
        dur_row.grid(row=1, column=0, sticky="ew", pady=1)
        dur_row.columnconfigure(1, weight=1)
        ttk.Label(dur_row, text="Transition duration (s)").grid(row=0, column=0, sticky="w", padx=(0, 6))
        dur_entry = ttk.Entry(dur_row, textvariable=transition_duration_var, width=12)
        dur_entry.grid(row=0, column=1, sticky="ew")
        self._bind_numeric_entry_behavior(dur_entry, on_commit=lambda a=axis: self._on_transition_editor_changed(a))

        eat_row = ttk.Frame(transition_editor)
        eat_row.grid(row=2, column=0, sticky="ew", pady=1)
        eat_row.columnconfigure(1, weight=1)
        ttk.Label(eat_row, text="Eat away").grid(row=0, column=0, sticky="w", padx=(0, 6))
        eat_combo = ttk.Combobox(
            eat_row,
            state="readonly",
            values=[EAT_AWAY_LEFT, EAT_AWAY_RIGHT, EAT_AWAY_BOTH],
            textvariable=transition_eat_var,
            width=12,
        )
        eat_combo.grid(row=0, column=1, sticky="ew")
        eat_combo.bind("<<ComboboxSelected>>", lambda _event, a=axis: self._on_transition_editor_changed(a))

        info_label = ttk.Label(
            transition_editor,
            textvariable=transition_info_var,
            wraplength=460,
            justify="left",
        )
        info_label.grid(row=3, column=0, sticky="ew", pady=(8, 0))

        self.axis_ui[axis] = {
            "axis_pane": axis_pane,
            "tree": tree,
            "row_map": {},
            "total_var": total_var,
            "section_editor": section_editor,
            "transition_editor": transition_editor,
            "duration_var": duration_var,
            "duration_scale_var": duration_scale_var,
            "duration_entry": duration_entry,
            "mode_var": mode_var,
            "mode_combo": mode_combo,
            "constant_var": constant_var,
            "amplitude_var": amplitude_var,
            "amplitude_scale_var": amplitude_scale_var,
            "offset_var": offset_var,
            "phase_var": phase_var,
            "frequency_var": frequency_var,
            "sweep_start_var": sweep_start_var,
            "sweep_end_var": sweep_end_var,
            "ramp_start_var": ramp_start_var,
            "ramp_end_var": ramp_end_var,
            "multisine_components_var": multisine_components_var,
            "rows": row_meta,
            "duration_row": duration_row,
            "mode_row": mode_row,
            "transition_enabled_var": transition_enabled_var,
            "transition_duration_var": transition_duration_var,
            "transition_eat_var": transition_eat_var,
            "transition_info_var": transition_info_var,
            "transition_check": check,
            "transition_duration_entry": dur_entry,
            "transition_eat_combo": eat_combo,
            "selected_type": "section",
            "selected_index": 0,
        }

        return panel

    def _build_plot_area(self, parent: ttk.Frame) -> None:
        notebook = ttk.Notebook(parent)
        notebook.grid(row=0, column=0, sticky="nsew")
        self.plot_notebook = notebook
        notebook.bind("<<NotebookTabChanged>>", lambda _event: self._on_plot_tab_changed())

        tab_pos = ttk.Frame(notebook)
        tab_dyn = ttk.Frame(notebook)
        tab_path = ttk.Frame(notebook)
        notebook.add(tab_pos, text="Position vs Time")
        notebook.add(tab_dyn, text="Velocity & Acceleration")
        notebook.add(tab_path, text="Y-Z Path")

        for tab in (tab_pos, tab_dyn, tab_path):
            tab.columnconfigure(0, weight=1)
            tab.rowconfigure(0, weight=1)

        self.fig_pos = Figure(figsize=(11.5, 8.0), dpi=100)
        self.ax_pos = self.fig_pos.add_subplot(111)
        self.canvas_pos = FigureCanvasTkAgg(self.fig_pos, master=tab_pos)
        self.canvas_pos.get_tk_widget().grid(row=0, column=0, sticky="nsew")

        self.fig_dyn = Figure(figsize=(11.5, 8.0), dpi=100)
        self.ax_vel = self.fig_dyn.add_subplot(211)
        self.ax_acc = self.fig_dyn.add_subplot(212)
        self.canvas_dyn = FigureCanvasTkAgg(self.fig_dyn, master=tab_dyn)
        self.canvas_dyn.get_tk_widget().grid(row=0, column=0, sticky="nsew")

        self.fig_path = Figure(figsize=(11.5, 8.0), dpi=100)
        self.ax_path = self.fig_path.add_subplot(111)
        self.canvas_path = FigureCanvasTkAgg(self.fig_path, master=tab_path)
        self.canvas_path.get_tk_widget().grid(row=0, column=0, sticky="nsew")

