"""GTK window for cropping and drawing over a captured screenshot."""

from __future__ import annotations

from typing import Callable

import cairo
import gi

gi.require_version("Gdk", "4.0")
gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, Gtk

from .annotation import (
    AnnotationDocument,
    CropRectangle,
    PendingAnnotation,
    canvas_to_image,
    draw_strokes,
    fit_image,
    normalise_crop,
)


class AnnotationWindow(Gtk.ApplicationWindow):
    def __init__(
        self,
        application: Gtk.Application,
        pending: PendingAnnotation,
        complete: Callable[[PendingAnnotation, AnnotationDocument], str | None],
        cancel: Callable[[PendingAnnotation], None],
    ) -> None:
        super().__init__(application=application)
        self.pending = pending
        self.complete = complete
        self.cancel = cancel
        self._resolved = False
        self._mode = "pen"
        self._drag_origin: tuple[float, float] | None = None
        self._crop_selection: CropRectangle | None = None
        self._crop_drag_handle: str | None = None
        self._crop_drag_start: CropRectangle | None = None
        self._crop_anchor = (0.0, 0.0)
        self.surface = cairo.ImageSurface.create_from_png(str(pending.image_path))
        self.document = AnnotationDocument(
            self.surface.get_width(), self.surface.get_height()
        )

        self.set_title("Edit Screenshot")
        self.set_default_size(1100, 760)
        self.set_size_request(640, 420)

        layout = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        layout.append(self._build_toolbar())

        self.error_label = Gtk.Label()
        self.error_label.add_css_class("error")
        self.error_label.set_margin_start(12)
        self.error_label.set_margin_end(12)
        self.error_label.set_margin_top(6)
        self.error_label.set_margin_bottom(6)
        self.error_label.set_wrap(True)
        self.error_label.set_visible(False)
        layout.append(self.error_label)

        self.canvas = Gtk.DrawingArea()
        self.canvas.set_hexpand(True)
        self.canvas.set_vexpand(True)
        self.canvas.set_draw_func(self._draw)
        gesture = Gtk.GestureDrag.new()
        gesture.set_button(Gdk.BUTTON_PRIMARY)
        gesture.connect("drag-begin", self._drag_begin)
        gesture.connect("drag-update", self._drag_update)
        gesture.connect("drag-end", self._drag_end)
        self.canvas.add_controller(gesture)
        layout.append(self.canvas)
        self.set_child(layout)

        keys = Gtk.EventControllerKey.new()
        keys.connect("key-pressed", self._key_pressed)
        self.add_controller(keys)
        self.connect("close-request", self._close_requested)

    def _build_toolbar(self) -> Gtk.Widget:
        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        toolbar.set_margin_top(10)
        toolbar.set_margin_bottom(10)
        toolbar.set_margin_start(12)
        toolbar.set_margin_end(12)

        self.pen_button = Gtk.ToggleButton.new_with_label("Pen")
        self.crop_button = Gtk.ToggleButton.new_with_label("Crop")
        self.crop_button.set_group(self.pen_button)
        self.pen_button.set_active(True)
        self.pen_button.connect("clicked", lambda *_args: self._select_mode("pen"))
        self.crop_button.connect("clicked", lambda *_args: self._select_mode("crop"))
        toolbar.append(self.pen_button)
        toolbar.append(self.crop_button)

        colour_dialog = Gtk.ColorDialog.new()
        colour_dialog.set_title("Pen colour")
        self.colour_button = Gtk.ColorDialogButton.new(colour_dialog)
        self.colour_button.set_tooltip_text("Pen colour")
        self.colour_button.set_rgba(Gdk.RGBA(1.0, 0.0, 0.0, 1.0))
        toolbar.append(self.colour_button)

        width_label = Gtk.Label(label="Width")
        toolbar.append(width_label)
        self.width_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, 1, 24, 1
        )
        self.width_scale.set_value(6)
        self.width_scale.set_size_request(150, -1)
        self.width_scale.set_tooltip_text("Pen width in image pixels")
        toolbar.append(self.width_scale)

        self.apply_crop_button = Gtk.Button(label="Apply crop")
        self.apply_crop_button.add_css_class("suggested-action")
        self.apply_crop_button.connect("clicked", lambda *_args: self._apply_crop())
        self.apply_crop_button.set_visible(False)
        toolbar.append(self.apply_crop_button)
        self.cancel_crop_button = Gtk.Button(label="Cancel crop")
        self.cancel_crop_button.connect(
            "clicked", lambda *_args: self._cancel_crop_mode()
        )
        self.cancel_crop_button.set_visible(False)
        toolbar.append(self.cancel_crop_button)

        self.undo_button = Gtk.Button(label="Undo")
        self.undo_button.connect("clicked", lambda *_args: self._undo())
        toolbar.append(self.undo_button)
        self.redo_button = Gtk.Button(label="Redo")
        self.redo_button.connect("clicked", lambda *_args: self._redo())
        toolbar.append(self.redo_button)
        self.clear_button = Gtk.Button(label="Clear")
        self.clear_button.connect("clicked", lambda *_args: self._clear())
        toolbar.append(self.clear_button)

        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        toolbar.append(spacer)
        cancel_button = Gtk.Button(label="Cancel")
        cancel_button.connect("clicked", lambda *_args: self._cancel())
        toolbar.append(cancel_button)
        done_button = Gtk.Button(label="Done")
        done_button.add_css_class("suggested-action")
        done_button.connect("clicked", lambda *_args: self._done())
        toolbar.append(done_button)
        self._update_buttons()
        return toolbar

    def _fit(self, width: int, height: int) -> tuple[float, float, float]:
        crop = self.document.crop
        return fit_image(crop.width, crop.height, width, height)

    def _draw(
        self, _area: Gtk.DrawingArea, context: cairo.Context, width: int, height: int
    ) -> None:
        context.set_source_rgb(0.12, 0.12, 0.12)
        context.paint()
        scale, offset_x, offset_y = self._fit(width, height)
        context.save()
        context.translate(offset_x, offset_y)
        context.scale(scale, scale)
        context.translate(-self.document.crop.left, -self.document.crop.top)
        context.rectangle(
            self.document.crop.left,
            self.document.crop.top,
            self.document.crop.width,
            self.document.crop.height,
        )
        context.clip()
        context.set_source_surface(self.surface)
        context.paint()
        draw_strokes(context, self.document.all_strokes())
        self._draw_crop_selection(context, scale)
        context.restore()

    def _draw_crop_selection(self, context: cairo.Context, scale: float) -> None:
        selection = self._crop_selection
        if self._mode != "crop" or selection is None:
            return
        crop = self.document.crop
        context.save()
        context.set_fill_rule(cairo.FILL_RULE_EVEN_ODD)
        context.rectangle(crop.left, crop.top, crop.width, crop.height)
        context.rectangle(
            selection.left, selection.top, selection.width, selection.height
        )
        context.set_source_rgba(0.0, 0.0, 0.0, 0.55)
        context.fill()
        context.rectangle(
            selection.left, selection.top, selection.width, selection.height
        )
        context.set_source_rgb(1.0, 1.0, 1.0)
        context.set_line_width(1.5 / scale)
        context.set_dash([6.0 / scale, 4.0 / scale])
        context.stroke()
        context.set_dash([])
        handle_size = 8.0 / scale
        for x in (selection.left, selection.right):
            for y in (selection.top, selection.bottom):
                context.rectangle(
                    x - handle_size / 2,
                    y - handle_size / 2,
                    handle_size,
                    handle_size,
                )
                context.fill()
        context.restore()

    def _image_point(
        self, x: float, y: float, clamp: bool = False
    ) -> tuple[float, float] | None:
        return canvas_to_image(
            x,
            y,
            self.document.width,
            self.document.height,
            self.canvas.get_allocated_width(),
            self.canvas.get_allocated_height(),
            self.document.crop,
            clamp,
        )

    def _drag_begin(self, _gesture: Gtk.GestureDrag, x: float, y: float) -> None:
        point = self._image_point(x, y)
        self._drag_origin = (x, y) if point is not None else None
        if point is None:
            return
        if self._mode == "crop":
            self._begin_crop_drag(point)
            return
        rgba = self.colour_button.get_rgba()
        self.document.begin_stroke(
            point,
            (rgba.red, rgba.green, rgba.blue, rgba.alpha),
            self.width_scale.get_value(),
        )
        self.canvas.queue_draw()

    def _drag_update(
        self, _gesture: Gtk.GestureDrag, offset_x: float, offset_y: float
    ) -> None:
        if self._drag_origin is None:
            return
        point = self._image_point(
            self._drag_origin[0] + offset_x,
            self._drag_origin[1] + offset_y,
            clamp=self._mode == "crop",
        )
        if self._mode == "crop":
            if point is not None:
                self._update_crop_drag(point)
            return
        if point is not None:
            self.document.append_point(point)
            self.canvas.queue_draw()

    def _drag_end(
        self, _gesture: Gtk.GestureDrag, _offset_x: float, _offset_y: float
    ) -> None:
        if self._drag_origin is not None:
            if self._mode == "crop":
                self._crop_drag_handle = None
                self._crop_drag_start = None
            else:
                self.document.end_stroke()
                self._update_buttons()
                self.canvas.queue_draw()
        self._drag_origin = None

    def _begin_crop_drag(self, point: tuple[float, float]) -> None:
        handle = self._crop_handle_at(point)
        self._crop_drag_handle = handle or "new"
        self._crop_drag_start = self._crop_selection
        if handle is None:
            self._crop_selection = None
            self._crop_anchor = point

    def _crop_handle_at(self, point: tuple[float, float]) -> str | None:
        selection = self._crop_selection
        if selection is None:
            return None
        scale, _offset_x, _offset_y = self._fit(
            self.canvas.get_allocated_width(), self.canvas.get_allocated_height()
        )
        tolerance = 12.0 / scale
        horizontal = ""
        vertical = ""
        if abs(point[0] - selection.left) <= tolerance:
            horizontal = "left"
        elif abs(point[0] - selection.right) <= tolerance:
            horizontal = "right"
        if abs(point[1] - selection.top) <= tolerance:
            vertical = "top"
        elif abs(point[1] - selection.bottom) <= tolerance:
            vertical = "bottom"
        if (
            horizontal
            and selection.top - tolerance
            <= point[1]
            <= selection.bottom + tolerance
        ):
            return horizontal + (f"-{vertical}" if vertical else "")
        if (
            vertical
            and selection.left - tolerance
            <= point[0]
            <= selection.right + tolerance
        ):
            return vertical
        return None

    def _update_crop_drag(self, point: tuple[float, float]) -> None:
        handle = self._crop_drag_handle
        original = self._crop_drag_start
        if handle == "new":
            selection = normalise_crop(self._crop_anchor, point, self.document.crop)
        elif handle is not None and original is not None:
            left = point[0] if "left" in handle else original.left
            right = point[0] if "right" in handle else original.right
            top = point[1] if "top" in handle else original.top
            bottom = point[1] if "bottom" in handle else original.bottom
            selection = normalise_crop((left, top), (right, bottom), self.document.crop)
        else:
            selection = None
        if selection is not None:
            self._crop_selection = selection
        self._update_buttons()
        self.canvas.queue_draw()

    def _select_mode(self, mode: str) -> None:
        if mode not in ("pen", "crop"):
            raise ValueError(f"Unknown editor mode: {mode}")
        self._mode = mode
        crop_mode = mode == "crop"
        self.pen_button.set_active(not crop_mode)
        self.crop_button.set_active(crop_mode)
        self.colour_button.set_sensitive(not crop_mode)
        self.width_scale.set_sensitive(not crop_mode)
        self.apply_crop_button.set_visible(crop_mode)
        self.cancel_crop_button.set_visible(crop_mode)
        if not crop_mode:
            self._crop_selection = None
        self._update_buttons()
        if hasattr(self, "canvas"):
            self.canvas.queue_draw()

    def _apply_crop(self) -> None:
        if self._crop_selection is not None:
            self.document.apply_crop(self._crop_selection)
        self._crop_selection = None
        self._select_mode("pen")

    def _cancel_crop_mode(self) -> None:
        self._crop_selection = None
        self._select_mode("pen")

    def _undo(self) -> None:
        self._crop_selection = None
        if self.document.undo():
            self.canvas.queue_draw()
            self._update_buttons()

    def _redo(self) -> None:
        self._crop_selection = None
        if self.document.redo():
            self.canvas.queue_draw()
            self._update_buttons()

    def _clear(self) -> None:
        if self.document.clear():
            self.canvas.queue_draw()
            self._update_buttons()

    def _update_buttons(self) -> None:
        self.undo_button.set_sensitive(self.document.can_undo)
        self.redo_button.set_sensitive(self.document.can_redo)
        self.clear_button.set_sensitive(bool(self.document.strokes))
        self.apply_crop_button.set_sensitive(self._crop_selection is not None)

    def _key_pressed(
        self,
        _controller: Gtk.EventControllerKey,
        keyval: int,
        _keycode: int,
        state: Gdk.ModifierType,
    ) -> bool:
        if keyval == Gdk.KEY_Escape:
            if self._mode == "crop":
                self._cancel_crop_mode()
                return True
            self._cancel()
            return True
        control = bool(state & Gdk.ModifierType.CONTROL_MASK)
        shift = bool(state & Gdk.ModifierType.SHIFT_MASK)
        if control and keyval in (Gdk.KEY_z, Gdk.KEY_Z):
            if shift:
                self._redo()
            else:
                self._undo()
            return True
        if control and keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            self._done()
            return True
        return False

    def _done(self) -> None:
        error = self.complete(self.pending, self.document)
        if error:
            self.error_label.set_label(error)
            self.error_label.set_visible(True)
            return
        self._resolved = True
        self.destroy()

    def _cancel(self) -> None:
        if not self._resolved:
            self._resolved = True
            self.cancel(self.pending)
        self.destroy()

    def _close_requested(self, _window: Gtk.Window) -> bool:
        if not self._resolved:
            self._resolved = True
            self.cancel(self.pending)
        return False
