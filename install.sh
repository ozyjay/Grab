#!/bin/sh
set -eu

APP_ID=org.grabtool.Grab
EXTENSION_UUID=grab@grabtool.org
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
DATA_HOME=${XDG_DATA_HOME:-"$HOME/.local/share"}
BIN_HOME=${XDG_BIN_HOME:-"$HOME/.local/bin"}
APP_DIR="$DATA_HOME/org.grabtool.Grab"
EXTENSION_DIR="$DATA_HOME/gnome-shell/extensions/$EXTENSION_UUID"
APPLICATIONS_DIR="$DATA_HOME/applications"
DBUS_SERVICES_DIR="$DATA_HOME/dbus-1/services"
ICON_DIR="$DATA_HOME/icons/hicolor/scalable/apps"
BIN_PATH="$BIN_HOME/grab"

missing=""
if [ ! -x /usr/bin/python3 ]; then
    missing="$missing python3"
elif ! /usr/bin/python3 -c "import gi; gi.require_version('Gtk','4.0'); gi.require_version('Gdk','4.0'); from gi.repository import Gtk, Gdk, Gio, GLib" >/dev/null 2>&1; then
    missing="$missing python3-gobject gtk4"
fi
if ! /usr/bin/python3 -c "import cairo" >/dev/null 2>&1; then
    missing="$missing python3-cairo"
fi
if ! command -v gdbus >/dev/null 2>&1; then
    missing="$missing glib2"
fi
if ! command -v gnome-extensions >/dev/null 2>&1; then
    missing="$missing gnome-shell"
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

mkdir -p "$APP_DIR/src" "$EXTENSION_DIR" "$BIN_HOME" "$APPLICATIONS_DIR" "$DBUS_SERVICES_DIR" "$ICON_DIR"
rm -rf "$APP_DIR/src/grab_app"
cp -R "$SCRIPT_DIR/src/grab_app" "$APP_DIR/src/grab_app"
rm -f "$EXTENSION_DIR/extension.js" "$EXTENSION_DIR/metadata.json"
install -m 644 "$SCRIPT_DIR/extension/extension.js" "$EXTENSION_DIR/extension.js"
install -m 644 "$SCRIPT_DIR/extension/metadata.json" "$EXTENSION_DIR/metadata.json"
install -m 755 "$SCRIPT_DIR/grab" "$APP_DIR/grab"
ln -sfn "$APP_DIR/grab" "$BIN_PATH"
install -m 644 "$SCRIPT_DIR/data/$APP_ID.svg" "$ICON_DIR/$APP_ID.svg"

escaped_executable=$(printf '%s' "$BIN_PATH" | sed 's/[\\&|]/\\&/g')
sed "s|@EXECUTABLE@|$escaped_executable|g" \
    "$SCRIPT_DIR/data/$APP_ID.desktop.in" > "$APPLICATIONS_DIR/$APP_ID.desktop"
chmod 644 "$APPLICATIONS_DIR/$APP_ID.desktop"
sed "s|@EXECUTABLE@|$escaped_executable|g" \
    "$SCRIPT_DIR/data/$APP_ID.service.in" > "$DBUS_SERVICES_DIR/$APP_ID.service"
chmod 644 "$DBUS_SERVICES_DIR/$APP_ID.service"

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$APPLICATIONS_DIR" >/dev/null 2>&1 || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -f -t "$DATA_HOME/icons/hicolor" >/dev/null 2>&1 || true
fi

extension_refreshed=0
if [ "${GRAB_SKIP_EXTENSION_ENABLE:-0}" != "1" ]; then
    if gnome-extensions info "$EXTENSION_UUID" >/dev/null 2>&1; then
        gnome-extensions disable "$EXTENSION_UUID" >/dev/null 2>&1 || true
        if gnome-extensions enable "$EXTENSION_UUID" >/dev/null 2>&1; then
            extension_refreshed=1
        fi
    fi

    /usr/bin/python3 -c "from gi.repository import Gio; s=Gio.Settings.new('org.gnome.shell'); v=s.get_strv('enabled-extensions'); u='$EXTENSION_UUID'; s.set_strv('enabled-extensions', v if u in v else [*v, u])"
fi

printf '%s\n' "Grab installed successfully."
if [ "$extension_refreshed" -eq 1 ]; then
    printf '%s\n' "The top-bar extension was disabled and re-enabled to refresh its camera icon."
else
    printf '%s\n' "Log out and back in once so GNOME Shell can load the new top-bar extension."
fi
