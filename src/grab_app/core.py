"""Capture orchestration independent of GTK widgets and D-Bus details."""

from __future__ import annotations

from pathlib import Path
import shutil
from typing import Callable, Protocol
from urllib.parse import unquote, urlparse

from .config import ConfigStore, next_screenshot_path, pictures_directory
from .portal import CaptureResult


class Portal(Protocol):
    def capture(self, callback: Callable[[CaptureResult], None]) -> None: ...


class CaptureCoordinator:
    def __init__(
        self,
        portal: Portal,
        config: ConfigStore,
        load_image: Callable[[Path], object],
        set_clipboard: Callable[[object], None],
        notify: Callable[[str, str | None, str | None, bool], None],
        clipboard_owned: Callable[[object], None],
        finished: Callable[[], None],
        stage_annotation: Callable[[Path, Path | None], str],
        pictures: Callable[[], Path] = pictures_directory,
        clipboard_already_set: bool = False,
    ) -> None:
        self.portal = portal
        self.config = config
        self.load_image = load_image
        self.set_clipboard = set_clipboard
        self.notify = notify
        self.clipboard_owned = clipboard_owned
        self.finished = finished
        self.stage_annotation = stage_annotation
        self.pictures = pictures
        self.clipboard_already_set = clipboard_already_set

    def capture(self) -> None:
        try:
            self.portal.capture(self._on_result)
        except Exception as error:
            self.notify("Screenshot failed", str(error), None, False)
            self.finished()

    @staticmethod
    def _path_from_uri(uri: str) -> Path:
        parsed = urlparse(uri)
        if parsed.scheme != "file" or parsed.netloc not in ("", "localhost"):
            raise ValueError("The screenshot service returned an unsupported image URI.")
        path = Path(unquote(parsed.path))
        if not path.is_absolute():
            raise ValueError("The screenshot service returned an invalid image path.")
        return path

    def _on_result(self, result: CaptureResult) -> None:
        if result.status == "cancelled":
            self.notify("Screenshot cancelled", None, None, False)
            self.finished()
            return
        if result.status != "success" or not result.uri:
            self.notify(
                "Screenshot failed",
                result.message or "Unknown screenshot error.",
                None,
                False,
            )
            self.finished()
            return

        source: Path | None = None
        saved: Path | None = None
        save_error: Exception | None = None
        annotation_error: Exception | None = None
        try:
            source = self._path_from_uri(result.uri)
            image = self.load_image(source)
            if self.config.load()["save_copy"]:
                try:
                    directory = self.pictures() / "Screenshots"
                    directory.mkdir(parents=True, exist_ok=True)
                    saved = next_screenshot_path(directory)
                    shutil.copy2(source, saved)
                except Exception as error:
                    save_error = error
            if not self.clipboard_already_set:
                self.set_clipboard(image)
                self.clipboard_owned(image)
            annotation_token: str | None = None
            try:
                annotation_token = self.stage_annotation(source, saved)
            except Exception as error:
                annotation_error = error
            if save_error:
                body = f"Could not save a copy: {save_error}"
                if annotation_error:
                    body += f"\nAnnotation unavailable: {annotation_error}"
                self.notify("Screenshot copied", body, annotation_token, True)
            elif saved:
                body = str(saved)
                if annotation_error:
                    body += f"\nAnnotation unavailable: {annotation_error}"
                self.notify(
                    "Screenshot copied and saved", body, annotation_token, False
                )
            else:
                body = (
                    f"Annotation unavailable: {annotation_error}"
                    if annotation_error
                    else None
                )
                self.notify("Screenshot copied", body, annotation_token, True)
        except Exception as error:
            self.notify("Screenshot failed", str(error), None, False)
        finally:
            if source is not None:
                try:
                    source.unlink(missing_ok=True)
                except OSError:
                    pass
            self.finished()
