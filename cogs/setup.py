"""
/setup — Wipes all channels & roles, rebuilds the full server structure,
         and sends welcome embeds to the appropriate channels.
"""

import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import logging
from config import ROLES, CHANNEL_STRUCTURE, COLORS
from utils.checks import is_admin
from utils.embeds import success_embed, error_embed, base_embed

logger = logging.getLogger('PluginMarket.Setup')

RULES_TEXT = """
**Welcome to the Minecraft Plugin Marketplace!**

📌 **Rule 1 — Be Respectful**
Treat everyone with respect. Harassment, hate speech, or discrimination in any form is not tolerated.

📌 **Rule 2 — No Spam**
Do not spam messages, commands, or plugin uploads. Repeated violations result in mutes or bans.

📌 **Rule 3 — Legitimate Plugins Only (Market)**
Only upload your own plugins or plugins you have the rights to. Do not steal and re-upload others' work in the market section.

📌 **Rule 4 — Leaked Section Rules**
The leaked section is for *educational/archival* purposes. Do not use leaked plugins for commercial gain or claim them as your own.

📌 **Rule 5 — No Malware**
Uploading malicious plugins (RATs, backdoors, etc.) is an **instant permanent ban** and will be reported.

📌 **Rule 6 — Dropper Conduct**
Droppers must maintain quality. Spam uploads, fake plugins, or low-effort submissions will result in role removal.

📌 **Rule 7 — Follow Discord ToS**
Always follow [Discord's Terms of Service](https://discord.com/terms) and [Community Guidelines](https://discord.com/guidelines).

📌 **Rule 8 — Staff Decisions are Final**
If you disagree with a staff decision, open a ticket — do not argue publicly.

*By being in this server, you agree to follow these rules.*
"""

DISCLAIMER_TEXT = """
⚠️ **LEGAL DISCLAIMER — LEAKED PLUGINS** ⚠️

This section contains plugins that may be premium/paid software obtained outside of official channels.

By accessing this section, you acknowledge:
• You will **not** use leaked plugins for commercial purposes.
• You will **not** redistribute or claim authorship of leaked plugins.
• This content is provided for **educational/archival** purposes only.
• The server staff are **not responsible** for any misuse.
• If you are the original developer and want a plugin removed, contact an admin.

*Accessing this section constitutes your agreement to the above.*
"""


class SetupCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="setup", description="⚙️ [ADMIN] Wipe and rebuild the entire server structure.")
    @is_admin()
    async def setup(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        confirm_embed = discord.Embed(
            title="⚠️ Confirm Server Setup",
            description=(
                "This will:\n"
                "• **Delete ALL** existing channels and roles\n"
                "• **Create** the full Plugin Marketplace structure\n"
                "• Send welcome embeds to the new channels\n\n"
                "**This action is irreversible. Continue?**"
            ),
            color=COLORS['red'],
        )
        view = ConfirmSetupView(interaction)
        msg = await interaction.followup.send(embed=confirm_embed, view=view, ephemeral=True)
        view.message = msg

    async def run_setup(self, interaction: discord.Interaction):
        guild = interaction.guild

        # ── 1. Send progress message ──────────────────────────────────────────
        progress = await interaction.followup.send("⚙️ **Setting up server…** (0%)", ephemeral=True)

        async def update(text: str):
            try:
                await progress.edit(content=text)
            except Exception:
                pass

        # ── 2. Delete channels ────────────────────────────────────────────────
        await update("🗑️ Deleting channels… (10%)")
        for ch in list(guild.channels):
            try:
                await ch.delete(reason="Server setup")
                await asyncio.sleep(0.3)
            except Exception as exc:
                logger.warning(f"Could not delete channel {ch.name}: {exc}")

        # ── 3. Delete roles (skip @everyone and bot's own role) ───────────────
        await update("🗑️ Deleting roles… (25%)")
        bot_role = guild.me.top_role
        for role in list(guild.roles):
            if role.is_default() or role == bot_role or role.managed:
                continue
            try:
                await role.delete(reason="Server setup")
                await asyncio.sleep(0.3)
            except Exception as exc:
                logger.warning(f"Could not delete role {role.name}: {exc}")

        # ── 4. Create roles ───────────────────────────────────────────────────
        await update("🎭 Creating roles… (40%)")
        created_roles: dict[str, discord.Role] = {}

        # Create all roles first (they all appear at position 1 initially)
        for role_def in ROLES:  # top→bottom order: Owner first, Buyer last
            try:
                r = await guild.create_role(
                    name=role_def['name'],
                    color=discord.Color(role_def['color']),
                    hoist=role_def.get('hoist', False),
                    mentionable=role_def.get('mentionable', False),
                    permissions=role_def['permissions'],
                    reason="Server setup",
                )
                created_roles[role_def['name']] = r
                await asyncio.sleep(0.4)
            except Exception as exc:
                logger.error(f"Could not create role {role_def['name']}: {exc}")

        # ── 5. Fix role hierarchy positions ───────────────────────────────────
        # ROLES list is defined top→bottom (Owner=index 0).
        # Discord position: higher int = higher in list = more power.
        # @everyone is always 0. Bot's own managed role must stay above all.
        await update("📊 Ordering role hierarchy… (48%)")
        try:
            # Build position map: Owner gets the highest slot, Buyer gets slot 1
            total = len(ROLES)
            position_map: dict[discord.Role, int] = {}
            for idx, role_def in enumerate(ROLES):
                role = created_roles.get(role_def['name'])
                if role:
                    # ROLES[0] = Owner → position (total), ROLES[-1] = Buyer → position 1
                    position_map[role] = total - idx
            await guild.edit_role_positions(positions=position_map, reason="Setup hierarchy")
            await asyncio.sleep(0.5)
        except Exception as exc:
            logger.warning(f"Could not set role positions (may need higher bot role): {exc}")

        # ── 5b. Assign bot role ───────────────────────────────────────────────
        if '🤖 Bot' in created_roles:
            try:
                await guild.me.add_roles(created_roles['🤖 Bot'], reason="Setup")
            except Exception:
                pass

        # ── 6. Create channels ────────────────────────────────────────────────
        await update("📺 Creating channels… (60%)")
        created_channels: dict[str, discord.abc.GuildChannel] = {}
        current_category: discord.CategoryChannel | None = None

        def build_overwrites(overwrite_def: dict) -> dict[discord.Role | discord.Member, discord.PermissionOverwrite]:
            result = {}
            for role_name, perm in overwrite_def.items():
                if role_name == '@everyone':
                    result[guild.default_role] = perm
                elif role_name in created_roles:
                    result[created_roles[role_name]] = perm
            return result

        for item in CHANNEL_STRUCTURE:
            overwrites = build_overwrites(item.get('overwrites', {}))
            try:
                if item['type'] == 'category':
                    cat = await guild.create_category(
                        name=item['name'],
                        overwrites=overwrites,
                        reason="Server setup",
                    )
                    created_channels[item['key']] = cat
                    current_category = cat
                else:
                    kwargs = dict(
                        name=item['name'],
                        category=current_category,
                        reason="Server setup",
                    )
                    if overwrites:
                        kwargs['overwrites'] = overwrites
                    if 'topic' in item:
                        kwargs['topic'] = item['topic']
                    ch = await guild.create_text_channel(**kwargs)
                    created_channels[item['key']] = ch
                await asyncio.sleep(0.4)
            except Exception as exc:
                logger.error(f"Could not create channel {item['name']}: {exc}")

        # ── 7. Save channel IDs to config ─────────────────────────────────────
        await update("💾 Saving config… (80%)")
        for key, ch in created_channels.items():
            await self.bot.db.set_config(key, str(ch.id))

        log_ch = created_channels.get('ch_log')
        if log_ch:
            await self.bot.db.set_config('log_channel', str(log_ch.id))

        # ── 8. Post welcome embeds ────────────────────────────────────────────
        await update("✍️ Sending welcome messages… (90%)")
        await self._post_welcome_messages(guild, created_channels, created_roles)

        # ── 9. Done ───────────────────────────────────────────────────────────
        await update("✅ **Server setup complete!** (100%)")
        logger.info(f"Server setup complete for guild {guild.id}")

    # ── Helper to post embeds ──────────────────────────────────────────────────

    async def _post_welcome_messages(
        self,
        guild: discord.Guild,
        channels: dict,
        roles: dict,
    ):
        # Rules
        if ch := channels.get('ch_rules'):
            embed = discord.Embed(title="📜 Server Rules", description=RULES_TEXT, color=COLORS['blue'])
            embed.set_footer(text="Plugin Marketplace • Stay safe, stay fair.")
            await ch.send(embed=embed)

        # Welcome
        if ch := channels.get('ch_welcome'):
            embed = discord.Embed(
                title="👋 Welcome to the Minecraft Plugin Marketplace!",
                description=(
                    "The #1 place to find, share, and discuss Minecraft plugins.\n\n"
                    "**Getting Started:**\n"
                    f"• Browse plugins with `/browse`\n"
                    f"• Search for plugins with `/search <name>`\n"
                    f"• Rate plugins with `/rate <plugin_id>`\n"
                    f"• Want to upload? Ask an Admin for the **💧 Dropper** role!\n\n"
                    f"**Role Guide:**\n"
                    f"{''.join(f'> {r} — {d}' + chr(10) for r, d in [(n, desc) for n, desc in [('💧 Dropper', 'Can upload plugins'), ('💎 Verified Seller', 'Trusted plugin author'), ('🔓 Leaked Access', 'Access to the leaked section'), ('🛒 Buyer', 'Download and review plugins')]])}"
                ),
                color=COLORS['green'],
            )
            embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
            await ch.send(embed=embed)

        # Disclaimer in leaked section
        if ch := channels.get('ch_disclaimer'):
            embed = discord.Embed(title="⚠️ Disclaimer", description=DISCLAIMER_TEXT, color=COLORS['orange'])
            await ch.send(embed=embed)

        # Bot status
        if ch := channels.get('ch_bot_status'):
            embed = discord.Embed(
                title="🤖 Bot Online",
                description=(
                    f"**Plugin Marketplace Bot** v{self.bot.version} is online!\n\n"
                    "**Commands:**\n"
                    "`/browse` — Browse all plugins\n"
                    "`/search` — Search plugins\n"
                    "`/upload` — Upload a plugin (Droppers only)\n"
                    "`/leak` — Submit a leaked plugin\n"
                    "`/rate` — Rate a plugin\n"
                    "`/top` — Top downloaded plugins\n"
                    "`/plugin` — View plugin details\n"
                    "`/approve` — Approve a plugin (Admin)\n"
                    "`/reject` — Reject a plugin (Admin)\n"
                    "`/give-dropper` — Award dropper role (Admin)\n"
                ),
                color=COLORS['green'],
            )
            await ch.send(embed=embed)

        # Top plugins placeholder
        if ch := channels.get('ch_top'):
            embed = discord.Embed(
                title="🏆 Top Plugins",
                description="*The leaderboard will be updated as plugins are downloaded.*\n\nUse `/top` to see the current leaderboard.",
                color=COLORS['gold'],
            )
            await ch.send(embed=embed)


class ConfirmSetupView(discord.ui.View):
    def __init__(self, interaction: discord.Interaction):
        super().__init__(timeout=60)
        self.interaction = interaction
        self.message = None

    @discord.ui.button(label="✅ Yes, wipe everything", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, _):
        if interaction.user.id != self.interaction.user.id:
            await interaction.response.send_message("❌ Not your button.", ephemeral=True)
            return
        await interaction.response.defer()
        self.stop()
        cog: SetupCog = interaction.client.cogs.get('SetupCog')
        if cog:
            await cog.run_setup(interaction)

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.grey)
    async def cancel(self, interaction: discord.Interaction, _):
        await interaction.response.edit_message(content="❌ Setup cancelled.", embed=None, view=None)
        self.stop()

    async def on_timeout(self):
        try:
            await self.message.edit(content="⏳ Confirmation timed out.", embed=None, view=None)
        except Exception:
            pass


async def setup(bot):
    await bot.add_cog(SetupCog(bot))
