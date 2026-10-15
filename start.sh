#!/bin/bash
# start.sh

run_python_logger() {
    while true; do
        echo "[Runner] Starting Python Selfbot Logger..."
        python -u main.py
        EXIT_CODE=$?
        echo "[Runner] Python Logger exited with code $EXIT_CODE. Restarting in 3 seconds..."
        sleep 3
    done
}

run_python_logger
