#!/bin/sh
cd "$(dirname "$0")" && echo "Starting a second console on port 8766 for the offline demo." && python3 launch.py 8766
