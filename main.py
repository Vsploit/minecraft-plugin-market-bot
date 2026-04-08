import discord
from discord.ext import commands
from discord import app_commands
import os
import asyncio
import logging
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(name)-20s | %(levelname)-8s | %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('PluginMarket')


class PluginMarketBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(
            command_prefix=commands.when_mentioned_or('pm!'),
            intents=intents,
            application_id=int(os.getenv('APPLICATION_ID', 0)),
            help_command=None,
        )
        self.guild_id = int(os.getenv('GUILD_ID', 0))
        self.log_channel_id: int = 0  # Set after setup
        self.version = '2.0.0'

    async def setup_hook(self):
        from database import Database
        self.db = Database('plugins.db')
        await self.db.initialize()
        logger.info("Database initialized")

        cogs = [
            'cogs.setup',
            'cogs.marketplace',
            'cogs.droppers',
            'cogs.leaks',
            'cogs.admin',
            'cogs.moderation',
        ]
        for cog in cogs:
            try:
                await self.load_extension(cog)
                logger.info(f"Loaded cog: {cog}")
            except Exception as exc:
                logger.error(f"Failed to load {cog}: {exc}", exc_info=True)

        guild = discord.Object(id=self.guild_id)
        self.tree.copy_global_to(guild=guild)
        synced = await self.tree.sync(guild=guild)
        logger.info(f"Synced {len(synced)} slash commands to guild {self.guild_id}")

    async def on_ready(self):
        logger.info(f"Logged in as {self.user.name}#{self.user.discriminator} ({self.user.id})")
        logger.info(f"discord.py version: {discord.__version__}")
        await self.change_presence(
            status=discord.Status.online,
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="🧩 Plugin Marketplace | /help"
            )
        )

    async def on_guild_join(self, guild: discord.Guild):
        logger.info(f"Joined guild: {guild.name} ({guild.id})")

    async def on_application_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
        elif isinstance(error, app_commands.CommandOnCooldown):
            await interaction.response.send_message(
                f"⏳ Command on cooldown. Try again in **{error.retry_after:.1f}s**.", ephemeral=True
            )
        else:
            logger.error(f"Unhandled command error: {error}", exc_info=True)
            try:
                await interaction.response.send_message("❌ An unexpected error occurred.", ephemeral=True)
            except discord.InteractionResponded:
                pass

    async def log_action(self, guild: discord.Guild, embed: discord.Embed):
        """Send an action to the audit log channel."""
        row = await self.db.fetchone("SELECT value FROM bot_config WHERE key='log_channel'")
        if row:
            ch = guild.get_channel(int(row['value']))
            if ch:
                try:
                    await ch.send(embed=embed)
                except Exception:
                    pass


bot = PluginMarketBot()

if __name__ == '__main__':
    token = os.getenv('DISCORD_TOKEN')
    if not token:
        logger.critical("DISCORD_TOKEN is not set in .env!")
        raise SystemExit(1)
    asyncio.run(bot.start(token))
