# Minimal Discord bot scaffold for Ouroboros
# This bot forwards Telegram messages and supports a simple !status command.
# It runs as a background task when the runtime starts.

import os
import asyncio
from telegram import Update, Bot
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters
import discord
from discord.ext import commands

# Load secrets from environment (set by supervisor)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
DISCORD_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
DISCORD_GUILD_ID = int(os.getenv("DISCORD_GUILD_ID", "0"))

# Shared queue for messages (simple in‑memory list)
message_queue = []

# Telegram handler – forward text to Discord channel and store for status command
async def telegram_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message and update.message.text:
        txt = f"[Telegram] {update.effective_user.full_name}: {update.message.text}"
        message_queue.append(txt)
        # Forward to Discord (first channel found)
        if discord_bot is not None:
            await discord_bot.send_message_to_channel(txt)

# Discord bot class
class DiscordBot(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.channel = None

    async def setup(self):
        # Wait until guild is ready then pick the first text channel
        await self.bot.wait_until_ready()
        guild = self.bot.get_guild(DISCORD_GUILD_ID)
        if guild:
            for ch in guild.text_channels:
                self.channel = ch
                break
        else:
            print("Discord guild not found, check DISCORD_GUILD_ID")

    async def send_message_to_channel(self, text: str):
        if self.channel:
            await self.channel.send(text)
        else:
            print("No Discord channel to forward message")

# Global instance placeholder (set after bot starts)
discord_bot = None

async def start_telegram():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, telegram_handler))
    await app.initialize()
    await app.start()
    # Keep running – the supervisor will handle graceful shutdown
    await asyncio.Event().wait()

async def start_discord():
    global discord_bot
    intents = discord.Intents.default()
    intents.message_content = True
    bot = commands.Bot(command_prefix="!", intents=intents)

    @bot.event
    async def on_ready():
        print(f"Discord bot logged in as {bot.user}")
        # Attach our cog
        discord_bot = DiscordBot(bot)
        await discord_bot.setup()
        # Register !status command
        @bot.command(name="status")
        async def status(ctx):
            # Summarize recent forwarded messages (last 5)
            recent = "\n".join(message_queue[-5:]) or "No recent messages"
            await ctx.send(f"Ouroboros status:\n{recent}")

    await bot.start(DISCORD_TOKEN)

# Entry point for background execution – called by supervisor after restart
async def main():
    await asyncio.gather(start_telegram(), start_discord())

if __name__ == "__main__":
    asyncio.run(main())
