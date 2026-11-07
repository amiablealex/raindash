#!/bin/sh
# One-shot check: fetch the image and draw it, without stopping the Kindle UI.
DIR=/mnt/us/extensions/raindash
. "$DIR/config.sh"
if wget -q -T 20 -O /tmp/rain.png "$IMAGE_URL"; then
    eips -f -g /tmp/rain.png
else
    eips 1 38 "Could not fetch $IMAGE_URL"
fi
