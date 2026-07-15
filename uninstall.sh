#!/bin/sh
set -eu

APP_ID=org.grabtool.Grab
EXTENSION_UUID=grab@grabtool.org
DATA_HOME=${XDG_DATA_HOME:-"$HOME/.local/share"}
BIN_HOME=${XDG_BIN_HOME:-"$HOME/.local/bin"}
APP_DIR="$DATA_HOME/org.grabtool.Grab"
EXTENSION_DIR="$DATA_HOME/gnome-shell/extensions/$EXTENSION_UUID"
APPLICATIONS_DIR="$DATA_HOME/applications"
DBUS_SERVICES_DIR="$DATA_HOME/dbus-1/services"
ICON_DIR="$DATA_HOME/icons/hicolor/scalable/apps"
BIN_PATH="$BIN_HOME/grab"

if [ "${GRAB_SKIP_EXTENSION_ENABLE:-0}" != "1" ]; then
    gnome-extensions disable "$EXTENSION_UUID" >/dev/null 2>&1 || true
    /usr/bin/python3 -c "from gi.repository import Gio; s=Gio.Settings.new('org.gnome.shell'); u='$EXTENSION_UUID'; s.set_strv('enabled-extensions', [v for v in s.get_strv('enabled-extensions') if v != u])" >/dev/null 2>&1 || true
fi

if [ -L "$BIN_PATH" ]; then
    link_target=$(readlink "$BIN_PATH")
    if [ "$link_target" = "$APP_DIR/grab" ]; then
        rm -f "$BIN_PATH"
    fi
fi
rm -f "$APPLICATIONS_DIR/$APP_ID.desktop"
rm -f "$DBUS_SERVICES_DIR/$APP_ID.service"
rm -f "$ICON_DIR/$APP_ID.svg"
rm -rf "$EXTENSION_DIR"
rm -rf "$APP_DIR"

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$APPLICATIONS_DIR" >/dev/null 2>&1 || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1 && [ -d "$DATA_HOME/icons/hicolor" ]; then
    gtk-update-icon-cache -f -t "$DATA_HOME/icons/hicolor" >/dev/null 2>&1 || true
fi

printf '%s\n' "Grab uninstalled. Preferences and saved screenshots were retained."
