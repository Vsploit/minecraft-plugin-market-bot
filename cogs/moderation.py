"""
Moderation cog — warn, kick, ban, mute, user info, warnings history.
"""

import discord
from discord.ext import commands
from discord import app_commands
import logging
from datetime import timedelta
from config import COLORS
from utils.checks import is_moderator, is_admin
from utils.embeds import success_embed, error_embed, info_embed, log_embed

logger = logging.getLogger('PluginMarket.Moderation')


class ModerationCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ── /warn ─────────────────────────────────────────────────────────────────

    @app_commands.command(name="warn", description="⚠️ [MOD] Warn a user.")
    @app_commands.describe(member="Member to warn", reason="Reason for warning")
    @is_moderator()
    async def warn(self, interaction: discord.Interaction, member: discord.Member, reason: str):
        await interaction.response.defer(ephemeral=True)

        if member.bot:
            await interaction.followup.send(embed=error_embed("Can't Warn", "You can't warn a bot."), ephemeral=True)
            return
        if member.guild_permissions.administrator:
            await interaction.followup.send(embed=error_embed("Can't Warn", "You can't warn an admin."), ephemeral=True)
            return

        warn_id = await self.bot.db.add_warning(member.id, interaction.guild_id, interaction.user.id, reason)
        warnings = await self.bot.db.get_warnings(member.id, interaction.guild_id)
        count = len(warnings)

        # DM the user
        try:
            await member.send(embed=discord.Embed(
                title=f"⚠️ Warning from {interaction.guild.name}",
                description=f"**Reason:** {reason}\nYou now have **{count}** warning(s).",
                color=COLORS['orange'],
            ))
        except Exception:
            pass

        await interaction.followup.send(
            embed=success_embed("Warning Issued", f"{member.mention} warned. Total warnings: **{count}**."),
            ephemeral=True,
        )
        await self.bot.log_action(
            interaction.guild,
            log_embed("User Warned", f"Reason: {reason} | Warn #{warn_id} | Total: {count}", interaction.user, member, COLORS['orange'])
        )

    # ── /warnings ─────────────────────────────────────────────────────────────

    @app_commands.command(name="warnings", description="📋 [MOD] View a user's warning history.")
    @app_commands.describe(member="Member to check")
    @is_moderator()
    async def warnings(self, interaction: discord.Interaction, member: discord.Member):
        await interaction.response.defer(ephemeral=True)
        warns = await self.bot.db.get_warnings(member.id, interaction.guild_id)

        embed = discord.Embed(
            title=f"⚠️ Warnings — {member.display_name}",
            description=f"Total warnings: **{len(warns)}**",
            color=COLORS['orange'],
        )
        embed.set_thumbnail(url=member.display_avatar.url)

        for w in warns[:10]:
            mod = interaction.guild.get_member(w['mod_id'])
            embed.add_field(
                name=f"Warn #{w['id']} — {w['created_at'][:10]}",
                value=f"> **Reason:** {w['reason']}\n> **By:** {mod.mention if mod else 'Unknown'}",
                inline=False,
            )

        await interaction.followup.send(embed=embed, ephemeral=True)

    # ── /clear-warnings ───────────────────────────────────────────────────────

    @app_commands.command(name="clear-warnings", description="🧹 [ADMIN] Clear all warnings for a user.")
    @app_commands.describe(member="Member")
    @is_admin()
    async def clear_warnings(self, interaction: discord.Interaction, member: discord.Member):
        await interaction.response.defer(ephemeral=True)
        await self.bot.db.execute(
            "DELETE FROM warnings WHERE user_id=? AND guild_id=?", (member.id, interaction.guild_id)
        )
        await interaction.followup.send(
            embed=success_embed("Warnings Cleared", f"All warnings cleared for {member.mention}."), ephemeral=True
        )

    # ── /kick ─────────────────────────────────────────────────────────────────

    @app_commands.command(name="kick", description="👢 [MOD] Kick a member from the server.")
    @app_commands.describe(member="Member to kick", reason="Reason")
    @is_moderator()
    async def kick(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason given"):
        await interaction.response.defer(ephemeral=True)
        if member.top_role >= interaction.user.top_role:
            await interaction.followup.send(embed=error_embed("Can't Kick", "You can't kick someone with equal or higher role."), ephemeral=True)
            return

        try:
            await member.send(embed=error_embed("Kicked", f"You were kicked from **{interaction.guild.name}**.\n**Reason:** {reason}"))
        except Exception:
            pass

        await member.kick(reason=f"{interaction.user}: {reason}")
        await interaction.followup.send(embed=success_embed("Kicked", f"{member} was kicked.\n**Reason:** {reason}"), ephemeral=True)
        await self.bot.log_action(interaction.guild, log_embed("Member Kicked", reason, interaction.user, member, COLORS['orange']))

    # ── /ban ──────────────────────────────────────────────────────────────────

    @app_commands.command(name="ban", description="🔨 [MOD] Ban a member from the server.")
    @app_commands.describe(member="Member to ban", reason="Reason", delete_days="Days of messages to delete (0-7)")
    @is_moderator()
    async def ban(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason given", delete_days: int = 0):
        await interaction.response.defer(ephemeral=True)
        if member.top_role >= interaction.user.top_role:
            await interaction.followup.send(embed=error_embed("Can't Ban", "You can't ban someone with equal or higher role."), ephemeral=True)
            return

        delete_days = max(0, min(7, delete_days))

        try:
            await member.send(embed=error_embed("Banned", f"You were banned from **{interaction.guild.name}**.\n**Reason:** {reason}"))
        except Exception:
            pass

        await member.ban(reason=f"{interaction.user}: {reason}", delete_message_days=delete_days)
        await interaction.followup.send(embed=success_embed("Banned", f"{member} was banned.\n**Reason:** {reason}"), ephemeral=True)
        await self.bot.log_action(interaction.guild, log_embed("Member Banned", reason, interaction.user, member, COLORS['red']))

    # ── /unban ────────────────────────────────────────────────────────────────

    @app_commands.command(name="unban", description="✅ [MOD] Unban a user by ID.")
    @app_commands.describe(user_id="Discord User ID", reason="Reason for unban")
    @is_moderator()
    async def unban(self, interaction: discord.Interaction, user_id: str, reason: str = "Unbanned"):
        await interaction.response.defer(ephemeral=True)
        try:
            user = await self.bot.fetch_user(int(user_id))
            await interaction.guild.unban(user, reason=reason)
            await interaction.followup.send(embed=success_embed("Unbanned", f"{user} (`{user_id}`) was unbanned."), ephemeral=True)
            await self.bot.log_action(interaction.guild, log_embed("Member Unbanned", reason, interaction.user, user, COLORS['green']))
        except discord.NotFound:
            await interaction.followup.send(embed=error_embed("Not Found", f"User `{user_id}` not found in ban list."), ephemeral=True)
        except ValueError:
            await interaction.followup.send(embed=error_embed("Invalid ID", "Provide a valid Discord User ID."), ephemeral=True)

    # ── /timeout ──────────────────────────────────────────────────────────────

    @app_commands.command(name="timeout", description="🔇 [MOD] Timeout (mute) a member.")
    @app_commands.describe(member="Member to timeout", minutes="Duration in minutes (max 40320 = 28 days)", reason="Reason")
    @is_moderator()
    async def timeout(self, interaction: discord.Interaction, member: discord.Member, minutes: int = 10, reason: str = "No reason given"):
        await interaction.response.defer(ephemeral=True)
        if member.top_role >= interaction.user.top_role:
            await interaction.followup.send(embed=error_embed("Can't Timeout", "Higher/equal role."), ephemeral=True)
            return
        minutes = max(1, min(40320, minutes))
        until   = discord.utils.utcnow() + timedelta(minutes=minutes)
        await member.timeout(until, reason=f"{interaction.user}: {reason}")

        duration_str = f"{minutes}m" if minutes < 60 else f"{minutes // 60}h {minutes % 60}m"
        await interaction.followup.send(
            embed=success_embed("Timeout Applied", f"{member.mention} timed out for **{duration_str}**.\n**Reason:** {reason}"),
            ephemeral=True,
        )
        await self.bot.log_action(interaction.guild, log_embed("Timeout", f"{duration_str} — {reason}", interaction.user, member, COLORS['orange']))

    # ── /untimeout ────────────────────────────────────────────────────────────

    @app_commands.command(name="untimeout", description="🔊 [MOD] Remove timeout from a member.")
    @app_commands.describe(member="Member to un-timeout")
    @is_moderator()
    async def untimeout(self, interaction: discord.Interaction, member: discord.Member):
        await interaction.response.defer(ephemeral=True)
        await member.timeout(None, reason=f"Removed by {interaction.user}")
        await interaction.followup.send(embed=success_embed("Timeout Removed", f"{member.mention}'s timeout has been removed."), ephemeral=True)

    # ── /purge ────────────────────────────────────────────────────────────────

    @app_commands.command(name="purge", description="🧹 [MOD] Bulk delete messages.")
    @app_commands.describe(amount="Number of messages to delete (1-100)", member="Only delete messages from this member")
    @is_moderator()
    async def purge(self, interaction: discord.Interaction, amount: int, member: discord.Member = None):
        await interaction.response.defer(ephemeral=True)
        amount = max(1, min(100, amount))

        def check(msg):
            return member is None or msg.author == member

        deleted = await interaction.channel.purge(limit=amount, check=check)
        await interaction.followup.send(
            embed=success_embed("Purged", f"Deleted **{len(deleted)}** message(s)" +
                                (f" from {member.mention}" if member else "") + "."),
            ephemeral=True,
        )
        await self.bot.log_action(interaction.guild, log_embed("Messages Purged", f"{len(deleted)} msgs in {interaction.channel.mention}", interaction.user, color=COLORS['orange']))

    # ── /userinfo ─────────────────────────────────────────────────────────────

    @app_commands.command(name="userinfo", description="ℹ️ View info about a user.")
    @app_commands.describe(member="Member to look up (defaults to yourself)")
    async def userinfo(self, interaction: discord.Interaction, member: discord.Member = None):
        await interaction.response.defer()
        target = member or interaction.user

        plugins    = await self.bot.db.fetchone("SELECT COUNT(*) as c FROM plugins WHERE author_id=? AND approved=1", (target.id,))
        downloads  = await self.bot.db.fetchone("SELECT SUM(downloads) as d FROM plugins WHERE author_id=? AND approved=1", (target.id,))
        warnings   = await self.bot.db.get_warnings(target.id, interaction.guild_id)
        dropper_row = await self.bot.db.get_dropper(target.id)

        embed = discord.Embed(title=f"ℹ️ {target.display_name}", color=target.color or COLORS['blurple'])
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="Username",   value=str(target),                                      inline=True)
        embed.add_field(name="ID",         value=f"`{target.id}`",                                  inline=True)
        embed.add_field(name="Joined",     value=discord.utils.format_dt(target.joined_at, 'R'),    inline=True)
        embed.add_field(name="Created",    value=discord.utils.format_dt(target.created_at, 'R'),   inline=True)
        embed.add_field(name="Plugins",    value=f"**{plugins['c']}**",                             inline=True)
        embed.add_field(name="Downloads",  value=f"**{(downloads['d'] or 0):,}**",                  inline=True)
        embed.add_field(name="Warnings",   value=f"**{len(warnings)}**",                            inline=True)

        dropper_status = "💎 Verified Seller" if dropper_row and dropper_row['verified'] else \
                         "💧 Dropper" if dropper_row else "🛒 Regular User"
        embed.add_field(name="Dropper Status", value=dropper_status, inline=True)

        role_str = ' '.join(r.mention for r in reversed(target.roles) if r.name != '@everyone')
        if role_str:
            embed.add_field(name=f"Roles ({len(target.roles)-1})", value=role_str[:1000], inline=False)

        await interaction.followup.send(embed=embed)

    # ── /serverinfo ───────────────────────────────────────────────────────────

    @app_commands.command(name="serverinfo", description="🏠 View server information.")
    async def serverinfo(self, interaction: discord.Interaction):
        await interaction.response.defer()
        guild = interaction.guild
        embed = discord.Embed(title=f"🏠 {guild.name}", color=COLORS['blurple'])
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        embed.add_field(name="Owner",      value=f"<@{guild.owner_id}>",             inline=True)
        embed.add_field(name="Members",    value=f"**{guild.member_count:,}**",       inline=True)
        embed.add_field(name="Channels",   value=f"**{len(guild.channels)}**",        inline=True)
        embed.add_field(name="Roles",      value=f"**{len(guild.roles)}**",           inline=True)
        embed.add_field(name="Boost Tier", value=f"**{guild.premium_tier}**",         inline=True)
        embed.add_field(name="Boosts",     value=f"**{guild.premium_subscription_count}**", inline=True)
        embed.add_field(name="Created",    value=discord.utils.format_dt(guild.created_at, 'R'), inline=True)
        await interaction.followup.send(embed=embed)

    # ── /help ─────────────────────────────────────────────────────────────────

    @app_commands.command(name="help", description="❓ View all bot commands.")
    async def help_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        embed = discord.Embed(title="🧩 Plugin Marketplace — Help", color=COLORS['blurple'])
        embed.add_field(name="🛒 Marketplace", value=(
            "`/browse` — Browse plugins\n"
            "`/search` — Search plugins\n"
            "`/plugin` — View plugin details\n"
            "`/top` — Top downloaded plugins\n"
            "`/rate` — Rate a plugin\n"
            "`/reviews` — View plugin reviews\n"
            "`/stats` — Marketplace stats\n"
            "`/my-plugins` — Your uploaded plugins"
        ), inline=False)
        embed.add_field(name="💧 Droppers", value=(
            "`/upload` — Upload a plugin *(Dropper+)*\n"
            "`/leak` — Submit leaked plugin *(Dropper+)*\n"
            "`/update-plugin` — Update your plugin\n"
            "`/delete-plugin` — Delete your plugin\n"
            "`/version-history` — Plugin version history\n"
            "`/dropper-profile` — View dropper profile\n"
            "`/set-bio` — Set your dropper bio"
        ), inline=False)
        embed.add_field(name="🔓 Leaked", value=(
            "`/leaked` — Browse leaked plugins *(Access required)*\n"
            "`/leaked-plugin` — View specific leaked plugin\n"
            "`/request-leak` — Request a plugin to be leaked\n"
            "`/leak-requests` — View all requests\n"
            "`/fulfill-request` — Mark request fulfilled *(Dropper+)*"
        ), inline=False)
        embed.add_field(name="🛡️ Moderation", value=(
            "`/warn` `/warnings` `/clear-warnings`\n"
            "`/kick` `/ban` `/unban`\n"
            "`/timeout` `/untimeout`\n"
            "`/purge` `/userinfo` `/serverinfo`"
        ), inline=False)
        embed.add_field(name="⚡ Admin", value=(
            "`/setup` — Rebuild server\n"
            "`/approve` `/reject` `/pending`\n"
            "`/give-dropper` `/revoke-dropper`\n"
            "`/give-leaked-access` `/revoke-leaked-access`\n"
            "`/give-verified-seller`\n"
            "`/reports` `/resolve-report`\n"
            "`/force-delete-plugin` `/announce`\n"
            "`/sync`"
        ), inline=False)
        embed.set_footer(text=f"Plugin Marketplace v{interaction.client.version}")
        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(ModerationCog(bot))
