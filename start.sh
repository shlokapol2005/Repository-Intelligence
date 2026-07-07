#!/bin/bash

# Start the Discord bot in the background (unbuffered)
cd discord_bot
python -u main.py &

# Go back to the root, then into the backend
cd ..
cd backend

# Start the FastAPI server in the foreground
uvicorn main:app --host 0.0.0.0 --port $PORT
