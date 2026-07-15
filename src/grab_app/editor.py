"""GTK window for drawing over a captured screenshot."""

from __future__ import annotations

from typing import Callable

import cairo
import gi

gi.require_version("Gdk", "4.0")
gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, Gtk

from .annotation import (
    AnnotationDocument,
    PendingAnnotation,
    canvas_to_image,
    draw_strokes,
    fit_image,
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
        self._drag_origin: tuple[float, float] | None = None
        self.surface = cairo.ImageSurface.create_from_png(str(pending.image_path))
        self.document = AnnotationDocument(
            self.surface.get_width(), self.surface.get_height()
        )

        self.set_title("Annotate Screenshot")
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
        return fit_image(self.document.width, self.document.height, width, height)

    def _draw(
        self, _area: Gtk.DrawingArea, context: cairo.Context, width: int, height: int
    ) -> None:
        context.set_source_rgb(0.12, 0.12, 0.12)
        context.paint()
        scale, offset_x, offset_y = self._fit(width, height)
        context.save()
        context.translate(offset_x, offset_y)
        context.scale(scale, scale)
        context.set_source_surface(self.surface)
        context.paint()
        draw_strokes(context, self.document.all_strokes())
        context.restore()

    def _image_point(self, x: float, y: float) -> tuple[float, float] | None:
        return canvas_to_image(
            x,
            y,
            self.document.width,
            self.document.height,
            self.canvas.get_allocated_width(),
            self.canvas.get_allocated_height(),
        )

    def _drag_begin(self, _gesture: Gtk.GestureDrag, x: float, y: float) -> None:
        point = self._image_point(x, y)
        self._drag_origin = (x, y) if point is not None else None
        if point is None:
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
            self._drag_origin[0] + offset_x, self._drag_origin[1] + offset_y
        )
        if point is not None:
            self.document.append_point(point)
            self.canvas.queue_draw()

    def _drag_end(
        self, _gesture: Gtk.GestureDrag, _offset_x: float, _offset_y: float
    ) -> None:
        if self._drag_origin is not None:
            self.document.end_stroke()
            self._update_buttons()
            self.canvas.queue_draw()
        self._drag_origin = None

    def _undo(self) -> None:
        if self.document.undo():
            self.canvas.queue_draw()
            self._update_buttons()

    def _redo(self) -> None:
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

    def _key_pressed(
        self,
        _controller: Gtk.EventControllerKey,
        keyval: int,
        _keycode: int,
        state: Gdk.ModifierType,
    ) -> bool:
        if keyval == Gdk.KEY_Escape:
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
