"""
Face Sorter - automatic na pag-sort ng photos ayon sa mukha.

Detection + recognition: InsightFace buffalo_l (RetinaFace + ArcFace), CPU.

Output (default: katabi ng input folder, "<input>_Sorted"):
    Face_1/, Face_2/, ...   -> photos na iisang mukha lang (Face_1 = pinakamaraming photos)
    Group_Photos/           -> photos na may 2+ mukha (hindi dinu-duplicate)
    Unknown/                -> walang mukha, malabo, o mukhang isang beses lang lumabas
    face_sorter_log.csv     -> record ng lahat ng nilipat (para sa --undo)

Gamit:
    python face_sorter.py "C:\\Users\\Ako\\Pictures\\Photos"
    python face_sorter.py "C:\\...\\Photos" --dry-run      # silip muna, walang ililipat
    python face_sorter.py "C:\\...\\Photos" --undo         # ibalik lahat sa dati

May cache ("<input>_Sorted_cache.pkl"): ang dry-run, pag-palit ng --threshold, at ang
totoong sort pagkatapos ay hindi na uulitin ang pagsusuri ng mukha. Kapag naputol
(Ctrl+C, nag-shutdown), itutuloy lang kung saan huminto.
"""

import argparse
import csv
import os
import pickle
import shutil
import sys
import warnings
from collections import Counter
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore", category=FutureWarning)  # ingay galing sa skimage/insightface
from PIL import Image, ImageOps

try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
    HEIC_OK = True
except ImportError:
    HEIC_OK = False

try:
    from tqdm import tqdm
except ImportError:  # gumagana pa rin kahit walang tqdm
    def tqdm(x, **_):
        return x

# ===================== SETTINGS (pwedeng baguhin) =====================
DET_SIZE = 640               # laki ng image na sinusuri ng detector
MIN_DET_SCORE = 0.60         # gaano kasigurado na mukha talaga (0-1)
MIN_FACE_PX = 40             # mukhang mas maliit dito ay hindi bibilangin (malayo/background)
MATCH_THRESHOLD = 0.50       # mas mababa = mas mahigpit (mas maraming Face folder)
MIN_PHOTOS_PER_FACE = 2      # ilang photo bago gawan ng sariling Face folder; kulang -> Unknown
MAX_SIDE = 2560              # pinapaliit ang sobrang laking image para bumilis
# ======================================================================

EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}
if HEIC_OK:
    EXTS |= {".heic", ".heif"}

LOG_NAME = "face_sorter_log.csv"
CACHE_VERSION = 1
SAVE_EVERY = 100             # i-save ang progress kada ilang image
UNKNOWN, GROUP = "Unknown", "Group_Photos"


def collect_images(root: Path, skip_dir: Path):
    files = []
    skip = skip_dir.resolve()
    for dirpath, dirnames, filenames in os.walk(root):
        dp = Path(dirpath)
        dirnames[:] = [d for d in dirnames if (dp / d).resolve() != skip]
        for f in filenames:
            p = dp / f
            if p.suffix.lower() in EXTS:
                files.append(p)
    return sorted(files)


def load_bgr(path: Path):
    # PIL para gumana kahit may special characters ang path sa Windows
    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")
        if max(im.size) > MAX_SIDE:
            im.thumbnail((MAX_SIDE, MAX_SIDE))
        arr = np.asarray(im)
    return arr[:, :, ::-1].copy()  # RGB -> BGR


def load_model():
    from insightface.app import FaceAnalysis
    app = FaceAnalysis(
        name="buffalo_l",
        providers=["CPUExecutionProvider"],
        allowed_modules=["detection", "recognition"],
    )
    app.prepare(ctx_id=-1, det_size=(DET_SIZE, DET_SIZE))
    return app


def cache_settings():
    return (CACHE_VERSION, DET_SIZE, MIN_DET_SCORE, MIN_FACE_PX, MAX_SIDE)


def file_key(p: Path):
    st = p.stat()
    return (st.st_size, int(st.st_mtime))


def load_cache(path: Path):
    try:
        with open(path, "rb") as fh:
            data = pickle.load(fh)
        if data.get("settings") == cache_settings():
            return data["items"]
    except Exception:
        pass
    return {}


def save_cache(path: Path, items):
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "wb") as fh:
        pickle.dump({"settings": cache_settings(), "items": items}, fh)
    os.replace(tmp, path)


def faces_in(app, img):
    good = []
    for f in app.get(img):
        x1, y1, x2, y2 = f.bbox
        if f.det_score < MIN_DET_SCORE or min(x2 - x1, y2 - y1) < MIN_FACE_PX:
            continue
        good.append(np.asarray(f.normed_embedding, dtype=np.float32))
    return good


def analyze(files, cache_path: Path):
    """Ibinabalik: {path: [embedding, ...]} at listahan ng di mabasang files."""
    cache = load_cache(cache_path)
    results, errors, todo = {}, [], []
    for p in files:
        try:
            key = file_key(p)
        except OSError as e:
            errors.append((p, str(e)))
            continue
        hit = cache.get(str(p))
        if hit and hit[0] == key:
            if hit[1] is None:
                errors.append((p, "hindi mabasa (naunang run)"))
            else:
                results[p] = hit[1]
        else:
            todo.append((p, key))

    if results:
        print(f"Galing sa cache (hindi na susuriin ulit): {len(results)}")
    if not todo:
        return results, errors

    print("Nilo-load ang model (unang run: magda-download ng ~300MB)...")
    app = load_model()
    done = 0
    try:
        for p, key in tqdm(todo, desc="Sinusuri ang mukha", unit="img"):
            try:
                good = faces_in(app, load_bgr(p))
            except Exception as e:  # sirang file o kakaibang image: i-skip, huwag i-crash
                errors.append((p, str(e)))
                cache[str(p)] = (key, None)
                continue
            results[p] = good
            cache[str(p)] = (key, good)
            done += 1
            if done % SAVE_EVERY == 0:
                save_cache(cache_path, cache)
    except KeyboardInterrupt:
        save_cache(cache_path, cache)
        sys.exit("\nNahinto. Naka-save ang progress; i-run ulit para ituloy.")
    save_cache(cache_path, cache)
    return results, errors


def cluster(embs, threshold):
    if len(embs) == 0:
        return np.array([], dtype=int)
    if len(embs) == 1:
        return np.array([0])
    from sklearn.cluster import AgglomerativeClustering
    model = AgglomerativeClustering(
        n_clusters=None, metric="cosine", linkage="average",
        distance_threshold=threshold,
    )
    return model.fit_predict(np.vstack(embs))


def make_plan(results, threshold):
    """Ibinabalik: listahan ng (source_path, folder_name)."""
    plan = []
    singles = [(p, e[0]) for p, e in results.items() if len(e) == 1]
    labels = cluster([e for _, e in singles], threshold)

    counts = Counter(labels.tolist())
    keep = sorted((l for l, c in counts.items() if c >= MIN_PHOTOS_PER_FACE),
                  key=lambda l: (-counts[l], l))
    names = {l: f"Face_{i + 1}" for i, l in enumerate(keep)}

    for (p, _), l in zip(singles, labels.tolist()):
        plan.append((p, names.get(l, UNKNOWN)))
    for p, e in results.items():
        if len(e) == 0:
            plan.append((p, UNKNOWN))
        elif len(e) >= 2:
            plan.append((p, GROUP))
    return plan


def unique_dest(folder: Path, name: str):
    dest = folder / name
    stem, suf, i = dest.stem, dest.suffix, 1
    while dest.exists():
        dest = folder / f"{stem}_{i}{suf}"
        i += 1
    return dest


def execute(plan, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = out_dir / LOG_NAME
    new_log = not log_path.exists()
    moved = 0
    with open(log_path, "a", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        if new_log:
            w.writerow(["original_path", "new_path", "folder"])
        for src, folder in tqdm(plan, desc="Inililipat", unit="img"):
            dest_dir = out_dir / folder
            dest_dir.mkdir(exist_ok=True)
            dest = unique_dest(dest_dir, src.name)
            try:
                shutil.move(str(src), str(dest))
            except Exception as e:
                print(f"  [hindi nailipat] {src}: {e}")
                continue
            w.writerow([str(src), str(dest), folder])
            fh.flush()  # para may record kahit maputol
            moved += 1
    return moved


def undo(out_dir: Path):
    log_path = out_dir / LOG_NAME
    if not log_path.exists():
        print(f"Walang log na nakita sa {out_dir}")
        return
    with open(log_path, newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    back = skipped = 0
    for r in reversed(rows):
        src, dst = Path(r["new_path"]), Path(r["original_path"])
        if not src.exists() or dst.exists():
            skipped += 1
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        back += 1
    log_path.replace(log_path.with_name("face_sorter_log_UNDONE.csv"))
    # tanggalin ang mga naiwang walang-lamang folder (Face_1, Unknown, ...)
    for dirpath, _, _ in sorted(os.walk(out_dir), key=lambda t: -len(t[0])):
        if Path(dirpath) != out_dir:
            try:
                os.rmdir(dirpath)
            except OSError:
                pass
    print(f"Naibalik: {back} | Na-skip: {skipped}")


def print_summary(plan, errors):
    c = Counter(f for _, f in plan)
    faces = sorted((k for k in c if k.startswith("Face_")), key=lambda k: int(k.split("_")[1]))
    print("\n===== RESULTA =====")
    for k in faces:
        print(f"  {k:<14} {c[k]} photos")
    print(f"  {GROUP:<14} {c.get(GROUP, 0)} photos")
    print(f"  {UNKNOWN:<14} {c.get(UNKNOWN, 0)} photos")
    print(f"  Mga tao: {len(faces)} | Kabuuan: {len(plan)}")
    if errors:
        print(f"  Hindi mabasa (naiwan sa pwesto): {len(errors)}")
        for p, e in errors[:10]:
            print(f"    - {p}: {e}")


def main():
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass

    ap = argparse.ArgumentParser(description="I-sort ang photos ayon sa mukha.")
    ap.add_argument("input", nargs="?", help="Folder ng photos (kasama ang subfolders)")
    ap.add_argument("--output", help="Saan ilalagay ang sorted folders")
    ap.add_argument("--dry-run", action="store_true", help="Silip lang, walang ililipat")
    ap.add_argument("--undo", action="store_true", help="Ibalik ang mga nilipat")
    ap.add_argument("--threshold", type=float, default=MATCH_THRESHOLD,
                    help=f"Match threshold (default {MATCH_THRESHOLD})")
    args = ap.parse_args()

    raw = args.input or input("I-paste ang folder path ng photos: ").strip().strip('"')
    in_dir = Path(raw).expanduser().resolve()
    if not in_dir.is_dir():
        sys.exit(f"Hindi makita ang folder: {in_dir}")
    out_dir = Path(args.output).resolve() if args.output else in_dir.parent / f"{in_dir.name}_Sorted"

    if args.undo:
        undo(out_dir)
        return

    if not args.dry_run and (out_dir / LOG_NAME).exists():
        print(f"\n[!] May laman na ang {out_dir} galing sa naunang sort.")
        print("    Ang Face_1 ngayon ay maaaring IBANG tao sa Face_1 dati, kaya maghahalo sila.")
        print('    Mas ligtas: gumamit ng ibang --output, o i-undo muna ang dati.')
        if input("    Ituloy pa rin? (y/N): ").strip().lower() != "y":
            return

    files = collect_images(in_dir, out_dir)
    print(f"Nakitang images: {len(files)}" + ("" if HEIC_OK else " (HEIC hindi kasama; i-install ang pillow-heif)"))
    if not files:
        return

    cache_path = out_dir.parent / f"{out_dir.name}_cache.pkl"
    results, errors = analyze(files, cache_path)

    print("Pinapangkat ang magkakaparehong mukha...")
    plan = make_plan(results, args.threshold)
    print_summary(plan, errors)

    if args.dry_run:
        preview = out_dir.parent / f"{out_dir.name}_preview.csv"
        with open(preview, "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.writer(fh)
            w.writerow(["original_path", "folder"])
            w.writerows((str(p), f) for p, f in plan)
        print(f"\n[DRY RUN] Walang nilipat. Tingnan ang plano: {preview}")
        return

    moved = execute(plan, out_dir)
    try:
        cache_path.unlink()  # nailipat na ang photos, wala nang silbi ang cache
    except OSError:
        pass
    print(f"\nTapos! {moved} photos nilipat sa: {out_dir}")
    print(f'Para ibalik: python face_sorter.py "{in_dir}" --undo')


if __name__ == "__main__":
    main()
