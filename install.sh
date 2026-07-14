#!/bin/sh
set -eu

APP_ID=org.grabtool.Grab
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
DATA_HOME=${XDG_DATA_HOME:-"$HOME/.local/share"}
BIN_HOME=${XDG_BIN_HOME:-"$HOME/.local/bin"}
APP_DIR="$DATA_HOME/org.grabtool.Grab"
APPLICATIONS_DIR="$DATA_HOME/applications"
ICON_DIR="$DATA_HOME/icons/hicolor/scalable/apps"
BIN_PATH="$BIN_HOME/grab"

missing=""
if [ ! -x /usr/bin/python3 ]; then
    missing="$missing python3"
elif ! /usr/bin/python3 -c "import gi; gi.require_version('Gtk','4.0'); gi.require_version('Gdk','4.0'); from gi.repository import Gtk, Gdk, Gio, GLib" >/dev/null 2>&1; then
    missing="$missing python3-gobject gtk4"
fi
if ! command -v gdbus >/dev/null 2>&1; then
    missing="$missing glib2"
fi
if command -v rpm >/dev/null 2>&1; then
    if ! rpm -q xdg-desktop-portal >/dev/null 2>&1; then
        missing="$missing xdg-desktop-portal"
    fi
    if ! rpm -q xdg-desktop-portal-gnome >/dev/null 2>&1; then
        missing="$missing xdg-desktop-portal-gnome"
    fi
fi

if [ -n "$missing" ]; then
    printf '%s\n' "Grab is missing required Fedora packages. Install them with:"
    printf '  sudo dnf install%s\n' "$missing"
    exit 1
fi

case "$BIN_PATH" in
    *'"'*|*'\n'*|*'\r'*)
        printf '%s\n' "Cannot install Grab: the installation path contains unsupported characters." >&2
        exit 1
        ;;
esac

mkdir -p "$APP_DIR/src" "$BIN_HOME" "$APPLICATIONS_DIR" "$ICON_DIR"
rm -rf "$APP_DIR/src/grab_app"
cp -R "$SCRIPT_DIR/src/grab_app" "$APP_DIR/src/grab_app"
install -m 755 "$SCRIPT_DIR/grab" "$APP_DIR/grab"
ln -sfn "$APP_DIR/grab" "$BIN_PATH"
install -m 644 "$SCRIPT_DIR/data/$APP_ID.svg" "$ICON_DIR/$APP_ID.svg"

escaped_executable=$(printf '%s' "$BIN_PATH" | sed 's/[\\&|]/\\&/g')
sed "s|@EXECUTABLE@|$escaped_executable|g" \
    "$SCRIPT_DIR/data/$APP_ID.desktop.in" > "$APPLICATIONS_DIR/$APP_ID.desktop"
chmod 644 "$APPLICATIONS_DIR/$APP_ID.desktop"

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$APPLICATIONS_DIR" >/dev/null 2>&1 || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -f -t "$DATA_HOME/icons/hicolor" >/dev/null 2>&1 || true
fi

printf '%s\n' "Grab installed successfully. Find it in the Fedora application menu."
