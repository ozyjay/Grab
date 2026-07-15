from pathlib import Path
import tempfile
import unittest

import cairo

from grab_app.annotation import (
    MAX_PENDING_AGE,
    AnnotationDocument,
    CropRectangle,
    PendingAnnotationStore,
    canvas_to_image,
    fit_image,
    normalise_crop,
    render_annotation,
)


def make_png(path: Path, width: int = 20, height: int = 10) -> None:
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
    context = cairo.Context(surface)
    context.set_source_rgb(1, 1, 1)
    context.paint()
    surface.write_to_png(str(path))


class AnnotationDocumentTests(unittest.TestCase):
    def test_fit_and_coordinate_conversion_preserve_image_space(self):
        self.assertEqual(fit_image(200, 100, 300, 300), (1.5, 0.0, 75.0))
        self.assertEqual(
            canvas_to_image(150, 150, 200, 100, 300, 300),
            (100.0, 50.0),
        )
        self.assertIsNone(canvas_to_image(150, 20, 200, 100, 300, 300))

    def test_coordinate_conversion_uses_crop_viewport(self):
        crop = CropRectangle(50, 20, 150, 70)
        self.assertEqual(
            canvas_to_image(150, 150, 200, 100, 300, 300, crop),
            (100.0, 45.0),
        )
        self.assertIsNone(canvas_to_image(150, 20, 200, 100, 300, 300, crop))
        self.assertEqual(
            canvas_to_image(150, 20, 200, 100, 300, 300, crop, clamp=True),
            (100.0, 20),
        )

    def test_crop_is_normalised_clamped_and_pixel_aligned(self):
        bounds = CropRectangle(10, 20, 90, 70)
        self.assertEqual(
            normalise_crop((80.2, 65.8), (5.4, 19.1), bounds),
            CropRectangle(10, 20, 81, 66),
        )
        self.assertIsNone(normalise_crop((10, 20), (10, 30), bounds))

    def test_history_preserves_stroke_properties_and_clear_is_undoable(self):
        document = AnnotationDocument(100, 50)
        document.begin_stroke((10, 12), (1, 0, 0, 1), 6)
        document.append_point((120, -5))
        document.end_stroke()

        self.assertEqual(document.strokes[0].colour, (1, 0, 0, 1))
        self.assertEqual(document.strokes[0].width, 6)
        self.assertEqual(document.strokes[0].points[-1], (100.0, 0.0))
        self.assertTrue(document.clear())
        self.assertEqual(document.strokes, ())
        self.assertTrue(document.undo())
        self.assertEqual(len(document.strokes), 1)
        self.assertTrue(document.redo())
        self.assertEqual(document.strokes, ())

    def test_crops_and_strokes_share_history_and_invalidate_redo(self):
        document = AnnotationDocument(100, 50)
        document.begin_stroke((5, 5), (1, 0, 0, 1), 2)
        document.end_stroke()
        crop = CropRectangle(10, 10, 90, 40)
        self.assertTrue(document.apply_crop(crop))
        document.begin_stroke((20, 20), (0, 0, 1, 1), 2)
        document.end_stroke()

        self.assertTrue(document.undo())
        self.assertEqual(len(document.strokes), 1)
        self.assertTrue(document.undo())
        self.assertEqual(document.crop, CropRectangle(0, 0, 100, 50))
        self.assertEqual(len(document.strokes), 1)
        self.assertTrue(document.redo())
        self.assertEqual(document.crop, crop)
        self.assertTrue(document.clear())
        self.assertEqual(document.crop, crop)
        self.assertFalse(document.can_redo)

    def test_repeated_crop_must_stay_inside_current_crop(self):
        document = AnnotationDocument(100, 50)
        self.assertTrue(document.apply_crop(CropRectangle(10, 5, 90, 45)))
        self.assertTrue(document.apply_crop(CropRectangle(20, 10, 80, 40)))
        self.assertFalse(document.apply_crop(CropRectangle(0, 0, 50, 30)))
        self.assertEqual(document.crop, CropRectangle(20, 10, 80, 40))

    def test_render_keeps_original_dimensions_and_adds_pixels(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.png"
            output = root / "output.png"
            make_png(source)
            document = AnnotationDocument(20, 10)
            document.begin_stroke((2, 5), (1, 0, 0, 1), 3)
            document.append_point((18, 5))
            document.end_stroke()

            render_annotation(source, output, document.strokes)

            rendered = cairo.ImageSurface.create_from_png(str(output))
            self.assertEqual((rendered.get_width(), rendered.get_height()), (20, 10))
            self.assertNotEqual(output.read_bytes(), source.read_bytes())

    def test_render_crop_sets_output_dimensions_and_clips_strokes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.png"
            output = root / "output.png"
            make_png(source, 20, 10)
            document = AnnotationDocument(20, 10)
            document.begin_stroke((2, 5), (1, 0, 0, 1), 3)
            document.append_point((18, 5))
            document.end_stroke()
            crop = CropRectangle(5, 2, 15, 8)

            render_annotation(source, output, document.strokes, crop)

            rendered = cairo.ImageSurface.create_from_png(str(output))
            self.assertEqual((rendered.get_width(), rendered.get_height()), (10, 6))
            rendered.flush()
            offset = 3 * rendered.get_stride() + 5 * 4
            pixel = bytes(rendered.get_data()[offset:][:4])
            self.assertGreater(pixel[2], 200)
            self.assertLess(pixel[1], 50)
            self.assertNotEqual(output.read_bytes(), source.read_bytes())


class PendingAnnotationStoreTests(unittest.TestCase):
    def test_record_can_be_claimed_and_new_capture_removes_unopened_record(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            screenshots = root / "Pictures" / "Screenshots"
            screenshots.mkdir(parents=True)
            source = root / "source.png"
            make_png(source)
            store = PendingAnnotationStore(root / "runtime", screenshots)

            first = store.create(source, None)
            claimed = store.claim(first.token)
            self.assertEqual(claimed.state, "open")
            second = store.create(source, None)

            self.assertTrue(first.image_path.exists())
            self.assertTrue(second.image_path.exists())
            third = store.create(source, None)
            self.assertFalse(second.image_path.exists())
            self.assertTrue(third.image_path.exists())

    def test_expired_and_outside_saved_paths_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.png"
            outside = root / "Screenshot outside.png"
            make_png(source)
            make_png(outside)
            now = [1000.0]
            store = PendingAnnotationStore(
                root / "runtime",
                root / "Pictures" / "Screenshots",
                now=lambda: now[0],
            )
            with self.assertRaises(ValueError):
                store.create(source, outside)

            record = store.create(source, None)
            now[0] += MAX_PENDING_AGE + 1
            with self.assertRaises(ValueError):
                store.load(record.token)
            self.assertFalse(record.image_path.exists())


if __name__ == "__main__":
    unittest.main()
