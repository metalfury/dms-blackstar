#!/bin/sh
# Install (or `./install.sh uninstall`) bsamp, the app, the udev rule and
# the DMS widget. Files are symlinked, so `git pull` updates them.
set -eu
REPO=$(cd "$(dirname "$0")" && pwd)
BIN=$HOME/.local/bin/bsamp
APPS=${XDG_DATA_HOME:-$HOME/.local/share}/applications
DESKTOP=$APPS/io.github.metalfury.bsamp.desktop
PLUG=$HOME/.config/DankMaterialShell/plugins/blackstar
RULE=/etc/udev/rules.d/70-blackstar-id.rules

if [ "${1:-}" = uninstall ]; then
  dms ipc call plugins disable blackstar >/dev/null 2>&1 || true
  rm -rf "$BIN" "$DESKTOP" "$PLUG"
  sudo rm -f "$RULE" && sudo udevadm control --reload
  echo "removed (your patches and backups in ~/.config/bsamp and ~/.local/share/bsamp are kept)"
  exit 0
fi

python3 -c 'import cairo, gi; gi.require_version("Adw", "1")' 2>/dev/null ||
  echo "warning: GTK/libadwaita for Python missing (sudo dnf install python3-gobject python3-cairo libadwaita)" >&2

if ! cmp -s "$REPO/udev/70-blackstar-id.rules" "$RULE" 2>/dev/null; then
  sudo install -m 644 "$REPO/udev/70-blackstar-id.rules" "$RULE"
  sudo udevadm control --reload
  sudo udevadm trigger -s hidraw
fi

mkdir -p "$(dirname "$BIN")" "$APPS" "$(dirname "$PLUG")"
ln -sfn "$REPO/bin/bsamp" "$BIN"
sed "s|^Exec=bsamp|Exec=$BIN|" "$REPO/data/io.github.metalfury.bsamp.desktop" > "$DESKTOP"
rm -rf "$PLUG"
ln -sfn "$REPO/plugin/blackstar" "$PLUG"

if command -v dms >/dev/null; then
  dms ipc call plugin-scan scan >/dev/null 2>&1 || true
  sleep 2
  dms ipc call plugins enable blackstar >/dev/null 2>&1 || true
fi
echo "installed - run 'bsamp gui' (or 'Blackstar Amp' in the launcher);"
echo "add 'Blackstar Amp' to the bar in DMS Settings > Dank Bar if it is not there"
