import discord
from discord import app_commands
from functools import wraps
from typing import Callable


def has_any_role(*role_names: str):
    """Slash-command check: user must have at least one of the named roles."""
    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.user.guild_permissions.administrator:
            return True
        user_roles = {r.name for r in interaction.user.roles}
        if any(rn in user_roles for rn in role_names):
            return True
        await interaction.response.send_message(
            f"❌ You need one of these roles: {', '.join(f'**{r}**' for r in role_names)}",
            ephemeral=True,
        )
        return False
    return app_commands.check(predicate)


def is_admin():
    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.user.guild_permissions.administrator:
            return True
        await interaction.response.send_message("❌ You need **Administrator** permission.", ephemeral=True)
        return False
    return app_commands.check(predicate)


def is_moderator():
    return has_any_role('🛡️ Moderator', '⚡ Admin', '👑 Owner')


def is_dropper():
    return has_any_role('💧 Dropper', '💎 Verified Seller', '🛡️ Moderator', '⚡ Admin', '👑 Owner')


def is_verified_seller():
    return has_any_role('💎 Verified Seller', '⚡ Admin', '👑 Owner')


def has_leaked_access():
    return has_any_role('🔓 Leaked Access', '💧 Dropper', '💎 Verified Seller', '🛡️ Moderator', '⚡ Admin', '👑 Owner')


def get_role_by_name(guild: discord.Guild, name: str) -> discord.Role | None:
    return discord.utils.get(guild.roles, name=name)


def user_has_role(member: discord.Member, *role_names: str) -> bool:
    user_roles = {r.name for r in member.roles}
    return any(rn in user_roles for rn in role_names)
