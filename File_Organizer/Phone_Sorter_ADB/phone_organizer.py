"""
Phone File Organizer  -  Android over USB (ADB)

1. Connect phone      : detects the USB device and shows connected / authorized state
2. Browse folders     : GUI folder picker for the phone's storage (DCIM, Pictures, Download, ...)
3. Scan folder        : recursive scan with progress, categorizes files, hashes possible duplicates
4. Organize files     : preview every destination, then confirm moves (no overwriting, names kept)
5. Clean duplicates   : groups by exact content (MD5), review full paths, explicit confirm to delete

Requirements
  * Python 3.8+ (Tkinter included on Windows/macOS; on Linux: sudo apt install python3-tk)                                                   
  * Android platform-tools (adb) on your PATH
      https://developer.android.com/tools/releases/platform-tools
  * On the phone: Settings > About phone > tap "Build number" 7x  -> Developer options
                  Developer options > enable "USB debugging"
                  Plug in USB and tap "Allow" on the phone's prompt.

Run:  python phone_organizer.py
"""

import posixpath
import queue
import shlex
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
from collections import defaultdict
from tkinter import messagebox, ttk

import os


def find_adb():
    """Find adb: PATH first, then common install spots (incl. a platform-tools folder next to this file)."""
    found = shutil.which("adb")
    if found:
        return found
    here = os.path.dirname(os.path.abspath(__file__))
    exe = "adb.exe" if sys.platform == "win32" else "adb"
    spots = [os.path.join(here, "platform-tools", exe), os.path.join(here, exe),
             os.path.join(os.environ.get("LOCALAPPDATA", ""), "Android", "Sdk", "platform-tools", exe),
             os.path.join("C:\\", "platform-tools", exe),
             os.path.expanduser(os.path.join("~", "Library", "Android", "sdk", "platform-tools", exe))]
    return next((s for s in spots if os.path.isfile(s)), "adb")


ADB = find_adb()
DEFAULT_ROOT = "/storage/emulated/0"          # the phone's "Internal storage"
QUICK_FOLDERS = ["DCIM", "Pictures", "Download", "Documents", "Movies", "Music"]
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0

CATEGORIES = {
    "Images":    {"jpg", "jpeg", "png", "gif", "webp", "heic", "heif", "bmp", "dng", "tif", "tiff"},
    "Videos":    {"mp4", "mkv", "mov", "avi", "3gp", "webm", "m4v", "ts"},
    "Audio":     {"mp3", "m4a", "aac", "wav", "flac", "ogg", "opus", "amr", "wma"},
    "Documents": {"pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "txt", "csv",
                  "odt", "ods", "odp", "rtf", "md", "epub"},
    "Archives":  {"zip", "rar", "7z", "tar", "gz", "bz2", "xz"},
    "Apps":      {"apk", "apks", "xapk"},
}
ALL_CATS = list(CATEGORIES) + ["Other"]
ON, OFF = "☑", "☐"
q = shlex.quote


def category_of(path):
    ext = posixpath.splitext(path)[1].lower().lstrip(".")
    for cat, exts in CATEGORIES.items():
        if ext in exts:
            return cat
    return "Other"


def human(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024


def unique_path(folder, name, taken_lower):
    """Return folder/name, or folder/'name (1).ext' etc. if that name is taken.
    Android shared storage is case-insensitive, so compare lowercase."""
    base, ext = posixpath.splitext(name)
    cand, n = posixpath.join(folder, name), 1
    while cand.lower() in taken_lower:
        cand = posixpath.join(folder, f"{base} ({n}){ext}")
        n += 1
    return cand


def batches(recs, max_files=40, max_chars=6000):
    batch, length = [], 0
    for r in recs:
        size = len(r.path) + 3
        if batch and (len(batch) >= max_files or length + size > max_chars):
            yield batch
            batch, length = [], 0
        batch.append(r)
        length += size
    if batch:
        yield batch


class AdbError(Exception):
    pass


class FileRec:
    __slots__ = ("path", "size", "hash", "checked")

    def __init__(self, path, size):
        self.path, self.size, self.hash, self.checked = path, size, None, False

    @property
    def name(self):
        return posixpath.basename(self.path)

    @property
    def cat(self):
        return category_of(self.path)


class Adb:
    def __init__(self):
        self.serial = None

    def _exec(self, args, timeout):
        try:
            p = subprocess.run(args, capture_output=True, timeout=timeout, creationflags=NO_WINDOW)
        except FileNotFoundError:
            raise AdbError("adb not found. Install Android platform-tools and add it to PATH.")
        except subprocess.TimeoutExpired:
            raise AdbError("adb timed out.")
        return p.returncode, p.stdout.decode("utf-8", "replace"), p.stderr.decode("utf-8", "replace")

    def shell(self, cmd, timeout=120):
        base = [ADB] + (["-s", self.serial] if self.serial else [])
        return self._exec(base + ["shell", cmd], timeout)

    def devices(self):
        _, out, _ = self._exec([ADB, "devices", "-l"], 20)
        devs = []
        for line in out.splitlines()[1:]:
            parts = line.split()
            if len(parts) < 2:
                continue
            state = "no permissions" if parts[1] == "no" else parts[1]
            model = next((p.split(":", 1)[1].replace("_", " ") for p in parts if p.startswith("model:")), "")
            devs.append({"serial": parts[0], "state": state, "model": model})
        return devs


# --------------------------------------------------------------------------- folder picker
class FolderPicker(tk.Toplevel):
    def __init__(self, master, adb, on_pick):
        super().__init__(master)
        self.title("Browse phone storage")
        self.geometry("560x540")
        self.transient(master)
        self.adb, self.on_pick = adb, on_pick

        quick = ttk.Frame(self)
        quick.pack(fill="x", padx=8, pady=(8, 4))
        ttk.Label(quick, text="Jump to:").pack(side="left")
        for name in QUICK_FOLDERS:
            ttk.Button(quick, text=name, width=9,
                       command=lambda n=name: self.go(posixpath.join(DEFAULT_ROOT, n))).pack(side="left", padx=1)

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True, padx=8)
        self.tree = ttk.Treeview(body, show="tree", selectmode="browse")
        sb = ttk.Scrollbar(body, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewOpen>>", self.on_open)
        self.tree.bind("<<TreeviewSelect>>", lambda e: self.sel_var.set(self.selected() or ""))
        self.tree.bind("<Double-1>", lambda e: self.after(50, self.pick) if not self.tree.get_children(self.selected() or "") else None)

        bottom = ttk.Frame(self)
        bottom.pack(fill="x", padx=8, pady=8)
        self.sel_var = tk.StringVar()
        ttk.Label(bottom, textvariable=self.sel_var, foreground="#555").pack(side="left", fill="x", expand=True)
        ttk.Button(bottom, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(bottom, text="Select this folder", command=self.pick).pack(side="right", padx=4)

        self.tree.insert("", "end", iid=DEFAULT_ROOT, text="📱 Internal storage", open=True)
        if not self.add_children(DEFAULT_ROOT):
            messagebox.showwarning("Empty", "Could not list the phone's storage. Is it unlocked and authorized?", parent=self)
        self.tree.selection_set(DEFAULT_ROOT)
        self.grab_set()

    def selected(self):
        sel = self.tree.selection()
        return sel[0] if sel else None

    def list_dirs(self, path):
        _, out, _ = self.adb.shell(f"find -H {q(path)} -mindepth 1 -maxdepth 1 -type d 2>/dev/null")
        names = {posixpath.basename(l.rstrip("/")) for l in out.splitlines() if l.strip()}
        return sorted(names, key=lambda n: (n.startswith("."), n.lower()))

    def add_children(self, parent):
        self.config(cursor="watch")
        self.update_idletasks()
        names = self.list_dirs(parent)
        for n in names:
            child = posixpath.join(parent, n)
            if not self.tree.exists(child):
                self.tree.insert(parent, "end", iid=child, text="📁 " + n)
                self.tree.insert(child, "end", iid=child + "::dummy", text="…")
        self.config(cursor="")
        return bool(names)

    def on_open(self, _):
        iid = self.tree.focus()
        dummy = iid + "::dummy"
        if self.tree.exists(dummy):
            self.tree.delete(dummy)
            self.add_children(iid)

    def go(self, path):
        if self.tree.exists(path):
            self.tree.selection_set(path)
            self.tree.focus(path)
            self.tree.see(path)
        else:
            messagebox.showinfo("Not found", f"{posixpath.basename(path)} doesn't exist on this phone.", parent=self)

    def pick(self):
        path = self.selected()
        if path:
            self.on_pick(path)
            self.destroy()


# --------------------------------------------------------------------------- main app
class App:
    def __init__(self, root):
        self.root = root
        self.adb = Adb()
        self.q = queue.Queue()
        self.records = []
        self.dup_groups = []
        self.dup_marked = set()
        self.busy = False
        self.devices = []
        self.cur_state = None
        self._indeterminate = False

        self.folder = tk.StringVar(value=posixpath.join(DEFAULT_ROOT, "DCIM"))
        self.dest_root = tk.StringVar(value=posixpath.join(DEFAULT_ROOT, "Organized"))
        self.skip_hidden = tk.BooleanVar(value=True)
        self.status = tk.StringVar(value="Ready.")
        self.conn = tk.StringVar(value="Looking for devices…")

        self.build_ui()
        self.root.after(100, self.poll)
        threading.Thread(target=self.device_watch, daemon=True).start()

    # ---------- UI
    def make_tree(self, parent, cols, show="headings"):
        frame = ttk.Frame(parent)
        frame.pack(fill="both", expand=True, padx=4, pady=4)
        tree = ttk.Treeview(frame, columns=[c[0] for c in cols], show=show, selectmode="none")
        for cid, title, width in cols:
            tree.heading(cid, text=title, anchor="w")
            tree.column(cid, width=width, anchor="w", stretch=cid in ("folder", "path", "name"))
        vs = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        hs = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=vs.set, xscrollcommand=hs.set)
        tree.grid(row=0, column=0, sticky="nsew")
        vs.grid(row=0, column=1, sticky="ns")
        hs.grid(row=1, column=0, sticky="ew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        return tree

    def build_ui(self):
        r = self.root
        r.title("Phone File Organizer")
        r.geometry("1150x720")
        r.minsize(900, 560)
        pad = dict(fill="x", padx=8, pady=4)

        f1 = ttk.LabelFrame(r, text="1. Phone connection")
        f1.pack(**pad)
        self.conn_dot = tk.Label(f1, text="●", fg="gray", font=("TkDefaultFont", 16))
        self.conn_dot.pack(side="left", padx=(6, 2))
        ttk.Label(f1, textvariable=self.conn).pack(side="left", pady=4)
        self.dev_combo = ttk.Combobox(f1, state="readonly", width=42)
        self.dev_combo.pack(side="right", padx=6)
        self.dev_combo.bind("<<ComboboxSelected>>", self.on_device_chosen)
        ttk.Label(f1, text="Device:").pack(side="right")

        f2 = ttk.LabelFrame(r, text="2. Choose folder   ·   3. Scan")
        f2.pack(**pad)
        ttk.Entry(f2, textvariable=self.folder).pack(side="left", fill="x", expand=True, padx=6, pady=6)
        self.btn_browse = ttk.Button(f2, text="Browse phone…", command=self.browse)
        self.btn_browse.pack(side="left")
        ttk.Checkbutton(f2, text="Skip hidden files/folders", variable=self.skip_hidden).pack(side="left", padx=8)
        self.btn_scan = ttk.Button(f2, text="Scan", command=self.scan)
        self.btn_scan.pack(side="left", padx=6)

        fp = ttk.Frame(r)
        fp.pack(**pad)
        self.pbar = ttk.Progressbar(fp, mode="determinate")
        self.pbar.pack(fill="x")
        ttk.Label(fp, textvariable=self.status).pack(anchor="w")

        nb = ttk.Notebook(r)
        nb.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        # --- organize tab
        ft = ttk.Frame(nb)
        nb.add(ft, text="4. Organize files")
        bar = ttk.Frame(ft)
        bar.pack(fill="x", padx=4, pady=4)
        ttk.Label(bar, text="Show:").pack(side="left")
        self.cat_filter = ttk.Combobox(bar, state="readonly", width=12, values=["All"] + ALL_CATS)
        self.cat_filter.set("All")
        self.cat_filter.pack(side="left", padx=4)
        self.cat_filter.bind("<<ComboboxSelected>>", lambda e: self.refresh_files())
        ttk.Button(bar, text="Select shown", command=lambda: self.set_checked(True)).pack(side="left", padx=2)
        ttk.Button(bar, text="Clear shown", command=lambda: self.set_checked(False)).pack(side="left", padx=2)
        self.file_summary = ttk.Label(bar, foreground="#555")
        self.file_summary.pack(side="left", padx=10)
        bar2 = ttk.Frame(ft)
        bar2.pack(fill="x", padx=4)
        ttk.Label(bar2, text="Move into (on phone):").pack(side="left")
        ttk.Entry(bar2, textvariable=self.dest_root, width=50).pack(side="left", padx=4)
        ttk.Label(bar2, text="/<Category>/", foreground="#555").pack(side="left")
        self.btn_preview = ttk.Button(bar2, text="Preview moves…", command=self.preview_moves)
        self.btn_preview.pack(side="right")
        self.ftree = self.make_tree(ft, [("sel", "✓", 36), ("cat", "Category", 90), ("name", "Name", 260),
                                         ("size", "Size", 80), ("folder", "Folder", 450)])
        self.ftree.bind("<Button-1>", self.on_file_click)

        # --- duplicates tab
        dt = ttk.Frame(nb)
        nb.add(dt, text="5. Clean duplicates")
        dbar = ttk.Frame(dt)
        dbar.pack(fill="x", padx=4, pady=4)
        self.btn_auto = ttk.Button(dbar, text="Auto-select extra copies (keep 1 per group)", command=self.auto_select)
        self.btn_auto.pack(side="left")
        ttk.Button(dbar, text="Clear selection", command=self.clear_dup_selection).pack(side="left", padx=4)
        self.dup_summary = ttk.Label(dbar, foreground="#555")
        self.dup_summary.pack(side="left", padx=10)
        self.btn_delete = ttk.Button(dbar, text="Review & delete selected…", command=self.review_delete)
        self.btn_delete.pack(side="right")
        self.dtree = self.make_tree(dt, [("sel", "✓", 36), ("size", "Size", 90), ("path", "Full path", 650)],
                                    show="tree headings")
        self.dtree.heading("#0", text="Duplicate group", anchor="w")
        self.dtree.column("#0", width=230, stretch=False)
        self.dtree.bind("<Button-1>", self.on_dup_click)

        self.action_buttons = [self.btn_browse, self.btn_scan, self.btn_preview, self.btn_auto, self.btn_delete]
        self.update_summaries()

    # ---------- background work plumbing
    def progress(self, cur, total, text):
        self.q.put(("progress", cur, total, text))

    def run_bg(self, work, on_done, label):
        self.set_busy(True)

        def target():
            try:
                self.q.put(("done", on_done, work()))
            except Exception as e:  # noqa: BLE001
                self.q.put(("error", label, e))
        threading.Thread(target=target, daemon=True).start()

    def set_busy(self, busy):
        self.busy = busy
        for b in self.action_buttons:
            b.state(["disabled"] if busy else ["!disabled"])
        if not busy:
            self.pbar.stop()
            self._indeterminate = False
            self.pbar.config(mode="determinate", value=0)

    def poll(self):
        try:
            while True:
                msg = self.q.get_nowait()
                kind = msg[0]
                if kind == "progress":
                    _, cur, total, text = msg
                    self.status.set(text)
                    if total:
                        if self._indeterminate:
                            self.pbar.stop()
                            self._indeterminate = False
                        self.pbar.config(mode="determinate", maximum=total, value=cur)
                    elif not self._indeterminate:
                        self.pbar.config(mode="indeterminate")
                        self.pbar.start(12)
                        self._indeterminate = True
                elif kind == "done":
                    self.set_busy(False)
                    msg[1](msg[2])
                elif kind == "error":
                    self.set_busy(False)
                    self.status.set(f"{msg[1]} failed.")
                    messagebox.showerror(f"{msg[1]} failed", str(msg[2]))
                elif kind == "devices":
                    self.update_devices(msg[1])
        except queue.Empty:
            pass
        self.root.after(100, self.poll)

    # ---------- 1. connection
    def device_watch(self):
        while True:
            try:
                devs = self.adb.devices()
            except AdbError as e:
                devs = e
            self.q.put(("devices", devs))
            time.sleep(2)

    def update_devices(self, devs):
        if isinstance(devs, AdbError):
            self.cur_state = None
            self.set_conn("gray", str(devs))
            return
        self.devices = devs
        self.dev_combo["values"] = [f"{d['model'] or 'Android device'} ({d['serial']}) — {d['state']}" for d in devs]
        serials = [d["serial"] for d in devs]
        if self.adb.serial not in serials:
            pick = next((d for d in devs if d["state"] == "device"), devs[0] if devs else None)
            self.adb.serial = pick["serial"] if pick else None
        if not self.adb.serial:
            self.dev_combo.set("")
            self.cur_state = None
            self.set_conn("gray", "No phone detected — plug in USB and enable USB debugging.")
            return
        idx = serials.index(self.adb.serial)
        self.dev_combo.current(idx)
        d = devs[idx]
        self.cur_state = d["state"]
        name = d["model"] or d["serial"]
        if d["state"] == "device":
            self.set_conn("#1a9e3a", f"{name}: connected and authorized ✔")
        elif d["state"] == "unauthorized":
            self.set_conn("#d98a00", f"{name}: connected but NOT authorized — unlock the phone and tap “Allow” on the USB debugging prompt.")
        elif d["state"] == "no permissions":
            self.set_conn("#c62828", f"{d['serial']}: no USB permission (Linux: add a udev rule / plugdev group).")
        else:
            self.set_conn("#c62828", f"{name}: {d['state']} — try reconnecting the cable.")

    def set_conn(self, color, text):
        self.conn_dot.config(fg=color)
        self.conn.set(text)

    def on_device_chosen(self, _):
        i = self.dev_combo.current()
        if 0 <= i < len(self.devices):
            self.adb.serial = self.devices[i]["serial"]
            self.update_devices(self.devices)

    def require_device(self):
        if self.busy:
            return False
        if self.cur_state != "device":
            messagebox.showwarning("Phone not ready", self.conn.get())
            return False
        return True

    # ---------- 2. browse
    def browse(self):
        if self.require_device():
            FolderPicker(self.root, self.adb, self.folder.set)

    # ---------- 3. scan
    def scan(self):
        if not self.require_device():
            return
        folder = self.folder.get().strip().rstrip("/") or DEFAULT_ROOT
        skip_hidden = self.skip_hidden.get()

        def work():
            self.progress(None, None, f"Listing files in {folder} …")
            code, out, err = self.adb.shell(
                f"find -H {q(folder)} -type f -exec stat -c '%s %n' {{}} + 2>/dev/null", timeout=1800)
            recs = []
            for line in out.splitlines():
                size, _, path = line.partition(" ")
                if not path or not size.isdigit():
                    continue
                rel = posixpath.relpath(path, folder)
                if skip_hidden and any(part.startswith(".") for part in rel.split("/")):
                    continue
                recs.append(FileRec(path, int(size)))
            if not recs and code != 0:
                raise AdbError(err.strip() or f"Could not read {folder}")
            self.progress(None, None, f"Found {len(recs)} files. Looking for possible duplicates…")

            # Only files that share a size with another file can be duplicates -> hash just those.
            by_size = defaultdict(list)
            for r in recs:
                if r.size > 0:
                    by_size[r.size].append(r)
            cands = [r for g in by_size.values() if len(g) > 1 for r in g]
            done = 0
            for batch in batches(cands):
                _, out, _ = self.adb.shell("md5sum " + " ".join(q(r.path) for r in batch), timeout=900)
                hashes = {line[34:]: line[:32] for line in out.splitlines()
                          if len(line) > 34 and line[32:34] == "  "}
                for r in batch:
                    r.hash = hashes.get(r.path)
                done += len(batch)
                self.progress(done, len(cands), f"Hashing possible duplicates… {done}/{len(cands)}")
            return folder, recs

        self.run_bg(work, self.scan_done, "Scan")

    def scan_done(self, result):
        folder, recs = result
        self.records = sorted(recs, key=lambda r: r.path.lower())
        self.dup_marked.clear()
        self.refresh_files()
        self.refresh_dups()
        counts = defaultdict(int)
        for r in self.records:
            counts[r.cat] += 1
        parts = ", ".join(f"{c} {counts[c]}" for c in ALL_CATS if counts[c])
        self.status.set(f"Scanned {folder}: {len(self.records)} files ({parts}). "
                        f"{len(self.dup_groups)} duplicate group(s).")

    # ---------- 4. organize
    def refresh_files(self):
        self.ftree.delete(*self.ftree.get_children())
        flt = self.cat_filter.get()
        for i, r in enumerate(self.records):
            if flt == "All" or r.cat == flt:
                self.ftree.insert("", "end", iid=str(i), values=(
                    ON if r.checked else OFF, r.cat, r.name, human(r.size), posixpath.dirname(r.path)))
        self.update_summaries()

    def on_file_click(self, e):
        if self.ftree.identify_region(e.x, e.y) != "cell":
            return
        iid = self.ftree.identify_row(e.y)
        if iid:
            r = self.records[int(iid)]
            r.checked = not r.checked
            self.ftree.set(iid, "sel", ON if r.checked else OFF)
            self.update_summaries()

    def set_checked(self, value):
        for iid in self.ftree.get_children():
            self.records[int(iid)].checked = value
            self.ftree.set(iid, "sel", ON if value else OFF)
        self.update_summaries()

    def preview_moves(self):
        if not self.require_device():
            return
        sel = [r for r in self.records if r.checked]
        if not sel:
            messagebox.showinfo("Nothing selected", "Tick the files you want to organize first.")
            return
        dest_root = self.dest_root.get().strip().rstrip("/")
        if not dest_root.startswith("/"):
            messagebox.showerror("Destination", "Destination must be a full phone path, e.g. /storage/emulated/0/Organized")
            return

        def work():
            self.progress(None, None, "Checking what already exists at the destination…")
            _, out, _ = self.adb.shell(f"find -H {q(dest_root)} -type f 2>/dev/null", timeout=600)
            taken = {l.strip().lower() for l in out.splitlines() if l.strip()}
            plan = []
            for r in sel:
                ddir = posixpath.join(dest_root, r.cat)
                if posixpath.dirname(r.path).lower() == ddir.lower():
                    plan.append((r, None, "Already in place — skipped"))
                    continue
                dest = unique_path(ddir, r.name, taken)
                taken.add(dest.lower())
                plan.append((r, dest, "" if posixpath.basename(dest) == r.name else "Renamed to avoid overwriting"))
            return plan

        self.run_bg(work, self.show_move_preview, "Preview")

    def show_move_preview(self, plan):
        moves = [(r, d) for r, d, _ in plan if d]
        renamed = sum(1 for _, d, n in plan if d and n)
        skipped = len(plan) - len(moves)
        self.status.set("Review the planned moves.")

        win = tk.Toplevel(self.root)
        win.title("Confirm moves")
        win.geometry("1050x560")
        win.transient(self.root)
        ttk.Label(win, padding=8, text=f"{len(moves)} file(s) will be moved  ·  {renamed} renamed to avoid "
                                         f"overwriting  ·  {skipped} skipped. Filenames are kept; nothing is overwritten.").pack(anchor="w")
        tree = self.make_tree(win, [("from", "From", 430), ("to", "To", 430), ("note", "Note", 180)])
        for r, d, note in plan:
            tree.insert("", "end", values=(r.path, d or "—", note))
        btns = ttk.Frame(win, padding=8)
        btns.pack(fill="x")
        ttk.Button(btns, text="Cancel", command=win.destroy).pack(side="right")
        go = ttk.Button(btns, text=f"Confirm & move {len(moves)} file(s)",
                        command=lambda: (win.destroy(), self.do_moves(moves)))
        go.pack(side="right", padx=6)
        if not moves:
            go.state(["disabled"])
        win.grab_set()

    def do_moves(self, moves):
        if not self.require_device():
            return

        def work():
            dirs = sorted({posixpath.dirname(d) for _, d in moves})
            code, _, err = self.adb.shell("mkdir -p " + " ".join(q(x) for x in dirs))
            if code != 0:
                raise AdbError(f"Could not create destination folders:\n{err.strip()}")
            ok, errors = 0, []
            for i, (r, d) in enumerate(moves, 1):
                _, out, err = self.adb.shell(
                    f"if [ -e {q(d)} ]; then echo EXISTS; "
                    f"else mv -n {q(r.path)} {q(d)} && [ -e {q(d)} ] && echo MOVED_OK; fi")
                if "MOVED_OK" in out:
                    r.path, r.checked = d, False
                    ok += 1
                else:
                    reason = "destination already exists" if "EXISTS" in out else (err.strip() or "move failed")
                    errors.append(f"{r.path}: {reason}")
                self.progress(i, len(moves), f"Moving {i}/{len(moves)} …")
            return ok, errors

        self.run_bg(work, self.moves_done, "Move")

    def moves_done(self, result):
        ok, errors = result
        self.refresh_files()
        self.refresh_dups()
        self.status.set(f"Moved {ok} file(s). {len(errors)} problem(s).")
        text = f"Moved {ok} file(s)."
        if errors:
            text += f"\n\n{len(errors)} not moved:\n" + "\n".join(errors[:15]) + ("\n…" if len(errors) > 15 else "")
        messagebox.showinfo("Organize finished", text)

    # ---------- 5. duplicates
    def refresh_dups(self):
        groups = defaultdict(list)
        for i, r in enumerate(self.records):
            if r.hash:
                groups[r.hash].append(i)
        self.dup_groups = sorted((g for g in groups.values() if len(g) > 1),
                                 key=lambda g: -self.records[g[0]].size * (len(g) - 1))
        self.dtree.delete(*self.dtree.get_children())
        for gi, idxs in enumerate(self.dup_groups):
            size = self.records[idxs[0]].size
            parent = self.dtree.insert("", "end", iid=f"g{gi}", open=True,
                                       text=f"Group {gi + 1} · {len(idxs)} identical copies",
                                       values=("", human(size), f"{human(size * (len(idxs) - 1))} reclaimable"))
            for i in sorted(idxs, key=lambda i: self.records[i].path.lower()):
                self.dtree.insert(parent, "end", iid=f"f{i}", values=(
                    ON if i in self.dup_marked else OFF, human(size), self.records[i].path))
        self.update_summaries()

    def on_dup_click(self, e):
        iid = self.dtree.identify_row(e.y)
        if not iid.startswith("f") or self.dtree.identify_region(e.x, e.y) not in ("cell", "tree"):
            return
        i = int(iid[1:])
        self.dup_marked.symmetric_difference_update({i})
        self.dtree.set(iid, "sel", ON if i in self.dup_marked else OFF)
        self.update_summaries()

    def auto_select(self):
        """Keep the copy with the shortest path in each group (usually the original), select the rest."""
        self.dup_marked.clear()
        for g in self.dup_groups:
            keep = min(g, key=lambda i: (len(self.records[i].path), self.records[i].path))
            self.dup_marked.update(i for i in g if i != keep)
        self.refresh_dups()

    def clear_dup_selection(self):
        self.dup_marked.clear()
        self.refresh_dups()

    def review_delete(self):
        if not self.require_device():
            return
        if not self.dup_marked:
            messagebox.showinfo("Nothing selected", "Click the copies you want to remove, or use Auto-select.")
            return
        plan = []
        for gi, g in enumerate(self.dup_groups):
            kept = [i for i in g if i not in self.dup_marked]
            if not kept:
                messagebox.showerror("Every copy selected",
                                     f"Group {gi + 1} has all its copies selected. Leave at least one unselected.")
                return
            plan += [(i, kept[0]) for i in g if i in self.dup_marked]
        total = sum(self.records[i].size for i, _ in plan)

        win = tk.Toplevel(self.root)
        win.title("Review deletion")
        win.geometry("1050x560")
        win.transient(self.root)
        ttk.Label(win, padding=8, foreground="#c62828",
                  text=f"These {len(plan)} file(s) ({human(total)}) will be PERMANENTLY deleted from the phone. "
                       f"There is no recycle bin.").pack(anchor="w")
        tree = self.make_tree(win, [("del", "Will be DELETED (full path)", 500), ("keep", "Identical copy kept", 500)])
        for i, k in plan:
            tree.insert("", "end", values=(self.records[i].path, self.records[k].path))
        btns = ttk.Frame(win, padding=8)
        btns.pack(fill="x")
        agree = tk.BooleanVar(value=False)
        go = ttk.Button(btns, text=f"Delete {len(plan)} file(s)", command=lambda: (win.destroy(), self.do_delete(plan)))
        go.state(["disabled"])
        ttk.Checkbutton(btns, variable=agree, text="I reviewed every path above and want to delete these files",
                        command=lambda: go.state(["!disabled"] if agree.get() else ["disabled"])).pack(side="left")
        ttk.Button(btns, text="Cancel", command=win.destroy).pack(side="right")
        go.pack(side="right", padx=6)
        win.grab_set()

    def do_delete(self, plan):
        if not self.require_device():
            return
        recs = self.records

        def work():
            deleted, errors, freed = set(), [], 0
            for n, (i, k) in enumerate(plan, 1):
                r, keep = recs[i], recs[k]
                # Safety: re-hash both right before deleting, so we never delete the last copy of anything.
                _, out, _ = self.adb.shell(f"md5sum {q(r.path)} {q(keep.path)}")
                hs = [l[:32] for l in out.splitlines() if len(l) > 34]
                if len(hs) != 2 or hs[0] != r.hash or hs[1] != r.hash:
                    errors.append(f"{r.path}: skipped — file changed or kept copy missing")
                else:
                    _, out, err = self.adb.shell(f"rm -f {q(r.path)} && [ ! -e {q(r.path)} ] && echo GONE")
                    if "GONE" in out:
                        deleted.add(i)
                        freed += r.size
                    else:
                        errors.append(f"{r.path}: {err.strip() or 'delete failed'}")
                self.progress(n, len(plan), f"Deleting {n}/{len(plan)} …")
            return deleted, errors, freed

        self.run_bg(work, self.delete_done, "Delete")

    def delete_done(self, result):
        deleted, errors, freed = result
        self.records = [r for i, r in enumerate(self.records) if i not in deleted]
        self.dup_marked.clear()
        self.refresh_files()
        self.refresh_dups()
        self.status.set(f"Deleted {len(deleted)} duplicate(s), freed {human(freed)}.")
        text = f"Deleted {len(deleted)} file(s), freed {human(freed)}."
        if errors:
            text += f"\n\n{len(errors)} skipped:\n" + "\n".join(errors[:15]) + ("\n…" if len(errors) > 15 else "")
        messagebox.showinfo("Cleanup finished", text)

    # ---------- summaries
    def update_summaries(self):
        sel = [r for r in self.records if r.checked]
        self.file_summary.config(text=f"{len(self.records)} files scanned · {len(sel)} selected "
                                      f"({human(sum(r.size for r in sel))})")
        size = sum(self.records[i].size for i in self.dup_marked if i < len(self.records))
        self.dup_summary.config(text=f"{len(self.dup_groups)} group(s) · {len(self.dup_marked)} selected "
                                     f"for deletion ({human(size)})")


def main():
    root = tk.Tk()
    try:
        ttk.Style().theme_use("clam" if sys.platform.startswith("linux") else ttk.Style().theme_use())
    except tk.TclError:
        pass
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
