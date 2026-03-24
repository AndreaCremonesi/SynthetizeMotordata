# Contributing

Contributions are welcome via pull requests.

## Development Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Architecture Boundaries

- Keep trajectory-generation logic in `synth_engine.py`.
- Keep GUI behavior in the `synth_gui_*` modules.
- Keep project serialization concerns in `synth_project_io.py`.
- Preserve CSV schema compatibility with `MotordataExample.csv` unless requirements change.

## Pre-PR Checks

Run before opening a pull request:

```powershell
python -m py_compile synth_engine.py
python -m py_compile synth_project_io.py synth_gui_shared.py synth_gui_layout.py synth_gui_axis.py synth_gui_runtime.py synth_gui_app.py synth_motordata_gui.py
```

Optional local GUI smoke test:

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

## Pull Request Notes

- Keep changes focused and include rationale in the PR description.
- Mention behavior changes and any known limitations.
- If UI behavior changes, include screenshots or short clips when possible.
