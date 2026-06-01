#!/bin/bash

start() {
  cd /app
  . .venv/bin/activate
  python3 src/app.py &
  echo $(ps -e | grep -i 'python3' | awk '{ print $1 }' | head -n1) > /tmp/ibgateway.pid
}

stop() {
  ps aux | grep [a]pp.py | awk '{ print $2 }' | xargs -I '{}' kill -9 '{}'
}

case "$1" in
    start)
        start
        exit
        ;;
    stop)
        stop
        exit
        ;;
    *)

    echo "Usage: $0 {start}"
esac

exit 0
