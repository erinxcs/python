"""
ERINX Drive Organizer  -  for folders on this laptop, USB flash drives (SanDisk, etc.)
                          and external HDD / SSD drives.

1. Drives & folders : lists this laptop's drives plus any USB flash drive / external HDD
                      the moment it's plugged in (refreshes every 3 s). Eject button included.
2. Choose folder    : Windows folder picker, or quick buttons (Desktop, Documents, Downloads...).
3. Scan             : recursive scan with progress + Cancel, categorizes every file, and hashes
                      possible duplicates (size -> quick hash -> full BLAKE2 hash).
4. Organize         : preview every destination, then confirm. Move OR Copy. Filenames are kept,
                      nothing is ever overwritten ("name (1).jpg" instead). Undo last organize.
5. Duplicates       : groups files with exactly the same content, you pick the copies to remove,
                      review full paths, tick a confirmation box, then send them to the
                      Recycle Bin / a _Duplicates folder / delete permanently.

Every move, copy and delete is written to _organizer_log.csv so you can trace what happened.
Windows system folders (Windows, Program Files, AppData, ...) are never scanned.

Only needs Python 3.8+ with Tkinter (standard installer). No pip packages.
Run:  python drive_organizer.py      or double-click run_drive_organizer.bat
"""

import csv
import datetime
import errno
import hashlib
import os
import queue
import shutil
import string
import subprocess
import sys
import threading
import time
import tkinter as tk
from collections import defaultdict
from tkinter import filedialog, messagebox, ttk

IS_WIN = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"
CASE_INSENSITIVE = IS_WIN or IS_MAC
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

CATEGORIES = {
    "Pictures":  {"jpg", "jpeg", "png", "gif", "webp", "heic", "heif", "bmp", "tif", "tiff",
                  "dng", "cr2", "nef", "arw", "raw", "svg", "ico"},
    "Videos":    {"mp4", "mkv", "mov", "avi", "wmv", "flv", "webm", "m4v", "3gp", "mts", "m2ts", "ts", "mpg", "mpeg"},
    "Music":     {"mp3", "wav", "flac", "aac", "m4a", "ogg", "opus", "wma", "amr", "aiff"},
    "Documents": {"pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "txt", "csv", "rtf", "odt",
                  "ods", "odp", "md", "epub", "pages", "numbers", "key"},
    "Archives":  {"zip", "rar", "7z", "tar", "gz", "bz2", "xz", "iso"},
    "Programs":  {"exe", "msi", "apk", "apks", "xapk", "dmg", "pkg", "deb", "appimage"},
}
ALL_CATS = list(CATEGORIES) + ["Others"]

# Folders that are never descended into.
SKIP_NAMES = {"$recycle.bin", "recycler", "system volume information", "$windows.~bt", "$windows.~ws",
              "$sysreset", "windowsapps", "appdata", ".trashes", ".trash", ".spotlight-v100",
              ".fseventsd", ".temporaryitems", ".documentrevisions-v100", "found.000", "lost+found"}
WIN_ROOT_PROTECTED = {"windows", "program files", "program files (x86)", "programdata", "recovery",
                      "perflogs", "msocache", "boot", "config.msi", "$winreagent"}
POSIX_PROTECTED = {"/System", "/Library", "/Applications", "/private", "/usr", "/bin", "/sbin", "/etc",
                   "/var", "/dev", "/proc", "/sys", "/boot", "/lib", "/lib64", "/opt", "/snap", "/run",
                   os.path.expanduser("~/Library")}

LOG_NAME = "_organizer_log.csv"
DUP_FOLDER = "_Duplicates"
QUICK_BYTES = 64 * 1024
CHUNK = 1024 * 1024
MAX_FILE_ROWS = 5000
MAX_DUP_GROUPS = 2000
ON, OFF = "☑", "☐"

# Windows file attribute bits
A_HIDDEN, A_SYSTEM, A_REPARSE = 0x2, 0x4, 0x400
A_CLOUD = 0x1000 | 0x40000 | 0x400000          # offline / recall-on-open / recall-on-data-access
JUNCTION_TAGS = {0xA0000003, 0xA000000C}         # mount point (junction), symlink


class Cancelled(Exception):
    pass


# =========================================================================== helpers
def category_of(path):
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    for cat, exts in CATEGORIES.items():
        if ext in exts:
            return cat
    return "Others"


def human(n):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024


def norm(p):
    p = os.path.normpath(os.path.abspath(p))
    return p.lower() if CASE_INSENSITIVE else p


def same_dir(a, b):
    return norm(a) == norm(b)


def is_inside(path, folder):
    p, f = norm(path), norm(folder)
    return p == f or p.startswith(f.rstrip(os.sep) + os.sep)


def is_drive_root(path):
    p = os.path.abspath(path)
    return os.path.dirname(p) == p


def is_protected_dir(path, name):
    lname = name.lower()
    if lname in SKIP_NAMES:
        return True
    if IS_WIN:
        return lname in WIN_ROOT_PROTECTED and is_drive_root(os.path.dirname(path))
    return path in POSIX_PROTECTED


def reveal(path):
    """Open the file's folder in Explorer / Finder with the file highlighted."""
    try:
        if IS_WIN:
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
        elif IS_MAC:
            subprocess.Popen(["open", "-R", path])
        else:
            subprocess.Popen(["xdg-open", os.path.dirname(path)])
    except OSError:
        pass


def write_log(folder, rows):
    """Append (action, from, to) rows to folder/_organizer_log.csv. Never fails the operation."""
    if not rows:
        return None
    path = os.path.join(folder, LOG_NAME)
    try:
        os.makedirs(folder, exist_ok=True)
        new = not os.path.exists(path)
        with open(path, "a", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            if new:
                w.writerow(["time", "action", "from", "to"])
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            for action, src, dst in rows:
                w.writerow([now, action, src, dst])
        return path
    except OSError:
        return None


# =========================================================================== drives
_bus_cache = {}


def _usb_bus(letter):
    """Ask Windows whether a 'fixed' drive is really an external USB HDD/SSD (cached)."""
    if letter not in _bus_cache:
        try:
            p = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 f"(Get-Partition -DriveLetter {letter} -ErrorAction Stop | Get-Disk).BusType"],
                capture_output=True, text=True, timeout=15, creationflags=NO_WINDOW)
            _bus_cache[letter] = p.stdout.strip().upper()
        except (OSError, subprocess.TimeoutExpired):
            _bus_cache[letter] = ""
    return _bus_cache[letter] == "USB"


def list_drives():
    drives = []
    if IS_WIN:
        import ctypes
        k32 = ctypes.windll.kernel32
        k32.SetErrorMode(0x0001 | 0x8000)          # no "insert a disk" popups
        mask = k32.GetLogicalDrives()
        sysdrive = os.environ.get("SystemDrive", "C:").upper()
        seen = set()
        for i, letter in enumerate(string.ascii_uppercase):
            if not (mask >> i) & 1:
                continue
            root = f"{letter}:\\"
            dtype = k32.GetDriveTypeW(ctypes.c_wchar_p(root))
            if dtype not in (2, 3, 4):            # removable, fixed, network
                continue
            label = ctypes.create_unicode_buffer(261)
            fs = ctypes.create_unicode_buffer(261)
            serial = ctypes.c_ulong(0)
            if not k32.GetVolumeInformationW(ctypes.c_wchar_p(root), label, 261, ctypes.byref(serial),
                                             None, None, fs, 261):
                continue                           # empty card reader slot etc.
            seen.add(letter)
            if dtype == 2:
                kind, external = "USB flash drive / SD card", True
            elif dtype == 4:
                kind, external = "Network drive", False
            elif f"{letter}:" == sysdrive:
                kind, external = "This laptop (system drive)", False
            elif _usb_bus(letter):
                kind, external = "External USB drive (HDD/SSD)", True
            else:
                kind, external = "Internal drive", False
            drives.append(dict(root=root, label=label.value or "Local Disk", kind=kind,
                               external=external, fs=fs.value))
        for gone in [l for l in list(_bus_cache) if l not in seen]:
            _bus_cache.pop(gone, None)             # drive letter freed -> re-check next time
    else:
        user = os.environ.get("USER", "")
        bases = ["/Volumes"] if IS_MAC else [f"/media/{user}", f"/run/media/{user}", "/media", "/mnt"]
        drives.append(dict(root=os.path.expanduser("~"), label="Home", kind="This computer",
                           external=False, fs=""))
        found = set()
        for base in bases:
            try:
                names = sorted(os.listdir(base))
            except OSError:
                continue
            for n in names:
                p = os.path.join(base, n)
                if p in found or not os.path.ismount(p) or os.path.realpath(p) == "/":
                    continue
                found.add(p)
                drives.append(dict(root=p, label=n, kind="External / USB drive", external=True, fs=""))
    for d in drives:
        try:
            u = shutil.disk_usage(d["root"])
            d["free"], d["total"] = u.free, u.total
        except OSError:
            d["free"] = d["total"] = 0
    return drives


def eject(root):
    if IS_WIN:
        letter = root[:2]
        cmd = (f"(New-Object -ComObject Shell.Application).Namespace(17).ParseName('{letter}')"
               f".InvokeVerb('Eject')")
        subprocess.run(["powershell", "-NoProfile", "-Command", cmd], timeout=30, creationflags=NO_WINDOW)
    elif IS_MAC:
        subprocess.run(["diskutil", "eject", root], timeout=60)
    else:
        subprocess.run(["udisksctl", "unmount", "-b", root], timeout=60)


def quick_folders():
    home = os.path.expanduser("~")
    onedrive = os.environ.get("OneDrive", "")
    out = []
    for name in ("Desktop", "Documents", "Downloads", "Pictures", "Videos", "Movies", "Music"):
        for base in (onedrive, home):
            p = os.path.join(base, name) if base else ""
            if p and os.path.isdir(p):
                out.append((name, p))
                break
    return out


# =========================================================================== scanning
class FileRec:
    __slots__ = ("path", "size", "mtime", "hash", "cloud", "checked")

    def __init__(self, path, size, mtime, cloud=False):
        self.path, self.size, self.mtime, self.cloud = path, size, mtime, cloud
        self.hash, self.checked = None, False

    @property
    def name(self):
        return os.path.basename(self.path)

    @property
    def cat(self):
        return category_of(self.path)


def iter_files(root, skip_hidden, cancel, errors):
    """Yield FileRec for every regular file under root, without following links/junctions."""
    stack = [root]
    while stack:
        if cancel.is_set():
            raise Cancelled()
        d = stack.pop()
        try:
            it = os.scandir(d)
        except OSError:
            errors.append(d)
            continue
        with it:
            for e in it:
                try:
                    if e.is_symlink():
                        continue
                    st = e.stat(follow_symlinks=False)
                    attrs = getattr(st, "st_file_attributes", 0)
                    if skip_hidden and (e.name.startswith(".") or attrs & (A_HIDDEN | A_SYSTEM)):
                        continue
                    if e.is_dir(follow_symlinks=False):
                        if attrs & A_REPARSE and getattr(st, "st_reparse_tag", 0) in JUNCTION_TAGS:
                            continue
                        if not is_protected_dir(e.path, e.name):
                            stack.append(e.path)
                    elif e.is_file(follow_symlinks=False):
                        if e.name == LOG_NAME:
                            continue
                        yield FileRec(e.path, st.st_size, st.st_mtime, bool(attrs & A_CLOUD))
                except OSError:
                    continue


def file_hash(path, cancel, on_bytes=None, limit=None):
    h = hashlib.blake2b(digest_size=20)
    left = limit
    with open(path, "rb") as f:
        while True:
            if cancel.is_set():
                raise Cancelled()
            n = CHUNK if left is None else min(CHUNK, left)
            if n <= 0:
                break
            b = f.read(n)
            if not b:
                break
            h.update(b)
            if on_bytes:
                on_bytes(len(b))
            if left is not None:
                left -= len(b)
    return h.hexdigest()


def find_duplicates(recs, cancel, progress):
    """Set rec.hash on every file that might have a twin. Size -> first 64 KB -> full content."""
    by_size = defaultdict(list)
    for r in recs:
        r.hash = None
        if r.size > 0 and not r.cloud:              # skip cloud-only OneDrive files (would download)
            by_size[r.size].append(r)
    groups = [g for g in by_size.values() if len(g) > 1]
    total = sum(len(g) for g in groups)
    done, last, full = 0, 0.0, []
    for g in groups:
        sub = defaultdict(list)
        for r in g:
            try:
                sub[file_hash(r.path, cancel, limit=QUICK_BYTES)].append(r)
            except OSError:
                pass
            done += 1
            if time.time() - last > 0.1:
                last = time.time()
                progress(done, total, f"Quick check of same-size files… {done}/{total}")
        for qh, members in sub.items():
            if len(members) < 2:
                continue
            if members[0].size <= QUICK_BYTES:      # quick hash already covered the whole file
                for r in members:
                    r.hash = f"{r.size}:{qh}"
            else:
                full.append(members)
    total_bytes = sum(r.size for m in full for r in m) or 1
    seen = [0]

    def on_bytes(n):
        nonlocal last
        seen[0] += n
        if time.time() - last > 0.1:
            last = time.time()
            progress(seen[0], total_bytes, f"Comparing contents… {human(seen[0])} / {human(total_bytes)}")

    for members in full:
        for r in members:
            try:
                r.hash = f"{r.size}:{file_hash(r.path, cancel, on_bytes)}"
            except OSError:
                r.hash = None


# =========================================================================== file operations
def unique_dest(folder, name, taken):
    base, ext = os.path.splitext(name)
    cand, n = os.path.join(folder, name), 1
    while norm(cand) in taken or os.path.lexists(cand):
        cand = os.path.join(folder, f"{base} ({n}){ext}")
        n += 1
    taken.add(norm(cand))
    return cand


def _rename_no_overwrite(src, dst):
    if IS_WIN:
        os.rename(src, dst)                          # Windows refuses to overwrite by itself
        return
    try:
        os.link(src, dst)                            # atomic "fail if exists"
    except FileExistsError:
        raise
    except OSError as e:
        if e.errno == errno.EXDEV:
            raise
        if os.path.lexists(dst):                     # FAT/exFAT drives: no hard links
            raise FileExistsError(dst)
        os.rename(src, dst)
        return
    os.unlink(src)


def transfer(src, dst, copy):
    """Move or copy src -> dst. Never overwrites. Cross-drive moves = verified copy + delete."""
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if os.path.lexists(dst):
        raise FileExistsError("destination already exists")
    if not copy:
        try:
            _rename_no_overwrite(src, dst)
            return
        except FileExistsError:
            raise
        except OSError as e:
            if e.errno != errno.EXDEV and getattr(e, "winerror", None) != 17:
                raise
    created = False
    try:
        with open(src, "rb") as fi, open(dst, "xb") as fo:
            created = True
            shutil.copyfileobj(fi, fo, CHUNK)
        shutil.copystat(src, dst)
        if os.path.getsize(dst) != os.path.getsize(src):
            raise OSError("copy incomplete (size mismatch)")
    except BaseException:
        if created:
            try:
                os.remove(dst)
            except OSError:
                pass
        raise
    if not copy:
        os.remove(src)


def to_recycle_bin(path):
    try:
        import send2trash  # optional; used if installed
        send2trash.send2trash(path)
        return
    except ImportError:
        pass
    if IS_WIN:
        import ctypes
        from ctypes import wintypes

        class SHFILEOPSTRUCTW(ctypes.Structure):
            _fields_ = [("hwnd", wintypes.HWND), ("wFunc", wintypes.UINT),
                        ("pFrom", wintypes.LPCWSTR), ("pTo", wintypes.LPCWSTR),
                        ("fFlags", ctypes.c_ushort), ("fAnyOperationsAborted", wintypes.BOOL),
                        ("hNameMappings", ctypes.c_void_p), ("lpszProgressTitle", wintypes.LPCWSTR)]
        op = SHFILEOPSTRUCTW()
        op.wFunc = 3                                 # FO_DELETE
        op.pFrom = os.path.abspath(path) + "\0"     # must be double-null terminated
        op.fFlags = 0x40 | 0x10 | 0x04 | 0x400      # ALLOWUNDO | NOCONFIRMATION | SILENT | NOERRORUI
        res = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
        if res != 0 or op.fAnyOperationsAborted or os.path.lexists(path):
            raise OSError(f"Recycle Bin refused the file (code {res})")
    elif IS_MAC:
        subprocess.run(["osascript", "-e", "on run argv", "-e",
                        'tell application "Finder" to delete (POSIX file (item 1 of argv))',
                        "-e", "end run", path], check=True, capture_output=True, timeout=60)
    elif shutil.which("gio"):
        subprocess.run(["gio", "trash", path], check=True, capture_output=True, timeout=60)
    else:
        raise OSError("No Recycle Bin available on this system")


# =========================================================================== app
class App:
    def __init__(self, root):
        self.root = root
        self.q = queue.Queue()
        self.cancel = threading.Event()
        self.records, self.dup_groups, self.dup_marked = [], [], set()
        self.scan_root = None
        self.last_ops = []            # [(rec, src, dst, copy)] for Undo
        self.busy = False
        self.drives, self.drive_view = [], None
        self._indet = False

        self.folder = tk.StringVar()
        self.dest_root = tk.StringVar()
        self.mode = tk.StringVar(value="move")
        self.skip_hidden = tk.BooleanVar(value=True)
        self.status = tk.StringVar(value="Pick a drive or folder, then click Scan.")

        self.build_ui()
        self.root.after(100, self.poll)
        threading.Thread(target=self.drive_watch, daemon=True).start()

    # ------------------------------------------------------------------ UI
    def make_tree(self, parent, cols, show="headings", height=None):
        frame = ttk.Frame(parent)
        frame.pack(fill="both", expand=True, padx=4, pady=4)
        tree = ttk.Treeview(frame, columns=[c[0] for c in cols], show=show, selectmode="none",
                            **({"height": height} if height else {}))
        for cid, title, width in cols:
            tree.heading(cid, text=title, anchor="w")
            tree.column(cid, width=width, anchor="w", stretch=cid in ("folder", "path", "name", "from", "to"))
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
        r.title("ERINX Drive Organizer — laptop folders, USB flash drives, external HDD")
        r.geometry("1180x780")
        r.minsize(940, 620)
        pad = dict(fill="x", padx=8, pady=4)

        # 1. drives
        f1 = ttk.LabelFrame(r, text="1. Drives  (plug in a USB flash drive or external HDD — it shows up here automatically)")
        f1.pack(**pad)
        self.drive_tree = ttk.Treeview(f1, columns=("drive", "name", "kind", "space"), show="headings",
                                       height=4, selectmode="browse")
        for cid, title, w in (("drive", "Drive", 110), ("name", "Name", 200), ("kind", "Type", 260),
                              ("space", "Free / Total", 200)):
            self.drive_tree.heading(cid, text=title, anchor="w")
            self.drive_tree.column(cid, width=w, anchor="w")
        self.drive_tree.pack(side="left", fill="x", expand=True, padx=(6, 0), pady=6)
        self.drive_tree.bind("<Double-1>", lambda e: self.use_drive())
        side = ttk.Frame(f1)
        side.pack(side="left", padx=6)
        ttk.Button(side, text="Use this drive", command=self.use_drive).pack(fill="x", pady=1)
        ttk.Button(side, text="Browse inside…", command=lambda: self.browse(self.selected_drive())).pack(fill="x", pady=1)
        self.btn_eject = ttk.Button(side, text="⏏ Eject", command=self.eject_drive)
        self.btn_eject.pack(fill="x", pady=1)

        # 2. folder + scan
        f2 = ttk.LabelFrame(r, text="2. Folder to scan   ·   3. Scan")
        f2.pack(**pad)
        row = ttk.Frame(f2)
        row.pack(fill="x", padx=6, pady=(6, 2))
        ttk.Entry(row, textvariable=self.folder).pack(side="left", fill="x", expand=True)
        self.btn_browse = ttk.Button(row, text="Browse…", command=lambda: self.browse(None))
        self.btn_browse.pack(side="left", padx=4)
        ttk.Checkbutton(row, text="Skip hidden/system files", variable=self.skip_hidden).pack(side="left", padx=6)
        self.btn_scan = ttk.Button(row, text="Scan", command=self.scan)
        self.btn_scan.pack(side="left", padx=2)
        self.btn_cancel = ttk.Button(row, text="Cancel", command=self.cancel.set)
        self.btn_cancel.pack(side="left", padx=2)
        self.btn_cancel.state(["disabled"])
        qrow = ttk.Frame(f2)
        qrow.pack(fill="x", padx=6, pady=(0, 6))
        ttk.Label(qrow, text="Quick:").pack(side="left")
        for name, path in quick_folders():
            ttk.Button(qrow, text=name, command=lambda p=path: self.folder.set(p)).pack(side="left", padx=1)

        fp = ttk.Frame(r)
        fp.pack(**pad)
        self.pbar = ttk.Progressbar(fp, mode="determinate")
        self.pbar.pack(fill="x")
        ttk.Label(fp, textvariable=self.status).pack(anchor="w")

        nb = ttk.Notebook(r)
        nb.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        # 4. organize
        ft = ttk.Frame(nb)
        nb.add(ft, text="4. Organize files")
        bar = ttk.Frame(ft)
        bar.pack(fill="x", padx=4, pady=4)
        ttk.Label(bar, text="Show:").pack(side="left")
        self.cat_filter = ttk.Combobox(bar, state="readonly", width=12, values=["All"] + ALL_CATS)
        self.cat_filter.set("All")
        self.cat_filter.pack(side="left", padx=4)
        self.cat_filter.bind("<<ComboboxSelected>>", lambda e: self.refresh_files())
        ttk.Button(bar, text="Select all (this filter)", command=lambda: self.set_checked(True)).pack(side="left", padx=2)
        ttk.Button(bar, text="Clear (this filter)", command=lambda: self.set_checked(False)).pack(side="left", padx=2)
        self.file_summary = ttk.Label(bar, foreground="#555")
        self.file_summary.pack(side="left", padx=10)

        bar2 = ttk.Frame(ft)
        bar2.pack(fill="x", padx=4)
        ttk.Label(bar2, text="Put into:").pack(side="left")
        ttk.Entry(bar2, textvariable=self.dest_root, width=48).pack(side="left", padx=4)
        ttk.Button(bar2, text="…", width=3, command=self.browse_dest).pack(side="left")
        ttk.Label(bar2, text="\\<Category>\\" if IS_WIN else "/<Category>/", foreground="#555").pack(side="left", padx=4)
        ttk.Radiobutton(bar2, text="Move", value="move", variable=self.mode).pack(side="left", padx=(10, 0))
        ttk.Radiobutton(bar2, text="Copy (keep originals)", value="copy", variable=self.mode).pack(side="left")
        self.btn_undo = ttk.Button(bar2, text="↶ Undo last organize", command=self.undo)
        self.btn_undo.pack(side="right")
        self.btn_preview = ttk.Button(bar2, text="Preview…", command=self.preview_moves)
        self.btn_preview.pack(side="right", padx=4)

        self.ftree = self.make_tree(ft, [("sel", "✓", 36), ("cat", "Category", 90), ("name", "Name", 260),
                                         ("size", "Size", 80), ("date", "Modified", 130), ("folder", "Folder", 420)])
        self.ftree.bind("<Button-1>", self.on_file_click)
        self.ftree.bind("<Double-1>", lambda e: self.reveal_row(self.ftree, e))
        ttk.Label(ft, text="Click a row to tick it · double-click to show it in Explorer",
                  foreground="#777").pack(anchor="w", padx=6)

        # 5. duplicates
        dt = ttk.Frame(nb)
        nb.add(dt, text="5. Clean duplicates")
        dbar = ttk.Frame(dt)
        dbar.pack(fill="x", padx=4, pady=4)
        self.btn_auto = ttk.Button(dbar, text="Auto-select extra copies (keep oldest)", command=self.auto_select)
        self.btn_auto.pack(side="left")
        ttk.Button(dbar, text="Clear selection", command=self.clear_dups).pack(side="left", padx=4)
        self.dup_summary = ttk.Label(dbar, foreground="#555")
        self.dup_summary.pack(side="left", padx=10)
        self.btn_delete = ttk.Button(dbar, text="Review & remove selected…", command=self.review_delete)
        self.btn_delete.pack(side="right")
        self.dtree = self.make_tree(dt, [("sel", "✓", 36), ("size", "Size", 90), ("date", "Modified", 130),
                                         ("path", "Full path", 620)], show="tree headings")
        self.dtree.heading("#0", text="Duplicate group", anchor="w")
        self.dtree.column("#0", width=220, stretch=False)
        self.dtree.bind("<Button-1>", self.on_dup_click)
        self.dtree.bind("<Double-1>", lambda e: self.reveal_row(self.dtree, e))
        ttk.Label(dt, text="Click a file to tick it for removal · double-click to show it in Explorer",
                  foreground="#777").pack(anchor="w", padx=6)

        self.action_buttons = [self.btn_browse, self.btn_scan, self.btn_preview, self.btn_auto,
                               self.btn_delete, self.btn_undo, self.btn_eject]
        self.update_summaries()

    # ------------------------------------------------------------------ background plumbing
    def progress(self, cur, total, text):
        self.q.put(("progress", cur, total, text))

    def run_bg(self, work, on_done, label, cancellable=False):
        self.set_busy(True, cancellable)
        self.cancel.clear()

        def target():
            try:
                self.q.put(("done", on_done, work()))
            except Cancelled:
                self.q.put(("cancelled", label))
            except Exception as e:  # noqa: BLE001
                self.q.put(("error", label, e))
        threading.Thread(target=target, daemon=True).start()

    def set_busy(self, busy, cancellable=False):
        self.busy = busy
        for b in self.action_buttons:
            b.state(["disabled"] if busy else ["!disabled"])
        self.btn_cancel.state(["!disabled"] if busy and cancellable else ["disabled"])
        if not busy:
            self.pbar.stop()
            self._indet = False
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
                        if self._indet:
                            self.pbar.stop()
                            self._indet = False
                        self.pbar.config(mode="determinate", maximum=total, value=cur)
                    elif not self._indet:
                        self.pbar.config(mode="indeterminate")
                        self.pbar.start(12)
                        self._indet = True
                elif kind == "done":
                    self.set_busy(False)
                    msg[1](msg[2])
                elif kind == "cancelled":
                    self.set_busy(False)
                    self.status.set(f"{msg[1]} cancelled.")
                elif kind == "error":
                    self.set_busy(False)
                    self.status.set(f"{msg[1]} failed.")
                    messagebox.showerror(f"{msg[1]} failed", str(msg[2]))
                elif kind == "drives":
                    self.update_drives(msg[1])
        except queue.Empty:
            pass
        self.root.after(100, self.poll)

    # ------------------------------------------------------------------ 1. drives
    def drive_watch(self):
        while True:
            try:
                self.q.put(("drives", list_drives()))
            except Exception:  # noqa: BLE001
                pass
            time.sleep(3)

    def update_drives(self, drives):
        view = [(d["root"], d["label"], d["kind"], f"{human(d['free'])} free of {human(d['total'])}")
                for d in drives]
        if view == self.drive_view:
            return
        if self.drive_view is not None:
            old = {v[0] for v in self.drive_view}
            new = {v[0] for v in view}
            added = [d for d in drives if d["root"] not in old]
            removed = old - new
            if added:
                d = added[0]
                self.status.set(f"Plugged in: {d['root']} {d['label']} ({d['kind']}). Double-click it to use it.")
            elif removed:
                self.status.set(f"Drive removed: {', '.join(sorted(removed))}")
                if self.scan_root and any(is_inside(self.scan_root, x) for x in removed):
                    self.status.set(self.status.get() + " — the scanned drive is gone; rescan after plugging it back in.")
        sel = self.selected_drive()
        self.drive_view, self.drives = view, drives
        self.drive_tree.delete(*self.drive_tree.get_children())
        for v in view:
            self.drive_tree.insert("", "end", iid=v[0], values=v)
        if sel and self.drive_tree.exists(sel):
            self.drive_tree.selection_set(sel)
        elif view:
            ext = next((d["root"] for d in drives if d["external"]), view[0][0])
            self.drive_tree.selection_set(ext)

    def selected_drive(self):
        s = self.drive_tree.selection()
        return s[0] if s else None

    def use_drive(self):
        d = self.selected_drive()
        if d:
            self.folder.set(d)

    def eject_drive(self):
        root = self.selected_drive()
        info = next((d for d in self.drives if d["root"] == root), None)
        if not info:
            return
        if not info["external"]:
            messagebox.showinfo("Eject", "That's not a USB / external drive.")
            return
        if self.scan_root and is_inside(self.scan_root, root):
            self.records, self.dup_groups, self.dup_marked, self.last_ops = [], [], set(), []
            self.refresh_files()
            self.refresh_dups()

        def work():
            self.progress(None, None, f"Ejecting {root} …")
            eject(root)
            for _ in range(20):
                time.sleep(0.5)
                if not os.path.exists(root):
                    return root, True
            return root, False

        def done(res):
            root_, ok = res
            if ok:
                self.status.set(f"{root_} ejected — safe to unplug.")
                messagebox.showinfo("Ejected", f"{root_} is safe to unplug now.")
            else:
                self.status.set(f"{root_} is still in use.")
                messagebox.showwarning("Not ejected", "Windows couldn't eject it — close any window or program "
                                                      "using files on that drive, then try again.")
        self.run_bg(work, done, "Eject")

    # ------------------------------------------------------------------ 2. browse
    def browse(self, start):
        if self.busy:
            return
        p = filedialog.askdirectory(title="Choose the folder to scan",
                                    initialdir=start or self.folder.get() or os.path.expanduser("~"),
                                    mustexist=True)
        if p:
            self.folder.set(os.path.normpath(p))

    def browse_dest(self):
        p = filedialog.askdirectory(title="Where should organized files go?",
                                    initialdir=self.dest_root.get() or self.folder.get() or os.path.expanduser("~"))
        if p:
            self.dest_root.set(os.path.normpath(p))

    # ------------------------------------------------------------------ 3. scan
    def scan(self):
        if self.busy:
            return
        folder = self.folder.get().strip()
        if not folder or not os.path.isdir(folder):
            messagebox.showwarning("Choose a folder", "Pick a drive or folder first (step 1 or 2).")
            return
        folder = os.path.normpath(os.path.abspath(folder))
        if IS_WIN and is_drive_root(folder) and folder[:2].upper() == os.environ.get("SystemDrive", "C:").upper():
            if not messagebox.askyesno("Whole system drive?",
                                       f"You're about to scan all of {folder} (your laptop's main drive).\n"
                                       "Windows system folders are skipped automatically, but it can take a "
                                       "long time.\n\nTip: scanning Documents / Downloads / Pictures is faster.\n\n"
                                       "Continue anyway?"):
                return
        skip_hidden = self.skip_hidden.get()

        def work():
            recs, errors, last = [], [], 0.0
            for rec in iter_files(folder, skip_hidden, self.cancel, errors):
                recs.append(rec)
                if time.time() - last > 0.15:
                    last = time.time()
                    self.progress(None, None, f"Scanning… {len(recs)} files found — {os.path.dirname(rec.path)}")
            self.progress(None, None, f"Found {len(recs)} files. Looking for duplicates…")
            find_duplicates(recs, self.cancel, self.progress)
            return folder, recs, errors

        self.run_bg(work, self.scan_done, "Scan", cancellable=True)

    def scan_done(self, result):
        folder, recs, errors = result
        self.scan_root = folder
        self.records = sorted(recs, key=lambda r: r.path.lower())
        self.dup_marked.clear()
        self.last_ops = []
        cur = self.dest_root.get().strip()
        if not cur or cur == getattr(self, "_auto_dest", None):      # user hasn't picked their own
            self._auto_dest = os.path.join(folder, "Organized")
            self.dest_root.set(self._auto_dest)
        self.refresh_files()
        self.refresh_dups()
        counts = defaultdict(int)
        for r in self.records:
            counts[r.cat] += 1
        parts = ", ".join(f"{c} {counts[c]}" for c in ALL_CATS if counts[c])
        extra = f" · {len(errors)} folder(s) couldn't be opened (no permission)" if errors else ""
        cloud = sum(r.cloud for r in self.records)
        extra += f" · {cloud} OneDrive online-only file(s) not checked for duplicates" if cloud else ""
        self.status.set(f"Scanned {folder}: {len(self.records)} files ({parts or 'none'}) · "
                        f"{len(self.dup_groups)} duplicate group(s){extra}")

    # ------------------------------------------------------------------ 4. organize
    def filtered(self):
        flt = self.cat_filter.get()
        return [(i, r) for i, r in enumerate(self.records) if flt == "All" or r.cat == flt]

    def refresh_files(self):
        self.ftree.delete(*self.ftree.get_children())
        rows = self.filtered()
        for i, r in rows[:MAX_FILE_ROWS]:
            self.ftree.insert("", "end", iid=str(i), values=(
                ON if r.checked else OFF, r.cat, r.name, human(r.size),
                time.strftime("%Y-%m-%d %H:%M", time.localtime(r.mtime)), os.path.dirname(r.path)))
        self.rows_hidden = max(0, len(rows) - MAX_FILE_ROWS)
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

    def reveal_row(self, tree, e):
        iid = tree.identify_row(e.y)
        if not iid or iid.startswith("g"):
            return
        i = int(iid[1:]) if iid.startswith("f") else int(iid)
        if i < len(self.records):
            reveal(self.records[i].path)

    def set_checked(self, value):
        for _, r in self.filtered():
            r.checked = value
        for iid in self.ftree.get_children():
            self.ftree.set(iid, "sel", ON if value else OFF)
        self.update_summaries()

    def preview_moves(self):
        if self.busy:
            return
        sel = [r for r in self.records if r.checked]
        if not sel:
            messagebox.showinfo("Nothing selected", "Tick the files you want to organize first.")
            return
        dest_root = self.dest_root.get().strip()
        if not dest_root or not os.path.isabs(dest_root):
            messagebox.showerror("Destination", "Choose where the organized files should go (the … button).")
            return
        dest_root = os.path.normpath(dest_root)
        copy = self.mode.get() == "copy"

        def work():
            self.progress(None, None, "Planning destinations…")
            taken, plan = set(), []
            for r in sel:
                ddir = os.path.join(dest_root, r.cat)
                if same_dir(os.path.dirname(r.path), ddir):
                    plan.append((r, None, "Already in place — skipped"))
                    continue
                if not os.path.exists(r.path):
                    plan.append((r, None, "File no longer exists — skipped"))
                    continue
                dest = unique_dest(ddir, r.name, taken)
                plan.append((r, dest, "" if os.path.basename(dest) == r.name else "Renamed — a file with that name exists"))
            need = sum(r.size for r, d, _ in plan if d and (copy or not same_volume(r.path, dest_root)))
            probe = dest_root
            while not os.path.exists(probe) and os.path.dirname(probe) != probe:
                probe = os.path.dirname(probe)
            try:
                free = shutil.disk_usage(probe).free
            except OSError:
                free = None
            return plan, copy, dest_root, need, free

        self.run_bg(work, self.show_move_preview, "Preview")

    def show_move_preview(self, result):
        plan, copy, dest_root, need, free = result
        ops = [(r, d) for r, d, _ in plan if d]
        renamed = sum(1 for _, d, n in plan if d and n)
        skipped = len(plan) - len(ops)
        verb = "copied" if copy else "moved"
        self.status.set("Review the planned changes.")

        win = tk.Toplevel(self.root)
        win.title("Confirm " + ("copy" if copy else "move"))
        win.geometry("1100x600")
        win.transient(self.root)
        ttk.Label(win, padding=(8, 8, 8, 0),
                  text=f"{len(ops)} file(s) will be {verb} into {dest_root}  ·  {renamed} renamed so nothing is "
                       f"overwritten  ·  {skipped} skipped.").pack(anchor="w")
        space_ok = free is None or need <= free
        if need:
            ttk.Label(win, padding=(8, 2), foreground="#1a7f37" if space_ok else "#c62828",
                      text=f"Needs {human(need)} of space on the destination drive — "
                           f"{'free: ' + human(free) if free is not None else 'free space unknown'}"
                           f"{'' if space_ok else '  ✖ NOT ENOUGH SPACE'}").pack(anchor="w")
        tree = self.make_tree(win, [("from", "From", 470), ("to", "To", 470), ("note", "Note", 220)])
        for r, d, note in plan:
            tree.insert("", "end", values=(r.path, d or "—", note))
        btns = ttk.Frame(win, padding=8)
        btns.pack(fill="x")
        ttk.Button(btns, text="Cancel", command=win.destroy).pack(side="right")
        go = ttk.Button(btns, text=f"Confirm — {'copy' if copy else 'move'} {len(ops)} file(s)",
                        command=lambda: (win.destroy(), self.do_transfer(ops, copy, dest_root)))
        go.pack(side="right", padx=6)
        if not ops or not space_ok:
            go.state(["disabled"])
        win.grab_set()

    def do_transfer(self, ops, copy, dest_root):
        def work():
            done, errors, log = [], [], []
            for n, (r, d) in enumerate(ops, 1):
                if self.cancel.is_set():
                    errors.append("Stopped by Cancel — the rest were not touched.")
                    break
                src = r.path
                try:
                    transfer(src, d, copy)
                    done.append((r, src, d, copy))
                    log.append(("copy" if copy else "move", src, d))
                except FileExistsError:
                    errors.append(f"{src}: destination appeared meanwhile — skipped")
                except OSError as e:
                    errors.append(f"{src}: {e.strerror or e}")
                self.progress(n, len(ops), f"{'Copying' if copy else 'Moving'} {n}/{len(ops)} — {r.name}")
            return done, errors, write_log(dest_root, log)

        self.run_bg(work, self.transfer_done, "Organize", cancellable=True)

    def transfer_done(self, result):
        done, errors, logpath = result
        for r, src, d, copy in done:
            if not copy:
                r.path = d
            r.checked = False
        self.last_ops = done
        self.refresh_files()
        self.refresh_dups()
        verb = "Copied" if done and done[0][3] else "Moved"
        self.status.set(f"{verb} {len(done)} file(s). {len(errors)} problem(s).")
        text = f"{verb} {len(done)} file(s)."
        if logpath:
            text += f"\nLog: {logpath}"
        if errors:
            text += f"\n\n{len(errors)} not done:\n" + "\n".join(errors[:15]) + ("\n…" if len(errors) > 15 else "")
        messagebox.showinfo("Organize finished", text)

    def undo(self):
        if self.busy:
            return
        if not self.last_ops:
            messagebox.showinfo("Undo", "Nothing to undo yet.")
            return
        ops = list(self.last_ops)
        copy = ops[0][3]
        msg = (f"Delete the {len(ops)} copies that were just made? (Originals are untouched.)" if copy else
               f"Move the {len(ops)} file(s) back to where they were?")
        if not messagebox.askyesno("Undo last organize", msg):
            return

        def work():
            undone, errors, log = [], [], []
            for n, (r, src, d, was_copy) in enumerate(reversed(ops), 1):
                try:
                    if was_copy:
                        if os.path.getsize(d) != os.path.getsize(src):
                            raise OSError("copy differs from original — left alone")
                        os.remove(d)
                        log.append(("undo-copy (deleted copy)", d, ""))
                    else:
                        transfer(d, src, copy=False)
                        log.append(("undo-move", d, src))
                    undone.append((r, src, d, was_copy))
                except OSError as e:
                    errors.append(f"{d}: {e.strerror or e}")
                self.progress(n, len(ops), f"Undoing {n}/{len(ops)}")
            if log:
                write_log(os.path.dirname(os.path.dirname(ops[0][2])), log)
            return undone, errors

        def done(res):
            undone, errors = res
            for r, src, d, was_copy in undone:
                if not was_copy:
                    r.path = src
            self.last_ops = [op for op in self.last_ops if op not in undone]
            self.refresh_files()
            self.refresh_dups()
            text = f"Undid {len(undone)} file(s)."
            if errors:
                text += f"\n\n{len(errors)} couldn't be undone:\n" + "\n".join(errors[:15])
            self.status.set(text.splitlines()[0])
            messagebox.showinfo("Undo finished", text)

        self.run_bg(work, done, "Undo")

    # ------------------------------------------------------------------ 5. duplicates
    def refresh_dups(self):
        groups = defaultdict(list)
        for i, r in enumerate(self.records):
            if r.hash:
                groups[r.hash].append(i)
        self.dup_groups = sorted((g for g in groups.values() if len(g) > 1),
                                 key=lambda g: -self.records[g[0]].size * (len(g) - 1))
        self.dup_marked &= {i for g in self.dup_groups for i in g}
        self.dtree.delete(*self.dtree.get_children())
        for gi, idxs in enumerate(self.dup_groups[:MAX_DUP_GROUPS]):
            size = self.records[idxs[0]].size
            parent = self.dtree.insert("", "end", iid=f"g{gi}", open=True,
                                       text=f"Group {gi + 1} · {len(idxs)} identical",
                                       values=("", human(size), "", f"{human(size * (len(idxs) - 1))} can be freed"))
            for i in sorted(idxs, key=lambda i: self.records[i].mtime):
                r = self.records[i]
                self.dtree.insert(parent, "end", iid=f"f{i}", values=(
                    ON if i in self.dup_marked else OFF, human(size),
                    time.strftime("%Y-%m-%d %H:%M", time.localtime(r.mtime)), r.path))
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
        """Keep the oldest copy in each group (ties: shortest path), tick all the others."""
        self.dup_marked.clear()
        for g in self.dup_groups:
            keep = min(g, key=lambda i: (self.records[i].mtime, len(self.records[i].path), self.records[i].path))
            self.dup_marked.update(i for i in g if i != keep)
        self.refresh_dups()

    def clear_dups(self):
        self.dup_marked.clear()
        self.refresh_dups()

    def review_delete(self):
        if self.busy:
            return
        if not self.dup_marked:
            messagebox.showinfo("Nothing selected", "Click the copies you want to remove, or use Auto-select.")
            return
        plan = []
        for gi, g in enumerate(self.dup_groups):
            kept = [i for i in g if i not in self.dup_marked]
            if not kept:
                messagebox.showerror("Every copy selected",
                                     f"Group {gi + 1}: all copies are ticked. Leave at least one unticked.")
                return
            plan += [(i, kept[0]) for i in g if i in self.dup_marked]
        total = sum(self.records[i].size for i, _ in plan)
        on_usb = any(d["external"] and is_inside(self.records[i].path, d["root"])
                     for i, _ in plan for d in self.drives if d["kind"].startswith("USB flash"))

        win = tk.Toplevel(self.root)
        win.title("Review removal")
        win.geometry("1100x620")
        win.transient(self.root)
        ttk.Label(win, padding=8, text=f"{len(plan)} file(s), {human(total)}. Each one has an identical copy "
                                       f"that will be KEPT (right column).").pack(anchor="w")
        tree = self.make_tree(win, [("del", "Will be REMOVED (full path)", 530), ("keep", "Identical copy kept", 530)])
        for i, k in plan:
            tree.insert("", "end", values=(self.records[i].path, self.records[k].path))

        how = tk.StringVar(value="recycle")
        opts = ttk.LabelFrame(win, text="How to remove them", padding=6)
        opts.pack(fill="x", padx=8)
        ttk.Radiobutton(opts, value="recycle", variable=how,
                        text="Send to Recycle Bin (can be restored)" +
                             ("  — ⚠ USB flash drives have no Recycle Bin: Windows deletes them permanently"
                              if on_usb and IS_WIN else "")).pack(anchor="w")
        ttk.Radiobutton(opts, value="folder", variable=how,
                        text=f"Move into a “{DUP_FOLDER}” folder inside the scanned folder (check it, then delete it yourself)"
                        ).pack(anchor="w")
        ttk.Radiobutton(opts, value="permanent", variable=how, text="Delete permanently (cannot be undone)").pack(anchor="w")

        btns = ttk.Frame(win, padding=8)
        btns.pack(fill="x")
        agree = tk.BooleanVar(value=False)
        go = ttk.Button(btns, text=f"Remove {len(plan)} file(s)",
                        command=lambda: (win.destroy(), self.do_delete(plan, how.get())))
        go.state(["disabled"])
        ttk.Checkbutton(btns, variable=agree, text="I reviewed every path above and want to remove these files",
                        command=lambda: go.state(["!disabled"] if agree.get() else ["disabled"])).pack(side="left")
        ttk.Button(btns, text="Cancel", command=win.destroy).pack(side="right")
        go.pack(side="right", padx=6)
        win.grab_set()

    def do_delete(self, plan, how):
        recs, scan_root = self.records, self.scan_root
        dup_dir = os.path.join(scan_root, DUP_FOLDER)

        def work():
            removed, errors, freed, log, taken = set(), [], 0, [], set()
            for n, (i, k) in enumerate(plan, 1):
                if self.cancel.is_set():
                    errors.append("Stopped by Cancel — the rest were not touched.")
                    break
                r, keep = recs[i], recs[k]
                self.progress(n - 1, len(plan), f"Verifying & removing {n}/{len(plan)} — {r.name}")
                try:
                    # Safety: re-check both files byte-for-byte right before removing anything.
                    if (os.path.getsize(r.path) != r.size or os.path.getsize(keep.path) != r.size or
                            file_hash(r.path, self.cancel) != file_hash(keep.path, self.cancel)):
                        errors.append(f"{r.path}: skipped — file changed or kept copy differs")
                        continue
                    if how == "recycle":
                        to_recycle_bin(r.path)
                        log.append(("recycle-bin", r.path, ""))
                    elif how == "folder":
                        dst = unique_dest(dup_dir, r.name, taken)
                        transfer(r.path, dst, copy=False)
                        log.append(("moved-duplicate", r.path, dst))
                    else:
                        os.remove(r.path)
                        log.append(("deleted", r.path, ""))
                    removed.add(i)
                    freed += r.size
                except FileNotFoundError:
                    errors.append(f"{r.path}: file or kept copy is missing — skipped")
                except OSError as e:
                    errors.append(f"{r.path}: {e.strerror or e}")
            self.progress(len(plan), len(plan), "Done.")
            return removed, errors, freed, how, write_log(scan_root, log)

        self.run_bg(work, self.delete_done, "Remove", cancellable=True)

    def delete_done(self, result):
        removed, errors, freed, how, logpath = result
        self.records = [r for i, r in enumerate(self.records) if i not in removed]
        self.dup_marked.clear()
        self.last_ops = []
        self.refresh_files()
        self.refresh_dups()
        where = {"recycle": "sent to the Recycle Bin", "folder": f"moved into {DUP_FOLDER}",
                 "permanent": "permanently deleted"}[how]
        self.status.set(f"{len(removed)} duplicate(s) {where}" + (f", {human(freed)} freed." if how != "folder" else "."))
        text = f"{len(removed)} file(s) {where}."
        if logpath:
            text += f"\nLog: {logpath}"
        if errors:
            text += f"\n\n{len(errors)} skipped:\n" + "\n".join(errors[:15]) + ("\n…" if len(errors) > 15 else "")
        messagebox.showinfo("Cleanup finished", text)

    # ------------------------------------------------------------------ summaries
    def update_summaries(self):
        sel = [r for r in self.records if r.checked]
        hidden = getattr(self, "rows_hidden", 0)
        self.file_summary.config(text=f"{len(self.records)} files · {len(sel)} ticked ({human(sum(r.size for r in sel))})"
                                      + (f" · list shows first {MAX_FILE_ROWS} — use the filter" if hidden else ""))
        size = sum(self.records[i].size for i in self.dup_marked if i < len(self.records))
        more = f" (showing biggest {MAX_DUP_GROUPS})" if len(self.dup_groups) > MAX_DUP_GROUPS else ""
        self.dup_summary.config(text=f"{len(self.dup_groups)} group(s){more} · {len(self.dup_marked)} ticked "
                                     f"for removal ({human(size)})")


def same_volume(a, b):
    """True if paths a and b are on the same drive (moves there are instant renames)."""
    if IS_WIN:
        return os.path.splitdrive(os.path.abspath(a))[0].lower() == os.path.splitdrive(os.path.abspath(b))[0].lower()
    probe = b
    while not os.path.exists(probe) and os.path.dirname(probe) != probe:
        probe = os.path.dirname(probe)
    try:
        return os.stat(a).st_dev == os.stat(probe).st_dev
    except OSError:
        return False


def main():
    if IS_WIN:
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)   # crisp text on high-DPI laptops
        except Exception:  # noqa: BLE001
            pass
    root = tk.Tk()
    style = ttk.Style()
    if "vista" not in style.theme_names() and "clam" in style.theme_names():
        style.theme_use("clam")
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
