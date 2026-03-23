import json
import os
import sys
import ctypes
import time
import tkinter as tk
from tkinter import messagebox
from tkinter import filedialog
from tkinter import ttk

# EXE로 패키징되면 sys.executable 기준, 개발 중엔 스크립트 파일 기준
if getattr(sys, "frozen", False):
    _BASE_DIR = os.path.dirname(sys.executable)
else:
    _BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DATA_FILE = os.path.join(_BASE_DIR, "memos.json")
AUTOSAVE_DELAY_MS = 500
UI_FONT = ("Malgun Gothic", 11)
TITLE_FONT = ("Malgun Gothic", 14, "bold")

# ── Design tokens ────────────────────────────────────
BG        = "#F0F4F8"
CARD      = "#FFFFFF"
ACCENT    = "#4A7CFF"
ACCENT_DK = "#3A6AEF"
TEXT      = "#1A1D2E"
SUBTEXT   = "#8892AA"
SEL_BG    = "#4A7CFF"
SEL_FG    = "#FFFFFF"
BORDER    = "#DDE2EF"
DEL_CLR   = "#FF5A65"
DEL_DK    = "#E04450"

APP_USER_MODEL_ID = "ddung.stickymemo.app"
ICON_FILE = os.path.join(_BASE_DIR, "memo.ico")
PNG_ICON_FILE = os.path.join(_BASE_DIR, "memo.png")


def _setup_windows_taskbar_id():
    if os.name != "nt":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
    except Exception:
        pass


def _apply_window_icon(window):
    if not os.path.exists(PNG_ICON_FILE):
        return
    try:
        icon_img = tk.PhotoImage(file=PNG_ICON_FILE)
        window.wm_iconphoto(True, icon_img)
        window._icon_img = icon_img
    except Exception:
        pass


class StickyMemoApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Sticky Memo")
        self.root.geometry("700x700")
        self.root.minsize(700, 700)
        _apply_window_icon(self.root)
        self.root.option_add("*Font", "{Malgun Gothic} 11")
        self._setup_style()

        self.memos = []
        self.filtered_indices = []  # listbox index -> self.memos index
        self.open_windows = {}  # memo_id -> Toplevel
        self.pending_save_job = {}  # memo_id -> after-job id
        self.save_callbacks = {}  # memo_id -> save callback
        self.sort_mode = "latest"
        self.sort_buttons = {}

        self._load_memos()
        self._build_main_ui()
        self._refresh_list()
        self._bind_global_shortcuts()

    def _setup_style(self):
        self.root.configure(bg=BG)

    def _bind_global_shortcuts(self):
        self.root.bind_all("<Control-n>", self._on_shortcut_new)
        self.root.bind_all("<Control-f>", self._on_shortcut_find)
        self.root.bind_all("/", self._on_shortcut_focus_list_first)
        self.root.bind_all("e", self._on_shortcut_export)
        self.root.bind_all("E", self._on_shortcut_export)
        self.root.bind_all("i", self._on_shortcut_import)
        self.root.bind_all("I", self._on_shortcut_import)
        self.root.bind_all("a", self._on_shortcut_sort_alpha)
        self.root.bind_all("A", self._on_shortcut_sort_alpha)
        self.root.bind_all("s", self._on_shortcut_sort_latest)
        self.root.bind_all("S", self._on_shortcut_sort_latest)
        self.root.bind_all("d", self._on_shortcut_sort_oldest)
        self.root.bind_all("D", self._on_shortcut_sort_oldest)
        self.root.bind_all("f", self._on_shortcut_sort_modified)
        self.root.bind_all("F", self._on_shortcut_sort_modified)
        self.root.bind_all("<question>", self._on_shortcut_show_help)
        self.root.bind_all("<Shift-slash>", self._on_shortcut_show_help)
        self.root.bind("<question>", self._on_shortcut_show_help)
        self.root.bind("<Shift-slash>", self._on_shortcut_show_help)

    def _is_text_input_widget(self, widget):
        return isinstance(widget, (tk.Entry, tk.Text, ttk.Entry))

    def _should_ignore_single_key_shortcut(self, event):
        widget = getattr(event, "widget", None)
        return self._is_text_input_widget(widget)

    def _on_shortcut_new(self, _event):
        self._new_memo()
        return "break"

    def _on_shortcut_find(self, _event):
        self.search_entry.focus_set()
        self.search_entry.selection_range(0, tk.END)
        return "break"

    def _on_shortcut_focus_list_first(self, _event):
        if hasattr(self, "search_var"):
            self.search_var.set("")
            self._refresh_list()
        self.listbox.focus_set()
        if self.filtered_indices:
            self.listbox.selection_clear(0, tk.END)
            self.listbox.selection_set(0)
            self.listbox.activate(0)
            self.listbox.see(0)
        return "break"

    def _on_shortcut_show_help(self, event):
        if self._should_ignore_single_key_shortcut(event):
            return
        self._show_shortcuts()
        return "break"

    def _on_shortcut_export(self, event):
        if self._should_ignore_single_key_shortcut(event):
            return
        self._export_memos()
        return "break"

    def _on_shortcut_import(self, event):
        if self._should_ignore_single_key_shortcut(event):
            return
        self._import_memos()
        return "break"

    def _on_shortcut_sort_alpha(self, event):
        if self._should_ignore_single_key_shortcut(event):
            return
        self._set_sort_mode("alpha")
        return "break"

    def _on_shortcut_sort_latest(self, event):
        if self._should_ignore_single_key_shortcut(event):
            return
        self._set_sort_mode("latest")
        return "break"

    def _on_shortcut_sort_oldest(self, event):
        if self._should_ignore_single_key_shortcut(event):
            return
        self._set_sort_mode("oldest")
        return "break"

    def _on_shortcut_sort_modified(self, event):
        if self._should_ignore_single_key_shortcut(event):
            return
        self._set_sort_mode("modified")
        return "break"

    def _build_main_ui(self):
        frame = tk.Frame(self.root, bg=BG, padx=16, pady=14)
        frame.pack(fill="both", expand=True)

        # Header
        header = tk.Frame(frame, bg=BG)
        header.pack(fill="x", pady=(0, 14))

        left_tools = tk.Frame(header, bg=BG)
        left_tools.pack(side="left")

        def mk_top_btn(parent, text, cmd):
            return tk.Button(
                parent,
                text=text,
                command=cmd,
                bg=BORDER,
                fg=TEXT,
                font=("Malgun Gothic", 9),
                relief="flat",
                bd=0,
                cursor="hand2",
                padx=10,
                pady=4,
                activebackground="#C8CDD9",
                activeforeground=TEXT,
            )

        mk_top_btn(left_tools, "내보내기", self._export_memos).pack(side="left")
        mk_top_btn(left_tools, "불러오기", self._import_memos).pack(side="left", padx=(6, 0))

        sort_wrap = tk.Frame(header, bg=BG)
        sort_wrap.pack(side="right")

        def mk_sort_btn(parent, text, mode):
            btn = tk.Button(
                parent,
                text=text,
                command=lambda m=mode: self._set_sort_mode(m),
                bg=CARD,
                fg=SUBTEXT,
                font=("Malgun Gothic", 9),
                relief="flat",
                bd=0,
                cursor="hand2",
                width=8,
                pady=4,
                activebackground="#E8ECF6",
                activeforeground=TEXT,
            )
            return btn

        self.sort_buttons = {
            "alpha": mk_sort_btn(sort_wrap, "가나다순", "alpha"),
            "latest": mk_sort_btn(sort_wrap, "최신순", "latest"),
            "oldest": mk_sort_btn(sort_wrap, "오래된순", "oldest"),
            "modified": mk_sort_btn(sort_wrap, "수정순", "modified"),
        }
        self.sort_buttons["alpha"].pack(side="left")
        self.sort_buttons["latest"].pack(side="left", padx=(6, 0))
        self.sort_buttons["oldest"].pack(side="left", padx=(6, 0))
        self.sort_buttons["modified"].pack(side="left", padx=(6, 0))
        self._update_sort_buttons()

        # Search box with border effect
        search_wrap = tk.Frame(frame, bg=BORDER, padx=1, pady=1)
        search_wrap.pack(fill="x", pady=(0, 10))
        search_inner = tk.Frame(search_wrap, bg=CARD)
        search_inner.pack(fill="x")
        self.search_var = tk.StringVar()
        self.search_entry = tk.Entry(search_inner, textvariable=self.search_var,
                                      bg=CARD, fg=TEXT, insertbackground=ACCENT,
                                      relief="flat", bd=0, font=UI_FONT)
        self.search_entry.pack(fill="x", padx=12, pady=9)
        self.search_entry.bind("<KeyRelease>", self._on_search_changed)
        self.search_entry.bind("<Escape>", self._on_clear_search)
        self.search_entry.bind("<Up>", self._on_search_move_up)
        self.search_entry.bind("<Down>", self._on_search_move_down)
        self.search_entry.bind("<Return>", self._on_search_open_selected)
        self.search_entry.bind("<Delete>", self._on_search_delete_selected)
        self.search_entry.bind("<Control-f>", self._on_shortcut_find)
        self.search_entry.bind("<Control-F>", self._on_shortcut_find)
        self.search_entry.bind("<Control-n>", self._on_shortcut_new)
        self.search_entry.bind("<Control-N>", self._on_shortcut_new)

        # Listbox with border effect
        list_wrap = tk.Frame(frame, bg=BORDER, padx=1, pady=1)
        list_wrap.pack(fill="both", expand=True, pady=(0, 14))
        self.listbox = tk.Listbox(
            list_wrap, font=UI_FONT, activestyle="none",
            bg=CARD, fg=TEXT,
            selectbackground=SEL_BG, selectforeground=SEL_FG,
            borderwidth=0, highlightthickness=0,
            relief="flat", cursor="hand2",
        )
        self.listbox.pack(fill="both", expand=True)
        self.listbox.bind("<Double-Button-1>", self._on_open_selected)
        self.listbox.bind("<Return>", self._on_open_selected)
        self.listbox.bind("<Delete>", self._on_delete_selected)
        self.listbox.bind("<Up>", self._on_move_up)
        self.listbox.bind("<Down>", self._on_move_down)
        self.listbox.bind("<Control-f>", self._on_shortcut_find)
        self.listbox.bind("<Control-F>", self._on_shortcut_find)
        self.listbox.bind("<Control-n>", self._on_shortcut_new)
        self.listbox.bind("<Control-N>", self._on_shortcut_new)
        self.listbox.focus_set()

        # Buttons
        btn_row = tk.Frame(frame, bg=BG)
        btn_row.pack(fill="x")

        def mk_btn(parent, text, cmd, bg, fg="white", abg=None):
            return tk.Button(parent, text=text, command=cmd,
                             bg=bg, fg=fg, font=("Malgun Gothic", 10),
                             relief="flat", bd=0, cursor="hand2",
                             padx=14, pady=4,
                             activebackground=abg or bg,
                             activeforeground=fg)

        mk_btn(btn_row, "+ New", self._new_memo, ACCENT, abg=ACCENT_DK).pack(side="left")
        mk_btn(btn_row, "Open", self._open_selected, "#5C6BC0", abg="#4A5AB0").pack(side="left", padx=(8, 0))
        mk_btn(btn_row, "Delete", self._delete_selected, DEL_CLR, abg=DEL_DK).pack(side="left", padx=(8, 0))
        mk_btn(btn_row, "?", self._show_shortcuts, BORDER, fg=SUBTEXT, abg="#C8CDD9").pack(side="right")

    def _show_shortcuts(self):
        text = (
            "Shortcuts\n\n"
            "Main list\n"
            "- Up/Down: Move selection\n"
            "- Enter: Open memo\n"
            "- Delete: Delete selected memo\n"
            "- Ctrl+N: New memo\n"
            "- Auto-save: Add/Edit/Delete is saved automatically\n\n"
            "- Ctrl+F: Focus search\n"
            "- E: Export memos\n"
            "- I: Import memos\n"
            "- A: Sort 가나다순\n"
            "- S: Sort 최신순\n"
            "- D: Sort 오래된순\n"
            "- F: Sort 수정순\n\n"
            "Search box\n"
            "- Up/Down: Move selected result\n"
            "- Enter: Open selected result\n\n"
            "- /: Clear search and focus first memo\n\n"
            "- ?: Open this help\n\n"
            "Memo popup\n"
            "- Esc: Close memo"
        )
        messagebox.showinfo("Shortcuts", text)

    def _on_search_changed(self, _event=None):
        self._refresh_list()

    def _on_clear_search(self, _event=None):
        self.search_var.set("")
        self._refresh_list()
        self.listbox.focus_set()
        return "break"

    def _on_search_move_up(self, _event=None):
        return self._move_selection(-1)

    def _on_search_move_down(self, _event=None):
        return self._move_selection(1)

    def _on_search_open_selected(self, _event=None):
        self._open_selected()
        return "break"

    def _on_search_delete_selected(self, _event=None):
        self._delete_selected()
        return "break"

    def _focus_main_list(self):
        self.listbox.focus_set()
        if self.filtered_indices and not self.listbox.curselection():
            self.listbox.selection_set(0)
            self.listbox.activate(0)
            self.listbox.see(0)

    def _memo_title(self, memo):
        title = memo.get("title", "").strip()
        if title:
            return title
        content = memo.get("content", "").strip()
        if content:
            first_line = content.splitlines()[0].strip()
            return first_line[:25] if first_line else "Untitled"
        return "Untitled"

    def _memo_sort_timestamp(self, memo):
        created_at = memo.get("created_at")
        if isinstance(created_at, (int, float)):
            return float(created_at)
        memo_id = memo.get("id")
        if isinstance(memo_id, int):
            return float(memo_id)
        return 0.0

    def _memo_modified_timestamp(self, memo):
        updated_at = memo.get("updated_at")
        if isinstance(updated_at, (int, float)):
            return float(updated_at)
        return self._memo_sort_timestamp(memo)

    def _set_sort_mode(self, mode):
        if mode not in ("alpha", "latest", "oldest", "modified"):
            return
        self.sort_mode = mode
        self._update_sort_buttons()
        self._refresh_list()

    def _export_memos(self):
        path = filedialog.asksaveasfilename(
            parent=self.root,
            title="메모 내보내기",
            defaultextension=".json",
            filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")],
            initialfile="memos_export.json",
        )
        if not path:
            return

        self._save_all_now()
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.memos, f, ensure_ascii=False, indent=2)
            messagebox.showinfo("내보내기", "메모를 내보냈습니다.")
        except OSError:
            messagebox.showerror("오류", "파일 저장에 실패했습니다.")

    def _import_memos(self):
        path = filedialog.askopenfilename(
            parent=self.root,
            title="메모 불러오기",
            filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")],
        )
        if not path:
            return

        ok = messagebox.askyesno("불러오기", "현재 메모를 대체하고 불러올까요?")
        if not ok:
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            messagebox.showerror("오류", "유효한 JSON 파일을 읽지 못했습니다.")
            return

        if not isinstance(data, list):
            messagebox.showerror("오류", "메모 형식이 올바르지 않습니다.")
            return

        # Close all currently open memo windows before replacing memo data.
        for win in list(self.open_windows.values()):
            try:
                if win.winfo_exists():
                    win.destroy()
            except tk.TclError:
                pass
        self.open_windows.clear()
        self.pending_save_job.clear()
        self.save_callbacks.clear()

        self.memos = data
        self._save_memos()
        self._refresh_list()
        messagebox.showinfo("불러오기", "메모를 불러왔습니다.")

    def _update_sort_buttons(self):
        if not self.sort_buttons:
            return
        for mode, button in self.sort_buttons.items():
            is_active = mode == self.sort_mode
            if is_active:
                button.configure(
                    bg=ACCENT,
                    fg="white",
                    activebackground=ACCENT_DK,
                    activeforeground="white",
                )
            else:
                button.configure(
                    bg=CARD,
                    fg=SUBTEXT,
                    activebackground="#E8ECF6",
                    activeforeground=TEXT,
                )

    def _load_memos(self):
        if not os.path.exists(DATA_FILE):
            self.memos = []
            return

        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                self.memos = data
            else:
                self.memos = []
        except (OSError, json.JSONDecodeError):
            messagebox.showwarning("Warning", "Failed to load memos file. Starting with empty list.")
            self.memos = []

    def _save_memos(self):
        try:
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(self.memos, f, ensure_ascii=False, indent=2)
        except OSError:
            messagebox.showerror("Error", "Failed to save memos.")

    def _save_all_now(self):
        for save_fn in list(self.save_callbacks.values()):
            try:
                save_fn()
            except tk.TclError:
                pass
        self._save_memos()

    def _refresh_list(self):
        selected_map_index = None
        selected = self.listbox.curselection()
        if selected:
            selected_map_index = selected[0]

        query = self.search_var.get().strip().lower() if hasattr(self, "search_var") else ""

        self.listbox.delete(0, tk.END)
        self.filtered_indices = []

        matching_indices = []
        for i, memo in enumerate(self.memos):
            title = memo.get("title", "")
            content = memo.get("content", "")
            haystack = f"{title}\n{content}".lower()
            if query and query not in haystack:
                continue

            matching_indices.append(i)

        if self.sort_mode == "alpha":
            matching_indices.sort(key=lambda idx: self._memo_title(self.memos[idx]).casefold())
        elif self.sort_mode == "oldest":
            matching_indices.sort(key=lambda idx: self._memo_sort_timestamp(self.memos[idx]))
        elif self.sort_mode == "modified":
            matching_indices.sort(key=lambda idx: self._memo_modified_timestamp(self.memos[idx]), reverse=True)
        else:  # latest
            matching_indices.sort(key=lambda idx: self._memo_sort_timestamp(self.memos[idx]), reverse=True)

        for i in matching_indices:
            memo = self.memos[i]
            self.filtered_indices.append(i)
            self.listbox.insert(tk.END, self._memo_title(memo))

        if self.filtered_indices:
            if selected_map_index is None:
                new_index = 0
            else:
                new_index = max(0, min(len(self.filtered_indices) - 1, selected_map_index))
            self.listbox.selection_set(new_index)
            self.listbox.activate(new_index)
            self.listbox.see(new_index)

    def _generate_memo_id(self):
        used = {m.get("id") for m in self.memos}
        next_id = 1
        while next_id in used:
            next_id += 1
        return next_id

    def _ask_new_title(self):
        """Show a styled dialog for new memo title. Returns str or None."""
        result = [None]
        dlg = tk.Toplevel(self.root)
        dlg.title("")
        dlg.resizable(False, False)
        dlg.configure(bg=CARD)
        dlg.attributes("-topmost", True)
        dlg.grab_set()

        # Center relative to root
        self.root.update_idletasks()
        rx, ry = self.root.winfo_x(), self.root.winfo_y()
        rw, rh = self.root.winfo_width(), self.root.winfo_height()
        dw, dh = 360, 240
        dlg.geometry(f"{dw}x{dh}+{rx + (rw - dw)//2}+{ry + (rh - dh)//2}")

        tk.Frame(dlg, bg=ACCENT, height=3).pack(fill="x")

        body = tk.Frame(dlg, bg=CARD, padx=20, pady=16)
        body.pack(fill="both", expand=True)

        tk.Label(body, text="새 메모", font=("Malgun Gothic", 12, "bold"),
                 bg=CARD, fg=TEXT).pack(anchor="w")
        tk.Label(body, text="제목 (비워도 됩니다)", font=("Malgun Gothic", 9),
                 bg=CARD, fg=SUBTEXT).pack(anchor="w", pady=(2, 8))

        entry_wrap = tk.Frame(body, bg=BORDER, padx=1, pady=1)
        entry_wrap.pack(fill="x")
        var = tk.StringVar()
        entry = tk.Entry(entry_wrap, textvariable=var,
                         bg=CARD, fg=TEXT, insertbackground=ACCENT,
                         relief="flat", bd=0, font=UI_FONT)
        entry.pack(fill="x", padx=10, pady=7)
        entry.focus_set()

        btn_row = tk.Frame(body, bg=CARD)
        btn_row.pack(fill="x", pady=(10, 0))

        def confirm():
            result[0] = var.get()
            dlg.destroy()

        def cancel():
            dlg.destroy()

        tk.Button(btn_row, text="확인", command=confirm,
                  bg=ACCENT, fg="white", font=("Malgun Gothic", 10),
                  relief="flat", bd=0, padx=16, pady=6,
                  activebackground=ACCENT_DK, activeforeground="white",
                  cursor="hand2").pack(side="right")
        tk.Button(btn_row, text="취소", command=cancel,
                  bg=BORDER, fg=SUBTEXT, font=("Malgun Gothic", 10),
                  relief="flat", bd=0, padx=16, pady=6,
                  activebackground="#C8CDD9", activeforeground=SUBTEXT,
                  cursor="hand2").pack(side="right", padx=(0, 8))

        entry.bind("<Return>", lambda _e: confirm())
        entry.bind("<Escape>", lambda _e: cancel())
        dlg.protocol("WM_DELETE_WINDOW", cancel)
        dlg.wait_window()
        return result[0]

    def _new_memo(self):
        title = self._ask_new_title()
        if title is None:
            return

        memo = {
            "id": self._generate_memo_id(),
            "title": title.strip(),
            "content": "",
            "geometry": "460x380+120+120",
            "created_at": time.time(),
            "updated_at": time.time(),
        }
        self.memos.append(memo)
        self._save_memos()
        self._refresh_list()

        self._open_memo_window(memo, focus_content=True)

    def _get_selected_memo(self):
        selected = self.listbox.curselection()
        if not selected:
            return None
        map_index = selected[0]
        if map_index < 0 or map_index >= len(self.filtered_indices):
            return None
        memo_index = self.filtered_indices[map_index]
        if memo_index < 0 or memo_index >= len(self.memos):
            return None
        return self.memos[memo_index]

    def _on_open_selected(self, _event):
        self._open_selected(focus_content=True)

    def _on_delete_selected(self, _event):
        self._delete_selected()

    def _move_selection(self, delta):
        if not self.filtered_indices:
            return "break"

        selected = self.listbox.curselection()
        if not selected:
            index = 0
        else:
            index = selected[0] + delta

        index = max(0, min(len(self.filtered_indices) - 1, index))
        self.listbox.selection_clear(0, tk.END)
        self.listbox.selection_set(index)
        self.listbox.activate(index)
        self.listbox.see(index)
        return "break"

    def _on_move_up(self, _event):
        return self._move_selection(-1)

    def _on_move_down(self, _event):
        return self._move_selection(1)

    def _open_selected(self, focus_content=False):
        memo = self._get_selected_memo()
        if not memo:
            return
        self._open_memo_window(memo, focus_content=focus_content)

    def _delete_selected(self):
        memo = self._get_selected_memo()
        if not memo:
            return

        ok = messagebox.askyesno("Delete", "Delete selected memo?")
        if not ok:
            return

        memo_id = memo["id"]
        self.memos = [m for m in self.memos if m.get("id") != memo_id]

        if memo_id in self.open_windows:
            window = self.open_windows[memo_id]
            if window.winfo_exists():
                window.destroy()
            self.open_windows.pop(memo_id, None)

        self._save_memos()
        self._refresh_list()

    def _open_memo_window(self, memo, focus_content=False):
        memo_id = memo["id"]

        if memo_id in self.open_windows and self.open_windows[memo_id].winfo_exists():
            win = self.open_windows[memo_id]
            win.deiconify()
            win.lift()
            win.focus_force()
            if focus_content:
                for child in win.winfo_children():
                    for grandchild in child.winfo_children():
                        if isinstance(grandchild, tk.Text):
                            grandchild.focus_set()
                            grandchild.mark_set("insert", "end-1c")
                            return
            return

        win = tk.Toplevel(self.root)
        win.title(self._memo_title(memo))
        win.geometry(memo.get("geometry", "460x380+140+140"))
        win.minsize(420, 320)
        win.attributes("-topmost", True)
        win.configure(bg=CARD)
        _apply_window_icon(win)

        # Accent top strip
        tk.Frame(win, bg=ACCENT, height=3).pack(fill="x")

        container = tk.Frame(win, bg=CARD, padx=14, pady=12)
        container.pack(fill="both", expand=True)

        title_var = tk.StringVar(value=memo.get("title", ""))
        title_entry = tk.Entry(container, textvariable=title_var,
                               bg=CARD, fg=TEXT, insertbackground=ACCENT,
                               relief="flat", bd=0,
                               font=("Malgun Gothic", 12, "bold"))
        title_entry.pack(fill="x")

        # Divider
        tk.Frame(container, bg=BORDER, height=1).pack(fill="x", pady=(6, 8))

        text = tk.Text(container, wrap="word", font=UI_FONT,
                       bg=CARD, fg=TEXT, insertbackground=ACCENT,
                       relief="flat", bd=0,
                       selectbackground=SEL_BG, selectforeground=SEL_FG,
                       spacing1=2, spacing3=2, padx=2)
        text.pack(fill="both", expand=True)
        text.insert("1.0", memo.get("content", ""))

        def schedule_save(_event=None):
            job = self.pending_save_job.get(memo_id)
            if job is not None:
                try:
                    win.after_cancel(job)
                except tk.TclError:
                    pass
            self.pending_save_job[memo_id] = win.after(AUTOSAVE_DELAY_MS, save_now)

        def save_now():
            self.pending_save_job[memo_id] = None
            old_title = self._memo_title(memo)
            memo["title"] = title_var.get().strip()
            memo["content"] = text.get("1.0", "end-1c")
            memo["geometry"] = win.geometry()
            memo["updated_at"] = time.time()

            new_title = self._memo_title(memo)
            win.title(new_title)
            self._save_memos()

            query = self.search_var.get().strip() if hasattr(self, "search_var") else ""
            if query or old_title != new_title:
                self._refresh_list()

        def on_close():
            save_now()
            self.open_windows.pop(memo_id, None)
            self.pending_save_job.pop(memo_id, None)
            self.save_callbacks.pop(memo_id, None)
            win.destroy()
            self.root.after_idle(self._focus_main_list)

        title_entry.bind("<KeyRelease>", schedule_save)
        text.bind("<KeyRelease>", schedule_save)
        win.bind("<Configure>", schedule_save)
        win.bind("<Escape>", lambda _event: on_close())
        win.protocol("WM_DELETE_WINDOW", on_close)

        self.open_windows[memo_id] = win
        self.save_callbacks[memo_id] = save_now

        win.lift()
        win.focus_force()
        if focus_content:
            win.after_idle(lambda: (text.focus_set(), text.mark_set("insert", "end-1c")))


def main():
    # --- 고해상도(High DPI) 대응 코드 추가 ---
    if os.name == "nt":  # Windows일 경우에만 실행
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)  # DPI 인식을 활성화
        except Exception:
            ctypes.windll.user32.SetProcessDPIAware()  # 구버전 Windows 대응
    # ---------------------------------------

    _setup_windows_taskbar_id()
    root = tk.Tk()
    app = StickyMemoApp(root)
    root.mainloop()
    


if __name__ == "__main__":
    main()