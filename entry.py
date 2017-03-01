#!/usr/bin/env python3

import signal
import sys
from subprocess import Popen

mongo = Popen(['/usr/bin/mongod'], stdout=sys.stdout, stderr=sys.stderr)
run   = Popen(['/usr/bin/python3', '/app/run.py'], stdout=sys.stdout, stderr=sys.stderr)

def graceful_stop(signal, frame):
    mongo.send_signal(signal)
    run.send_signal(signal)
    mongo.wait()
    run.wait()
    sys.exit(0)

signal.signal(signal.SIGHUP,  graceful_stop)
signal.signal(signal.SIGTERM, graceful_stop)
signal.signal(signal.SIGINT,  graceful_stop)

while True:
    pass
