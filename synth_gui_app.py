"""Top-level application class that composes GUI mixins."""

from __future__ import annotations

try:
    from synth_gui_axis import AxisEditorMixin
    from synth_gui_layout import LayoutMixin
    from synth_gui_runtime import RuntimeMixin
    from synth_gui_shared import (
        EDIT_MODE_EASY,
        Path,
        TEMPLATE_PATH,
        Any,
        Dict,
        Optional,
        TrajectoryRecipe,
        create_default_recipe,
        load_csv_header,
        tk,
        ttk,
        validate_header,
    )
except ModuleNotFoundError:
    from .synth_gui_axis import AxisEditorMixin  # type: ignore[no-redef]
    from .synth_gui_layout import LayoutMixin  # type: ignore[no-redef]
    from .synth_gui_runtime import RuntimeMixin  # type: ignore[no-redef]
    from .synth_gui_shared import (  # type: ignore[no-redef]
        EDIT_MODE_EASY,
        Path,
        TEMPLATE_PATH,
        Any,
        Dict,
        Optional,
        TrajectoryRecipe,
        create_default_recipe,
        load_csv_header,
        tk,
        ttk,
        validate_header,
    )


class TrajectorySynthApp(LayoutMixin, AxisEditorMixin, RuntimeMixin):
    """Tkinter application for dual-axis motor trajectory synthesis."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("MotorData Y/Z Dual-Axis Synthesizer")
        self.root.geometry("1800x1020")

        self.recipe: TrajectoryRecipe = create_default_recipe()
        self.header = load_csv_header(TEMPLATE_PATH)
        validate_header(self.header)

        self.edit_mode_var = tk.StringVar(value=EDIT_MODE_EASY)
        self.sample_rate_var = tk.StringVar(value=f"{self.recipe.sample_rate_hz:.3f}")
        self.sample_rate_scale_var = tk.DoubleVar(value=self.recipe.sample_rate_hz)
        self.status_var = tk.StringVar(value="Ready")
        self.output_name_var = tk.StringVar(value=self._suggest_unique_output_path().name)
        self.project_path_var = tk.StringVar(value="Project: (unsaved)")
        self.project_path: Optional[Path] = None

        self.axis_ui: Dict[str, Dict[str, Any]] = {}
        self.limit_vars: Dict[str, Dict[str, tk.Variable]] = {}
        self.warning_text_widget: Optional[tk.Text] = None
        self.status_label: Optional[ttk.Label] = None

        self._suspend_events = False
        self._pending_refresh_id: Optional[str] = None
        self._last_generated: Optional[Dict[str, Any]] = None

        self._build_layout()
        self._refresh_axis_tree("y")
        self._refresh_axis_tree("z")
        self._load_selected_item_into_editor("y")
        self._load_selected_item_into_editor("z")
        self._apply_easy_mode_if_needed()
        self._schedule_refresh()


def main() -> None:
    root = tk.Tk()
    _app = TrajectorySynthApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
