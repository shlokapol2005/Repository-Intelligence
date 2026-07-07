"""
main.py — Code Detective Discord Bot entry point.

Startup sequence:
  1. Load .env (BOT_TOKEN)
  2. Create discord.Client with required intents
  3. Register all /repobot slash commands
  4. on_ready: sync commands to Discord's servers
  5. client.run() — blocks forever, keeps WebSocket open
"""
import os
import sys
import asyncio
import logging

import discord
from discord import app_commands
from dotenv import load_dotenv

# ── Load environment variables ─────────────────────────────────────────────────
# Looks for .env in the discord_bot/ folder first, then the parent backend/ folder
from pathlib import Path
_env_path = Path(__file__).parent / ".env"
if not _env_path.exists():
    _env_path = Path(__file__).parent.parent / "backend" / ".env"
load_dotenv(dotenv_path=_env_path)

BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
if not BOT_TOKEN:
    sys.exit(
        "ERROR: DISCORD_BOT_TOKEN is not set.\n"
        "Add it to discord_bot/.env or backend/.env:\n"
        "  DISCORD_BOT_TOKEN=your_token_here"
    )

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("repobot")

# ── Discord client setup ───────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True   # needed to read @mention content

client = discord.Client(intents=intents)
tree   = app_commands.CommandTree(client)

# ── Register all commands from commands.py ─────────────────────────────────────
import commands
commands.register(tree)


# ── Events ─────────────────────────────────────────────────────────────────────

@client.event
async def on_ready():
    log.info(f"Logged in as {client.user} (ID: {client.user.id})")
    log.info("Syncing slash commands with Discord...")
    try:
        synced = await tree.sync()
        log.info(f"Synced {len(synced)} command(s): {[c.name for c in synced]}")
    except Exception as exc:
        log.error(f"Command sync failed: {exc}")

    await client.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name="your codebase 🔍",
        )
    )
    log.info("RepoBot is online and ready!")


@client.event
async def on_disconnect():
    log.warning("Bot disconnected from Discord. Will attempt to reconnect automatically.")


# ── Run ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    log.info("Starting Code Detective Discord Bot...")
    client.run(BOT_TOKEN, log_handler=None)  # log_handler=None uses our config above
