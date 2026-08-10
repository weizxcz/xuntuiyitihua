import argparse
import os
from multiprocessing import Process
from pathlib import Path

try:
    from tqdm import tqdm
except ImportError:
    def tqdm(iterable):
        return iterable

from utils.config import BRIGHTNESS
from utils.render_pipeline import render_item_from_bpy_script


ROOT_DIR = Path(__file__).resolve().parent


def resolve_blender_executable(user_path: str | None) -> str:
    """Resolve a usable Blender executable path.

    On Windows Blender is normally installed to
    ``C:\\Program Files\\Blender Foundation\\Blender <ver>\\blender.exe`` and is
    not on PATH, so we probe the common locations when the user did not pass an
    explicit ``--blender_executable``.
    """
    if user_path:
        return user_path

    import glob

    candidates: list[str] = []
    if os.name == "nt":  # Windows
        # Standard installer location.
        base = r"C:\Program Files\Blender Foundation"
        if os.path.isdir(base):
            # Glob over every installed major.minor version directory.
            candidates += glob.glob(os.path.join(base, "Blender *", "blender.exe"))
        # Portable copy downloaded next to the repo (e.g. Blender/blender-4.4.1-windows-x64/blender.exe).
        portable_dir = ROOT_DIR.parent / "Blender"
        if os.path.isdir(str(portable_dir)):
            candidates += glob.glob(
                os.path.join(str(portable_dir), "blender-*-windows-x64", "blender.exe")
            )
        # Also accept a portable copy inside the repo root.
        candidates.append(str(ROOT_DIR / "blender" / "blender.exe"))
    else:
        candidates.append("blender")  # rely on PATH

    for cand in candidates:
        if cand and os.path.exists(cand):
            return cand

    # Fall back to letting subprocess fail with a clear later error.
    return candidates[0] if candidates else "blender"



def load_bpy_script(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read()


def has_rendered_image(item_dir):
    for file in os.listdir(item_dir):
        if file.lower().endswith(".png"):
            return True
    return False


def _render_worker(script, item_name, item_dir, blender_executable, brightness):
    render_item_from_bpy_script(
        script=script,
        item_name=item_name,
        output_folder=item_dir,
        blender_executable=blender_executable,
        brightness=brightness,
    )


def process_single_item(
    item_dir,
    item_name,
    blender_executable,
    brightness,
    timeout=None,
    overwrite=False,
):
    if has_rendered_image(item_dir) and not overwrite:
        print(f"[SKIP] PNG image already exists for {item_name}, skipping...")
        return

    bpy_path = os.path.join(item_dir, "bpy.txt")
    if not os.path.exists(bpy_path):
        print(f"[WARNING] bpy.txt not found in {item_dir}. Skipping.")
        return

    print(f"[INFO] Processing {item_name}...")
    script = load_bpy_script(bpy_path)

    if timeout is None or timeout <= 0:
        render_item_from_bpy_script(
            script=script,
            item_name=item_name,
            output_folder=item_dir,
            blender_executable=blender_executable,
            brightness=brightness,
        )
        print(f"Image rendered and saved in {item_dir}")
        return

    print(f"[INFO] Start rendering {item_name} with timeout = {timeout}s ...")
    process = Process(
        target=_render_worker,
        args=(script, item_name, item_dir, blender_executable, brightness),
    )
    process.start()
    process.join(timeout)

    if process.is_alive():
        print(f"[TIMEOUT] Rendering {item_name} exceeded {timeout} seconds. Skipping this item.")
        process.terminate()
        process.join()
    elif process.exitcode == 0:
        print(f"Image rendered and saved in {item_dir}")
    else:
        print(f"[ERROR] Rendering process for {item_name} exited with code {process.exitcode}.")


def iter_target_dirs(base_dir, all_subdirs=False, recursive=False, target_name=None):
    if not os.path.exists(base_dir):
        print(f"[ERROR] Directory '{base_dir}' does not exist.")
        return

    if all_subdirs:
        if recursive:
            for root, dirs, _files in os.walk(base_dir):
                for d in dirs:
                    path = os.path.join(root, d)
                    if os.path.isdir(path):
                        yield path, d
        else:
            for d in os.listdir(base_dir):
                path = os.path.join(base_dir, d)
                if os.path.isdir(path):
                    yield path, d
    else:
        found_any = False
        for d in os.listdir(base_dir):
            path = os.path.join(base_dir, d)
            if not os.path.isdir(path):
                continue
            if d.startswith(f"{target_name} ("):
                found_any = True
                yield path, d
        if not found_any:
            print(f"[WARNING] No folders found for target name: '{target_name}'")


def batch_render(
    base_dir,
    blender_executable,
    brightness,
    all_subdirs=False,
    recursive=False,
    target_name="Smartphone",
    timeout=None,
    overwrite=False,
):
    count = 0
    for item_path, item_folder in tqdm(
        iter_target_dirs(
            base_dir,
            all_subdirs=all_subdirs,
            recursive=recursive,
            target_name=target_name,
        )
    ):
        process_single_item(
            item_path,
            item_folder,
            blender_executable,
            brightness,
            timeout=timeout,
            overwrite=overwrite,
        )
        count += 1

    if count == 0:
        scope = "all subfolders" if all_subdirs else f"target '{target_name}'"
        print(f"[INFO] Nothing to process under {scope} in '{base_dir}'.")


def parse_args():
    parser = argparse.ArgumentParser(description="Batch render Blender objects with bbox-aware cameras.")
    parser.add_argument(
        "--base_dir",
        type=str,
        default=str(ROOT_DIR / "output"),
        help="Base directory where item folders are stored.",
    )
    parser.add_argument(
        "--blender_executable",
        type=str,
        default=None,
        help="Path to Blender executable. On Windows this is auto-detected "
        "from 'C:\\Program Files\\Blender Foundation' when omitted.",
    )
    parser.add_argument(
        "--brightness",
        type=str,
        default="Dark",
        choices=BRIGHTNESS.keys(),
        help="Brightness level.",
    )
    parser.add_argument(
        "--target_name",
        type=str,
        default="Airplane",
        help="Item name to match. Ignored when --all is set.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Render all subfolders and ignore --target_name.",
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="When used with --all, search subfolders recursively.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=180,
        help="Max seconds for rendering a single item. 0 or negative means no timeout.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Re-render folders even if PNG images already exist.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    blender_executable = resolve_blender_executable(args.blender_executable)
    print(f"[INFO] Using Blender executable: {blender_executable}")
    batch_render(
        base_dir=args.base_dir,
        blender_executable=blender_executable,
        brightness=args.brightness,
        all_subdirs=args.all,
        recursive=args.recursive,
        target_name=args.target_name,
        timeout=args.timeout,
        overwrite=args.overwrite,
    )
