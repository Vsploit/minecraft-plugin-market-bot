"""
Plugin Marketplace cog — browse, search, view, rate, download plugins.
"""

import discord
from discord.ext import commands
from discord import app_commands
import logging
import math
from config import COLORS, PLUGIN_CATEGORIES, PLUGIN_TYPES, MC_VERSIONS
from utils.embeds import plugin_embed, plugin_list_embed, success_embed, error_embed, info_embed
from utils.paginator import PluginPaginator, PluginActionView

logger = logging.getLogger('PluginMarket.Marketplace')

PAGE_SIZE = 5


class MarketplaceCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ── /browse ───────────────────────────────────────────────────────────────

    @app_commands.command(name="browse", description="🛒 Browse all approved plugins in the marketplace.")
    @app_commands.describe(category="Filter by category (optional)")
    @app_commands.choices(category=[app_commands.Choice(name=c, value=c) for c in PLUGIN_CATEGORIES])
    async def browse(self, interaction: discord.Interaction, category: str = None):
        await interaction.response.defer()

        async def fetch(page: int):
            items = await self.bot.db.get_plugins(category=category, leaked=False, limit=PAGE_SIZE, offset=(page - 1) * PAGE_SIZE)
            total = await self.bot.db.count_plugins(category=category, leaked=False)
            total_pages = max(1, math.ceil(total / PAGE_SIZE))
            return items, total_pages

        items, total_pages = await fetch(1)
        cat_str = f" — {category}" if category else ""
        embed = plugin_list_embed(items, 1, total_pages, title=f"🛒 Plugin Marketplace{cat_str}")

        view = PluginPaginator(fetch, lambda i, p, t: plugin_list_embed(i, p, t, title=f"🛒 Plugin Marketplace{cat_str}"), interaction)
        view.total_pages = total_pages
        view._update_buttons()

        msg = await interaction.followup.send(embed=embed, view=view)

        # Track listing in the listings channel
        listing_ch_id = await self.bot.db.get_config('ch_listings')
        if listing_ch_id:
            try:
                ch = interaction.guild.get_channel(int(listing_ch_id))
                if ch and ch.id != interaction.channel_id:
                    pass  # Only show in search channel; listing channel is auto-managed
            except Exception:
                pass

    # ── /search ───────────────────────────────────────────────────────────────

    @app_commands.command(name="search", description="🔍 Search plugins by name, description, or tags.")
    @app_commands.describe(query="Search term", category="Filter by category (optional)")
    @app_commands.choices(category=[app_commands.Choice(name=c, value=c) for c in PLUGIN_CATEGORIES])
    async def search(self, interaction: discord.Interaction, query: str, category: str = None):
        await interaction.response.defer()

        async def fetch(page: int):
            items = await self.bot.db.search_plugins(query, category=category, leaked=False, limit=PAGE_SIZE, offset=(page - 1) * PAGE_SIZE)
            # Count
            total_items = await self.bot.db.fetchone(
                "SELECT COUNT(*) as c FROM plugins WHERE approved=1 AND is_leaked=0 "
                "AND (LOWER(name) LIKE ? OR LOWER(description) LIKE ? OR LOWER(tags) LIKE ?)"
                + (" AND LOWER(category)=?" if category else ""),
                (f'%{query.lower()}%', f'%{query.lower()}%', f'%{query.lower()}%') + ((category.lower(),) if category else ()),
            )
            total = total_items['c'] if total_items else 0
            total_pages = max(1, math.ceil(total / PAGE_SIZE))
            return items, total_pages

        items, total_pages = await fetch(1)
        title = f"🔍 Results for \"{query}\""
        if category:
            title += f" in {category}"

        embed = plugin_list_embed(items, 1, total_pages, title=title)
        if not items:
            embed.description = f"No plugins found matching **{query}**."

        view = PluginPaginator(fetch, lambda i, p, t: plugin_list_embed(i, p, t, title=title), interaction)
        view.total_pages = total_pages
        view._update_buttons()
        await interaction.followup.send(embed=embed, view=view)

    # ── /plugin ───────────────────────────────────────────────────────────────

    @app_commands.command(name="plugin", description="🧩 View details and download a specific plugin.")
    @app_commands.describe(plugin_id="The numeric plugin ID")
    async def plugin_info(self, interaction: discord.Interaction, plugin_id: int):
        await interaction.response.defer()
        plugin = await self.bot.db.get_plugin(plugin_id)
        if not plugin or not plugin['approved']:
            await interaction.followup.send(embed=error_embed("Not Found", "Plugin not found."), ephemeral=True)
            return
        if plugin['is_leaked'] and not self._has_leaked_access(interaction.user):
            await interaction.followup.send(embed=error_embed("Access Denied", "You need the 🔓 Leaked Access role."), ephemeral=True)
            return

        author = interaction.guild.get_member(plugin['author_id'])
        embed  = plugin_embed(plugin, author)

        # Download the actual .jar and attach it to the response
        import aiohttp, io
        file_bytes = None
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(plugin['file_url']) as resp:
                    if resp.status == 200:
                        file_bytes = await resp.read()
        except Exception:
            pass

        await self.bot.db.increment_downloads(plugin_id)

        # Include action buttons (Rate / Report) via the view
        view = PluginActionView(plugin['id'], self.bot)

        if file_bytes:
            disc_file = discord.File(
                io.BytesIO(file_bytes),
                filename=plugin['file_name'],
                description=f"{plugin['name']} v{plugin['version']}",
            )
            await interaction.followup.send(
                content=f"📥 **{plugin['name']}** v{plugin['version']} — download the file below:",
                embed=embed, file=disc_file, view=view,
            )
        else:
            await interaction.followup.send(embed=embed, view=view)

    # ── /top ──────────────────────────────────────────────────────────────────

    @app_commands.command(name="top", description="🏆 View the top downloaded plugins.")
    @app_commands.describe(limit="Number of plugins to show (default 10, max 25)")
    async def top(self, interaction: discord.Interaction, limit: int = 10):
        await interaction.response.defer()
        limit = max(1, min(limit, 25))
        plugins = await self.bot.db.fetchall(
            "SELECT * FROM plugins WHERE approved=1 AND is_leaked=0 ORDER BY downloads DESC LIMIT ?",
            (limit,)
        )

        embed = discord.Embed(title="🏆 Top Downloaded Plugins", color=COLORS['gold'])
        for i, p in enumerate(plugins, 1):
            avg = (p['rating_sum'] / p['rating_count']) if p['rating_count'] > 0 else 0
            medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(i, f"**#{i}**")
            price = f"${p['price']:.2f}" if p['price'] > 0 else "Free"
            embed.add_field(
                name=f"{medal} {p['name']} v{p['version']}",
                value=(
                    f"> 📥 {p['downloads']:,} downloads • ⭐ {avg:.1f}/5 • 💰 {price}\n"
                    f"> `{p['category']}` • `{p['plugin_type']}` • ID: `{p['id']}`"
                ),
                inline=False,
            )

        embed.set_footer(text="Plugin Marketplace • Top Charts")
        await interaction.followup.send(embed=embed)

    # ── /rate ─────────────────────────────────────────────────────────────────

    @app_commands.command(name="rate", description="⭐ Rate a plugin (1-5 stars).")
    @app_commands.describe(plugin_id="Plugin ID to rate", rating="Stars (1-5)", review="Optional review text")
    @app_commands.choices(rating=[app_commands.Choice(name=f"{'⭐'*i} ({i})", value=i) for i in range(1, 6)])
    async def rate(self, interaction: discord.Interaction, plugin_id: int, rating: int, review: str = None):
        await interaction.response.defer(ephemeral=True)
        plugin = await self.bot.db.get_plugin(plugin_id)
        if not plugin or not plugin['approved']:
            await interaction.followup.send(embed=error_embed("Not Found", "Plugin not found."), ephemeral=True)
            return

        added = await self.bot.db.add_rating(plugin_id, interaction.user.id, rating, review)
        if not added:
            await interaction.followup.send(embed=error_embed("Already Rated", "You already rated this plugin."), ephemeral=True)
            return

        stars = "⭐" * rating
        await interaction.followup.send(
            embed=success_embed("Rating Submitted", f"You gave **{plugin['name']}** a **{stars}** rating!\n> {review or ''}"),
            ephemeral=True,
        )

        # Post review in reviews channel
        ch_id = await self.bot.db.get_config('ch_reviews')
        if ch_id:
            ch = interaction.guild.get_channel(int(ch_id))
            if ch:
                embed = discord.Embed(
                    title=f"⭐ New Review — {plugin['name']}",
                    description=f"{'⭐' * rating}{'☆' * (5 - rating)}\n\n{review or '*No review text.*'}",
                    color=COLORS['gold'],
                )
                embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
                embed.set_footer(text=f"Plugin ID: {plugin_id}")
                await ch.send(embed=embed)

    # ── /reviews ──────────────────────────────────────────────────────────────

    @app_commands.command(name="reviews", description="💬 View reviews for a plugin.")
    @app_commands.describe(plugin_id="Plugin ID")
    async def reviews(self, interaction: discord.Interaction, plugin_id: int):
        await interaction.response.defer()
        plugin = await self.bot.db.get_plugin(plugin_id)
        if not plugin:
            await interaction.followup.send(embed=error_embed("Not Found", "Plugin not found."), ephemeral=True)
            return

        ratings = await self.bot.db.get_ratings(plugin_id)
        embed = discord.Embed(title=f"💬 Reviews — {plugin['name']}", color=COLORS['blurple'])

        if not ratings:
            embed.description = "No reviews yet. Be the first to rate this plugin with `/rate`!"
        else:
            avg = plugin['rating_sum'] / plugin['rating_count'] if plugin['rating_count'] else 0
            embed.description = f"**Average:** {'⭐' * round(avg)}{'☆' * (5 - round(avg))} ({avg:.1f}/5, {plugin['rating_count']} reviews)\n"
            for r in ratings[:10]:
                stars = '⭐' * r['rating'] + '☆' * (5 - r['rating'])
                user = interaction.guild.get_member(r['user_id'])
                name = user.display_name if user else f"User#{r['user_id']}"
                embed.add_field(
                    name=f"{stars} — {name}",
                    value=r['review'] or '*No text review.*',
                    inline=False,
                )

        await interaction.followup.send(embed=embed)

    # ── /stats ────────────────────────────────────────────────────────────────

    @app_commands.command(name="stats", description="📊 View marketplace statistics.")
    async def stats(self, interaction: discord.Interaction):
        await interaction.response.defer()

        total_plugins   = await self.bot.db.fetchone("SELECT COUNT(*) as c FROM plugins WHERE approved=1 AND is_leaked=0")
        total_leaked    = await self.bot.db.fetchone("SELECT COUNT(*) as c FROM plugins WHERE approved=1 AND is_leaked=1")
        total_pending   = await self.bot.db.fetchone("SELECT COUNT(*) as c FROM plugins WHERE approved=0 AND rejected=0")
        total_downloads = await self.bot.db.fetchone("SELECT SUM(downloads) as d FROM plugins WHERE approved=1")
        total_reviews   = await self.bot.db.fetchone("SELECT COUNT(*) as c FROM ratings")
        total_droppers  = await self.bot.db.fetchone("SELECT COUNT(*) as c FROM droppers")

        embed = discord.Embed(title="📊 Marketplace Statistics", color=COLORS['blurple'])
        embed.add_field(name="🧩 Plugins",      value=f"**{total_plugins['c']:,}**",                              inline=True)
        embed.add_field(name="🔓 Leaked",       value=f"**{total_leaked['c']:,}**",                               inline=True)
        embed.add_field(name="⏳ Pending",      value=f"**{total_pending['c']:,}**",                              inline=True)
        embed.add_field(name="📥 Total DLs",    value=f"**{(total_downloads['d'] or 0):,}**",                     inline=True)
        embed.add_field(name="⭐ Reviews",      value=f"**{total_reviews['c']:,}**",                              inline=True)
        embed.add_field(name="💧 Droppers",     value=f"**{total_droppers['c']:,}**",                             inline=True)
        embed.add_field(name="👥 Members",      value=f"**{interaction.guild.member_count:,}**",                  inline=True)
        embed.set_footer(text="Plugin Marketplace Statistics")
        await interaction.followup.send(embed=embed)

    # ── /myPlugins ────────────────────────────────────────────────────────────

    @app_commands.command(name="my-plugins", description="📦 View your uploaded plugins.")
    async def my_plugins(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        plugins = await self.bot.db.fetchall(
            "SELECT * FROM plugins WHERE author_id=? ORDER BY created_at DESC", (interaction.user.id,)
        )
        if not plugins:
            await interaction.followup.send(embed=info_embed("No Plugins", "You haven't uploaded any plugins yet."), ephemeral=True)
            return

        embed = discord.Embed(title="📦 Your Plugins", color=COLORS['blurple'])
        for p in plugins:
            status = "✅ Approved" if p['approved'] else ("❌ Rejected" if p['rejected'] else "⏳ Pending")
            embed.add_field(
                name=f"[{p['id']}] {p['name']} v{p['version']} — {status}",
                value=f"> 📥 {p['downloads']:,} downloads • {p['category']} • {p['plugin_type']}",
                inline=False,
            )
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ── helpers ───────────────────────────────────────────────────────────────

    def _has_leaked_access(self, member: discord.Member) -> bool:
        role_names = {'🔓 Leaked Access', '💧 Dropper', '💎 Verified Seller', '🛡️ Moderator', '⚡ Admin', '👑 Owner'}
        return member.guild_permissions.administrator or any(r.name in role_names for r in member.roles)


async def setup(bot):
    await bot.add_cog(MarketplaceCog(bot))
