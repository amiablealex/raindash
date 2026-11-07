#!/bin/sh
# Stop the loop and hand the screen back to the Kindle UI.
export PATH=/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH
PID=/tmp/raindash.pid
[ -f "$PID" ] && kill "$(cat "$PID")" 2>/dev/null
rm -f "$PID"
lipc-set-prop com.lab126.powerd preventScreenSaver 0
lipc-set-prop com.lab126.pillow disableEnablePillow enable 2>/dev/null
echo "=== $(date) stopped" >> /mnt/us/extensions/raindash/debug.txt
