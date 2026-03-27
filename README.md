# MotorData Dual-Axis Trajectory Synthesizer

Desktop Python application to build synthetic motor trajectories for:

- `mrk_hor_pos(m)` (Y axis)
- `mrk_ver_pos(m)` (Z axis)

The app previews position/velocity/acceleration/path, validates limits, supports boundary smoothing transitions, saves/loads full projects, and exports CSV files compatible with `MotordataExample.csv`.

## Features

- Independent Y and Z section pipelines
- Section waveform modes
  - `sine`
  - `sweep` (linear or logarithmic frequency sweep in Hz)
  - `ramp`
    - Optional ramp speed + `Lock speed` coupling (duration <-> end position)
  - `constant`
  - `multisine` (sum of multiple sine terms `A,f,phi; ...`)
  - Optional secondary waveform summed with the primary waveform (all mode combinations)
- Easy/Expert editing modes
  - Easy: continuity auto-linking between consecutive sections
  - Expert: full manual control
- Transition rows between section boundaries
  - Warning-driven boundary status (`active`/`resolved`)
  - Optional smoothing (`smoothen transition`) with eat-away modes (`left`, `right`, `both`)
  - Quintic C2 blending to match value, velocity, and acceleration at both ends
- Pipeline section copy/paste
  - Multi-select sections with Ctrl+Click in a pipeline tree
  - Copy/paste within the same axis or across Y/Z axes
- Live plots
  - Position vs time
    - Optional split view (`Split Y/Z` / `Unite Y/Z`)
  - Velocity and acceleration
  - Y-Z path
- Optional warning limits (per axis)
  - min/max value
  - max speed
  - max acceleration
  - boundary jump threshold
- Automatic length balancing
  - Preview stays available when Y and Z durations differ
  - A trailing constant `auto-fill` section is inserted on the shorter axis
  - Auto-fill section is highlighted and auto-resized/removed as edits change durations
- CSV export
  - Non-overwriting filename resolution
  - Warning confirmation before export
  - Output format aligned to template header
- Project persistence (`Save Project` / `Load Project`)
  - Recipe, limits, UI selections, geometry, and pane layout are restored
  - Project format is `*.synthproj.json`
- Header menu actions
  - Top window row contains `Save Project`, `Save Project As...`, `Load Project`, `Load CSV`, `Close CSV Preview`, `Export`, and `Export As...`
- External CSV visualization
  - Load an existing trajectory CSV and use the app as a viewer (position, dynamics, Y-Z path, limits warnings)
  - While CSV viewer mode is active, waveform/pipeline editing controls are disabled
  - Use `Close CSV Preview` to return to normal synthesis mode
- Small-screen usability
  - Left controls panel is scrollable (wheel + scrollbar), while plots remain fixed

## Repository Structure

- `synth_motordata_gui.py`: compatibility launcher/entrypoint
- `synth_gui_app.py`: top-level `TrajectorySynthApp` composition and startup
- `synth_gui_shared.py`: shared constants, imports, engine bindings
- `synth_gui_layout.py`: Tkinter layout/widgets construction
- `synth_gui_axis.py`: axis editor logic (sections/transitions/input parsing)
- `synth_gui_runtime.py`: preview generation, warnings, plotting, export flow
- `synth_project_io.py`: project file serializer/deserializer (schema versioned)
- `synth_engine.py`: core generation engine, transitions, limits, CSV row builder
- `MotordataExample.csv`: schema/template reference used for header validation
- `requirements.txt`: Python dependencies
- `.github/workflows/ci.yml`: syntax-check CI for push and pull requests

## Requirements

- Python 3.10+
- OS with Tk support (`tkinter`)
- Dependencies in `requirements.txt`:
  - `numpy`
  - `matplotlib`

Notes:

- On Windows, `tkinter` is included with standard Python installers.
- On Linux, you may need `python3-tk`.

## Quick Start

```powershell
git clone https://github.com/AndreaCremonesi/SynthetizeMotordata.git
cd SynthetizeMotordata
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python synth_motordata_gui.py
```

On macOS/Linux, activate the environment with:

```bash
source .venv/bin/activate
```

## Typical Workflow

1. Set `Sample rate (Hz)` and edit mode (`Easy` or `Expert`).
2. Build Y and Z pipelines independently (add/delete/reorder sections).
3. Select each section and configure waveform parameters.
4. Review warnings (with boundary index/time context).
5. Optionally enable transition smoothing at problematic boundaries.
6. If one axis is shorter, review the highlighted `auto-fill` section.
7. Add/adjust manual sections; auto-fill resizes or disappears once lengths match.
8. Check plots (position, dynamics, Y-Z path).
9. Use the top header row for `Save Project`, `Save Project As...`, `Load Project`, `Load CSV`, `Close CSV Preview`, `Export`, and `Export As...`.

## Easy vs Expert

- Easy mode
  - Section continuity is auto-applied across boundaries (value continuity)
  - Transition advanced fields are locked, while enable/disable remains available
  - Active boundary jumps can auto-enable default transitions
- Expert mode
  - All section and transition fields are manually editable

## CSV Output Rules

- Header and column order follow `MotordataExample.csv`.
- `SeqNo` increments from `1..N`.
- Synthesized columns:
  - `mrk_hor_pos(m)` <- Y
  - `mrk_ver_pos(m)` <- Z
- `Date` and `UTC Time` are valid UTC timestamps per sample.
- Other numeric columns are written as `0`.

## Project Save/Load

- Project files use `*.synthproj.json`.
- Save behavior
  - First save opens a save dialog
  - Subsequent saves overwrite the same project path
- Load behavior restores
  - Recipe (sample rate + full Y/Z pipelines)
  - Transitions (enabled/duration/eat-away/auto-added/status)
  - Auto-fill section flags
  - Limits
  - Edit mode
  - Output filename field
  - Selected rows (Y and Z)
  - Active plot tab
  - Window geometry and paned-window sash positions
- Validation
  - Schema is versioned (`schema_version`)
  - Incompatible versions and invalid payloads are rejected with explicit errors

## Validation and CI

Local syntax checks:

```powershell
python -m py_compile synth_engine.py
python -m py_compile synth_project_io.py synth_gui_shared.py synth_gui_layout.py synth_gui_axis.py synth_gui_runtime.py synth_gui_app.py synth_motordata_gui.py
```

Optional GUI smoke test:

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

The same `py_compile` checks run automatically in GitHub Actions on each push and pull request.

## Contributing

See `CONTRIBUTING.md` for contribution workflow, code ownership guidance, and pre-PR checks.

## License

This project is licensed under the MIT License. See `LICENSE`.
