import discord
from typing import Callable, Awaitable


class PluginPaginator(discord.ui.View):
    """Interactive paginator for plugin listings."""

    def __init__(
        self,
        fetch_fn: Callable[[int], Awaitable[tuple[list, int]]],  # (page) → (items, total_pages)
        embed_fn: Callable[[list, int, int], discord.Embed],      # (items, page, total) → Embed
        interaction: discord.Interaction,
        timeout: int = 120,
    ):
        super().__init__(timeout=timeout)
        self.fetch_fn   = fetch_fn
        self.embed_fn   = embed_fn
        self.interaction = interaction
        self.page        = 1
        self.total_pages = 1
        self._update_buttons()

    def _update_buttons(self):
        self.first_btn.disabled    = self.page == 1
        self.prev_btn.disabled     = self.page == 1
        self.next_btn.disabled     = self.page >= self.total_pages
        self.last_btn.disabled     = self.page >= self.total_pages
        self.page_label.label      = f"{self.page} / {self.total_pages}"

    async def _go_to(self, interaction: discord.Interaction, page: int):
        self.page = page
        items, self.total_pages = await self.fetch_fn(page)
        self._update_buttons()
        embed = self.embed_fn(items, self.page, self.total_pages)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="⏮", style=discord.ButtonStyle.grey, custom_id="first")
    async def first_btn(self, interaction: discord.Interaction, _):
        await self._go_to(interaction, 1)

    @discord.ui.button(label="◀", style=discord.ButtonStyle.blurple, custom_id="prev")
    async def prev_btn(self, interaction: discord.Interaction, _):
        await self._go_to(interaction, self.page - 1)

    @discord.ui.button(label="1 / 1", style=discord.ButtonStyle.grey, custom_id="page_label", disabled=True)
    async def page_label(self, interaction: discord.Interaction, _):
        pass

    @discord.ui.button(label="▶", style=discord.ButtonStyle.blurple, custom_id="next")
    async def next_btn(self, interaction: discord.Interaction, _):
        await self._go_to(interaction, self.page + 1)

    @discord.ui.button(label="⏭", style=discord.ButtonStyle.grey, custom_id="last")
    async def last_btn(self, interaction: discord.Interaction, _):
        await self._go_to(interaction, self.total_pages)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.interaction.user.id:
            await interaction.response.send_message("❌ This menu belongs to someone else.", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        try:
            await self.interaction.edit_original_response(view=self)
        except Exception:
            pass


class PluginActionView(discord.ui.View):
    """Buttons attached to a single plugin embed: Download, Rate, Report."""

    def __init__(self, plugin_id: int, file_url: str, file_name: str, bot, timeout: int = 180):
        super().__init__(timeout=timeout)
        self.plugin_id = plugin_id
        self.bot       = bot
        # Add direct download link button
        self.add_item(discord.ui.Button(
            label=f"📥 Download {file_name}",
            url=file_url,
            style=discord.ButtonStyle.link,
        ))

    @discord.ui.button(label="⭐ Rate", style=discord.ButtonStyle.green, custom_id="rate_plugin")
    async def rate_btn(self, interaction: discord.Interaction, _):
        await interaction.response.send_modal(RatePluginModal(self.plugin_id, self.bot))

    @discord.ui.button(label="🚩 Report", style=discord.ButtonStyle.red, custom_id="report_plugin")
    async def report_btn(self, interaction: discord.Interaction, _):
        await interaction.response.send_modal(ReportPluginModal(self.plugin_id, self.bot))


class RatePluginModal(discord.ui.Modal, title="⭐ Rate This Plugin"):
    rating = discord.ui.TextInput(
        label="Rating (1–5 stars)",
        placeholder="Enter a number from 1 to 5",
        min_length=1,
        max_length=1,
    )
    review = discord.ui.TextInput(
        label="Review (optional)",
        placeholder="Share your thoughts about this plugin...",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=500,
    )

    def __init__(self, plugin_id: int, bot):
        super().__init__()
        self.plugin_id = plugin_id
        self.bot       = bot

    async def on_submit(self, interaction: discord.Interaction):
        try:
            rating = int(self.rating.value)
            assert 1 <= rating <= 5
        except (ValueError, AssertionError):
            await interaction.response.send_message("❌ Rating must be a number from 1 to 5.", ephemeral=True)
            return

        added = await self.bot.db.add_rating(self.plugin_id, interaction.user.id, rating, self.review.value or None)
        if not added:
            await interaction.response.send_message("❌ You have already rated this plugin.", ephemeral=True)
        else:
            stars = "⭐" * rating
            await interaction.response.send_message(
                f"✅ Thanks! Your **{stars}** rating has been recorded.", ephemeral=True
            )


class ReportPluginModal(discord.ui.Modal, title="🚩 Report Plugin"):
    reason = discord.ui.TextInput(
        label="Reason for reporting",
        placeholder="Describe why you're reporting this plugin...",
        style=discord.TextStyle.paragraph,
        max_length=500,
    )

    def __init__(self, plugin_id: int, bot):
        super().__init__()
        self.plugin_id = plugin_id
        self.bot       = bot

    async def on_submit(self, interaction: discord.Interaction):
        await self.bot.db.execute(
            "INSERT INTO plugin_reports (plugin_id, reporter_id, reason) VALUES (?,?,?)",
            (self.plugin_id, interaction.user.id, self.reason.value),
        )
        await interaction.response.send_message("✅ Report submitted. Staff will review it shortly.", ephemeral=True)


class ApproveRejectView(discord.ui.View):
    """Quick approve/reject buttons on the pending-review channel."""

    def __init__(self, plugin_id: int, bot):
        super().__init__(timeout=None)
        self.plugin_id = plugin_id
        self.bot       = bot

    @discord.ui.button(label="✅ Approve", style=discord.ButtonStyle.green, custom_id="approve_quick")
    async def approve(self, interaction: discord.Interaction, _):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("❌ No permission.", ephemeral=True)
            return
        await self.bot.db.approve_plugin(self.plugin_id)
        await interaction.response.send_message(f"✅ Plugin `{self.plugin_id}` approved!", ephemeral=True)
        self.stop()

    @discord.ui.button(label="❌ Reject", style=discord.ButtonStyle.red, custom_id="reject_quick")
    async def reject(self, interaction: discord.Interaction, _):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("❌ No permission.", ephemeral=True)
            return
        await interaction.response.send_modal(QuickRejectModal(self.plugin_id, self.bot))

    @discord.ui.button(label="👁 View Details", style=discord.ButtonStyle.blurple, custom_id="view_plugin")
    async def view(self, interaction: discord.Interaction, _):
        plugin = await self.bot.db.get_plugin(self.plugin_id)
        if not plugin:
            await interaction.response.send_message("Plugin not found.", ephemeral=True)
            return
        from utils.embeds import plugin_embed
        await interaction.response.send_message(embed=plugin_embed(plugin), ephemeral=True)


class QuickRejectModal(discord.ui.Modal, title="❌ Reject Plugin"):
    reason = discord.ui.TextInput(
        label="Rejection reason",
        placeholder="Why is this plugin being rejected?",
        style=discord.TextStyle.paragraph,
        max_length=300,
    )

    def __init__(self, plugin_id: int, bot):
        super().__init__()
        self.plugin_id = plugin_id
        self.bot       = bot

    async def on_submit(self, interaction: discord.Interaction):
        await self.bot.db.reject_plugin(self.plugin_id, self.reason.value)
        # Notify author
        plugin = await self.bot.db.get_plugin(self.plugin_id)
        if plugin:
            try:
                user = interaction.client.get_user(plugin['author_id'])
                if user:
                    from utils.embeds import error_embed
                    await user.send(embed=error_embed(
                        "Plugin Rejected",
                        f"Your plugin **{plugin['name']}** was rejected.\n**Reason:** {self.reason.value}",
                    ))
            except Exception:
                pass
        await interaction.response.send_message(f"❌ Plugin `{self.plugin_id}` rejected.", ephemeral=True)
