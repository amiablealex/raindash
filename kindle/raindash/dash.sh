#!/bin/sh
# Rain dashboard loop for Kindle Touch (K5). Started by start.sh - don't run directly.
# Draws over the Kindle UI rather than stopping it.
export PATH=/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH
trap '' HUP

DIR=/mnt/us/extensions/raindash
. "$DIR/config.sh"

IMG=/tmp/rain.png
LOG=$DIR/log.txt
echo $$ > /tmp/raindash.pid

log() {
    echo "$(date '+%F %T') $*" >> "$LOG"
    # keep the log small: trim to the last 300 lines once it passes 600
    if [ "$(wc -l < "$LOG")" -gt 600 ]; then
        tail -n 300 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
    fi
}

wait_for_wifi() {
    i=0
    while [ "$(lipc-get-prop com.lab126.wifid cmState 2>/dev/null)" != "CONNECTED" ]; do
        [ $i -eq 0 ] && lipc-set-prop com.lab126.wifid enable 1 2>/dev/null
        i=$((i + 1))
        [ $i -gt 30 ] && return 1
        sleep 2
    done
    return 0
}

log "started, refresh every ${REFRESH_MIN} min"
sleep 3   # let KUAL close and the library finish drawing first

while true; do
    # Re-assert every cycle: Home, sleep/wake etc. can switch these back.
    lipc-set-prop com.lab126.powerd preventScreenSaver 1
    lipc-set-prop com.lab126.pillow disableEnablePillow disable 2>/dev/null

    if wait_for_wifi && wget -q -T 20 -O "$IMG.new" "$IMAGE_URL" && [ -s "$IMG.new" ]; then
        mv "$IMG.new" "$IMG"
        eips -f -g "$IMG"          # -f = full flashing refresh, clears ghosting
        log "ok"
    else
        # keep the last good chart on screen; its "updated" time shows it's stale
        log "fetch failed"
    fi
    sleep $((REFRESH_MIN * 60))
done
