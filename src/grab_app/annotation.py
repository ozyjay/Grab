"""Annotation strokes, rendering, and pending screenshot storage."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import time
from typing import Callable, Iterable
import uuid

import cairo


TOKEN_PATTERN = re.compile(r"^[0-9a-f]{32}$")
MAX_PENDING_AGE = 24 * 60 * 60


@dataclass(frozen=True)
class Stroke:
    colour: tuple[float, float, float, float]
    width: float
    points: tuple[tuple[float, float], ...]


class AnnotationDocument:
    """Mutable stroke history for an image-sized drawing surface."""

    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        self._history: list[tuple[Stroke, ...]] = [()]
        self._history_index = 0
        self._current_colour: tuple[float, float, float, float] | None = None
        self._current_width = 0.0
        self._current_points: list[tuple[float, float]] = []

    @property
    def strokes(self) -> tuple[Stroke, ...]:
        return self._history[self._history_index]

    @property
    def can_undo(self) -> bool:
        return self._history_index > 0

    @property
    def can_redo(self) -> bool:
        return self._history_index < len(self._history) - 1

    def begin_stroke(
        self,
        point: tuple[float, float],
        colour: tuple[float, float, float, float],
        width: float,
    ) -> None:
        self._current_colour = colour
        self._current_width = width
        self._current_points = [self._clamp(point)]

    def append_point(self, point: tuple[float, float]) -> None:
        if self._current_colour is None:
            return
        self._current_points.append(self._clamp(point))

    def end_stroke(self) -> None:
        if self._current_colour is None:
            return
        stroke = Stroke(
            self._current_colour,
            self._current_width,
            tuple(self._current_points),
        )
        self._commit((*self.strokes, stroke))
        self._current_colour = None
        self._current_points = []

    def undo(self) -> bool:
        if self._history_index == 0:
            return False
        self._history_index -= 1
        return True

    def redo(self) -> bool:
        if self._history_index == len(self._history) - 1:
            return False
        self._history_index += 1
        return True

    def clear(self) -> bool:
        if not self.strokes:
            return False
        self._commit(())
        return True

    def all_strokes(self) -> tuple[Stroke, ...]:
        if self._current_colour is None:
            return self.strokes
        current = Stroke(
            self._current_colour,
            self._current_width,
            tuple(self._current_points),
        )
        return (*self.strokes, current)

    def _commit(self, strokes: tuple[Stroke, ...]) -> None:
        del self._history[self._history_index + 1 :]
        self._history.append(strokes)
        self._history_index += 1

    def _clamp(self, point: tuple[float, float]) -> tuple[float, float]:
        return (
            min(max(point[0], 0.0), float(self.width)),
            min(max(point[1], 0.0), float(self.height)),
        )


def draw_strokes(context: cairo.Context, strokes: Iterable[Stroke]) -> None:
    context.set_line_cap(cairo.LINE_CAP_ROUND)
    context.set_line_join(cairo.LINE_JOIN_ROUND)
    for stroke in strokes:
        if not stroke.points:
            continue
        context.set_source_rgba(*stroke.colour)
        context.set_line_width(stroke.width)
        first = stroke.points[0]
        if len(stroke.points) == 1:
            context.arc(first[0], first[1], stroke.width / 2, 0, 2 * 3.141592653589793)
            context.fill()
            continue
        context.move_to(*first)
        for point in stroke.points[1:]:
            context.line_to(*point)
        context.stroke()


def fit_image(
    image_width: int, image_height: int, canvas_width: int, canvas_height: int
) -> tuple[float, float, float]:
    """Return scale and offsets for fitting an image inside a canvas."""
    if min(image_width, image_height, canvas_width, canvas_height) <= 0:
        return 1.0, 0.0, 0.0
    scale = min(canvas_width / image_width, canvas_height / image_height)
    return (
        scale,
        (canvas_width - image_width * scale) / 2,
        (canvas_height - image_height * scale) / 2,
    )


def canvas_to_image(
    x: float,
    y: float,
    image_width: int,
    image_height: int,
    canvas_width: int,
    canvas_height: int,
) -> tuple[float, float] | None:
    scale, offset_x, offset_y = fit_image(
        image_width, image_height, canvas_width, canvas_height
    )
    image_x = (x - offset_x) / scale
    image_y = (y - offset_y) / scale
    if not (0 <= image_x <= image_width and 0 <= image_y <= image_height):
        return None
    return image_x, image_y


def render_annotation(
    source: Path, destination: Path, strokes: Iterable[Stroke]
) -> None:
    surface = cairo.ImageSurface.create_from_png(str(source))
    output = cairo.ImageSurface(
        cairo.FORMAT_ARGB32, surface.get_width(), surface.get_height()
    )
    context = cairo.Context(output)
    context.set_source_surface(surface)
    context.paint()
    draw_strokes(context, strokes)
    output.write_to_png(str(destination))
    output.finish()


@dataclass(frozen=True)
class PendingAnnotation:
    token: str
    image_path: Path
    metadata_path: Path
    saved_path: Path | None
    created_at: float
    state: str


class PendingAnnotationStore:
    """Keep notification annotation targets in the private runtime directory."""

    def __init__(
        self,
        runtime_directory: Path,
        screenshots_directory: Path,
        now: Callable[[], float] = time.time,
    ) -> None:
        self.directory = runtime_directory / "grab-annotations"
        self.screenshots_directory = screenshots_directory
        self.now = now

    def create(self, source: Path, saved_path: Path | None) -> PendingAnnotation:
        self.cleanup(remove_unopened=True)
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.directory, 0o700)
        token = uuid.uuid4().hex
        image_path = self.directory / f"{token}.png"
        metadata_path = self.directory / f"{token}.json"
        try:
            with source.open("rb") as input_stream, image_path.open("xb") as output_stream:
                os.chmod(image_path, 0o600)
                shutil.copyfileobj(input_stream, output_stream)
            payload = {
                "token": token,
                "saved_path": str(saved_path) if saved_path else None,
                "created_at": self.now(),
                "state": "pending",
            }
            self._write_metadata(metadata_path, payload)
            return self.load(token)
        except BaseException:
            image_path.unlink(missing_ok=True)
            metadata_path.unlink(missing_ok=True)
            raise

    def claim(self, token: str) -> PendingAnnotation:
        record = self.load(token)
        payload = self._read_metadata(record.metadata_path)
        payload["state"] = "open"
        self._write_metadata(record.metadata_path, payload)
        return self.load(token)

    def load(self, token: str) -> PendingAnnotation:
        if not TOKEN_PATTERN.fullmatch(token):
            raise ValueError("The annotation token is invalid.")
        image_path = self.directory / f"{token}.png"
        metadata_path = self.directory / f"{token}.json"
        payload = self._read_metadata(metadata_path)
        if payload.get("token") != token:
            raise ValueError("The annotation metadata is invalid.")
        if not image_path.is_file() or image_path.is_symlink():
            raise ValueError("The pending screenshot is invalid.")
        created_at = payload.get("created_at")
        state = payload.get("state")
        if not isinstance(created_at, (int, float)) or state not in ("pending", "open"):
            raise ValueError("The annotation metadata is invalid.")
        if self.now() - float(created_at) > MAX_PENDING_AGE:
            self.delete(token)
            raise ValueError("The pending screenshot has expired.")
        saved_path = self._validated_saved_path(payload.get("saved_path"))
        return PendingAnnotation(
            token,
            image_path,
            metadata_path,
            saved_path,
            float(created_at),
            state,
        )

    def delete(self, token: str) -> None:
        if not TOKEN_PATTERN.fullmatch(token):
            return
        (self.directory / f"{token}.png").unlink(missing_ok=True)
        (self.directory / f"{token}.json").unlink(missing_ok=True)

    def cleanup(self, remove_unopened: bool = False) -> None:
        if not self.directory.exists():
            return
        for metadata_path in self.directory.glob("*.json"):
            token = metadata_path.stem
            if not TOKEN_PATTERN.fullmatch(token):
                continue
            try:
                payload = self._read_metadata(metadata_path)
                created_at = float(payload["created_at"])
                state = payload["state"]
            except (KeyError, TypeError, ValueError, OSError, json.JSONDecodeError):
                self.delete(token)
                continue
            if self.now() - created_at > MAX_PENDING_AGE or (
                remove_unopened and state == "pending"
            ):
                self.delete(token)
        for image_path in self.directory.glob("*.png"):
            token = image_path.stem
            if TOKEN_PATTERN.fullmatch(token) and not (
                self.directory / f"{token}.json"
            ).exists():
                image_path.unlink(missing_ok=True)

    def _validated_saved_path(self, value: object) -> Path | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("The saved screenshot path is invalid.")
        path = Path(value)
        if path.is_symlink() or not path.is_file() or path.suffix.lower() != ".png":
            raise ValueError("The saved screenshot path is invalid.")
        expected = self.screenshots_directory.resolve()
        resolved = path.resolve()
        if resolved.parent != expected or not resolved.name.startswith("Screenshot "):
            raise ValueError("The saved screenshot is outside the screenshot directory.")
        return resolved

    def validate_saved_path(self, path: Path) -> Path:
        """Revalidate a saved destination immediately before replacement."""
        validated = self._validated_saved_path(str(path))
        if validated is None:
            raise ValueError("The saved screenshot path is invalid.")
        return validated

    @staticmethod
    def _read_metadata(path: Path) -> dict[str, object]:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("The annotation metadata is invalid.")
        return value

    @staticmethod
    def _write_metadata(path: Path, payload: dict[str, object]) -> None:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(
            dir=path.parent, prefix=".annotation-", suffix=".json"
        )
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(payload, stream)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        except BaseException:
            try:
                os.unlink(temporary)
            except OSError:
                pass
            raise


def replace_saved_copy(rendered: Path, destination: Path) -> None:
    """Atomically replace a saved screenshot without risking the original."""
    fd, temporary = tempfile.mkstemp(
        dir=destination.parent, prefix=".grab-annotated-", suffix=".png"
    )
    os.close(fd)
    temporary_path = Path(temporary)
    try:
        shutil.copyfile(rendered, temporary_path)
        os.chmod(temporary_path, 0o600)
        os.replace(temporary_path, destination)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise
