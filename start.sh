#!/usr/bin/env bash
# Starts Endelea. Optional: export GEMINI_API_KEY="..." first. Without a key it runs in demo mode.
cd "$(dirname "$0")"
if [ -z "$GEMINI_API_KEY" ]; then
  read -r -p "Paste your free Gemini key (or press Enter for DEMO MODE): " GEMINI_API_KEY
  export GEMINI_API_KEY
fi
(sleep 2; (xdg-open http://127.0.0.1:8000 || open http://127.0.0.1:8000) >/dev/null 2>&1) &
python3 -m uvicorn backend.main:app --port 8000
