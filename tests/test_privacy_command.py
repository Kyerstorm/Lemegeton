"""Tests for the in-bot privacy notice and compact help disclosure."""

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord

from cogs.utilities.help import HelpCog
from cogs.utilities.privacy import (
    PRIVACY_SECTIONS,
    PrivacyCog,
    PrivacyNavigationView,
    build_privacy_embeds,
)


class PrivacyNoticeTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.embeds = build_privacy_embeds()
        self.notice = "\n".join(
            part
            for embed in self.embeds
            for part in (
                embed.title or "",
                embed.description or "",
                *(field.name + "\n" + field.value for field in embed.fields),
                embed.footer.text or "",
            )
        ).casefold()

    def test_intro_explains_the_private_dropdown_guide_and_e2ee_limit(self):
        intro = self.embeds[0]
        self.assertIn("one private, interactive guide", intro.description.casefold())
        self.assertIn("choose a section from the menu below", intro.description.casefold())
        self.assertIn("not end-to-end encrypted", intro.description.casefold())

    def test_notice_sections_match_dropdown_navigation(self):
        self.assertEqual(len(self.embeds), len(PRIVACY_SECTIONS))
        view = PrivacyNavigationView(SimpleNamespace(id=123), self.embeds)
        self.assertEqual(len(view.children), 1)

        select = view.children[0]
        self.assertIsInstance(select, discord.ui.Select)
        self.assertEqual(len(select.options), len(self.embeds))
        self.assertTrue(select.options[0].default)
        self.assertEqual(
            [option.label for option in select.options],
            [section[0] for section in PRIVACY_SECTIONS],
        )

    async def test_command_sends_one_ephemeral_message_with_navigation(self):
        send_message = AsyncMock()
        followup_send = AsyncMock()
        interaction = SimpleNamespace(
            user=SimpleNamespace(id=123),
            response=SimpleNamespace(send_message=send_message),
            original_response=AsyncMock(return_value=object()),
            followup=SimpleNamespace(send=followup_send),
        )

        await PrivacyCog.privacy.callback(PrivacyCog(None), interaction)

        send_message.assert_awaited_once()
        self.assertTrue(send_message.await_args.kwargs["ephemeral"])
        self.assertIsInstance(send_message.await_args.kwargs["view"], PrivacyNavigationView)
        followup_send.assert_not_awaited()

    def test_notice_explicitly_rejects_an_end_to_end_encryption_claim(self):
        self.assertIn("not end-to-end encrypted", self.notice)
        self.assertIn("encryption in transit", self.notice)
        self.assertNotIn("all data is end-to-end encrypted", self.notice)

    def test_notice_explains_mit_and_lawful_data_requests(self):
        self.assertIn("mit licence governs", self.notice)
        self.assertIn("does not make a hosted database public", self.notice)
        self.assertIn("valid, binding legal request", self.notice)
        self.assertIn("automatic access", self.notice)
        self.assertIn("open-source project", self.notice)
        self.assertIn("https://github.com/Kyerstorm/Lemegeton".casefold(), self.notice)

    def test_notice_names_current_intents_and_message_processing(self):
        self.assertIn("message content", self.notice)
        self.assertIn("members", self.notice)
        self.assertIn("explicitly mentioned", self.notice)

    def test_notice_discloses_material_logging_and_content_categories(self):
        for value in (
            "display names",
            "guild ids/names",
            "channel, message and interaction ids",
            "steam profile lookup value",
            "not the submitted message text",
            "feedback text",
            "public thread",
            "conversation text",
        ):
            with self.subTest(value=value):
                self.assertIn(value, self.notice)

    def test_embed_limits_are_respected(self):
        self.assertLessEqual(len(self.embeds), 10)
        for embed in self.embeds:
            total = len(embed.title or "") + len(embed.description or "") + len(embed.footer.text or "")
            for field in embed.fields:
                self.assertLessEqual(len(field.name), 256)
                self.assertLessEqual(len(field.value), 1024)
                total += len(field.name) + len(field.value)
            self.assertLessEqual(total, 6000)

    async def test_help_overview_contains_compact_privacy_disclosure(self):
        help_instance = SimpleNamespace(
            bot=SimpleNamespace(user=None),
            repository_stats=None,
        )
        embed = await HelpCog._create_overview_embed(
            help_instance,
            interaction=None,
            categories={},
        )
        fields = {field.name: field.value for field in embed.fields}
        self.assertIn("🔒 Privacy at a glance", fields)
        self.assertIn("/privacy", fields["🔒 Privacy at a glance"])
        self.assertIn("not end-to-end encrypted", fields["🔒 Privacy at a glance"].casefold())
        self.assertIn("GitHub Repository", next(field.value for field in embed.fields if field.name == "🔗 Useful Links"))
        self.assertIn("open source", next(field.value for field in embed.fields if field.name == "🔗 Useful Links").casefold())


if __name__ == "__main__":
    unittest.main()
