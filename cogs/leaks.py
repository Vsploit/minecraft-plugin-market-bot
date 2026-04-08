"""
Leaked plugins cog — submit, browse, and request leaked plugins.
"""

import discord
from discord.ext import commands
from discord import app_commands
import logging
import math
from config import COLORS, PLUGIN_CATEGORIES, PLUGIN_TYPES, MC_VERSIONS
from utils.checks import has_leaked_access, is_dropper
from utils.embeds import (success_embed, error_embed, info_embed,
                          plugin_embed, plugin_list_embed, log_embed)
from utils.paginator import PluginPaginator, ApproveRejectView

logger = logging.getLogger('PluginMarket.Leaks')

PAGE_SIZE = 5


# ── Leak submission modal ─────────────────────────────────────────────────────

class LeakSubmitModal(discord.ui.Modal, title="🔓 Submit Leaked Plugin"):
    p_name    = discord.ui.TextInput(label="Plugin Name",        placeholder="e.g. RealisticSeasons",      max_length=64)
    p_version = discord.ui.TextInput(label="Version",            placeholder="e.g. 3.2.1",                 max_length=20, default="Unknown")
    p_desc    = discord.ui.TextInput(label="Description",        placeholder="What does this plugin do?",   style=discord.TextStyle.paragraph, max_length=800)
    p_origin  = discord.ui.TextInput(label="Original Price/Site", placeholder="e.g. $14.99 on SpigotMC",  max_length=200, required=False)

    def __init__(self, bot, plugin_type: str, mc_version: str,
                 attachment: discord.Attachment, image_url: str = None):
        super().__init__()
        self.bot         = bot
        self.plugin_type = plugin_type
        self.mc_version  = mc_version
        self.attachment  = attachment
        self.image_url   = image_url

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        if not self.attachment.filename.lower().endswith('.jar'):
            await interaction.followup.send(
                embed=error_embed("Invalid File", "Only `.jar` files are accepted."), ephemeral=True
            )
            return

        plugin_id = await self.bot.db.add_plugin(
            name        = self.p_name.value.strip(),
            description = self.p_desc.value.strip(),
            version     = self.p_version.value.strip(),
            category    = 'Misc',
            tags        = 'leaked',
            file_url    = self.attachment.url,
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

        await interaction.followup.send(
            embed=success_embed(
                "Leak Submitted!",
                f"**{self.p_name.value}** (ID: `{plugin_id}`) has been submitted for staff review.\n"
                "Once approved it will appear in the leaked plugins channel.",
            ),
            ephemeral=True,
        )

        # Send to pending channel
        pending_ch_id = await self.bot.db.get_config('ch_pending')
        if pending_ch_id:
            ch = interaction.guild.get_channel(int(pending_ch_id))
            if ch:
                from utils.embeds import pending_embed
                embed = pending_embed(plugin, interaction.user.display_name)
                embed.title = f"🔓 Leaked Plugin Submission — {plugin['name']}"
                embed.color = COLORS['pink']
                view = ApproveRejectView(plugin_id, self.bot)
                await ch.send(embed=embed, view=view)

        # Log
        await self.bot.log_action(
            interaction.guild,
            log_embed("Leaked Plugin Submitted",
                      f"**{self.p_name.value}** by {interaction.user.mention}",
                      interaction.user, color=COLORS['pink'])
        )

        logger.info(f"Leaked plugin {plugin_id} submitted by {interaction.user.id}")


class LeakTypeSelectView(discord.ui.View):
    def __init__(self, bot, plugin_type: str, mc_version: str,
                 attachment: discord.Attachment, image_url: str = None):
        super().__init__(timeout=120)
        self.bot         = bot
        self.plugin_type = plugin_type
        self.mc_version  = mc_version
        self.attachment  = attachment
        self.image_url   = image_url

    @discord.ui.button(label="📝 Fill in Details", style=discord.ButtonStyle.green)
    async def fill_details(self, interaction: discord.Interaction, _):
        await interaction.response.send_modal(
            LeakSubmitModal(self.bot, self.plugin_type, self.mc_version, self.attachment, self.image_url)
        )


# ── Request modal ─────────────────────────────────────────────────────────────

class LeakRequestModal(discord.ui.Modal, title="📩 Request a Plugin Leak"):
    plugin_name = discord.ui.TextInput(label="Plugin Name",    placeholder="e.g. ShopGUI+",        max_length=64)
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
            embed=success_embed("Request Submitted", f"Requested **{self.plugin_name.value}** to be leaked."),
            ephemeral=True,
        )


# ── Cog ───────────────────────────────────────────────────────────────────────

class LeaksCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ── /leak ─────────────────────────────────────────────────────────────────

    @app_commands.command(name="leak", description="🔓 Submit a leaked Minecraft plugin.")
    @app_commands.describe(
        plugin_file = ".jar file of the leaked plugin",
        plugin_type = "Platform",
        mc_version  = "Target MC version",
        thumbnail   = "Thumbnail image (optional)",
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

        image_url = thumbnail.url if thumbnail else None
        await interaction.response.send_message(
            embed=info_embed(
                "Submit Leak",
                "Click below to fill in the plugin details."
            ),
            view=LeakTypeSelectView(self.bot, plugin_type, mc_version, plugin_file, image_url),
            ephemeral=True,
        )

    # ── /leaked ───────────────────────────────────────────────────────────────

    @app_commands.command(name="leaked", description="🔓 Browse all leaked plugins.")
    @has_leaked_access()
    async def leaked(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        async def fetch(page: int):
            items = await self.bot.db.get_plugins(leaked=True, limit=PAGE_SIZE, offset=(page - 1) * PAGE_SIZE)
            total = await self.bot.db.count_plugins(leaked=True)
            total_pages = max(1, math.ceil(total / PAGE_SIZE))
            return items, total_pages

        items, total_pages = await fetch(1)
        embed = plugin_list_embed(items, 1, total_pages, title="🔓 Leaked Plugins", leaked=True)

        view = PluginPaginator(fetch, lambda i, p, t: plugin_list_embed(i, p, t, title="🔓 Leaked Plugins", leaked=True), interaction)
        view.total_pages = total_pages
        view._update_buttons()
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    # ── /request-leak ─────────────────────────────────────────────────────────

    @app_commands.command(name="request-leak", description="📩 Request a plugin to be leaked.")
    @has_leaked_access()
    async def request_leak(self, interaction: discord.Interaction):
        await interaction.response.send_modal(LeakRequestModal(self.bot))

    # ── /leaked-plugin ────────────────────────────────────────────────────────

    @app_commands.command(name="leaked-plugin", description="🔓 View a specific leaked plugin.")
    @app_commands.describe(plugin_id="Plugin ID")
    @has_leaked_access()
    async def leaked_plugin(self, interaction: discord.Interaction, plugin_id: int):
        await interaction.response.defer(ephemeral=True)
        plugin = await self.bot.db.get_plugin(plugin_id)
        if not plugin or not plugin['is_leaked']:
            await interaction.followup.send(embed=error_embed("Not Found", "Leaked plugin not found."), ephemeral=True)
            return

        author = interaction.guild.get_member(plugin['author_id'])
        embed = plugin_embed(plugin, author)

        view = discord.ui.View()
        view.add_item(discord.ui.Button(
            label=f"📥 Download {plugin['file_name']}",
            url=plugin['file_url'],
            style=discord.ButtonStyle.link,
        ))
        await self.bot.db.increment_downloads(plugin_id)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    # ── /leak-requests ────────────────────────────────────────────────────────

    @app_commands.command(name="leak-requests", description="📋 View all pending leak requests.")
    @has_leaked_access()
    async def view_requests(self, interaction: discord.Interaction):
        await interaction.response.defer()
        requests = await self.bot.db.fetchall(
            "SELECT * FROM leak_requests WHERE fulfilled=0 ORDER BY created_at DESC LIMIT 20"
        )
        embed = discord.Embed(title="📩 Pending Leak Requests", color=COLORS['pink'])
        if not requests:
            embed.description = "No pending requests."
        else:
            for r in requests:
                user = interaction.guild.get_member(r['requester_id'])
                name = user.display_name if user else f"Unknown#{r['requester_id']}"
                embed.add_field(
                    name=f"[#{r['id']}] {r['plugin_name']}",
                    value=f"> Requested by **{name}**\n> {r['description'] or '*No description.*'}",
                    inline=False,
                )
        await interaction.followup.send(embed=embed)

    # ── /fulfill-request ──────────────────────────────────────────────────────

    @app_commands.command(name="fulfill-request", description="✅ Mark a leak request as fulfilled.")
    @app_commands.describe(request_id="The request ID to mark fulfilled")
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
        # DM requester
        try:
            user = interaction.client.get_user(row['requester_id'])
            if user:
                await user.send(embed=success_embed(
                    "Leak Request Fulfilled!",
                    f"Your request for **{row['plugin_name']}** has been fulfilled!\nCheck the leaked plugins channel."
                ))
        except Exception:
            pass
        await interaction.followup.send(
            embed=success_embed("Fulfilled", f"Request #{request_id} marked as fulfilled."), ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(LeaksCog(bot))
