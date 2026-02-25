from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable

from core.config import AppConfig
from utils.platform import get_local_appdata


ProgressCB = Callable[[str, int], None]
CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def _popen_kwargs() -> dict:
    if os.name == "nt":
        return {"creationflags": CREATE_NO_WINDOW}
    return {}


class ToolBootstrap:
    DVC_RELEASE_API = "https://api.github.com/repos/iterative/dvc/releases/latest"
    DVC_EXE_BASE_URL = "https://downloads.dvc.org/exe"

    def __init__(self, config: AppConfig | None = None, tools_dir: Path | None = None) -> None:
        self.config = config or AppConfig()
        self.tools_dir = tools_dir or (get_local_appdata() / "tools")
        self.tools_dir.mkdir(parents=True, exist_ok=True)

        self.mingit_dir = self.tools_dir / "mingit"
        self.dvc_dir = self.tools_dir / "dvc"

    def ensure_git(self, progress_cb: ProgressCB | None = None) -> Path:
        system_git = shutil.which("git")
        if system_git:
            return Path(system_git)

        if os.name != "nt":
            raise RuntimeError("Git executable not found on PATH. Please install Git.")

        candidates = [self.mingit_dir / "cmd" / "git.exe", self.mingit_dir / "bin" / "git.exe"]
        for candidate in candidates:
            if candidate.exists():
                return candidate

        source = self._resolve_source(self.config.mingit_lan, self.config.mingit_url)
        self._download_and_extract_zip(source, self.mingit_dir, "MinGit", progress_cb)

        for candidate in candidates:
            if candidate.exists():
                return candidate
        raise RuntimeError("MinGit installation incomplete: git.exe not found")

    def ensure_dvc(self, progress_cb: ProgressCB | None = None) -> Path:
        existing = self._find_dvc_cli()
        if existing:
            return existing

        if os.name != "nt":
            raise RuntimeError("DVC executable not found on PATH. Please install DVC.")

        source = self._resolve_source(self.config.dvc_lan, self.config.dvc_url)
        if source.lower().startswith(("http://", "https://")):
            source = self._resolve_dvc_source(source)

        self.dvc_dir.mkdir(parents=True, exist_ok=True)

        if source.lower().endswith(".zip"):
            self._download_and_extract_zip(source, self.dvc_dir, "DVC", progress_cb)
        elif source.lower().endswith(".exe"):
            with tempfile.TemporaryDirectory(prefix="datagest-dvc-") as tmp:
                installer = Path(tmp) / "dvc-installer.exe"
                self._download_or_copy(source, installer, "DVC installer", progress_cb)
                install_root = self.dvc_dir / "install"
                if install_root.exists():
                    shutil.rmtree(install_root)
                install_root.mkdir(parents=True, exist_ok=True)
                self._install_dvc_installer(installer, install_root, progress_cb)
        else:
            # Fallback for a directly provided CLI binary.
            target = self.dvc_dir / "dvc.exe"
            self._download_or_copy(source, target, "DVC", progress_cb)

        cli = self._find_dvc_cli()
        if not cli:
            raise RuntimeError(
                "DVC installation completed but no working dvc CLI was found. "
                "Set 'dvc_lan' to a known-good installer or CLI archive."
            )
        return cli

    def _resolve_source(self, lan_path: str | None, url: str) -> str:
        if lan_path:
            path = Path(lan_path)
            if path.exists():
                return str(path)
        if not url:
            raise RuntimeError("No tool source available (LAN path missing and URL not configured)")
        return url

    def _resolve_dvc_source(self, preferred_url: str) -> str:
        if self._url_exists(preferred_url):
            return preferred_url

        latest_version = self._fetch_latest_dvc_version()
        if latest_version:
            candidate = f"{self.DVC_EXE_BASE_URL}/dvc-{latest_version}.exe"
            if self._url_exists(candidate):
                return candidate

        raise RuntimeError(
            "Unable to download DVC. Configured URL returned 404 and no valid fallback was found. "
            "Set 'dvc_lan' to a network installer or update 'dvc_url' in config.yaml."
        )

    def _fetch_latest_dvc_version(self) -> str | None:
        try:
            request = urllib.request.Request(
                self.DVC_RELEASE_API,
                headers={"Accept": "application/vnd.github+json", "User-Agent": "DataGest"},
            )
            with urllib.request.urlopen(request, timeout=15) as response:
                payload = json.loads(response.read().decode("utf-8"))
            tag = str(payload.get("tag_name") or "").strip()
            return tag.lstrip("v") if tag else None
        except Exception:
            return None

    def _url_exists(self, url: str) -> bool:
        try:
            request = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "DataGest"})
            with urllib.request.urlopen(request, timeout=15):
                return True
        except urllib.error.HTTPError as exc:
            if exc.code in (403, 405):
                try:
                    request = urllib.request.Request(
                        url,
                        headers={"Range": "bytes=0-0", "User-Agent": "DataGest"},
                    )
                    with urllib.request.urlopen(request, timeout=15):
                        return True
                except Exception:
                    return False
            return False
        except Exception:
            return False

    def _download_or_copy(
        self,
        source: str,
        target: Path,
        label: str,
        progress_cb: ProgressCB | None = None,
    ) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        if progress_cb:
            progress_cb(f"Preparing {label}", 5)

        if source.lower().startswith(("http://", "https://")):
            tmp_target = target.with_suffix(target.suffix + ".tmp")
            if tmp_target.exists():
                tmp_target.unlink()

            try:
                with urllib.request.urlopen(source) as response, tmp_target.open("wb") as out:
                    total = int(response.headers.get("Content-Length", "0") or 0)
                    downloaded = 0
                    while True:
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        out.write(chunk)
                        downloaded += len(chunk)
                        if progress_cb and total > 0:
                            percent = min(95, int(downloaded * 100 / total))
                            progress_cb(f"Downloading {label}", percent)
            except urllib.error.HTTPError as exc:
                if tmp_target.exists():
                    tmp_target.unlink(missing_ok=True)
                raise RuntimeError(f"Failed to download {label}: HTTP {exc.code} for {source}") from exc

            tmp_target.replace(target)
        else:
            shutil.copy2(Path(source), target)

        if progress_cb:
            progress_cb(f"{label} ready", 100)

    def _download_and_extract_zip(
        self,
        source: str,
        target_dir: Path,
        label: str,
        progress_cb: ProgressCB | None = None,
    ) -> None:
        target_dir.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory(prefix="datagest-tools-") as tmp:
            archive = Path(tmp) / f"{label.lower()}.zip"
            self._download_or_copy(source, archive, label, progress_cb)

            if progress_cb:
                progress_cb(f"Extracting {label}", 96)
            with zipfile.ZipFile(archive, "r") as zf:
                zf.extractall(target_dir)

        if progress_cb:
            progress_cb(f"{label} ready", 100)

    def _install_dvc_installer(
        self,
        installer_path: Path,
        target_dir: Path,
        progress_cb: ProgressCB | None = None,
    ) -> None:
        if progress_cb:
            progress_cb("Installing DVC", 97)

        proc = subprocess.run(
            [
                str(installer_path),
                "/SP-",
                "/VERYSILENT",
                "/SUPPRESSMSGBOXES",
                "/NORESTART",
                f"/DIR={target_dir}",
            ],
            capture_output=True,
            text=True,
            check=False,
            **_popen_kwargs(),
        )
        if proc.returncode != 0:
            msg = proc.stderr.strip() or proc.stdout.strip() or "Unknown installer error"
            raise RuntimeError(f"DVC installer failed: {msg}")

    def _find_dvc_cli(self) -> Path | None:
        path_candidate = shutil.which("dvc")
        if path_candidate:
            candidate = Path(path_candidate)
            if self._is_valid_dvc_exe(candidate):
                return candidate

        executable_name = "dvc.exe" if os.name == "nt" else "dvc"
        search_roots = [
            self.dvc_dir,
            self.dvc_dir / "install",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "DVC",
            Path(os.environ.get("ProgramFiles", "")) / "DVC",
            Path(os.environ.get("ProgramFiles(x86)", "")) / "DVC",
        ]

        candidates: list[Path] = []
        for root in search_roots:
            if not str(root):
                continue
            root = Path(root)
            if not root.exists():
                continue
            direct = root / executable_name
            if direct.exists():
                candidates.append(direct)
            candidates.extend(root.rglob(executable_name))

        seen: set[str] = set()
        for candidate in sorted(candidates, key=lambda p: len(str(p))):
            key = str(candidate).lower()
            if key in seen:
                continue
            seen.add(key)
            if self._is_valid_dvc_exe(candidate):
                return candidate
        return None

    def _is_valid_dvc_exe(self, exe_path: Path) -> bool:
        if self._looks_like_installer(exe_path):
            return False
        try:
            proc = subprocess.run(
                [str(exe_path), "version"],
                capture_output=True,
                text=True,
                check=False,
                timeout=20,
                **_popen_kwargs(),
            )
        except (OSError, subprocess.TimeoutExpired):
            return False

        output = (proc.stdout or "") + "\n" + (proc.stderr or "")
        return proc.returncode == 0 and "dvc version" in output.lower()

    def _looks_like_installer(self, exe_path: Path) -> bool:
        try:
            with exe_path.open("rb") as f:
                data = f.read(1024 * 1024)
            return b"Inno Setup" in data
        except OSError:
            return False

    def check_versions(self, install_missing: bool = True) -> dict[str, str]:
        versions: dict[str, str] = {"git": "unknown", "dvc": "unknown"}

        git_path: Path | None
        dvc_path: Path | None

        if install_missing:
            try:
                git_path = self.ensure_git()
            except Exception:
                git_path = None
            try:
                dvc_path = self.ensure_dvc()
            except Exception:
                dvc_path = None
        else:
            git_from_path = shutil.which("git")
            if git_from_path:
                git_path = Path(git_from_path)
            else:
                git_path = self.mingit_dir / "cmd" / "git.exe"
                if not git_path.exists():
                    git_path = self.mingit_dir / "bin" / "git.exe"
                    if not git_path.exists():
                        git_path = None
            dvc_path = self._find_dvc_cli()

        if git_path:
            proc = subprocess.run([str(git_path), "--version"], capture_output=True, text=True, check=False)
            git_out = (proc.stdout or "").strip()
            versions["git"] = git_out.replace("git version", "").strip() if git_out else "unknown"

        if dvc_path:
            proc = subprocess.run([str(dvc_path), "version"], capture_output=True, text=True, check=False)
            dvc_out = (proc.stdout or "").strip()
            versions["dvc"] = dvc_out.splitlines()[0].strip() if dvc_out else "unknown"

        return versions
