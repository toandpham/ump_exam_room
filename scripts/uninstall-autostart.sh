#!/usr/bin/env bash
# Remove the auto-start LaunchAgent.
set -euo pipefail
LABEL="com.examsystem.autostart"
PLIST="$HOME/Library/LaunchAgents/${LABEL}.plist"

launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null || launchctl unload "$PLIST" 2>/dev/null || true
rm -f "$PLIST"
echo "Removed LaunchAgent: $PLIST"
