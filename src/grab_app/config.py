"""Configuration and screenshot destination helpers."""

from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
import tempfile
from typing import Any


DEFAULT_CONFIG = {"save_copy": False}


def config_home() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))


def config_path() -> Path:
    return config_home() / "grab" / "settings.json"


class ConfigStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or config_path()

    def load(self) -> dict[str, bool]:
        try:
            raw: Any = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeError):
            return DEFAULT_CONFIG.copy()

        if not isinstance(raw, dict) or not isinstance(raw.get("save_copy"), bool):
            return DEFAULT_CONFIG.copy()
        return {"save_copy": raw["save_copy"]}

    def set_save_copy(self, enabled: bool) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps({"save_copy": bool(enabled)}, indent=2) + "\n"
        fd, temporary = tempfile.mkstemp(
            dir=self.path.parent, prefix=".settings-", suffix=".json"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        except BaseException:
            try:
                os.unlink(temporary)
            except OSError:
                pass
            raise


def pictures_directory() -> Path:
    """Return the XDG pictures directory, with a predictable fallback."""
    try:
        import gi

        gi.require_version("GLib", "2.0")
        from gi.repository import GLib

        value = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_PICTURES)
        if value:
            return Path(value)
    except (ImportError, ValueError):
        pass
    return Path.home() / "Pictures"


def next_screenshot_path(
    directory: Path, when: datetime | None = None
) -> Path:
    when = when or datetime.now()
    stem = f"Screenshot {when:%Y-%m-%d %H-%M-%S}"
    candidate = directory / f"{stem}.png"
    suffix = 2
    while candidate.exists():
        candidate = directory / f"{stem} ({suffix}).png"
        suffix += 1
    return candidate
