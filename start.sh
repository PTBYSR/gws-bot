#!/bin/bash
# start.sh

# Ensure WHATSAPP_MONITOR_URL points to the internal Node.js Express server running on Render's $PORT
export WHATSAPP_MONITOR_URL="http://localhost:${PORT:-3005}/send"

# Start the Node.js WhatsApp monitor in the background
# (WhatsApp feature paused)
# echo "Starting WhatsApp Monitor in background..."
# cd whatsapp
# node monitor.js &
# NODE_PID=$!
# cd ..

# Wait a moment for the server to spin up
sleep 3

# Start the Python Selfbot Logger in the foreground
echo "Starting Python Selfbot Logger..."
python main.py

# Wait for node process to ensure container stays alive if python exits
# wait $NODE_PID
