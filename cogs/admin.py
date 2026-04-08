"""
Admin cog — role management, takedowns, reports, moderation tools.

Plugins no longer need approval — they auto-post to #dropped-plugins the
moment a dropper submits them. Admins can still force-delete any drop.
"""

import discord
from discord.ext import commands
from discord import app_commands
import logging
from config import COLORS
from utils.checks import is_admin, is_moderator
from utils.embeds import success_embed, error_embed, info_embed, plugin_embed, log_embed
from utils.checks import get_role_by_name

logger = logging.getLogger('PluginMarket.Admin')

    # ── /give-dropper ─────────────────────────────────────────────────────────

    @app_commands.command(name="give-dropper", description="💧 [ADMIN] Give a user the Dropper role.")
    @app_commands.describe(member="Member to promote")
    @is_moderator()
    async def give_dropper(self, interaction: discord.Interaction, member: discord.Member):
        await interaction.response.defer(ephemeral=True)
        role = get_role_by_name(interaction.guild, '💧 Dropper')
        if not role:
            await interaction.followup.send(embed=error_embed("Role Not Found", "Run /setup first."), ephemeral=True)
            return

        if role in member.roles:
            await interaction.followup.send(embed=error_embed("Already Dropper", f"{member.mention} already has the Dropper role."), ephemeral=True)
            return

        await member.add_roles(role, reason=f"Promoted by {interaction.user}")
        await self.bot.db.add_dropper(member.id, interaction.guild_id)

        # DM user
        try:
            await member.send(embed=success_embed(
                "You're now a Dropper! 💧",
                "You can now upload plugins to the marketplace using `/upload`.\n"
                "You also have access to the Dropper Zone and can submit leaked plugins.\n\n"
                "*Keep it clean — spam or malicious uploads will get your role removed.*"
            ))
        except Exception:
            pass

        await interaction.followup.send(
            embed=success_embed("Role Granted", f"{member.mention} is now a **💧 Dropper**!"), ephemeral=True
        )
        await self.bot.log_action(interaction.guild, log_embed("Dropper Given", "", interaction.user, member, COLORS['cyan']))

    # ── /revoke-dropper ───────────────────────────────────────────────────────

    @app_commands.command(name="revoke-dropper", description="🚫 [ADMIN] Revoke the Dropper role from a user.")
    @app_commands.describe(member="Member to demote", reason="Reason")
    @is_moderator()
    async def revoke_dropper(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason given"):
        await interaction.response.defer(ephemeral=True)
        role = get_role_by_name(interaction.guild, '💧 Dropper')
        if role and role in member.roles:
            await member.remove_roles(role, reason=f"Revoked by {interaction.user}: {reason}")

        try:
            await member.send(embed=error_embed(
                "Dropper Role Revoked",
                f"Your **💧 Dropper** role has been revoked.\n**Reason:** {reason}"
            ))
        except Exception:
            pass

        await interaction.followup.send(
            embed=success_embed("Role Revoked", f"Dropper role removed from {member.mention}."), ephemeral=True
        )
        await self.bot.log_action(interaction.guild, log_embed("Dropper Revoked", reason, interaction.user, member, COLORS['red']))

    # ── /give-leaked-access ───────────────────────────────────────────────────

    @app_commands.command(name="give-leaked-access", description="🔓 [ADMIN] Give a user access to leaked plugins.")
    @app_commands.describe(member="Member to grant access")
    @is_moderator()
    async def give_leaked_access(self, interaction: discord.Interaction, member: discord.Member):
        await interaction.response.defer(ephemeral=True)
        role = get_role_by_name(interaction.guild, '🔓 Leaked Access')
        if not role:
            await interaction.followup.send(embed=error_embed("Role Not Found", "Run /setup first."), ephemeral=True)
            return
        await member.add_roles(role, reason=f"Granted by {interaction.user}")
        try:
            await member.send(embed=success_embed(
                "Leaked Access Granted! 🔓",
                "You now have access to the **🔓 Leaked Plugins** section.\n"
                "Remember to read the disclaimer and use this access responsibly."
            ))
        except Exception:
            pass
        await interaction.followup.send(
            embed=success_embed("Access Granted", f"{member.mention} now has **🔓 Leaked Access**."), ephemeral=True
        )
        await self.bot.log_action(interaction.guild, log_embed("Leaked Access Given", "", interaction.user, member, COLORS['pink']))

    # ── /revoke-leaked-access ─────────────────────────────────────────────────

    @app_commands.command(name="revoke-leaked-access", description="🚫 [ADMIN] Revoke leaked access from a user.")
    @is_moderator()
    async def revoke_leaked_access(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason given"):
        await interaction.response.defer(ephemeral=True)
        role = get_role_by_name(interaction.guild, '🔓 Leaked Access')
        if role and role in member.roles:
            await member.remove_roles(role, reason=reason)
        await interaction.followup.send(
            embed=success_embed("Access Revoked", f"Leaked access removed from {member.mention}."), ephemeral=True
        )
        await self.bot.log_action(interaction.guild, log_embed("Leaked Access Revoked", reason, interaction.user, member, COLORS['red']))

    # ── /give-verified-seller ─────────────────────────────────────────────────

    @app_commands.command(name="give-verified-seller", description="💎 [ADMIN] Grant Verified Seller status.")
    @is_admin()
    async def give_verified_seller(self, interaction: discord.Interaction, member: discord.Member):
        await interaction.response.defer(ephemeral=True)
        role = get_role_by_name(interaction.guild, '💎 Verified Seller')
        if not role:
            await interaction.followup.send(embed=error_embed("Role Not Found", "Run /setup first."), ephemeral=True)
            return
        await member.add_roles(role, reason=f"Verified by {interaction.user}")
        await self.bot.db.execute("UPDATE droppers SET verified=1 WHERE user_id=?", (member.id,))
        try:
            await member.send(embed=success_embed(
                "Verified Seller Status! 💎",
                "Congratulations! You've been verified as a **💎 Verified Seller**.\n"
                "Your plugins get a verified badge and priority placement in the marketplace."
            ))
        except Exception:
            pass
        await interaction.followup.send(
            embed=success_embed("Verified", f"{member.mention} is now a **💎 Verified Seller**!"), ephemeral=True
        )

    # ── /reports ──────────────────────────────────────────────────────────────

    @app_commands.command(name="reports", description="🚩 [ADMIN] View unresolved plugin reports.")
    @is_moderator()
    async def reports(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        rows = await self.bot.db.fetchall(
            "SELECT pr.*, p.name as plugin_name FROM plugin_reports pr "
            "JOIN plugins p ON pr.plugin_id = p.id WHERE pr.resolved=0 ORDER BY pr.created_at DESC LIMIT 20"
        )
        embed = discord.Embed(title="🚩 Plugin Reports", color=COLORS['red'])
        if not rows:
            embed.description = "No unresolved reports. Great!"
        else:
            for r in rows:
                reporter = interaction.guild.get_member(r['reporter_id'])
                embed.add_field(
                    name=f"[Report #{r['id']}] {r['plugin_name']} (Plugin #{r['plugin_id']})",
                    value=(
                        f"> **Reporter:** {reporter.mention if reporter else r['reporter_id']}\n"
                        f"> **Reason:** {r['reason']}\n"
                        f"> Use `/resolve-report {r['id']}` to close"
                    ),
                    inline=False,
                )
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ── /resolve-report ───────────────────────────────────────────────────────

    @app_commands.command(name="resolve-report", description="✅ [ADMIN] Mark a plugin report as resolved.")
    @app_commands.describe(report_id="Report ID")
    @is_moderator()
    async def resolve_report(self, interaction: discord.Interaction, report_id: int):
        await interaction.response.defer(ephemeral=True)
        await self.bot.db.execute("UPDATE plugin_reports SET resolved=1 WHERE id=?", (report_id,))
        await interaction.followup.send(embed=success_embed("Resolved", f"Report #{report_id} resolved."), ephemeral=True)

    # ── /force-delete-plugin ──────────────────────────────────────────────────

    @app_commands.command(name="force-delete-plugin", description="🗑️ [ADMIN] Force delete any plugin.")
    @app_commands.describe(plugin_id="Plugin ID to delete", reason="Reason for deletion")
    @is_moderator()
    async def force_delete(self, interaction: discord.Interaction, plugin_id: int, reason: str = "Violates rules"):
        await interaction.response.defer(ephemeral=True)
        plugin = await self.bot.db.get_plugin(plugin_id)
        if not plugin:
            await interaction.followup.send(embed=error_embed("Not Found", "Plugin not found."), ephemeral=True)
            return

        # Notify author
        try:
            author = self.bot.get_user(plugin['author_id'])
            if author:
                await author.send(embed=error_embed(
                    "Plugin Removed by Staff",
                    f"Your plugin **{plugin['name']}** was removed by staff.\n**Reason:** {reason}"
                ))
        except Exception:
            pass

        await self.bot.db.execute("DELETE FROM plugins WHERE id=?", (plugin_id,))
        await interaction.followup.send(
            embed=success_embed("Deleted", f"Plugin **{plugin['name']}** removed. Reason: {reason}"),
            ephemeral=True,
        )
        await self.bot.log_action(
            interaction.guild,
            log_embed("Plugin Force-Deleted", f"{plugin['name']} — {reason}", interaction.user, color=COLORS['red'])
        )

    # ── /announce ─────────────────────────────────────────────────────────────

    @app_commands.command(name="announce", description="📢 [ADMIN] Send an announcement.")
    @app_commands.describe(title="Announcement title", message="Announcement content", ping_everyone="Ping @everyone?")
    @is_admin()
    async def announce(self, interaction: discord.Interaction, title: str, message: str, ping_everyone: bool = False):
        await interaction.response.defer(ephemeral=True)
        ch_id = await self.bot.db.get_config('ch_announcements')
        if not ch_id:
            await interaction.followup.send(embed=error_embed("No Announcement Channel", "Run /setup first."), ephemeral=True)
            return
        ch = interaction.guild.get_channel(int(ch_id))
        if not ch:
            await interaction.followup.send(embed=error_embed("Channel Not Found", "Announcement channel missing."), ephemeral=True)
            return

        embed = discord.Embed(title=f"📢 {title}", description=message, color=COLORS['gold'])
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        embed.set_footer(text="Plugin Marketplace Announcement")
        import datetime
        embed.timestamp = datetime.datetime.utcnow()

        content = "@everyone" if ping_everyone else None
        await ch.send(content=content, embed=embed)
        await interaction.followup.send(embed=success_embed("Announced!", f"Your announcement has been posted to {ch.mention}."), ephemeral=True)

    # ── /plugin-info-admin ────────────────────────────────────────────────────

    @app_commands.command(name="plugin-info-admin", description="🔎 [ADMIN] View full plugin info including pending ones.")
    @app_commands.describe(plugin_id="Plugin ID")
    @is_moderator()
    async def plugin_info_admin(self, interaction: discord.Interaction, plugin_id: int):
        await interaction.response.defer(ephemeral=True)
        plugin = await self.bot.db.get_plugin(plugin_id)
        if not plugin:
            await interaction.followup.send(embed=error_embed("Not Found", f"Plugin #{plugin_id} not found."), ephemeral=True)
            return
        author = interaction.guild.get_member(plugin['author_id'])
        await interaction.followup.send(embed=plugin_embed(plugin, author), ephemeral=True)

    # ── /sync ─────────────────────────────────────────────────────────────────

    @app_commands.command(name="sync", description="🔄 [ADMIN] Force sync slash commands.")
    @is_admin()
    async def sync_commands(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = discord.Object(id=interaction.guild_id)
        self.bot.tree.copy_global_to(guild=guild)
        synced = await self.bot.tree.sync(guild=guild)
        await interaction.followup.send(
            embed=success_embed("Commands Synced", f"Synced **{len(synced)}** slash commands."), ephemeral=True
        )

    # No internal helpers needed — plugins post themselves on drop.


async def setup(bot):
    await bot.add_cog(AdminCog(bot))
