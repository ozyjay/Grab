# Grab

Grab is a one-click, whole-desktop screenshot tool for Fedora Workstation. It
uses the XDG Screenshot portal, copies the result to the Wayland clipboard, and
shows a desktop notification. Saving a timestamped PNG is optional and disabled
by default.

## Install

```sh
./install.sh
```

Open Fedora's application menu and click **Grab**. Right-click its icon and
choose **Preferences** to enable saving under `Pictures/Screenshots`.

The first capture can display Fedora's screenshot permission prompt. This is a
security feature of the portal and is not bypassed.

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

If a dependency check fails, the installer prints the corresponding `dnf`
command. Installation is per-user and does not require root.

## Test

```sh
PYTHONPATH=src /usr/bin/python3 -m unittest discover -s tests -v
```
