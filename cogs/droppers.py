"""
Dropper system — upload plugins, manage dropper profiles, approval workflow.
Files are downloaded from the interaction attachment and re-uploaded to the
pending-review channel so they persist (no expiring CDN links).
"""

import discord
from discord.ext import commands
from discord import app_commands
import logging
import aiohttp
import io
from config import COLORS, PLUGIN_CATEGORIES, PLUGIN_TYPES, MC_VERSIONS
from utils.checks import is_dropper
from utils.embeds import success_embed, error_embed, info_embed, pending_embed, log_embed
from utils.paginator import ApproveRejectView

logger = logging.getLogger('PluginMarket.Droppers')


async def download_bytes(url: str) -> bytes | None:
    """Download a file from a URL and return its raw bytes."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    return await resp.read()
    except Exception as exc:
        logger.error(f"Failed to download {url}: {exc}")
    return None


# ── Upload Modal ──────────────────────────────────────────────────────────────

class UploadPluginModal(discord.ui.Modal, title="🧩 Upload Plugin"):
    p_name    = discord.ui.TextInput(label="Plugin Name",               placeholder="e.g. SuperEconomy",             max_length=64)
    p_version = discord.ui.TextInput(label="Version",                   placeholder="e.g. 1.0.0",                    max_length=20, default="1.0.0")
    p_desc    = discord.ui.TextInput(label="Description",               placeholder="Describe what your plugin does.", style=discord.TextStyle.paragraph, max_length=1000)
    p_tags    = discord.ui.TextInput(label="Tags (comma-separated)",    placeholder="economy, shops, trade",          max_length=200, required=False)
    p_source  = discord.ui.TextInput(label="Source URL (optional)",    placeholder="https://github.com/...",         required=False, max_length=200)

    def __init__(self, bot, category: str, plugin_type: str, mc_version: str,
                 price: float, attachment: discord.Attachment, image_url: str = None):
        super().__init__()
        self.bot         = bot
        self.category    = category
        self.plugin_type = plugin_type
        self.mc_version  = mc_version
        self.price       = price
        self.attachment  = attachment
        self.image_url   = image_url

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        if not self.attachment.filename.lower().endswith('.jar'):
            await interaction.followup.send(embed=error_embed("Invalid File", "Only `.jar` files are accepted."), ephemeral=True)
            return

        # ── Download the file from Discord's CDN right now ────────────────────
        await interaction.followup.send(
            embed=info_embed("Uploading…", "Downloading and saving your plugin file. Please wait…"),
            ephemeral=True,
        )

        file_bytes = await download_bytes(self.attachment.url)
        if not file_bytes:
            await interaction.edit_original_response(
                embed=error_embed("Download Failed", "Could not download your plugin file. Please try again.")
            )
            return

        # ── Insert a 'placeholder' plugin row first so we have an ID ─────────
        plugin_id = await self.bot.db.add_plugin(
            name        = self.p_name.value.strip(),
            description = self.p_desc.value.strip(),
            version     = self.p_version.value.strip(),
            category    = self.category,
            tags        = self.p_tags.value.strip() if self.p_tags.value else '',
            file_url    = self.attachment.url,   # temporary; updated below
            file_name   = self.attachment.filename,
            image_url   = self.image_url,
            author_id   = interaction.user.id,
            guild_id    = interaction.guild_id,
            price       = self.price,
            plugin_type = self.plugin_type,
            mc_version  = self.mc_version,
            source_url  = self.p_source.value.strip() if self.p_source.value else None,
            is_leaked   = 0,
        )

        plugin = await self.bot.db.get_plugin(plugin_id)

        # ── Post to pending channel with ACTUAL file attached ─────────────────
        pending_ch_id = await self.bot.db.get_config('ch_pending')
        if pending_ch_id:
            ch = interaction.guild.get_channel(int(pending_ch_id))
            if ch:
                embed  = pending_embed(plugin, interaction.user.display_name)
                view   = ApproveRejectView(plugin_id, self.bot)
                disc_file = discord.File(
                    io.BytesIO(file_bytes),
                    filename=self.attachment.filename,
                    description=f"Plugin ID {plugin_id} — {self.p_name.value}",
                )
                pending_msg = await ch.send(embed=embed, view=view, file=disc_file)

                # Update DB with the stable attachment URL from the pending msg
                stable_url = pending_msg.attachments[0].url if pending_msg.attachments else self.attachment.url
                await self.bot.db.update_plugin(
                    plugin_id,
                    file_url   = stable_url,
                    msg_id     = pending_msg.id,
                    channel_id = ch.id,
                )

        # Increment dropper drop count
        await self.bot.db.increment_drops(interaction.user.id)

        await interaction.edit_original_response(embed=success_embed(
            "Plugin Submitted! 🎉",
            f"**{self.p_name.value}** (ID: `{plugin_id}`) is now pending staff review.\n"
            "You'll receive a DM when it's approved or rejected.",
        ))

        # Audit log
        log_e = log_embed(
            "Plugin Submitted",
            f"**{self.p_name.value}** (ID `{plugin_id}`) by {interaction.user.mention}",
            interaction.user, color=COLORS['cyan'],
        )
        await self.bot.log_action(interaction.guild, log_e)
        logger.info(f"Plugin {plugin_id} submitted by {interaction.user} ({interaction.user.id})")


# ── Category select → triggers modal ─────────────────────────────────────────

class CategorySelect(discord.ui.Select):
    def __init__(self, bot, plugin_type: str, mc_version: str, price: float,
                 attachment: discord.Attachment, image_url: str = None):
        self.bot         = bot
        self.plugin_type = plugin_type
        self.mc_version  = mc_version
        self.price       = price
        self.attachment  = attachment
        self.image_url   = image_url

        options = [discord.SelectOption(label=c, value=c, emoji="📂") for c in PLUGIN_CATEGORIES]
        super().__init__(placeholder="📂 Select your plugin's category…", options=options, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(
            UploadPluginModal(
                self.bot, self.values[0], self.plugin_type, self.mc_version,
                self.price, self.attachment, self.image_url,
            )
        )


class CategorySelectView(discord.ui.View):
    def __init__(self, bot, plugin_type: str, mc_version: str, price: float,
                 attachment: discord.Attachment, image_url: str = None):
        super().__init__(timeout=120)
        self.add_item(CategorySelect(bot, plugin_type, mc_version, price, attachment, image_url))


# ── Cog ───────────────────────────────────────────────────────────────────────

class DroppersCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ── /upload ───────────────────────────────────────────────────────────────

    @app_commands.command(name="upload", description="💧 Upload a Minecraft plugin to the marketplace.")
    @app_commands.describe(
        plugin_file = "The .jar plugin file to upload",
        plugin_type = "Server platform (Spigot, Paper, Fabric, etc.)",
        mc_version  = "Target Minecraft version",
        price       = "Price in USD — enter 0 for free",
        thumbnail   = "Optional thumbnail image for the listing",
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
        plugin_type: str = "Spigot",
        mc_version:  str = "1.20",
        price:       float = 0.0,
        thumbnail:   discord.Attachment = None,
    ):
        if not plugin_file.filename.lower().endswith('.jar'):
            await interaction.response.send_message(
                embed=error_embed("Invalid File", "Only `.jar` plugin files are accepted."), ephemeral=True
            )
            return

        if plugin_file.size > 25 * 1024 * 1024:
            await interaction.response.send_message(
                embed=error_embed("File Too Large", "Plugin must be under **25 MB**."), ephemeral=True
            )
            return

        image_url = thumbnail.url if thumbnail else None

        await interaction.response.send_message(
            embed=info_embed(
                "Step 2 — Choose a Category",
                f"**File:** `{plugin_file.filename}` ({plugin_file.size // 1024:,} KB)\n"
                f"**Type:** {plugin_type} | **MC:** {mc_version} | **Price:** {'Free' if price == 0 else f'${price:.2f}'}\n\n"
                "Select a category below, then fill in the plugin details."
            ),
            view=CategorySelectView(self.bot, plugin_type, mc_version, price, plugin_file, image_url),
            ephemeral=True,
        )

    # ── /dropper-profile ──────────────────────────────────────────────────────

    @app_commands.command(name="dropper-profile", description="💧 View a dropper's public profile.")
    @app_commands.describe(member="The dropper to look up (defaults to yourself)")
    async def dropper_profile(self, interaction: discord.Interaction, member: discord.Member = None):
        await interaction.response.defer()
        target = member or interaction.user
        row = await self.bot.db.get_dropper(target.id)

        plugins = await self.bot.db.fetchall(
            "SELECT * FROM plugins WHERE author_id=? AND approved=1 ORDER BY downloads DESC LIMIT 5",
            (target.id,)
        )
        total_dl = sum(p['downloads'] for p in plugins)

        embed = discord.Embed(
            title=f"💧 {target.display_name}'s Dropper Profile",
            color=COLORS['cyan'],
        )
        embed.set_thumbnail(url=target.display_avatar.url)

        if row:
            verified = "✅ Verified Seller" if row['verified'] else "💧 Standard Dropper"
            embed.add_field(name="Status",          value=verified,              inline=True)
            embed.add_field(name="Total Drops",     value=f"**{row['drops_count']}**", inline=True)
            embed.add_field(name="Total Downloads", value=f"**{total_dl:,}**",    inline=True)
            if row['bio']:
                embed.add_field(name="Bio", value=row['bio'], inline=False)
        else:
            embed.description = f"{target.mention} is not a registered dropper."

        if plugins:
            plist = "\n".join(
                f"`[{p['id']}]` **{p['name']}** v{p['version']} — 📥 {p['downloads']:,}"
                for p in plugins
            )
            embed.add_field(name="📦 Top Plugins", value=plist, inline=False)

        await interaction.followup.send(embed=embed)

    # ── /set-bio ──────────────────────────────────────────────────────────────

    @app_commands.command(name="set-bio", description="✏️ Set your dropper profile bio.")
    @app_commands.describe(bio="Your bio (max 200 characters)")
    @is_dropper()
    async def set_bio(self, interaction: discord.Interaction, bio: str):
        await interaction.response.defer(ephemeral=True)
        await self.bot.db.execute(
            "UPDATE droppers SET bio=? WHERE user_id=?", (bio[:200], interaction.user.id)
        )
        await interaction.followup.send(
            embed=success_embed("Bio Updated", f"Your bio:\n> {bio[:200]}"), ephemeral=True
        )

    # ── /update-plugin ────────────────────────────────────────────────────────

    @app_commands.command(name="update-plugin", description="🔄 Push a new version of one of your plugins.")
    @app_commands.describe(plugin_id="Plugin ID to update", new_file="New .jar file", new_version="New version string (e.g. 1.2.0)", changelog="What changed in this version?")
    @is_dropper()
    async def update_plugin(
        self,
        interaction: discord.Interaction,
        plugin_id: int,
        new_file: discord.Attachment,
        new_version: str,
        changelog: str = None,
    ):
        await interaction.response.defer(ephemeral=True)

        plugin = await self.bot.db.get_plugin(plugin_id)
        if not plugin:
            await interaction.followup.send(embed=error_embed("Not Found", "Plugin not found."), ephemeral=True)
            return
        if plugin['author_id'] != interaction.user.id and not interaction.user.guild_permissions.administrator:
            await interaction.followup.send(embed=error_embed("Permission Denied", "You don't own this plugin."), ephemeral=True)
            return
        if not new_file.filename.lower().endswith('.jar'):
            await interaction.followup.send(embed=error_embed("Invalid File", "Only `.jar` files accepted."), ephemeral=True)
            return

        await interaction.followup.send(embed=info_embed("Uploading…", "Saving new version…"), ephemeral=True)

        file_bytes = await download_bytes(new_file.url)
        if not file_bytes:
            await interaction.edit_original_response(embed=error_embed("Download Failed", "Could not download the file."))
            return

        # Archive old version
        await self.bot.db.execute(
            "INSERT INTO plugin_versions (plugin_id, version, changelog, file_url, file_name) VALUES (?,?,?,?,?)",
            (plugin_id, plugin['version'], changelog, plugin['file_url'], plugin['file_name']),
        )

        # Post new file to pending
        stable_url = new_file.url
        pending_ch_id = await self.bot.db.get_config('ch_pending')
        if pending_ch_id:
            ch = interaction.guild.get_channel(int(pending_ch_id))
            if ch:
                disc_file = discord.File(io.BytesIO(file_bytes), filename=new_file.filename)
                msg = await ch.send(
                    content=f"🔄 **Update** for plugin `{plugin_id}` — **{plugin['name']}** → v{new_version}",
                    file=disc_file,
                )
                if msg.attachments:
                    stable_url = msg.attachments[0].url

        await self.bot.db.update_plugin(
            plugin_id,
            version   = new_version,
            file_url  = stable_url,
            file_name = new_file.filename,
            approved  = 0,  # Needs re-approval
        )

        await interaction.edit_original_response(embed=success_embed(
            "Plugin Updated",
            f"**{plugin['name']}** updated to **v{new_version}** and is pending re-approval.",
        ))

    # ── /delete-plugin ────────────────────────────────────────────────────────

    @app_commands.command(name="delete-plugin", description="🗑️ Delete one of your plugins from the marketplace.")
    @app_commands.describe(plugin_id="Plugin ID to delete")
    @is_dropper()
    async def delete_plugin(self, interaction: discord.Interaction, plugin_id: int):
        await interaction.response.defer(ephemeral=True)
        plugin = await self.bot.db.get_plugin(plugin_id)
        if not plugin:
            await interaction.followup.send(embed=error_embed("Not Found", "Plugin not found."), ephemeral=True)
            return
        if plugin['author_id'] != interaction.user.id and not interaction.user.guild_permissions.administrator:
            await interaction.followup.send(embed=error_embed("Permission Denied", "You don't own this plugin."), ephemeral=True)
            return

        await self.bot.db.execute("DELETE FROM plugins WHERE id=?", (plugin_id,))
        await interaction.followup.send(
            embed=success_embed("Deleted", f"Plugin **{plugin['name']}** (ID `{plugin_id}`) has been deleted."),
            ephemeral=True,
        )

    # ── /version-history ─────────────────────────────────────────────────────

    @app_commands.command(name="version-history", description="📜 View all past versions of a plugin.")
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
        embed.add_field(
            name=f"🟢 Current — v{plugin['version']}",
            value=f"`{plugin['file_name']}`",
            inline=False,
        )
        for v in versions[:10]:
            embed.add_field(
                name=f"📦 v{v['version']} — {v['released_at'][:10]}",
                value=v['changelog'] or '*No changelog.*',
                inline=False,
            )
        await interaction.followup.send(embed=embed)


async def setup(bot):
    await bot.add_cog(DroppersCog(bot))
