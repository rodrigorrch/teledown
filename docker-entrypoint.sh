#!/bin/bash
set -e

# Create and set permissions for required directories
mkdir -p /app/downloads /app/cache /app/session
chown -R nobody:nogroup /app/downloads /app/cache /app/session
chmod -R 777 /app/downloads /app/cache /app/session

# Wait for Redis to be ready
echo "Waiting for Redis..."
wait-for-it redis:6379 -t 60

if [ $? -ne 0 ]; then
    echo "Redis failed to start"
    exit 1
fi

echo "Redis is ready!"

# Load environment variables if .env exists
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

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