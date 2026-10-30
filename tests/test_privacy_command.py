"""Tests for the in-bot privacy notice and compact help disclosure."""

import unittest
from types import SimpleNamespace

from cogs.utilities.help import HelpCog
from cogs.utilities.privacy import build_privacy_embeds


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

    def test_notice_explicitly_rejects_an_end_to_end_encryption_claim(self):
        self.assertIn("not end-to-end encrypted", self.notice)
        self.assertIn("encryption in transit", self.notice)
        self.assertNotIn("all data is end-to-end encrypted", self.notice)

    def test_notice_explains_mit_and_lawful_data_requests(self):
        self.assertIn("mit licence governs", self.notice)
        self.assertIn("does not make a hosted database public", self.notice)
        self.assertIn("valid, binding legal request", self.notice)
        self.assertIn("automatic access", self.notice)

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


if __name__ == "__main__":
    unittest.main()
