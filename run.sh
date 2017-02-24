#!/bin/sh -e

if [ "$1" = "pb" ]; then
    chown -R mongodb /data/db
    su -s /bin/sh -c mongod &

    exec python3 /app/run.py
    exit $?
fi

cmd=exec
for i; do
    cmd="$cmd '$i'"
done

exec /bin/sh -c "$cmd"
