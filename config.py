"""
Server structure definition for the Minecraft Plugin Marketplace.
Edit the colours, names, and channel list to your liking.
"""

import discord

# ── Colour palette ────────────────────────────────────────────────────────────
COLORS = {
    'gold':    0xFFD700,
    'red':     0xFF4136,
    'orange':  0xFF6B35,
    'blue':    0x4169E1,
    'green':   0x00C851,
    'cyan':    0x00BCD4,
    'pink':    0xFF69B4,
    'purple':  0x9B59B6,
    'silver':  0x95A5A6,
    'white':   0xFFFFFF,
    'dark':    0x2C2F33,
    'blurple': 0x5865F2,
}

# ── Role definitions (top→bottom = highest→lowest) ───────────────────────────
ROLES = [
    {
        'name':        '👑 Owner',
        'color':       COLORS['gold'],
        'hoist':       True,
        'mentionable': True,
        'permissions': discord.Permissions(administrator=True),
    },
    {
        'name':        '⚡ Admin',
        'color':       COLORS['red'],
        'hoist':       True,
        'mentionable': True,
        'permissions': discord.Permissions(administrator=True),
    },
    {
        'name':        '🛡️ Moderator',
        'color':       COLORS['blue'],
        'hoist':       True,
        'mentionable': True,
        'permissions': discord.Permissions(
            kick_members=True, ban_members=True,
            manage_messages=True, moderate_members=True,
            view_channel=True, send_messages=True,
            embed_links=True, read_message_history=True,
            manage_channels=False,
        ),
    },
    {
        'name':        '💎 Verified Seller',
        'color':       COLORS['green'],
        'hoist':       True,
        'mentionable': False,
        'permissions': discord.Permissions(
            view_channel=True, send_messages=True,
            embed_links=True, attach_files=True,
            read_message_history=True, use_application_commands=True,
        ),
    },
    {
        'name':        '💧 Dropper',
        'color':       COLORS['cyan'],
        'hoist':       True,
        'mentionable': False,
        'permissions': discord.Permissions(
            view_channel=True, send_messages=True,
            embed_links=True, attach_files=True,
            read_message_history=True, use_application_commands=True,
        ),
    },
    {
        'name':        '🔓 Leaked Access',
        'color':       COLORS['pink'],
        'hoist':       False,
        'mentionable': False,
        'permissions': discord.Permissions(
            view_channel=True, send_messages=True,
            embed_links=True, read_message_history=True,
            use_application_commands=True,
        ),
    },
    {
        'name':        '🛒 Buyer',
        'color':       COLORS['silver'],
        'hoist':       False,
        'mentionable': False,
        'permissions': discord.Permissions(
            view_channel=True, send_messages=True,
            embed_links=True, read_message_history=True,
            use_application_commands=True,
        ),
    },
    {
        'name':        '🤖 Bot',
        'color':       COLORS['blurple'],
        'hoist':       False,
        'mentionable': False,
        'permissions': discord.Permissions(administrator=True),
    },
]

# ── Channel / Category structure ─────────────────────────────────────────────
# Each entry is either a CATEGORY or a CHANNEL inside the preceding category.
# 'overwrites' is a dict: role_name → PermissionOverwrite
CHANNEL_STRUCTURE = [
    # ── INFO ──────────────────────────────────────────────────────────────────
    {
        'type':     'category',
        'name':     '📢 INFO',
        'key':      'cat_info',
        'overwrites': {
            '@everyone': discord.PermissionOverwrite(view_channel=True, send_messages=False),
        },
    },
    {
        'type':    'text',
        'name':    '📜│rules',
        'key':     'ch_rules',
        'topic':   'Server rules and guidelines. Read before participating.',
        'overwrites': {
            '@everyone': discord.PermissionOverwrite(view_channel=True, send_messages=False),
        },
    },
    {
        'type':    'text',
        'name':    '📢│announcements',
        'key':     'ch_announcements',
        'topic':   'Important announcements from the staff team.',
        'overwrites': {
            '@everyone': discord.PermissionOverwrite(view_channel=True, send_messages=False),
        },
    },
    {
        'type':    'text',
        'name':    '👋│welcome',
        'key':     'ch_welcome',
        'topic':   'Welcome to the Minecraft Plugin Marketplace!',
        'overwrites': {
            '@everyone': discord.PermissionOverwrite(view_channel=True, send_messages=False),
        },
    },
    {
        'type':    'text',
        'name':    '🤖│bot-status',
        'key':     'ch_bot_status',
        'topic':   'Bot status and uptime information.',
        'overwrites': {
            '@everyone': discord.PermissionOverwrite(view_channel=True, send_messages=False),
        },
    },

    # ── MARKETPLACE ───────────────────────────────────────────────────────────
    {
        'type':     'category',
        'name':     '🛒 MARKETPLACE',
        'key':      'cat_market',
    },
    {
        'type':    'text',
        'name':    '🧩│dropped-plugins',
        'key':     'ch_dropped',
        'topic':   'Every plugin dropped by our droppers — file is attached to each post. Use /search or /browse to filter.',
        'overwrites': {
            # Everyone can read; ONLY the bot can post (no human messages)
            '@everyone':          discord.PermissionOverwrite(view_channel=True, send_messages=False, add_reactions=True),
            '💧 Dropper':         discord.PermissionOverwrite(view_channel=True, send_messages=False),
            '💎 Verified Seller': discord.PermissionOverwrite(view_channel=True, send_messages=False),
            '🛡️ Moderator':       discord.PermissionOverwrite(view_channel=True, send_messages=False),
            '⚡ Admin':           discord.PermissionOverwrite(view_channel=True, send_messages=True),
            '👑 Owner':           discord.PermissionOverwrite(view_channel=True, send_messages=True),
        },
    },
    {
        'type':    'text',
        'name':    '🔍│plugin-search',
        'key':     'ch_search',
        'topic':   'Use /search <query> or /browse to find plugins by category.',
    },
    {
        'type':    'text',
        'name':    '⭐│reviews',
        'key':     'ch_reviews',
        'topic':   'Plugin reviews and ratings. Use /rate <plugin_id>.',
    },
    {
        'type':    'text',
        'name':    '🏆│top-plugins',
        'key':     'ch_top',
        'topic':   'Leaderboard of the most downloaded plugins.',
        'overwrites': {
            '@everyone': discord.PermissionOverwrite(view_channel=True, send_messages=False),
        },
    },

    # ── DROPPERS ──────────────────────────────────────────────────────────────
    {
        'type':     'category',
        'name':     '💧 DROPPERS ZONE',
        'key':      'cat_droppers',
        'overwrites': {
            '@everyone':         discord.PermissionOverwrite(view_channel=False),
            '💧 Dropper':        discord.PermissionOverwrite(view_channel=True),
            '💎 Verified Seller': discord.PermissionOverwrite(view_channel=True),
            '🛡️ Moderator':      discord.PermissionOverwrite(view_channel=True),
            '⚡ Admin':          discord.PermissionOverwrite(view_channel=True),
            '👑 Owner':          discord.PermissionOverwrite(view_channel=True),
        },
    },
    {
        'type':    'text',
        'name':    '💧│drop-commands',
        'key':     'ch_drop',
        'topic':   'Run /upload here to drop your plugin. It will auto-post to #dropped-plugins instantly.',
        'overwrites': {
            '@everyone':          discord.PermissionOverwrite(view_channel=False),
            '💧 Dropper':         discord.PermissionOverwrite(view_channel=True, send_messages=True, use_application_commands=True),
            '💎 Verified Seller': discord.PermissionOverwrite(view_channel=True, send_messages=True, use_application_commands=True),
            '🛡️ Moderator':       discord.PermissionOverwrite(view_channel=True, send_messages=True),
            '⚡ Admin':           discord.PermissionOverwrite(view_channel=True, send_messages=True),
        },
    },
    {
        'type':    'text',
        'name':    '📋│drop-log',
        'key':     'ch_drop_log',
        'topic':   'Staff log of all plugin drops — name, dropper, timestamp.',
        'overwrites': {
            '@everyone':    discord.PermissionOverwrite(view_channel=False),
            '🛡️ Moderator': discord.PermissionOverwrite(view_channel=True, send_messages=False),
            '⚡ Admin':     discord.PermissionOverwrite(view_channel=True, send_messages=True),
            '👑 Owner':     discord.PermissionOverwrite(view_channel=True, send_messages=True),
        },
    },
    {
        'type':    'text',
        'name':    '💬│dropper-lounge',
        'key':     'ch_dropper_lounge',
        'topic':   'Chat for verified droppers.',
        'overwrites': {
            '@everyone':         discord.PermissionOverwrite(view_channel=False),
            '💧 Dropper':        discord.PermissionOverwrite(view_channel=True, send_messages=True),
            '💎 Verified Seller': discord.PermissionOverwrite(view_channel=True, send_messages=True),
            '🛡️ Moderator':      discord.PermissionOverwrite(view_channel=True),
        },
    },

    # ── LEAKED ────────────────────────────────────────────────────────────────
    {
        'type':     'category',
        'name':     '🔓 LEAKED PLUGINS',
        'key':      'cat_leaked',
        'overwrites': {
            '@everyone':      discord.PermissionOverwrite(view_channel=False),
            '🔓 Leaked Access': discord.PermissionOverwrite(view_channel=True),
            '💧 Dropper':     discord.PermissionOverwrite(view_channel=True),
            '💎 Verified Seller': discord.PermissionOverwrite(view_channel=True),
            '🛡️ Moderator':   discord.PermissionOverwrite(view_channel=True),
            '⚡ Admin':       discord.PermissionOverwrite(view_channel=True),
            '👑 Owner':       discord.PermissionOverwrite(view_channel=True),
        },
    },
    {
        'type':    'text',
        'name':    '🔓│leaked-plugins',
        'key':     'ch_leaked',
        'topic':   'Leaked premium plugins. Use /leak to submit a plugin.',
        'overwrites': {
            '@everyone':         discord.PermissionOverwrite(view_channel=False),
            '🔓 Leaked Access':  discord.PermissionOverwrite(view_channel=True, send_messages=False),
            '💧 Dropper':        discord.PermissionOverwrite(view_channel=True, send_messages=True, attach_files=True),
            '💎 Verified Seller': discord.PermissionOverwrite(view_channel=True, send_messages=True, attach_files=True),
            '🛡️ Moderator':      discord.PermissionOverwrite(view_channel=True, send_messages=True),
            '⚡ Admin':          discord.PermissionOverwrite(view_channel=True, send_messages=True),
        },
    },
    {
        'type':    'text',
        'name':    '📩│leak-requests',
        'key':     'ch_leak_requests',
        'topic':   'Request a plugin to be leaked. Use /request-leak.',
    },
    {
        'type':    'text',
        'name':    '⚠️│disclaimer',
        'key':     'ch_disclaimer',
        'topic':   'Legal disclaimer for leaked content.',
        'overwrites': {
            '@everyone':      discord.PermissionOverwrite(view_channel=False),
            '🔓 Leaked Access': discord.PermissionOverwrite(view_channel=True, send_messages=False),
        },
    },

    # ── COMMUNITY ─────────────────────────────────────────────────────────────
    {
        'type':     'category',
        'name':     '💬 COMMUNITY',
        'key':      'cat_community',
    },
    {
        'type':    'text',
        'name':    '💬│general',
        'key':     'ch_general',
        'topic':   'General discussion about Minecraft plugins.',
    },
    {
        'type':    'text',
        'name':    '🆘│plugin-support',
        'key':     'ch_support',
        'topic':   'Ask for help with Minecraft plugins.',
    },
    {
        'type':    'text',
        'name':    '🐛│bug-reports',
        'key':     'ch_bugs',
        'topic':   'Report bugs in plugins listed on this server.',
    },
    {
        'type':    'text',
        'name':    '💡│suggestions',
        'key':     'ch_suggestions',
        'topic':   'Suggest new features or improvements.',
    },
    {
        'type':    'text',
        'name':    '🎭│off-topic',
        'key':     'ch_offtopic',
        'topic':   'Talk about anything off-topic here.',
    },

    # ── ADMIN ─────────────────────────────────────────────────────────────────
    {
        'type':     'category',
        'name':     '🔧 STAFF',
        'key':      'cat_staff',
        'overwrites': {
            '@everyone':    discord.PermissionOverwrite(view_channel=False),
            '🛡️ Moderator': discord.PermissionOverwrite(view_channel=True),
            '⚡ Admin':     discord.PermissionOverwrite(view_channel=True),
            '👑 Owner':     discord.PermissionOverwrite(view_channel=True),
        },
    },
    {
        'type':    'text',
        'name':    '💬│staff-chat',
        'key':     'ch_staff_chat',
        'topic':   'Private staff communication.',
        'overwrites': {
            '@everyone':    discord.PermissionOverwrite(view_channel=False),
            '🛡️ Moderator': discord.PermissionOverwrite(view_channel=True, send_messages=True),
            '⚡ Admin':     discord.PermissionOverwrite(view_channel=True, send_messages=True),
            '👑 Owner':     discord.PermissionOverwrite(view_channel=True, send_messages=True),
        },
    },
    {
        'type':    'text',
        'name':    '📋│audit-log',
        'key':     'ch_log',
        'topic':   'Bot audit log — all moderation actions are recorded here.',
        'overwrites': {
            '@everyone':    discord.PermissionOverwrite(view_channel=False),
            '🛡️ Moderator': discord.PermissionOverwrite(view_channel=True, send_messages=False),
            '⚡ Admin':     discord.PermissionOverwrite(view_channel=True, send_messages=False),
            '👑 Owner':     discord.PermissionOverwrite(view_channel=True, send_messages=True),
        },
    },
    {
        'type':    'text',
        'name':    '🤖│bot-commands',
        'key':     'ch_bot_cmd',
        'topic':   'Admin bot commands.',
        'overwrites': {
            '@everyone':    discord.PermissionOverwrite(view_channel=False),
            '⚡ Admin':     discord.PermissionOverwrite(view_channel=True, send_messages=True),
            '👑 Owner':     discord.PermissionOverwrite(view_channel=True, send_messages=True),
        },
    },
]

# ── Plugin categories ─────────────────────────────────────────────────────────
PLUGIN_CATEGORIES = [
    'Utility',
    'Economy',
    'PvP',
    'Mini-Games',
    'WorldEdit',
    'Administration',
    'Fun',
    'Chat',
    'Permissions',
    'Anti-Cheat',
    'Misc',
]

PLUGIN_TYPES = ['Spigot', 'Paper', 'Fabric', 'Forge', 'BungeeCord', 'Velocity', 'Sponge', 'Other']

MC_VERSIONS = ['1.8', '1.12', '1.16', '1.17', '1.18', '1.19', '1.20', '1.20.4', '1.21', 'All']

STAR_EMOJIS = {1: '⭐', 2: '⭐⭐', 3: '⭐⭐⭐', 4: '⭐⭐⭐⭐', 5: '⭐⭐⭐⭐⭐'}
