# Grab

Grab is a one-click, whole-desktop screenshot tool for Fedora Workstation. Its
camera icon lives in the GNOME top bar, while the capture helper stays hidden
from the application grid. The extension captures the desktop through GNOME
Shell, then its helper copies the result to the Wayland clipboard and shows a
desktop notification. Saving a timestamped PNG is optional and disabled by
default.

## Install

```sh
./install.sh
```

The installer automatically disables and re-enables an extension GNOME Shell
already knows about. GNOME caches new or changed extension JavaScript, however,
so a first installation or extension-code upgrade can still require one logout
and login. Left-click the top-bar icon to capture. Right-click it to open
**Preferences** and enable saving under `Pictures/Screenshots`.

## Commands

```sh
grab                 # capture, copy, and notify
grab --preferences   # open preferences
./uninstall.sh       # remove the application, retaining settings and images
```

## Requirements

- Fedora Workstation 42 or newer
- Python 3 with PyGObject
- GTK 4
- `xdg-desktop-portal` and a GNOME portal backend
- GNOME Shell 48, 49, or 50

If a dependency check fails, the installer prints the corresponding `dnf`
command. Installation is per-user and does not require root.

## Test

```sh
PYTHONPATH=src /usr/bin/python3 -m unittest discover -s tests -v
```
