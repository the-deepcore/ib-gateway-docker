#!/bin/bash

start() {
  cd /app
  . .venv/bin/activate
  python3 src/app.py &
}

case "$1" in 
    start)
       start
       ;;
    *)
       echo "Usage: $0 {start}"
esac

exit 0
