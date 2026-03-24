# MotorData Dual-Axis Trajectory Synthesizer

Desktop Python application to build synthetic motor trajectories for:

- `mrk_hor_pos(m)` (Y axis)
- `mrk_ver_pos(m)` (Z axis)

It previews position/velocity/acceleration/path, checks limits, applies optional boundary smoothing transitions, supports full project save/load, and exports CSV files compatible with your `MotordataExample.csv` schema.

## 1. Features

- Independent Y and Z section pipelines.
- Section waveform modes:
- `sine`
- `sweep` (linear frequency sweep in Hz)
- `ramp`
- `constant`
- Easy/Expert editing modes:
- Easy: continuity auto-linking between consecutive sections.
- Expert: full manual control.
- Transition rows between section boundaries:
- Warning-driven boundary status (`active`/`resolved`).
- Optional smoothing (`smoothen transition`) with eat-away modes (`left`, `right`, `both`).
- Smoothing uses a quintic C2 blend to match value, velocity, and acceleration at both ends.
- Live plots:
- Position vs Time.
- Velocity & Acceleration.
- Y-Z path.
- Optional warning limits (per axis):
- min/max value
- max speed
- max acceleration
- boundary jump threshold
- Automatic length balancing:
- if Y and Z durations do not match, preview remains available
- shorter axis gets an automatic constant `auto-fill` section
- auto-fill section is visually highlighted and labeled
- auto-fill section resizes or disappears automatically when user changes sections
- CSV export:
- non-overwriting filename resolution
- warning confirmation before export
- output format aligned to template header
- Project persistence:
- `Save Project` / `Load Project`
- restores recipe, limits, UI selections, geometry, and pane layout
- project format: `*.synthproj.json`
- Header menu actions:
- top horizontal row in the whole window header with `Save Project`, `Load Project`, `Export`, `Export As...`
- Small-screen usability:
- left controls panel is scrollable (vertical scrollbar + mouse wheel), while plot panel stays fixed
- controls widgets use minimum layout heights; when unavailable space is smaller, the controls panel scrolls

## 2. Project Structure

- `synth_motordata_gui.py`: compatibility launcher/entrypoint.
- `synth_gui_app.py`: top-level `TrajectorySynthApp` composition and startup.
- `synth_gui_shared.py`: shared constants, imports, engine bindings.
- `synth_gui_layout.py`: Tkinter layout/widgets construction.
- `synth_gui_axis.py`: axis editor logic (sections/transitions/input parsing).
- `synth_gui_runtime.py`: preview generation, warnings, plotting, export flow.
- `synth_project_io.py`: project file serializer/deserializer (schema versioned).
- `synth_engine.py`: core generation engine, transitions, limits, CSV row builder.
- `MotordataExample.csv`: schema/template reference used for header validation.
- `requirements.txt`: pip dependencies.
- `.gitignore`: recommended ignore rules for repository use.

## 3. Requirements

- Python `>= 3.10` recommended.
- OS with Tk support (Tkinter GUI).
- Python packages:
- `numpy`
- `matplotlib`

Install:

```powershell
cd Software/syntetizeMotordata
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Notes:

- `tkinter` is part of standard Python on Windows.
- On Linux you may need system package `python3-tk`.

## 4. Run

From `Software/syntetizeMotordata`:

```powershell
python synth_motordata_gui.py
```

## 5. Typical Workflow

1. Set `Sample rate (Hz)` and edit mode (`Easy` or `Expert`).
2. Build Y and Z pipelines independently (add/delete/reorder sections).
3. Select each section and configure waveform parameters.
4. Review warnings (with boundary index/time context).
5. Optionally enable transition smoothing at problematic boundaries.
6. If one axis is shorter, check the highlighted `auto-fill` section that is inserted automatically.
7. Add/adjust manual sections; auto-fill resizes or disappears once lengths match.
8. Check plots (position, dynamics, Y-Z path).
9. Use the top window header row (not the signal settings panel) for `Save Project` / `Load Project` and `Export` / `Export As...`.

## 6. Easy vs Expert

- Easy mode:
- section continuity is auto-applied across boundaries (value continuity)
- transition advanced fields are locked; enable/disable checkbox stays available
- active boundary jumps can auto-enable default transitions
- Expert mode:
- all section and transition fields are manually editable

## 7. CSV Output Rules

- Header and column order follow `MotordataExample.csv`.
- `SeqNo` increments from `1..N`.
- Only these columns get synthesized values:
- `mrk_hor_pos(m)` <- Y
- `mrk_ver_pos(m)` <- Z
- `Date` and `UTC Time` are valid UTC timestamps per sample.
- All other numeric columns are written as `0`.

## 8. Project Save/Load

- Project files use JSON with extension `*.synthproj.json`.
- Save:
- first save opens a save dialog
- subsequent saves overwrite the same project file path
- Load:
- opens a project file and restores:
- recipe (sample rate + full Y/Z pipelines)
- transitions (enabled/duration/eat-away/auto-added/status)
- auto-fill section flags
- limits
- edit mode
- output filename field
- selected rows (Y and Z)
- active plot tab
- window geometry and paned-window sash positions
- Notes:
- project schema is versioned (`schema_version`)
- incompatible schema versions are rejected with explicit error
- invalid project payloads are rejected with explicit error

## 9. Automatic Length Balancing

- When total rounded sample counts differ between Y and Z:
- the app no longer blocks preview
- it inserts one trailing constant section on the shorter axis
- inserted section properties:
- mode: `constant`
- value: equal to the last generated value of that axis (continuity)
- duration: exactly the missing sample count at current sample rate
- Visual cues:
- pipeline row is marked as auto-fill and highlighted with dedicated color
- position plot shows shaded auto-fill intervals with labels (`Y auto-fill`, `Z auto-fill`)
- Behavior during editing:
- if user modifies sections and mismatch shrinks, auto-fill section auto-resizes
- if user makes lengths equal, auto-fill section is removed automatically

## 10. Validation and Warnings

- Hard errors (block preview/export):
- invalid numeric input
- invalid sample rate or durations
- Warnings (non-blocking, but export requires confirmation):
- limit violations
- boundary jump excess (compared to local neighborhood step, to reduce false positives)
- transition clamping when requested transition duration is not feasible

## 11. Development and Maintainability

Current maintainability choices:

- Modularized architecture (layout/axis/runtime/app/shared split).
- Type annotations across engine and GUI code.
- Non-destructive export naming (`resolve_non_overwriting_path`).
- Centralized shared constants/imports in `synth_gui_shared.py`.

Recommended coding standards for future changes:

1. Keep engine logic in `synth_engine.py`; keep GUI modules UI-only.
2. Add methods to the correct mixin instead of growing one file.
3. Preserve strict CSV schema compatibility unless requirements change.
4. Add docstrings for new modules/classes/public functions.
5. Run the validation checklist before committing.

## 12. Validation Checklist (before commit)

```powershell
python -m py_compile synth_engine.py
python -m py_compile synth_project_io.py synth_gui_shared.py synth_gui_layout.py synth_gui_axis.py synth_gui_runtime.py synth_gui_app.py synth_motordata_gui.py
```

Optional smoke test:

```powershell
python - <<'PY'
import tkinter as tk
from synth_motordata_gui import TrajectorySynthApp
root = tk.Tk()
root.withdraw()
_app = TrajectorySynthApp(root)
root.update_idletasks()
root.destroy()
print("GUI init OK")
PY
```

## 13. Repository Migration Notes

When moving this folder into a dedicated git repository:

1. Keep all Python modules and `MotordataExample.csv` in the same package folder.
2. Include `requirements.txt` and this `README.md` at repository root (or adapt paths).
3. Keep `.gitignore` for virtual environment, cache files, generated CSV outputs, and local artifacts.
4. Optionally add CI to run `py_compile` checks on push/PR.
5. If you archive/share projects, include `*.synthproj.json` files separately from generated CSV output files.
