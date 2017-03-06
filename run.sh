#!/bin/sh -e

if [ "$1" = "pb" ]; then
    exec python3 /app/run.py
    exit $?
fi

cmd=exec
for i; do
    cmd="$cmd '$i'"
done

exec /bin/sh -c "$cmd"
