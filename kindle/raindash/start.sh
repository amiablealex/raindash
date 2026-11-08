#!/bin/sh
# Launched from KUAL. Always (re)starts the loop, so Start works even if an old
# loop is still running behind the library screen.
export PATH=/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH
DIR=/mnt/us/extensions/raindash
PID=/tmp/raindash.pid

echo "=== $(date) start.sh" >> "$DIR/debug.txt"
if [ -f "$PID" ] && kill "$(cat "$PID")" 2>/dev/null; then
    echo "stopped old loop (pid $(cat "$PID"))" >> "$DIR/debug.txt"
fi
rm -f "$PID"
( sh "$DIR/dash.sh" >> "$DIR/debug.txt" 2>&1 < /dev/null & )
