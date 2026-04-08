# 🧩 Minecraft Plugin Marketplace Bot

An advanced Discord bot that sets up a **complete Minecraft plugin marketplace** on your server — with a plugin store, dropper system, leaked plugins section, ratings, and full moderation tools.

---

## ✨ Features

### 🛒 Plugin Marketplace
- Browse, search, and filter plugins by category
- Paginated listings with interactive buttons
- Plugin detail pages with download links, ratings, tags, and version info
- Top charts (most downloaded)
- Plugin version history

### 💧 Dropper System
- Dedicated **Dropper** role for plugin authors
- `/upload` command with modal form (name, desc, version, tags, source URL)
- Category + type selection (Spigot, Paper, Fabric, Forge, BungeeCord, etc.)
- Plugin approval workflow with pending review channel
- Staff gets **Approve/Reject** buttons for each submission
- DM notifications for approval/rejection
- Dropper profiles with bio support
- Plugin update system (creates version history)

### 🔓 Leaked Plugins Section
- Separate **Leaked Access** role + hidden channels
- `/leak` command for droppers to submit leaked plugins
- Leak request system (`/request-leak`, `/fulfill-request`)
- Legal disclaimer channel

### ⭐ Rating System
- Star rating (1–5) with optional written review
- Rate via `/rate` command or in-embed button
- Reviews posted publicly to the reviews channel
- Plugin average rating displayed on all embeds

### 🛡️ Moderation
- Warn / Kick / Ban / Unban / Timeout / Purge
- Warning history per user
- Full moderation audit log
- Plugin reports system

### ⚙️ Server Setup
- `/setup` command **wipes all channels and roles** and rebuilds from scratch
- Creates the full category/channel structure
- Creates all roles with correct permissions
- Posts welcome embeds, rules, disclaimer, and bot status

---

## 📋 Commands

| Command | Access | Description |
|---|---|---|
| `/setup` | Admin | Wipe & rebuild server |
| `/browse` | Everyone | Browse marketplace |
| `/search` | Everyone | Search plugins |
| `/plugin <id>` | Everyone | View plugin details |
| `/top` | Everyone | Top downloaded plugins |
| `/rate <id>` | Everyone | Rate a plugin |
| `/reviews <id>` | Everyone | View plugin reviews |
| `/stats` | Everyone | Marketplace statistics |
| `/my-plugins` | Everyone | Your uploaded plugins |
| `/upload` | Dropper+ | Upload a plugin |
| `/leak` | Dropper+ | Submit a leaked plugin |
| `/update-plugin` | Dropper+ | Update plugin version |
| `/delete-plugin` | Dropper+ | Delete your plugin |
| `/dropper-profile` | Everyone | View dropper profile |
| `/set-bio` | Dropper+ | Set dropper bio |
| `/leaked` | Leaked Access+ | Browse leaked plugins |
| `/request-leak` | Leaked Access+ | Request a leak |
| `/fulfill-request` | Dropper+ | Fulfill a leak request |
| `/approve <id>` | Mod+ | Approve plugin |
| `/reject <id>` | Mod+ | Reject plugin |
| `/pending` | Mod+ | View pending submissions |
| `/give-dropper` | Mod+ | Grant Dropper role |
| `/revoke-dropper` | Mod+ | Revoke Dropper role |
| `/give-leaked-access` | Mod+ | Grant leaked access |
| `/give-verified-seller` | Admin | Grant Verified Seller |
| `/reports` | Mod+ | View plugin reports |
| `/announce` | Admin | Post announcement |
| `/warn` | Mod+ | Warn a user |
| `/kick` | Mod+ | Kick a user |
| `/ban` | Mod+ | Ban a user |
| `/timeout` | Mod+ | Timeout a user |
| `/userinfo` | Everyone | View user info |
| `/help` | Everyone | Show command list |

---

## 🚀 Setup

### 1. Create a Discord Application
1. Go to [discord.com/developers/applications](https://discord.com/developers/applications)
2. Click **New Application** → name it → go to **Bot** tab
3. Click **Add Bot** → copy the **Token**
4. Under **Privileged Gateway Intents**, enable all three intents
5. Under **OAuth2 → URL Generator**: select `bot` + `applications.commands`, give `Administrator` permission
6. Invite the bot to your server using the generated URL

### 2. Configure the Bot
```bash
git clone https://github.com/Vsploit/minecraft-plugin-market-bot
cd minecraft-plugin-market-bot
cp .env.example .env
```

Edit `.env`:
```env
DISCORD_TOKEN=your_token_here
APPLICATION_ID=your_app_id_here
GUILD_ID=your_server_id_here
```

### 3. Install & Run
```bash
pip install -r requirements.txt
python main.py
```

### 4. Set Up Server
Run `/setup` in any channel (requires Administrator). The bot will:
- Delete all existing channels and roles
- Create the full marketplace structure
- Post welcome embeds

---

## 📁 Project Structure

```
minecraft-plugin-market-bot/
├── main.py              # Bot entry point
├── database.py          # Async SQLite database
├── config.py            # Server structure config
├── requirements.txt
├── .env.example
├── cogs/
│   ├── setup.py         # /setup command
│   ├── marketplace.py   # Browse, search, rate
│   ├── droppers.py      # Upload, dropper profiles
│   ├── leaks.py         # Leaked plugins
│   ├── admin.py         # Approve, reject, roles
│   └── moderation.py    # Warn, kick, ban, userinfo
└── utils/
    ├── embeds.py        # Embed builders
    ├── checks.py        # Permission checks
    └── paginator.py     # Page views + modals
```

---

## 🛡️ Role Hierarchy

| Role | Color | Permissions |
|------|-------|-------------|
| 👑 Owner | Gold | Administrator |
| ⚡ Admin | Red | Administrator |
| 🛡️ Moderator | Blue | Kick, Ban, Manage Messages |
| 💎 Verified Seller | Green | Upload plugins (verified) |
| 💧 Dropper | Cyan | Upload plugins, leaked section |
| 🔓 Leaked Access | Pink | View leaked plugins |
| 🛒 Buyer | Silver | Download, rate plugins |
| 🤖 Bot | Blurple | Administrator (bot only) |

---

## ⚠️ Notes

- Plugin files are stored as Discord CDN links (attachments). For permanent storage, consider hosting files externally.
- The `/setup` command **deletes everything** and rebuilds — use it only once during initial setup.
- The leaked section is for educational/archival purposes. You are responsible for your server's content.

---

*Built with [discord.py](https://discordpy.readthedocs.io/) 2.x*
