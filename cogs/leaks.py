"""
Leaked plugins cog — submit, browse, and request leaked plugins.
Files are re-uploaded to the pending channel immediately on submission.
"""

import discord
from discord.ext import commands
from discord import app_commands
import logging
import math
import aiohttp
import io
from config import COLORS, PLUGIN_TYPES, MC_VERSIONS
from utils.checks import has_leaked_access, is_dropper
from utils.embeds import (success_embed, error_embed, info_embed,
                          plugin_embed, plugin_list_embed, log_embed)
from utils.paginator import PluginPaginator, ApproveRejectView

logger = logging.getLogger('PluginMarket.Leaks')

PAGE_SIZE = 5


async def download_bytes(url: str) -> bytes | None:
    """Download a URL and return raw bytes."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    return await resp.read()
    except Exception as exc:
        logger.error(f"Failed to download {url}: {exc}")
    return None


# ── Leak submission modal ─────────────────────────────────────────────────────

class LeakSubmitModal(discord.ui.Modal, title="🔓 Submit Leaked Plugin"):
    p_name   = discord.ui.TextInput(label="Plugin Name",         placeholder="e.g. RealisticSeasons",      max_length=64)
    p_ver    = discord.ui.TextInput(label="Version",              placeholder="e.g. 3.2.1",                 max_length=20, default="Unknown")
    p_desc   = discord.ui.TextInput(label="Description",         placeholder="What does this plugin do?",   style=discord.TextStyle.paragraph, max_length=800)
    p_origin = discord.ui.TextInput(label="Original Price / Source", placeholder="e.g. $14.99 on SpigotMC — MC-Market link", max_length=200, required=False)

    def __init__(self, bot, plugin_type: str, mc_version: str,
                 attachment: discord.Attachment, file_bytes: bytes, image_url: str = None):
        super().__init__()
        self.bot         = bot
        self.plugin_type = plugin_type
        self.mc_version  = mc_version
        self.attachment  = attachment
        self.file_bytes  = file_bytes
        self.image_url   = image_url

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        # Insert placeholder row
        plugin_id = await self.bot.db.add_plugin(
            name        = self.p_name.value.strip(),
            description = self.p_desc.value.strip(),
            version     = self.p_ver.value.strip(),
            category    = 'Misc',
            tags        = 'leaked',
            file_url    = self.attachment.url,   # temporary
            file_name   = self.attachment.filename,
            image_url   = self.image_url,
            author_id   = interaction.user.id,
            guild_id    = interaction.guild_id,
            price       = 0.0,
            plugin_type = self.plugin_type,
            mc_version  = self.mc_version,
            source_url  = self.p_origin.value.strip() if self.p_origin.value else None,
            is_leaked   = 1,
            approved    = 0,
        )

        plugin = await self.bot.db.get_plugin(plugin_id)

        # ── Post to pending with ACTUAL file attached ─────────────────────────
        pending_ch_id = await self.bot.db.get_config('ch_pending')
        if pending_ch_id:
            ch = interaction.guild.get_channel(int(pending_ch_id))
            if ch:
                from utils.embeds import pending_embed
                embed = pending_embed(plugin, interaction.user.display_name)
                embed.title = f"🔓 LEAKED Submission — {plugin['name']}"
                embed.color = COLORS['pink']
                view      = ApproveRejectView(plugin_id, self.bot)
                disc_file = discord.File(
                    io.BytesIO(self.file_bytes),
                    filename=self.attachment.filename,
                    description=f"Leaked Plugin ID {plugin_id}",
                )
                pending_msg = await ch.send(embed=embed, view=view, file=disc_file)

                stable_url = pending_msg.attachments[0].url if pending_msg.attachments else self.attachment.url
                await self.bot.db.update_plugin(
                    plugin_id,
                    file_url   = stable_url,
                    msg_id     = pending_msg.id,
                    channel_id = ch.id,
                )

        await interaction.followup.send(
            embed=success_embed(
                "Leak Submitted! 🔓",
                f"**{self.p_name.value}** (ID: `{plugin_id}`) is in the review queue.\n"
                "Once a staff member approves it, it'll appear in the leaked channel.",
            ),
            ephemeral=True,
        )

        await self.bot.log_action(
            interaction.guild,
            log_embed("Leaked Plugin Submitted",
                      f"**{self.p_name.value}** (ID `{plugin_id}`) by {interaction.user.mention}",
                      interaction.user, color=COLORS['pink'])
        )
        logger.info(f"Leaked plugin {plugin_id} submitted by {interaction.user.id}")


# ── Request modal ─────────────────────────────────────────────────────────────

class LeakRequestModal(discord.ui.Modal, title="📩 Request a Plugin Leak"):
    plugin_name = discord.ui.TextInput(label="Plugin Name",         placeholder="e.g. ShopGUI+",              max_length=64)
    description = discord.ui.TextInput(label="Why do you want it?", placeholder="Optional context…",
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
                    title=f"📩 Leak Request — {self.plugin_name.value}",
                    description=self.description.value or "*No additional info.*",
                    color=COLORS['pink'],
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

    @app_commands.command(name="leak", description="🔓 Submit a leaked Minecraft plugin (Droppers only).")
    @app_commands.describe(
        plugin_file = ".jar file of the leaked plugin",
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
                embed=error_embed("Invalid File", "Only `.jar` plugin files are accepted."), ephemeral=True
            )
            return
        if plugin_file.size > 50 * 1024 * 1024:
            await interaction.response.send_message(
                embed=error_embed("File Too Large", "Leaked plugin must be under 50 MB."), ephemeral=True
            )
            return

        # Defer and download immediately before the modal
        await interaction.response.defer(ephemeral=True)
        file_bytes = await download_bytes(plugin_file.url)
        if not file_bytes:
            await interaction.followup.send(
                embed=error_embed("Download Failed", "Could not fetch the file. Please try again."), ephemeral=True
            )
            return

        image_url = thumbnail.url if thumbnail else None

        # Can't open a modal after defer, so send a button instead
        view = _FillDetailsView(self.bot, plugin_type, mc_version, plugin_file, file_bytes, image_url)
        await interaction.followup.send(
            embed=info_embed(
                "File Downloaded ✅",
                f"**`{plugin_file.filename}`** ({plugin_file.size // 1024:,} KB) ready.\n\n"
                "Click **Fill in Details** to complete the submission."
            ),
            view=view,
            ephemeral=True,
        )


class _FillDetailsView(discord.ui.View):
    def __init__(self, bot, plugin_type, mc_version, attachment, file_bytes, image_url):
        super().__init__(timeout=180)
        self.bot, self.plugin_type = bot, plugin_type
        self.mc_version, self.attachment = mc_version, attachment
        self.file_bytes, self.image_url = file_bytes, image_url

    @discord.ui.button(label="📝 Fill in Details", style=discord.ButtonStyle.green)
    async def fill(self, interaction: discord.Interaction, _):
        await interaction.response.send_modal(
            LeakSubmitModal(self.bot, self.plugin_type, self.mc_version,
                            self.attachment, self.file_bytes, self.image_url)
        )

    # ── /leaked ───────────────────────────────────────────────────────────────


class LeaksCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="leak", description="🔓 Submit a leaked Minecraft plugin.")
    @app_commands.describe(
        plugin_file="The .jar file", plugin_type="Platform",
        mc_version="MC version", thumbnail="Thumbnail (optional)",
    )
    @app_commands.choices(
        plugin_type=[app_commands.Choice(name=t, value=t) for t in PLUGIN_TYPES],
        mc_version =[app_commands.Choice(name=v, value=v) for v in MC_VERSIONS],
    )
    @is_dropper()
    async def leak(self, interaction: discord.Interaction,
                   plugin_file: discord.Attachment,
                   plugin_type: str = "Spigot", mc_version: str = "1.20",
                   thumbnail: discord.Attachment = None):
        if not plugin_file.filename.lower().endswith('.jar'):
            await interaction.response.send_message(
                embed=error_embed("Invalid File", "Only `.jar` plugin files are accepted."), ephemeral=True)
            return
        if plugin_file.size > 50 * 1024 * 1024:
            await interaction.response.send_message(
                embed=error_embed("File Too Large", "Max 50 MB."), ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        file_bytes = await download_bytes(plugin_file.url)
        if not file_bytes:
            await interaction.followup.send(
                embed=error_embed("Download Failed", "Could not fetch the file. Try again."), ephemeral=True)
            return

        view = _FillDetailsView(self.bot, plugin_type, mc_version, plugin_file, file_bytes, thumbnail.url if thumbnail else None)
        await interaction.followup.send(
            embed=info_embed("Ready ✅", f"`{plugin_file.filename}` downloaded. Click below to submit."),
            view=view, ephemeral=True,
        )

    @app_commands.command(name="leaked", description="🔓 Browse all approved leaked plugins.")
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

    @app_commands.command(name="request-leak", description="📩 Request a plugin to be leaked.")
    @has_leaked_access()
    async def request_leak(self, interaction: discord.Interaction):
        await interaction.response.send_modal(LeakRequestModal(self.bot))

    @app_commands.command(name="leaked-plugin", description="🔓 View and download a specific leaked plugin.")
    @app_commands.describe(plugin_id="Plugin ID")
    @has_leaked_access()
    async def leaked_plugin(self, interaction: discord.Interaction, plugin_id: int):
        await interaction.response.defer(ephemeral=True)
        plugin = await self.bot.db.get_plugin(plugin_id)
        if not plugin or not plugin['is_leaked'] or not plugin['approved']:
            await interaction.followup.send(embed=error_embed("Not Found", "Leaked plugin not found."), ephemeral=True)
            return

        author = interaction.guild.get_member(plugin['author_id'])
        embed  = plugin_embed(plugin, author)

        # Re-upload the actual file so the user gets a fresh download
        file_bytes = await download_bytes(plugin['file_url'])
        if file_bytes:
            disc_file = discord.File(io.BytesIO(file_bytes), filename=plugin['file_name'])
            await self.bot.db.increment_downloads(plugin_id)
            await interaction.followup.send(
                content=f"🔓 **{plugin['name']}** v{plugin['version']} — download below:",
                embed=embed, file=disc_file, ephemeral=True,
            )
        else:
            await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="leak-requests", description="📋 View all pending leak requests.")
    @has_leaked_access()
    async def view_requests(self, interaction: discord.Interaction):
        await interaction.response.defer()
        rows = await self.bot.db.fetchall(
            "SELECT * FROM leak_requests WHERE fulfilled=0 ORDER BY created_at DESC LIMIT 20"
        )
        embed = discord.Embed(title="📩 Pending Leak Requests", color=COLORS['pink'])
        if not rows:
            embed.description = "No pending requests."
        else:
            for r in rows:
                user = interaction.guild.get_member(r['requester_id'])
                name = user.display_name if user else f"User#{r['requester_id']}"
                embed.add_field(
                    name=f"[#{r['id']}] {r['plugin_name']}",
                    value=f"> By **{name}**\n> {r['description'] or '*No description.*'}",
                    inline=False,
                )
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="fulfill-request", description="✅ Mark a leak request as fulfilled.")
    @app_commands.describe(request_id="Request ID to close")
    @is_dropper()
    async def fulfill_request(self, interaction: discord.Interaction, request_id: int):
        await interaction.response.defer(ephemeral=True)
        row = await self.bot.db.fetchone("SELECT * FROM leak_requests WHERE id=?", (request_id,))
        if not row:
            await interaction.followup.send(embed=error_embed("Not Found", "Request not found."), ephemeral=True)
            return
        await self.bot.db.execute(
            "UPDATE leak_requests SET fulfilled=1, fulfilled_by=? WHERE id=?",
            (interaction.user.id, request_id)
        )
        try:
            user = interaction.client.get_user(row['requester_id'])
            if user:
                await user.send(embed=success_embed(
                    "Leak Request Fulfilled!",
                    f"Your request for **{row['plugin_name']}** has been fulfilled!\n"
                    "Check the 🔓 leaked-plugins channel."
                ))
        except Exception:
            pass
        await interaction.followup.send(
            embed=success_embed("Fulfilled", f"Request `#{request_id}` marked as fulfilled."), ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(LeaksCog(bot))
