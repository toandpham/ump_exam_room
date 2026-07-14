#!/usr/bin/env bash
# Install (or refresh) a macOS LaunchAgent that auto-starts the exam stack at login.
# Reversible:  ./scripts/uninstall-autostart.sh
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.examsystem.autostart"
PLIST="$HOME/Library/LaunchAgents/${LABEL}.plist"

mkdir -p "$HOME/Library/LaunchAgents" "$PROJECT_DIR/logs"

cat > "$PLIST" <<PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>${PROJECT_DIR}/scripts/autostart.sh</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>StandardOutPath</key>
    <string>${PROJECT_DIR}/logs/autostart.log</string>
    <key>StandardErrorPath</key>
    <string>${PROJECT_DIR}/logs/autostart.log</string>
</dict>
</plist>
PLISTEOF

# Reload (modern bootstrap, fallback to legacy load).
launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null || true
if ! launchctl bootstrap "gui/$(id -u)" "$PLIST" 2>/dev/null; then
  launchctl unload "$PLIST" 2>/dev/null || true
  launchctl load -w "$PLIST"
fi

echo "Installed LaunchAgent: $PLIST"
echo "It runs scripts/autostart.sh at login (and once now)."
