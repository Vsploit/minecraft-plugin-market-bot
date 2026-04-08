"""
Dropper system — /upload posts the .jar + embed directly to #dropped-plugins
the instant the dropper submits the form. No approval queue needed.
"""

import discord
from discord.ext import commands
from discord import app_commands
import logging
import aiohttp
import io
from datetime import datetime
from config import COLORS, PLUGIN_CATEGORIES, PLUGIN_TYPES, MC_VERSIONS
from utils.checks import is_dropper
from utils.embeds import success_embed, error_embed, info_embed, log_embed

logger = logging.getLogger('PluginMarket.Droppers')


async def download_bytes(url: str) -> bytes | None:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    return await resp.read()
    except Exception as exc:
        logger.error(f"Download failed for {url}: {exc}")
    return None


def build_drop_embed(data: dict, author: discord.Member) -> discord.Embed:
    """Build the public-facing embed that goes into #dropped-plugins."""
    price_str = f"**${data['price']:.2f}**" if data['price'] > 0 else "**Free**"
    color     = COLORS['pink'] if data.get('is_leaked') else COLORS['cyan']
    badge     = "🔓 LEAKED" if data.get('is_leaked') else "🧩 Plugin Drop"

    embed = discord.Embed(
        title       = f"{badge} — {data['name']} v{data['version']}",
        description = data['description'],
        color       = color,
        timestamp   = datetime.utcnow(),
    )
    embed.set_author(name=f"Dropped by {author.display_name}", icon_url=author.display_avatar.url)
    embed.add_field(name="📦 Type",     value=data['plugin_type'], inline=True)
    embed.add_field(name="🎮 MC Ver",   value=data['mc_version'],  inline=True)
    embed.add_field(name="🗂 Category", value=data['category'],    inline=True)
    embed.add_field(name="💰 Price",    value=price_str,           inline=True)

    if data.get('tags'):
        tag_str = ' '.join(f"`{t.strip()}`" for t in data['tags'].split(',') if t.strip())
        embed.add_field(name="🏷️ Tags", value=tag_str, inline=False)

    if data.get('source_url'):
        embed.add_field(name="🔗 Source", value=data['source_url'], inline=False)

    embed.set_footer(text="📥 Download the .jar file attached below")
    if data.get('image_url'):
        embed.set_thumbnail(url=data['image_url'])
    return embed


# ── Upload modal ──────────────────────────────────────────────────────────────

class UploadModal(discord.ui.Modal, title="🧩 Drop Your Plugin"):
    p_name    = discord.ui.TextInput(label="Plugin Name",            placeholder="e.g. SuperEconomy",              max_length=64)
    p_version = discord.ui.TextInput(label="Version",                placeholder="e.g. 1.0.0",                     max_length=20,  default="1.0.0")
    p_desc    = discord.ui.TextInput(label="Description",            placeholder="What does your plugin do?",       style=discord.TextStyle.paragraph, max_length=1000)
    p_tags    = discord.ui.TextInput(label="Tags (comma-separated)", placeholder="economy, shops, auctions",        max_length=200, required=False)
    p_source  = discord.ui.TextInput(label="Source / GitHub URL",   placeholder="https://github.com/you/plugin",  max_length=200, required=False)

    def __init__(self, bot, *, category: str, plugin_type: str, mc_version: str,
                 price: float, file_bytes: bytes, filename: str, image_url: str | None):
        super().__init__()
        self.bot         = bot
        self.category    = category
        self.plugin_type = plugin_type
        self.mc_version  = mc_version
        self.price       = price
        self.file_bytes  = file_bytes
        self.filename    = filename
        self.image_url   = image_url

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        data = {
            'name':        self.p_name.value.strip(),
            'version':     self.p_version.value.strip(),
            'description': self.p_desc.value.strip(),
            'tags':        self.p_tags.value.strip(),
            'source_url':  self.p_source.value.strip() or None,
            'category':    self.category,
            'plugin_type': self.plugin_type,
            'mc_version':  self.mc_version,
            'price':       self.price,
            'image_url':   self.image_url,
            'is_leaked':   0,
        }

        # ── 1. Post directly to #dropped-plugins ─────────────────────────────
        dropped_ch_id = await self.bot.db.get_config('ch_dropped')
        if not dropped_ch_id:
            await interaction.followup.send(
                embed=error_embed("Setup Needed", "The `#dropped-plugins` channel doesn't exist yet. Ask an admin to run `/setup`."),
                ephemeral=True,
            )
            return

        dropped_ch = interaction.guild.get_channel(int(dropped_ch_id))
        if not dropped_ch:
            await interaction.followup.send(
                embed=error_embed("Channel Missing", "`#dropped-plugins` channel not found. Re-run `/setup`."),
                ephemeral=True,
            )
            return

        embed     = build_drop_embed(data, interaction.user)
        disc_file = discord.File(
            io.BytesIO(self.file_bytes),
            filename    = self.filename,
            description = f"{data['name']} v{data['version']} by {interaction.user.display_name}",
        )
        dropped_msg = await dropped_ch.send(embed=embed, file=disc_file)

        # ── 2. Save metadata to DB (lightweight — no file storage, just link) ─
        stable_url = dropped_msg.attachments[0].url if dropped_msg.attachments else ""
        plugin_id  = await self.bot.db.add_plugin(
            name        = data['name'],
            description = data['description'],
            version     = data['version'],
            category    = data['category'],
            tags        = data['tags'],
            file_url    = stable_url,
            file_name   = self.filename,
            image_url   = data['image_url'],
            author_id   = interaction.user.id,
            guild_id    = interaction.guild_id,
            price       = data['price'],
            plugin_type = data['plugin_type'],
            mc_version  = data['mc_version'],
            source_url  = data['source_url'],
            is_leaked   = 0,
            approved    = 1,                         # auto-approved — it's already live
            msg_id      = dropped_msg.id,
            channel_id  = dropped_ch.id,
        )

        # ── 3. Increment dropper count ────────────────────────────────────────
        await self.bot.db.increment_drops(interaction.user.id)

        # ── 4. Staff drop-log ─────────────────────────────────────────────────
        log_ch_id = await self.bot.db.get_config('ch_drop_log')
        if log_ch_id:
            log_ch = interaction.guild.get_channel(int(log_ch_id))
            if log_ch:
                log_embed_obj = discord.Embed(
                    title       = f"📋 New Drop — {data['name']} v{data['version']}",
                    description = (
                        f"**Dropper:** {interaction.user.mention}\n"
                        f"**Plugin ID:** `{plugin_id}`\n"
                        f"**File:** `{self.filename}`\n"
                        f"**Category:** {data['category']} • **Type:** {data['plugin_type']}\n"
                        f"**Message:** {dropped_msg.jump_url}"
                    ),
                    color     = COLORS['cyan'],
                    timestamp = datetime.utcnow(),
                )
                log_embed_obj.set_thumbnail(url=interaction.user.display_avatar.url)
                await log_ch.send(embed=log_embed_obj)

        # ── 5. Audit log ──────────────────────────────────────────────────────
        await self.bot.log_action(
            interaction.guild,
            log_embed("Plugin Dropped", f"**{data['name']}** (ID `{plugin_id}`) → {dropped_ch.mention}", interaction.user, color=COLORS['cyan']),
        )

        await interaction.followup.send(
            embed=success_embed(
                "Plugin Dropped! 🎉",
                f"**{data['name']}** is now live in {dropped_ch.mention}!\n"
                f"Plugin ID: `{plugin_id}` — use `/plugin {plugin_id}` to link directly.",
            ),
            ephemeral=True,
        )
        logger.info(f"Plugin '{data['name']}' (ID {plugin_id}) dropped by {interaction.user} into #{dropped_ch.name}")


# ── Category select (step 2) → opens modal (step 3) ──────────────────────────

class CategorySelect(discord.ui.Select):
    def __init__(self, bot, *, plugin_type, mc_version, price, file_bytes, filename, image_url):
        self.bot, self.plugin_type  = bot, plugin_type
        self.mc_version, self.price = mc_version, price
        self.file_bytes, self.filename = file_bytes, filename
        self.image_url              = image_url

        super().__init__(
            placeholder = "📂 Choose a category for your plugin…",
            options     = [discord.SelectOption(label=c, value=c, emoji="📦") for c in PLUGIN_CATEGORIES],
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(UploadModal(
            self.bot,
            category    = self.values[0],
            plugin_type = self.plugin_type,
            mc_version  = self.mc_version,
            price       = self.price,
            file_bytes  = self.file_bytes,
            filename    = self.filename,
            image_url   = self.image_url,
        ))


class CategorySelectView(discord.ui.View):
    def __init__(self, bot, *, plugin_type, mc_version, price, file_bytes, filename, image_url):
        super().__init__(timeout=120)
        self.add_item(CategorySelect(bot,
            plugin_type=plugin_type, mc_version=mc_version, price=price,
            file_bytes=file_bytes, filename=filename, image_url=image_url,
        ))


# ── Cog ───────────────────────────────────────────────────────────────────────

class DroppersCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ── /upload ───────────────────────────────────────────────────────────────

    @app_commands.command(name="upload", description="💧 Drop a Minecraft plugin — posts instantly to #dropped-plugins.")
    @app_commands.describe(
        plugin_file = "The .jar plugin file",
        plugin_type = "Server platform",
        mc_version  = "Target Minecraft version",
        price       = "Price in USD (0 = free)",
        thumbnail   = "Optional thumbnail image for the embed",
    )
    @app_commands.choices(
        plugin_type=[app_commands.Choice(name=t, value=t) for t in PLUGIN_TYPES],
        mc_version =[app_commands.Choice(name=v, value=v) for v in MC_VERSIONS],
    )
    @is_dropper()
    async def upload(
        self,
        interaction: discord.Interaction,
        plugin_file: discord.Attachment,
        plugin_type: str   = "Spigot",
        mc_version:  str   = "1.20",
        price:       float = 0.0,
        thumbnail:   discord.Attachment = None,
    ):
        if not plugin_file.filename.lower().endswith('.jar'):
            await interaction.response.send_message(
                embed=error_embed("Wrong File Type", "Only `.jar` files are accepted."), ephemeral=True
            )
            return
        if plugin_file.size > 25 * 1024 * 1024:
            await interaction.response.send_message(
                embed=error_embed("File Too Large", "Max file size is **25 MB**."), ephemeral=True
            )
            return

        # Defer and download the file immediately (Discord attachment URLs expire)
        await interaction.response.defer(ephemeral=True)
        await interaction.followup.send(
            embed=info_embed("⏳ Downloading file…", f"Fetching `{plugin_file.filename}` ({plugin_file.size // 1024:,} KB)…"),
            ephemeral=True,
        )

        file_bytes = await download_bytes(plugin_file.url)
        if not file_bytes:
            await interaction.edit_original_response(
                embed=error_embed("Download Failed", "Couldn't fetch your file from Discord. Try again.")
            )
            return

        image_url = thumbnail.url if thumbnail else None

        await interaction.edit_original_response(
            embed=info_embed(
                "✅ File Ready — Pick a Category",
                f"**`{plugin_file.filename}`** ({plugin_file.size // 1024:,} KB) is cached.\n"
                f"**Platform:** {plugin_type} | **MC:** {mc_version} | **Price:** {'Free' if price == 0 else f'${price:.2f}'}\n\n"
                "Select a category below then fill in the details.",
            ),
            view=CategorySelectView(self.bot,
                plugin_type=plugin_type, mc_version=mc_version, price=price,
                file_bytes=file_bytes, filename=plugin_file.filename, image_url=image_url,
            ),
        )

    # ── /dropper-profile ──────────────────────────────────────────────────────

    @app_commands.command(name="dropper-profile", description="💧 View a dropper's public profile and their drops.")
    @app_commands.describe(member="The dropper to look up (defaults to yourself)")
    async def dropper_profile(self, interaction: discord.Interaction, member: discord.Member = None):
        await interaction.response.defer()
        target = member or interaction.user

        row     = await self.bot.db.get_dropper(target.id)
        plugins = await self.bot.db.fetchall(
            "SELECT * FROM plugins WHERE author_id=? AND approved=1 ORDER BY downloads DESC LIMIT 5",
            (target.id,)
        )
        total_dl = sum(p['downloads'] for p in plugins)

        embed = discord.Embed(title=f"💧 {target.display_name}'s Dropper Profile", color=COLORS['cyan'])
        embed.set_thumbnail(url=target.display_avatar.url)

        if row:
            status = "💎 Verified Seller" if row['verified'] else "💧 Dropper"
            embed.add_field(name="Status",          value=status,                   inline=True)
            embed.add_field(name="Total Drops",     value=f"**{row['drops_count']}**", inline=True)
            embed.add_field(name="Total Downloads", value=f"**{total_dl:,}**",      inline=True)
            if row['bio']:
                embed.add_field(name="Bio", value=row['bio'], inline=False)
        else:
            embed.description = f"{target.mention} hasn't been set up as a dropper yet."

        if plugins:
            lines = "\n".join(
                f"`[{p['id']}]` **{p['name']}** v{p['version']} — 📥 {p['downloads']:,}"
                for p in plugins
            )
            embed.add_field(name="📦 Top Drops", value=lines, inline=False)

        await interaction.followup.send(embed=embed)

    # ── /set-bio ──────────────────────────────────────────────────────────────

    @app_commands.command(name="set-bio", description="✏️ Set your dropper profile bio.")
    @app_commands.describe(bio="Your bio shown on your dropper profile (max 200 chars)")
    @is_dropper()
    async def set_bio(self, interaction: discord.Interaction, bio: str):
        await interaction.response.defer(ephemeral=True)
        await self.bot.db.execute("UPDATE droppers SET bio=? WHERE user_id=?", (bio[:200], interaction.user.id))
        await interaction.followup.send(
            embed=success_embed("Bio Updated", f"> {bio[:200]}"), ephemeral=True
        )

    # ── /delete-plugin ────────────────────────────────────────────────────────

    @app_commands.command(name="delete-plugin", description="🗑️ Remove one of your drops from the marketplace.")
    @app_commands.describe(plugin_id="The plugin ID to delete")
    @is_dropper()
    async def delete_plugin(self, interaction: discord.Interaction, plugin_id: int):
        await interaction.response.defer(ephemeral=True)
        plugin = await self.bot.db.get_plugin(plugin_id)
        if not plugin:
            await interaction.followup.send(embed=error_embed("Not Found", f"No plugin with ID `{plugin_id}`."), ephemeral=True)
            return
        if plugin['author_id'] != interaction.user.id and not interaction.user.guild_permissions.administrator:
            await interaction.followup.send(embed=error_embed("Permission Denied", "That's not your plugin."), ephemeral=True)
            return

        name = plugin['name']

        # Try to delete the original drop message in #dropped-plugins
        if plugin['msg_id'] and plugin['channel_id']:
            try:
                ch  = interaction.guild.get_channel(int(plugin['channel_id']))
                msg = await ch.fetch_message(int(plugin['msg_id']))
                await msg.delete()
            except Exception:
                pass

        await self.bot.db.execute("DELETE FROM plugins WHERE id=?", (plugin_id,))
        await interaction.followup.send(
            embed=success_embed("Deleted", f"**{name}** (ID `{plugin_id}`) removed from the marketplace."),
            ephemeral=True,
        )

    # ── /version-history ─────────────────────────────────────────────────────

    @app_commands.command(name="version-history", description="📜 View version history of a plugin.")
    @app_commands.describe(plugin_id="Plugin ID")
    async def version_history(self, interaction: discord.Interaction, plugin_id: int):
        await interaction.response.defer()
        plugin = await self.bot.db.get_plugin(plugin_id)
        if not plugin:
            await interaction.followup.send(embed=error_embed("Not Found", "Plugin not found."), ephemeral=True)
            return

        versions = await self.bot.db.fetchall(
            "SELECT * FROM plugin_versions WHERE plugin_id=? ORDER BY released_at DESC", (plugin_id,)
        )
        embed = discord.Embed(title=f"📜 Version History — {plugin['name']}", color=COLORS['blurple'])
        embed.add_field(name=f"🟢 Current — v{plugin['version']}", value=f"`{plugin['file_name']}`", inline=False)
        for v in versions[:10]:
            embed.add_field(
                name  = f"📦 v{v['version']} — {v['released_at'][:10]}",
                value = v['changelog'] or '*No changelog.*',
                inline=False,
            )
        await interaction.followup.send(embed=embed)


async def setup(bot):
    await bot.add_cog(DroppersCog(bot))
