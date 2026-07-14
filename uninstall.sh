#!/bin/sh
set -eu

APP_ID=org.grabtool.Grab
DATA_HOME=${XDG_DATA_HOME:-"$HOME/.local/share"}
BIN_HOME=${XDG_BIN_HOME:-"$HOME/.local/bin"}
APP_DIR="$DATA_HOME/org.grabtool.Grab"
APPLICATIONS_DIR="$DATA_HOME/applications"
ICON_DIR="$DATA_HOME/icons/hicolor/scalable/apps"
BIN_PATH="$BIN_HOME/grab"

if [ -L "$BIN_PATH" ]; then
    link_target=$(readlink "$BIN_PATH")
    if [ "$link_target" = "$APP_DIR/grab" ]; then
        rm -f "$BIN_PATH"
    fi
fi
rm -f "$APPLICATIONS_DIR/$APP_ID.desktop"
rm -f "$ICON_DIR/$APP_ID.svg"
rm -rf "$APP_DIR"

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$APPLICATIONS_DIR" >/dev/null 2>&1 || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1 && [ -d "$DATA_HOME/icons/hicolor" ]; then
    gtk-update-icon-cache -f -t "$DATA_HOME/icons/hicolor" >/dev/null 2>&1 || true
fi

printf '%s\n' "Grab uninstalled. Preferences and saved screenshots were retained."
