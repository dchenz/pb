#!/bin/sh -e

if [ "$1" = "pb" ]; then
    mongod &

    if [ -d /data/db ]; then
        python3 /app/runonce.py
    fi

    exec python3 /app/run.py
    exit $?
fi

cmd=exec
for i; do
    cmd="$cmd '$i'"
done

exec /bin/sh -c "$cmd"
