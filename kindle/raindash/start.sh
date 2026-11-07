#!/bin/sh
# Launched from KUAL. This Kindle has no setsid/nohup, so just background the loop;
# the Kindle UI keeps running, so nothing kills it.
export PATH=/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH
DIR=/mnt/us/extensions/raindash
PID=/tmp/raindash.pid

echo "=== $(date) start.sh" >> "$DIR/debug.txt"
if [ -f "$PID" ] && kill -0 "$(cat "$PID")" 2>/dev/null; then
    echo "already running (pid $(cat "$PID"))" >> "$DIR/debug.txt"
    exit 0
fi
( sh "$DIR/dash.sh" >> "$DIR/debug.txt" 2>&1 < /dev/null & )
