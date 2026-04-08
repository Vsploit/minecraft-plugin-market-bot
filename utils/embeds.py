import discord
from datetime import datetime
from config import COLORS, STAR_EMOJIS


def base_embed(title: str, description: str = "", color: int = COLORS['blurple']) -> discord.Embed:
    embed = discord.Embed(title=title, description=description, color=color)
    embed.timestamp = datetime.utcnow()
    embed.set_footer(text="🧩 Plugin Marketplace")
    return embed


def plugin_embed(plugin, author: discord.Member | None = None) -> discord.Embed:
    """Build a rich embed for a single plugin."""
    avg = (plugin['rating_sum'] / plugin['rating_count']) if plugin['rating_count'] > 0 else 0
    stars = _star_bar(avg)

    badge = "🔓 LEAKED" if plugin['is_leaked'] else "✅ Approved" if plugin['approved'] else "⏳ Pending"
    color = COLORS['pink'] if plugin['is_leaked'] else COLORS['green'] if plugin['approved'] else COLORS['orange']

    embed = discord.Embed(
        title=f"{'🔓 ' if plugin['is_leaked'] else '🧩 '}{plugin['name']} v{plugin['version']}",
        description=plugin['description'],
        color=color,
    )
    embed.add_field(name="📦 Type",      value=plugin['plugin_type'], inline=True)
    embed.add_field(name="🎮 MC",        value=plugin['mc_version'],  inline=True)
    embed.add_field(name="🗂️ Category",  value=plugin['category'],    inline=True)
    embed.add_field(name="⭐ Rating",    value=f"{stars} ({avg:.1f}/5, {plugin['rating_count']} reviews)", inline=False)
    embed.add_field(name="📥 Downloads", value=f"**{plugin['downloads']:,}**", inline=True)
    price_str = f"**${plugin['price']:.2f}**" if plugin['price'] > 0 else "**Free**"
    embed.add_field(name="💰 Price",     value=price_str, inline=True)
    embed.add_field(name="🆔 Plugin ID", value=f"`{plugin['id']}`", inline=True)

    if plugin['tags']:
        tags = ' '.join(f"`{t.strip()}`" for t in plugin['tags'].split(',') if t.strip())
        embed.add_field(name="🏷️ Tags", value=tags, inline=False)

    if plugin['source_url']:
        embed.add_field(name="🔗 Source", value=f"[GitHub/Site]({plugin['source_url']})", inline=True)

    embed.add_field(name="📊 Status", value=badge, inline=True)

    if plugin['image_url']:
        embed.set_thumbnail(url=plugin['image_url'])

    if author:
        embed.set_author(name=author.display_name, icon_url=author.display_avatar.url)

    embed.timestamp = datetime.utcnow()
    embed.set_footer(text=f"Plugin ID: {plugin['id']} • Plugin Marketplace")
    return embed


def plugin_list_embed(plugins: list, page: int, total_pages: int,
                      title: str = "🧩 Plugin Listings", leaked: bool = False) -> discord.Embed:
    color = COLORS['pink'] if leaked else COLORS['blurple']
    embed = discord.Embed(title=title, color=color)

    if not plugins:
        embed.description = "No plugins found."
    else:
        for p in plugins:
            avg = (p['rating_sum'] / p['rating_count']) if p['rating_count'] > 0 else 0
            stars = "⭐" * round(avg) if avg > 0 else "☆☆☆☆☆"
            price = f"${p['price']:.2f}" if p['price'] > 0 else "Free"
            badge = "🔓" if p['is_leaked'] else "🧩"
            embed.add_field(
                name=f"{badge} [{p['id']}] {p['name']} v{p['version']}",
                value=(
                    f"> {p['description'][:80]}{'...' if len(p['description']) > 80 else ''}\n"
                    f"> {stars} • `{p['category']}` • `{p['plugin_type']}` • 📥{p['downloads']:,} • 💰{price}"
                ),
                inline=False,
            )

    embed.set_footer(text=f"Page {page}/{total_pages} • Plugin Marketplace")
    embed.timestamp = datetime.utcnow()
    return embed


def success_embed(title: str, description: str = "") -> discord.Embed:
    return base_embed(f"✅  {title}", description, COLORS['green'])


def error_embed(title: str, description: str = "") -> discord.Embed:
    return base_embed(f"❌  {title}", description, COLORS['red'])


def warning_embed(title: str, description: str = "") -> discord.Embed:
    return base_embed(f"⚠️  {title}", description, COLORS['orange'])


def info_embed(title: str, description: str = "") -> discord.Embed:
    return base_embed(f"ℹ️  {title}", description, COLORS['cyan'])


def pending_embed(plugin, author_name: str = "Unknown") -> discord.Embed:
    embed = discord.Embed(
        title=f"📥 New Plugin Submission — {plugin['name']}",
        description=plugin['description'],
        color=COLORS['orange'],
    )
    embed.add_field(name="Author",    value=f"<@{plugin['author_id']}> ({author_name})", inline=True)
    embed.add_field(name="Version",   value=plugin['version'],     inline=True)
    embed.add_field(name="Type",      value=plugin['plugin_type'], inline=True)
    embed.add_field(name="Category",  value=plugin['category'],    inline=True)
    embed.add_field(name="MC Ver",    value=plugin['mc_version'],  inline=True)
    embed.add_field(name="Price",     value=f"${plugin['price']:.2f}" if plugin['price'] else "Free", inline=True)
    if plugin['tags']:
        embed.add_field(name="Tags",  value=plugin['tags'],        inline=False)
    if plugin['source_url']:
        embed.add_field(name="Source", value=plugin['source_url'], inline=False)
    embed.add_field(name="File",      value=f"[{plugin['file_name']}]({plugin['file_url']})", inline=False)
    embed.add_field(name="Plugin ID", value=f"`{plugin['id']}`",   inline=True)
    embed.set_footer(text="Use /approve <id> or /reject <id> <reason>")
    embed.timestamp = datetime.utcnow()
    return embed


def log_embed(action: str, description: str, mod: discord.Member, target=None, color: int = COLORS['orange']) -> discord.Embed:
    embed = discord.Embed(title=f"📋 {action}", description=description, color=color)
    embed.add_field(name="Moderator", value=mod.mention, inline=True)
    if target:
        embed.add_field(name="Target", value=str(target), inline=True)
    embed.timestamp = datetime.utcnow()
    return embed


def _star_bar(avg: float) -> str:
    full  = int(avg)
    half  = 1 if avg - full >= 0.5 else 0
    empty = 5 - full - half
    return "⭐" * full + "✨" * half + "☆" * empty
