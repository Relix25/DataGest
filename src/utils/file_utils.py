from __future__ import annotations

import shutil
from pathlib import Path
from typing import Callable, Iterable

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}


ProgressCB = Callable[[str, int], None]


def _iter_files(folder: Path) -> Iterable[Path]:
    for path in folder.rglob("*"):
        if path.is_file():
            yield path


def count_files(folder: Path, extensions: set[str] | None = None) -> tuple[int, int]:
    folder = Path(folder)
    if not folder.exists() or not folder.is_dir():
        return (0, 0)

    allowed = {ext.lower() for ext in extensions} if extensions else None
    count = 0
    size = 0
    for f in _iter_files(folder):
        if allowed and f.suffix.lower() not in allowed:
            continue
        count += 1
        size += f.stat().st_size
    return count, size


def validate_image_folder(path: Path) -> tuple[bool, str, int, int]:
    folder = Path(path)
    if not folder.exists() or not folder.is_dir():
        return False, "Selected folder does not exist.", 0, 0

    count, size = count_files(folder, IMAGE_EXTENSIONS)
    if count == 0:
        return False, "Folder does not contain supported image files.", 0, 0
    return True, "ok", count, size


def copy_files(src: Path, dst: Path, progress_callback: ProgressCB | None = None) -> tuple[int, int]:
    src = Path(src)
    dst = Path(dst)
    files = [p for p in _iter_files(src)]
    total = len(files)
    copied = 0
    copied_size = 0

    for item in files:
        rel = item.relative_to(src)
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, target)
        copied += 1
        copied_size += item.stat().st_size
        if progress_callback:
            percent = int(copied * 100 / total) if total else 100
            progress_callback(f"Copying {rel}", percent)

    if progress_callback:
        progress_callback("Copy complete", 100)
    return copied, copied_size


def clear_folder(folder: Path) -> int:
    """Remove all files/folders under folder and return removed file count."""
    folder = Path(folder)
    if not folder.exists():
        return 0

    files = list(_iter_files(folder))
    for file_path in files:
        file_path.unlink(missing_ok=True)

    directories = [p for p in folder.rglob("*") if p.is_dir()]
    directories.sort(key=lambda p: len(p.parts), reverse=True)
    for directory in directories:
        try:
            directory.rmdir()
        except OSError:
            pass

    return len(files)
