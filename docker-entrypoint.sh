#!/bin/bash
set -e

# Function to wait for Redis
wait_for_redis() {
    echo "Waiting for Redis..."
    while ! redis-cli -h redis ping &>/dev/null; do
        echo "Redis is unavailable - sleeping"
        sleep 1
    done
    echo "Redis is ready!"
}

# Function to handle process termination
handle_term() {
    echo "Received SIGTERM/SIGINT, forwarding to Python process..."
    if [ -n "$child" ]; then
        kill -TERM "$child" 2>/dev/null || true
    fi
    exit 0
}

# Set up signal handlers
trap handle_term SIGTERM SIGINT

# Wait for Redis to be ready
wait_for_redis

# Check if we have a TTY
if [ -t 0 ]; then
    # Start with TTY
    echo "Starting TeleDown with TTY..."
    exec python -u main.py
else
    # No TTY available, try to allocate one
    echo "Starting TeleDown without TTY, attempting to allocate one..."
    # Try to use script to emulate a TTY
    if command -v script >/dev/null 2>&1; then
        exec script -qec "python -u main.py" /dev/null
    else
        # Fallback to basic execution
        exec python -u main.py
    fi
fi