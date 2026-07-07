"""
run_all.py — Starts both the FastAPI backend and the Discord bot together.

Usage:
    python run_all.py

Press Ctrl+C to stop both.
"""
import subprocess
import sys
import time
from pathlib import Path

ROOT    = Path(__file__).parent
BACKEND = ROOT / "backend"
BOT     = ROOT / "discord_bot"

print("=" * 55)
print("  Code Detective — Starting all services")
print("=" * 55)

# ── Find the virtual environment ───────────────────────────────────────────────
VENV_PYTHON = ROOT / "backend" / ".venv" / "Scripts" / "python.exe"
if not VENV_PYTHON.exists():
    VENV_PYTHON = ROOT / "backend" / ".venv" / "bin" / "python" # Mac/Linux fallback
    if not VENV_PYTHON.exists():
        print("ERROR: Could not find virtual environment python executable.")
        sys.exit(1)

# ── Start FastAPI backend ──────────────────────────────────────────────────────
print("\n[1/2] Starting FastAPI backend on http://localhost:8000 ...")
api_proc = subprocess.Popen(
    [str(VENV_PYTHON), "-m", "uvicorn", "main:app", "--port", "8000", "--reload", "--reload-dir", "routers", "--reload-dir", "utils"],
    cwd=str(BACKEND),
)
time.sleep(3)   # give FastAPI a moment to bind the port before the bot tries to call it

# ── Start Discord bot ──────────────────────────────────────────────────────────
print("[2/2] Starting Discord bot ...")
bot_proc = subprocess.Popen(
    [str(VENV_PYTHON), "main.py"],
    cwd=str(BOT),
)

print("\n✅ Both services running.")
print("   FastAPI: http://localhost:8000/docs")
print("   Bot:     watching Discord for /repobot commands")
print("\nPress Ctrl+C to stop everything.\n")

try:
    api_proc.wait()
except KeyboardInterrupt:
    print("\nShutting down...")
    api_proc.terminate()
    bot_proc.terminate()
    api_proc.wait()
    bot_proc.wait()
    print("All services stopped.")
