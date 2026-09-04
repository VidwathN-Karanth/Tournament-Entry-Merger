"""Three colour-coded drop zones over the merge pipeline (plan section 5)."""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from pipeline.config import Config, Platform, asset_path, load_config
from pipeline.merger import MergeResult, merge_sources
from pipeline.writer import WriteError, write_xlsx

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD

    DND_AVAILABLE = True
except ImportError:  # the app still works via the Add files button
    DND_FILES = None
    TkinterDnD = None
    DND_AVAILABLE = False

APP_TITLE = "Tournament Entry Merger"
APP_TAGLINE = "Merge chess tournament entries into one Swiss Manager-ready sheet."
CREDIT = "Developed by Vidwath N Karanth"
BG = "#F4F5F7"
INK = "#22272E"
MUTED = "#6B7280"
ACCEPTED = {".csv", ".xlsx", ".xlsm", ".xls"}


class DropZone(ttk.Frame):
    """One platform's box: accepts files, lists them, allows removal."""

    def __init__(self, master: tk.Misc, platform: Platform, on_change) -> None:
        super().__init__(master, padding=0)
        self.platform = platform
        self.on_change = on_change
        self.paths: list[Path] = []

        self.outer = tk.Frame(
            self,
            bg=platform.ui_color,
            highlightbackground=platform.ui_border,
            highlightthickness=2,
            bd=0,
        )
        self.outer.pack(fill="both", expand=True)

        header = tk.Frame(self.outer, bg=platform.ui_border)
        header.pack(fill="x")
        tk.Label(
            header,
            text=f"{platform.name}  ({platform.abbrev})",
            bg=platform.ui_border,
            fg="white",
            font=("Segoe UI", 11, "bold"),
            pady=6,
        ).pack()

        self.hint = tk.Label(
            self.outer,
            text=self._idle_hint(),
            bg=platform.ui_color,
            fg=MUTED,
            font=("Segoe UI", 9),
            pady=10,
        )
        self.hint.pack(fill="x")

        self.files_frame = tk.Frame(self.outer, bg=platform.ui_color)
        self.files_frame.pack(fill="both", expand=True, padx=8)

        tk.Button(
            self.outer,
            text="+ Add files",
            command=self.browse,
            relief="flat",
            bg="white",
            fg=platform.ui_border,
            activebackground="white",
            font=("Segoe UI", 9, "bold"),
            cursor="hand2",
            pady=4,
        ).pack(fill="x", padx=8, pady=8)

        if DND_AVAILABLE:
            for widget in (self.outer, self.hint, self.files_frame):
                widget.drop_target_register(DND_FILES)
                widget.dnd_bind("<<Drop>>", self._on_drop)
                widget.dnd_bind("<<DragEnter>>", self._on_drag_enter)
                widget.dnd_bind("<<DragLeave>>", self._on_drag_leave)

    # -- file list -----------------------------------------------------

    def _idle_hint(self) -> str:
        lead = "Drop files here" if DND_AVAILABLE else "Add files below"
        return lead + "\n.csv or .xlsx"

    def browse(self) -> None:
        chosen = filedialog.askopenfilenames(
            title=f"Choose {self.platform.name} file(s)",
            filetypes=[
                ("Entry exports", "*.csv *.xlsx *.xlsm *.xls"),
                ("All files", "*.*"),
            ],
        )
        self.add(chosen)

    def add(self, paths) -> None:
        skipped = []
        for raw in paths:
            path = Path(str(raw))
            if path.suffix.lower() not in ACCEPTED:
                skipped.append(path.name)
                continue
            if path not in self.paths:
                self.paths.append(path)
        if skipped:
            messagebox.showwarning(
                APP_TITLE,
                "Ignored (not a .csv or .xlsx file):\n  " + "\n  ".join(skipped),
            )
        self.refresh()

    def remove(self, path: Path) -> None:
        self.paths = [p for p in self.paths if p != path]
        self.refresh()

    def refresh(self) -> None:
        for child in self.files_frame.winfo_children():
            child.destroy()

        for path in self.paths:
            row = tk.Frame(self.files_frame, bg="white")
            row.pack(fill="x", pady=2)
            tk.Label(
                row,
                text=path.name,
                bg="white",
                fg=INK,
                font=("Segoe UI", 9),
                anchor="w",
                padx=6,
            ).pack(side="left", fill="x", expand=True)
            tk.Button(
                row,
                text="✕",
                command=lambda p=path: self.remove(p),
                relief="flat",
                bg="white",
                fg=MUTED,
                activebackground="white",
                cursor="hand2",
                bd=0,
            ).pack(side="right")

        count = len(self.paths)
        if count:
            plural = "" if count == 1 else "s"
            self.hint.config(text=f"{count} file{plural} loaded")
        else:
            self.hint.config(text=self._idle_hint())
        self.on_change()

    # -- drag and drop -------------------------------------------------

    def _on_drop(self, event):
        self._on_drag_leave(event)
        self.add(self.tk.splitlist(event.data))
        return event.action

    def _on_drag_enter(self, event):
        self.outer.config(highlightthickness=4)
        return event.action

    def _on_drag_leave(self, event):
        self.outer.config(highlightthickness=2)
        return event.action


class App:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.root = TkinterDnD.Tk() if DND_AVAILABLE else tk.Tk()
        self.root.title(APP_TITLE)
        self.root.geometry("980x680")
        self.root.minsize(860, 600)
        self.root.configure(bg=BG)
        self._set_icon()

        self.output_path: Path | None = None
        self.previous_path: Path | None = None
        self.queue: queue.Queue = queue.Queue()

        self._build()
        self._sync_button()

    def _set_icon(self) -> None:
        """Replace Tk's default feather with the chess pawn."""
        icon = asset_path("pawn.ico")
        if not icon.exists():
            return
        try:
            self.root.iconbitmap(default=str(icon))
        except tk.TclError:
            pass  # a missing or unreadable icon is never worth failing over

    # -- layout --------------------------------------------------------

    def _build(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TFrame", background=BG)

        tk.Label(
            self.root,
            text=APP_TITLE,
            bg=BG,
            fg=INK,
            font=("Segoe UI", 16, "bold"),
        ).pack(anchor="w", padx=20, pady=(16, 0))
        tk.Label(
            self.root,
            text=APP_TAGLINE,
            bg=BG,
            fg=MUTED,
            font=("Segoe UI", 10),
        ).pack(anchor="w", padx=20, pady=(0, 12))

        zones = ttk.Frame(self.root)
        zones.pack(fill="both", expand=True, padx=16)

        self.zones: dict[str, DropZone] = {}
        for index, platform in enumerate(self.cfg.platform_list):
            zones.columnconfigure(index, weight=1, uniform="zone")
            zone = DropZone(zones, platform, self._sync_button)
            zone.grid(row=0, column=index, sticky="nsew", padx=6)
            self.zones[platform.key] = zone
        zones.rowconfigure(0, weight=1)

        previous_bar = tk.Frame(self.root, bg=BG)
        previous_bar.pack(fill="x", padx=22, pady=(14, 0))
        tk.Button(
            previous_bar,
            text="Import previous merged list...",
            command=self.choose_previous,
            relief="flat",
            bg="white",
            fg=INK,
            cursor="hand2",
            padx=12,
            pady=6,
        ).pack(side="left")
        self.previous_label = tk.Label(
            previous_bar,
            text="Optional - leave empty and every player is marked NEW",
            bg=BG,
            fg=MUTED,
            font=("Segoe UI", 9),
        )
        self.previous_label.pack(side="left", padx=10)
        self.previous_clear = tk.Button(
            previous_bar,
            text="✕",
            command=self.clear_previous,
            relief="flat",
            bg=BG,
            fg=MUTED,
            activebackground=BG,
            cursor="hand2",
            bd=0,
        )

        bar = tk.Frame(self.root, bg=BG)
        bar.pack(fill="x", padx=22, pady=(8, 4))
        tk.Button(
            bar,
            text="Choose output location...",
            command=self.choose_output,
            relief="flat",
            bg="white",
            fg=INK,
            cursor="hand2",
            padx=12,
            pady=6,
        ).pack(side="left")
        self.output_label = tk.Label(
            bar, text="No output file chosen", bg=BG, fg=MUTED, font=("Segoe UI", 9)
        )
        self.output_label.pack(side="left", padx=10)

        self.merge_button = tk.Button(
            bar,
            text="Merge & Export",
            command=self.merge,
            relief="flat",
            bg="#2F6FEB",
            fg="white",
            activebackground="#2559C0",
            activeforeground="white",
            disabledforeground="#C9CDD3",
            font=("Segoe UI", 10, "bold"),
            cursor="hand2",
            padx=18,
            pady=7,
        )
        self.merge_button.pack(side="right")

        self.progress = ttk.Progressbar(self.root, mode="determinate", maximum=100)
        self.progress.pack(fill="x", padx=22, pady=(4, 2))

        self.summary = tk.Text(
            self.root,
            height=8,
            bg="white",
            fg=INK,
            font=("Consolas", 9),
            relief="flat",
            wrap="word",
            state="disabled",
            padx=10,
            pady=8,
        )
        self.summary.pack(fill="both", padx=22, pady=(4, 2))

        tk.Label(
            self.root,
            text=CREDIT,
            bg=BG,
            fg=MUTED,
            font=("Segoe UI", 9, "italic"),
            anchor="e",
        ).pack(fill="x", padx=24, pady=(0, 12))

    # -- state ---------------------------------------------------------

    def _any_files(self) -> bool:
        return any(zone.paths for zone in self.zones.values())

    def _sync_button(self) -> None:
        ready = self._any_files() and self.output_path is not None
        self.merge_button.config(state="normal" if ready else "disabled")

    def _log(self, text: str) -> None:
        self.summary.config(state="normal")
        self.summary.delete("1.0", "end")
        self.summary.insert("1.0", text)
        self.summary.config(state="disabled")

    def choose_previous(self) -> None:
        chosen = filedialog.askopenfilename(
            title="Choose the merged list you exported previously",
            filetypes=[("Excel workbook", "*.xlsx *.xlsm *.xls"), ("All files", "*.*")],
        )
        if chosen:
            self.previous_path = Path(chosen)
            self.previous_label.config(text=self.previous_path.name, fg=INK)
            self.previous_clear.pack(side="left")

    def clear_previous(self) -> None:
        self.previous_path = None
        self.previous_label.config(
            text="Optional - leave empty and every player is marked NEW", fg=MUTED
        )
        self.previous_clear.pack_forget()

    def choose_output(self) -> None:
        chosen = filedialog.asksaveasfilename(
            title="Save merged entries as",
            defaultextension=".xlsx",
            initialfile="MergedEntries.xlsx",
            filetypes=[("Excel workbook", "*.xlsx")],
        )
        if chosen:
            self.output_path = Path(chosen)
            self.output_label.config(text=str(self.output_path), fg=INK)
        self._sync_button()

    # -- merge ---------------------------------------------------------

    def merge(self) -> None:
        if not self._any_files() or self.output_path is None:
            return
        sources = {key: list(zone.paths) for key, zone in self.zones.items()}
        self.merge_button.config(state="disabled")
        self.progress.config(value=0)
        self._log("Working...")

        threading.Thread(
            target=self._worker,
            args=(sources, self.output_path, self.previous_path),
            daemon=True,
        ).start()
        self.root.after(60, self._drain)

    def _worker(self, sources, output: Path, previous: Path | None) -> None:
        try:
            result = merge_sources(
                sources,
                self.cfg,
                progress=lambda msg, frac: self.queue.put(("progress", (msg, frac))),
                previous=previous,
            )
            if result.frame.empty and result.errors:
                self.queue.put(("done", (result, None)))
                return
            write_xlsx(result.frame, output, self.cfg)
            self.queue.put(("done", (result, output)))
        except WriteError as exc:
            self.queue.put(("failed", str(exc)))
        except Exception as exc:  # never leave the UI stuck on "Working..."
            self.queue.put(("failed", f"Unexpected error: {exc}"))

    def _drain(self) -> None:
        pending = True
        while True:
            try:
                kind, payload = self.queue.get_nowait()
            except queue.Empty:
                break
            if kind == "progress":
                message, fraction = payload
                self.progress.config(value=fraction * 100)
                self._log(f"{message}...")
            elif kind == "done":
                result, output = payload
                self.progress.config(value=100)
                self._show_result(result, output)
                pending = False
            elif kind == "failed":
                self.progress.config(value=0)
                self._log(payload)
                messagebox.showerror(APP_TITLE, payload)
                pending = False
        if pending:
            self.root.after(60, self._drain)
        else:
            self._sync_button()

    def _show_result(self, result: MergeResult, output: Path | None) -> None:
        stats = result.stats
        lines = []
        for platform in self.cfg.output_platform_list:
            rows = stats.rows_by_platform.get(platform.abbrev, 0)
            dropped = stats.dropped_by_platform.get(platform.abbrev, 0)
            lines.append(
                f"{platform.name:<14}{rows:>5} rows in{dropped:>6} duplicate(s) dropped"
            )
        lines.append("")
        lines.append(f"{'Merged total':<14}{stats.final_rows:>5} rows")
        if result.baseline is not None:
            lines.append(
                f"{'Previous list':<14}{result.baseline.rows:>5} rows "
                f"({result.baseline.path.name})"
            )
            lines.append(
                f"{'NEW (green)':<14}{stats.new_rows:>5} to enter in Swiss Manager"
            )
            lines.append(f"{'Already in':<14}{stats.existing_rows:>5} rows")
        else:
            lines.append(
                f"{'NEW (green)':<14}{stats.new_rows:>5} "
                "- no previous list, so every player is new"
            )
        if output:
            lines.append(f"\nSaved to {output}")

        if stats.shared_ids:
            lines.append("")
            lines.append(
                f"Shared IDs    {len(stats.shared_ids)} pair(s) kept "
                "- same ID, different DOB:"
            )
            for shared in stats.shared_ids[:6]:
                lines.append(
                    f"  {shared.names[0]} / {shared.names[1]} "
                    f"({shared.column} {shared.value})"
                )
            if len(stats.shared_ids) > 6:
                lines.append(f"  ... and {len(stats.shared_ids) - 6} more")

        if result.baseline_error:
            lines.append(f"\nPrevious list not used: {result.baseline_error}")
        for report in result.warnings:
            lines.append(
                f"\nNote: {report.path.name} had no "
                f"{', '.join(report.missing_columns)} column - left blank."
            )
        self._log("\n".join(lines))

        if result.baseline_error:
            messagebox.showerror(
                APP_TITLE,
                "The previous merged list could not be used, so every player "
                f"has been marked NEW:\n\n{result.baseline_error}",
            )
        if result.errors:
            detail = "\n\n".join(f"{r.path.name}:\n{r.error}" for r in result.errors)
            messagebox.showerror(APP_TITLE, f"Some files could not be used:\n\n{detail}")
        elif output and not result.baseline_error:
            messagebox.showinfo(
                APP_TITLE,
                f"Merged {stats.final_rows} rows "
                f"({stats.total_dropped} duplicate(s) dropped).\n\n"
                f"{stats.new_rows} marked NEW (green).\n\nSaved to {output}",
            )

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    App(load_config()).run()


if __name__ == "__main__":
    main()
