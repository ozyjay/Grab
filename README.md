# Grab

Grab is a whole-desktop screenshot and animated GIF recording tool for Fedora
Workstation. Its camera icon lives in the GNOME top bar, while the capture
helper stays hidden from the application grid. Screenshots are copied to the
Wayland clipboard and can optionally be saved as timestamped PNG files.
Successful screenshot notifications include an **Edit** action for cropping or
drawing before replacing the clipboard image.

Grab can also record a silent screencast of the whole desktop, including the
pointer. Choose a preset duration from **Record GIF**, or enter a custom duration
from 1 to 300 seconds. Recording stops automatically when the time expires, or
can be stopped early from the menu. After recording, drag or resize the crop,
preview the result, and select **Save GIF**. GIFs are optimised to 15 frames per
second and a maximum longest side of 1280 pixels.

## Install

```sh
./install.sh
```

The installer automatically disables and re-enables an extension GNOME Shell
already knows about. GNOME caches new or changed extension JavaScript, however,
so a first installation or extension-code upgrade can still require one logout
and login. Select the top-bar icon to open Grab's screenshot, GIF recording,
and preferences actions. **Preferences** can enable saving screenshots under
`Pictures/Screenshots`.

Select **Edit** on a screenshot notification to open the image editor. Use
**Pen** to choose a colour and width and draw over the image. Use **Crop** to
drag a free-form selection, adjust its edges or corners, then apply it. Crops
and pen strokes share the same undo and redo history. Select **Done** to replace
the clipboard image and its saved copy (when enabled). Cancelling keeps the
original screenshot unchanged.

## Commands

```sh
grab                 # capture, copy, and notify
grab --preferences   # open preferences
./uninstall.sh       # remove the application, retaining settings and images
```

## Requirements

- Fedora Workstation 42 or newer
- Python 3 with PyGObject
- Python 3 Cairo bindings
- GTK 4
- `ffmpeg-free`
- GStreamer VP8 playback support (`gstreamer1-plugins-good`)
- `xdg-desktop-portal` and a GNOME portal backend
- GNOME Shell 48, 49, or 50

If a dependency check fails, the installer prints the corresponding `dnf`
command. Installation is per-user and does not require root.

## Test

```sh
PYTHONPATH=src /usr/bin/python3 -m unittest discover -s tests -v
```
