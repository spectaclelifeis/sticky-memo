import json
import os
import sys
from pathlib import Path
import ctypes

os.environ.setdefault("PYWEBVIEW_GUI", "edgechromium")

import webview

if getattr(sys, "frozen", False):
    RUNTIME_DIR = Path(sys.executable).resolve().parent
    RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", RUNTIME_DIR))
else:
    RUNTIME_DIR = Path(__file__).resolve().parent
    RESOURCE_DIR = RUNTIME_DIR

DATA_FILE = RUNTIME_DIR / "todo_data.json"
HTML_FILE = RESOURCE_DIR / "todo.html"
BACKUP_DIR = RUNTIME_DIR


def get_window_size_by_screen_ratio():
    try:
        user32 = ctypes.windll.user32
        screen_width = user32.GetSystemMetrics(0)
        screen_height = user32.GetSystemMetrics(1)
    except Exception:
        screen_width = 1600
        screen_height = 900

    width = max(900, int(screen_width * (19 / 20)))
    height = max(600, int(screen_height * (17 / 20)))
    return width, height


class Api:
    def load_data(self):
        if not DATA_FILE.exists():
            return {}

        try:
            with DATA_FILE.open("r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception as error:
            print(f"[load_data] failed: {error}")
            return {}

    def save_data(self, data):
        if not isinstance(data, dict):
            return {"ok": False, "message": "Invalid data format"}

        try:
            with DATA_FILE.open("w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return {"ok": True}
        except Exception as error:
            print(f"[save_data] failed: {error}")
            return {"ok": False, "message": str(error)}

    def export_backup(self, data, filename):
        if not isinstance(data, dict):
            return {"ok": False, "message": "Invalid data format"}
        if not isinstance(filename, str) or not filename.strip():
            return {"ok": False, "message": "Invalid filename"}

        safe_name = Path(filename).name
        if not safe_name.lower().endswith(".json"):
            safe_name += ".json"

        try:
            out_path = BACKUP_DIR / safe_name
            with out_path.open("w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return {"ok": True, "path": str(out_path)}
        except Exception as error:
            print(f"[export_backup] failed: {error}")
            return {"ok": False, "message": str(error)}


def main():
    if not HTML_FILE.exists():
        raise FileNotFoundError(f"Cannot find HTML file: {HTML_FILE}")

    width, height = get_window_size_by_screen_ratio()

    window = webview.create_window(
        "Weekly TODO",
        url=HTML_FILE.as_uri(),
        js_api=Api(),
        width=width,
        height=height,
    )
    webview.start(debug=False)


if __name__ == "__main__":
    main()
