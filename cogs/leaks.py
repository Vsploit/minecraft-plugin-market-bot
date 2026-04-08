"""
Leaked plugins cog — /leak posts the .jar + embed directly to #leaked-plugins
the instant the dropper submits the form. No approval queue.
"""

import discord
from discord.ext import commands
from discord import app_commands
import logging
import aiohttp
import io
import math
from datetime import datetime
from config import COLORS, PLUGIN_TYPES, MC_VERSIONS
from utils.checks import has_leaked_access, is_dropper
from utils.embeds import success_embed, error_embed, info_embed, plugin_embed, plugin_list_embed, log_embed
from utils.paginator import PluginPaginator

logger = logging.getLogger('PluginMarket.Leaks')
PAGE_SIZE = 5


async def download_bytes(url: str) -> bytes | None:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    return await resp.read()
    except Exception as exc:
        logger.error(f"Download failed: {exc}")
    return None


def build_leak_embed(data: dict, author: discord.Member) -> discord.Embed:
    embed = discord.Embed(
        title       = f"🔓 LEAKED — {data['name']} v{data['version']}",
        description = data['description'],
        color       = COLORS['pink'],
        timestamp   = datetime.utcnow(),
    )
    embed.set_author(name=f"Dropped by {author.display_name}", icon_url=author.display_avatar.url)
    embed.add_field(name="📦 Type",   value=data['plugin_type'], inline=True)
    embed.add_field(name="🎮 MC",    value=data['mc_version'],  inline=True)
    if data.get('origin'):
        embed.add_field(name="💸 Original", value=data['origin'], inline=True)
    embed.set_footer(text="📥 Download the .jar file attached below  |  For educational use only")
    if data.get('image_url'):
        embed.set_thumbnail(url=data['image_url'])
    return embed


# ── Leak modal ────────────────────────────────────────────────────────────────

class LeakModal(discord.ui.Modal, title="🔓 Drop a Leaked Plugin"):
    p_name   = discord.ui.TextInput(label="Plugin Name",          placeholder="e.g. RealisticSeasons",      max_length=64)
    p_ver    = discord.ui.TextInput(label="Version",               placeholder="e.g. 3.2.1",                 max_length=20, default="Unknown")
    p_desc   = discord.ui.TextInput(label="Description",          placeholder="What does this plugin do?",   style=discord.TextStyle.paragraph, max_length=800)
    p_origin = discord.ui.TextInput(label="Original Price / Source", placeholder="e.g. $14.99 on SpigotMC", max_length=200, required=False)

    def __init__(self, bot, *, plugin_type: str, mc_version: str,
                 file_bytes: bytes, filename: str, image_url: str | None):
        super().__init__()
        self.bot, self.plugin_type = bot, plugin_type
        self.mc_version            = mc_version
        self.file_bytes, self.filename = file_bytes, filename
        self.image_url             = image_url

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        data = {
            'name':        self.p_name.value.strip(),
            'version':     self.p_ver.value.strip(),
            'description': self.p_desc.value.strip(),
            'origin':      self.p_origin.value.strip() or None,
            'plugin_type': self.plugin_type,
            'mc_version':  self.mc_version,
            'image_url':   self.image_url,
        }

        # ── 1. Post directly to #leaked-plugins ──────────────────────────────
        leaked_ch_id = await self.bot.db.get_config('ch_leaked')
        if not leaked_ch_id:
            await interaction.followup.send(
                embed=error_embed("Setup Needed", "`#leaked-plugins` channel missing. Ask an admin to run `/setup`."),
                ephemeral=True,
            )
            return

        leaked_ch = interaction.guild.get_channel(int(leaked_ch_id))
        if not leaked_ch:
            await interaction.followup.send(
                embed=error_embed("Channel Missing", "`#leaked-plugins` not found. Re-run `/setup`."),
                ephemeral=True,
            )
            return

        embed     = build_leak_embed(data, interaction.user)
        disc_file = discord.File(
            io.BytesIO(self.file_bytes),
            filename    = self.filename,
            description = f"[LEAKED] {data['name']} v{data['version']}",
        )
        dropped_msg = await leaked_ch.send(embed=embed, file=disc_file)

        # ── 2. Save metadata to DB ────────────────────────────────────────────
        stable_url = dropped_msg.attachments[0].url if dropped_msg.attachments else ""
        plugin_id  = await self.bot.db.add_plugin(
            name        = data['name'],
            description = data['description'],
            version     = data['version'],
            category    = 'Misc',
            tags        = 'leaked',
            file_url    = stable_url,
            file_name   = self.filename,
            image_url   = data['image_url'],
            author_id   = interaction.user.id,
            guild_id    = interaction.guild_id,
            price       = 0.0,
            plugin_type = data['plugin_type'],
            mc_version  = data['mc_version'],
            source_url  = data['origin'],
            is_leaked   = 1,
            approved    = 1,          # auto-live
            msg_id      = dropped_msg.id,
            channel_id  = leaked_ch.id,
        )

        # ── 3. Staff drop-log ─────────────────────────────────────────────────
        log_ch_id = await self.bot.db.get_config('ch_drop_log')
        if log_ch_id:
            log_ch = interaction.guild.get_channel(int(log_ch_id))
            if log_ch:
                log_e = discord.Embed(
                    title       = f"📋 Leaked Drop — {data['name']} v{data['version']}",
                    description = (
                        f"**Dropper:** {interaction.user.mention}\n"
                        f"**Plugin ID:** `{plugin_id}`\n"
                        f"**File:** `{self.filename}`\n"
                        f"**Origin:** {data['origin'] or 'Unknown'}\n"
                        f"**Message:** {dropped_msg.jump_url}"
                    ),
                    color     = COLORS['pink'],
                    timestamp = datetime.utcnow(),
                )
                log_e.set_thumbnail(url=interaction.user.display_avatar.url)
                await log_ch.send(embed=log_e)

        await self.bot.log_action(
            interaction.guild,
            log_embed("Leaked Plugin Dropped",
                      f"**{data['name']}** (ID `{plugin_id}`) → {leaked_ch.mention}",
                      interaction.user, color=COLORS['pink']),
        )

        await interaction.followup.send(
            embed=success_embed(
                "Leaked Plugin Dropped! 🔓",
                f"**{data['name']}** is now live in {leaked_ch.mention}!\n"
                f"Plugin ID: `{plugin_id}`",
            ),
            ephemeral=True,
        )
        logger.info(f"Leaked '{data['name']}' (ID {plugin_id}) dropped by {interaction.user.id}")


# ── Button to open the modal (needed because we deferred before) ──────────────

class FillLeakDetailsView(discord.ui.View):
    def __init__(self, bot, *, plugin_type, mc_version, file_bytes, filename, image_url):
        super().__init__(timeout=180)
        self.bot, self.plugin_type = bot, plugin_type
        self.mc_version  = mc_version
        self.file_bytes  = file_bytes
        self.filename    = filename
        self.image_url   = image_url

    @discord.ui.button(label="📝 Fill in Details", style=discord.ButtonStyle.danger, emoji="🔓")
    async def fill(self, interaction: discord.Interaction, _):
        await interaction.response.send_modal(LeakModal(
            self.bot,
            plugin_type = self.plugin_type,
            mc_version  = self.mc_version,
            file_bytes  = self.file_bytes,
            filename    = self.filename,
            image_url   = self.image_url,
        ))


# ── Request a leak modal ──────────────────────────────────────────────────────

class LeakRequestModal(discord.ui.Modal, title="📩 Request a Plugin Leak"):
    plugin_name = discord.ui.TextInput(label="Plugin Name",          placeholder="e.g. ShopGUI+",   max_length=64)
    description = discord.ui.TextInput(label="Why do you want it?",  placeholder="Optional context…",
                                       style=discord.TextStyle.paragraph, required=False, max_length=400)

    def __init__(self, bot):
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        await self.bot.db.execute(
            "INSERT INTO leak_requests (plugin_name, description, requester_id) VALUES (?,?,?)",
            (self.plugin_name.value.strip(), self.description.value.strip(), interaction.user.id),
        )
        req_ch_id = await self.bot.db.get_config('ch_leak_requests')
        if req_ch_id:
            ch = interaction.guild.get_channel(int(req_ch_id))
            if ch:
                embed = discord.Embed(
                    title       = f"📩 Leak Request — {self.plugin_name.value}",
                    description = self.description.value or "*No additional info.*",
                    color       = COLORS['pink'],
                    timestamp   = datetime.utcnow(),
                )
                embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
                embed.set_footer(text=f"User ID: {interaction.user.id}")
                await ch.send(embed=embed)

        await interaction.response.send_message(
            embed=success_embed("Request Submitted!", f"Requested **{self.plugin_name.value}** to be leaked."),
            ephemeral=True,
        )


# ── Cog ───────────────────────────────────────────────────────────────────────

class LeaksCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ── /leak ─────────────────────────────────────────────────────────────────

    @app_commands.command(name="leak", description="🔓 Drop a leaked plugin — posts instantly to #leaked-plugins.")
    @app_commands.describe(
        plugin_file = "The .jar file of the leaked plugin",
        plugin_type = "Server platform",
        mc_version  = "Target Minecraft version",
        thumbnail   = "Optional thumbnail image",
    )
    @app_commands.choices(
        plugin_type=[app_commands.Choice(name=t, value=t) for t in PLUGIN_TYPES],
        mc_version =[app_commands.Choice(name=v, value=v) for v in MC_VERSIONS],
    )
    @is_dropper()
    async def leak(
        self,
        interaction: discord.Interaction,
        plugin_file: discord.Attachment,
        plugin_type: str = "Spigot",
        mc_version:  str = "1.20",
        thumbnail:   discord.Attachment = None,
    ):
        if not plugin_file.filename.lower().endswith('.jar'):
            await interaction.response.send_message(
                embed=error_embed("Wrong File Type", "Only `.jar` files are accepted."), ephemeral=True
            )
            return
        if plugin_file.size > 50 * 1024 * 1024:
            await interaction.response.send_message(
                embed=error_embed("File Too Large", "Max file size is **50 MB**."), ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)
        await interaction.followup.send(
            embed=info_embed("⏳ Downloading…", f"Fetching `{plugin_file.filename}`…"), ephemeral=True
        )

        file_bytes = await download_bytes(plugin_file.url)
        if not file_bytes:
            await interaction.edit_original_response(
                embed=error_embed("Download Failed", "Couldn't fetch your file. Try again.")
            )
            return

        image_url = thumbnail.url if thumbnail else None

        await interaction.edit_original_response(
            embed=info_embed(
                "✅ File Ready",
                f"`{plugin_file.filename}` ({plugin_file.size // 1024:,} KB) cached.\nClick below to fill in plugin details.",
            ),
            view=FillLeakDetailsView(self.bot,
                plugin_type=plugin_type, mc_version=mc_version,
                file_bytes=file_bytes, filename=plugin_file.filename, image_url=image_url,
            ),
        )

    # ── /leaked ───────────────────────────────────────────────────────────────

    @app_commands.command(name="leaked", description="🔓 Browse all dropped leaked plugins.")
    @has_leaked_access()
    async def leaked(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        async def fetch(page: int):
            items = await self.bot.db.get_plugins(leaked=True, limit=PAGE_SIZE, offset=(page - 1) * PAGE_SIZE)
            total = await self.bot.db.count_plugins(leaked=True)
            return items, max(1, math.ceil(total / PAGE_SIZE))

        items, total_pages = await fetch(1)
        embed = plugin_list_embed(items, 1, total_pages, title="🔓 Leaked Plugins", leaked=True)
        view  = PluginPaginator(fetch, lambda i, p, t: plugin_list_embed(i, p, t, title="🔓 Leaked Plugins", leaked=True), interaction)
        view.total_pages = total_pages
        view._update_buttons()
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    # ── /request-leak ─────────────────────────────────────────────────────────

    @app_commands.command(name="request-leak", description="📩 Request a plugin to be leaked.")
    @has_leaked_access()
    async def request_leak(self, interaction: discord.Interaction):
        await interaction.response.send_modal(LeakRequestModal(self.bot))

    # ── /leak-requests ────────────────────────────────────────────────────────

    @app_commands.command(name="leak-requests", description="📋 View all pending leak requests.")
    @has_leaked_access()
    async def view_requests(self, interaction: discord.Interaction):
        await interaction.response.defer()
        rows = await self.bot.db.fetchall(
            "SELECT * FROM leak_requests WHERE fulfilled=0 ORDER BY created_at DESC LIMIT 20"
        )
        embed = discord.Embed(title="📩 Pending Leak Requests", color=COLORS['pink'])
        if not rows:
            embed.description = "No pending requests — all clear!"
        else:
            for r in rows:
                user = interaction.guild.get_member(r['requester_id'])
                name = user.display_name if user else f"#{r['requester_id']}"
                embed.add_field(
                    name  = f"[#{r['id']}] {r['plugin_name']}",
                    value = f"> By **{name}**\n> {r['description'] or '*No description.*'}",
                    inline=False,
                )
        await interaction.followup.send(embed=embed)

    # ── /fulfill-request ──────────────────────────────────────────────────────

    @app_commands.command(name="fulfill-request", description="✅ Mark a leak request as fulfilled.")
    @app_commands.describe(request_id="Request ID")
    @is_dropper()
    async def fulfill_request(self, interaction: discord.Interaction, request_id: int):
        await interaction.response.defer(ephemeral=True)
        row = await self.bot.db.fetchone("SELECT * FROM leak_requests WHERE id=?", (request_id,))
        if not row:
            await interaction.followup.send(embed=error_embed("Not Found", f"Request `#{request_id}` not found."), ephemeral=True)
            return

        await self.bot.db.execute(
            "UPDATE leak_requests SET fulfilled=1, fulfilled_by=? WHERE id=?",
            (interaction.user.id, request_id),
        )
        try:
            user = interaction.client.get_user(row['requester_id'])
            if user:
                await user.send(embed=success_embed(
                    "Leak Request Fulfilled! 🔓",
                    f"Your request for **{row['plugin_name']}** has been fulfilled!\n"
                    "Check the 🔓 leaked-plugins channel."
                ))
        except Exception:
            pass

        await interaction.followup.send(
            embed=success_embed("Fulfilled", f"Request `#{request_id}` marked as done."), ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(LeaksCog(bot))
