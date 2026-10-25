"""Offline tests for feedback form shape, validation, upload handling, and failures."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from cogs.social import feedback as feedback_module


class FakeUser:
    def __init__(self, user_id=123, name="Test User"):
        self.id = user_id
        self.display_name = name
        self.display_avatar = SimpleNamespace(url="https://cdn.example/avatar.png")

    def __str__(self):
        return self.display_name


class FakeUpload:
    def __init__(self, filename="image.png", content_type="image/png", data=b"image-data", size=None):
        self.filename = filename
        self.content_type = content_type
        self.data = data
        self.size = len(data) if size is None else size
        self.read_calls = 0

    async def read(self):
        self.read_calls += 1
        return self.data


class FakeTextChannel:
    def __init__(self, message_id=9001):
        self.send = AsyncMock(return_value=SimpleNamespace(id=message_id))


class FakeBot:
    def __init__(self, channel=None):
        self.channel = channel
        self.get_channel = lambda _channel_id: self.channel
        self.fetch_channel = AsyncMock(return_value=self.channel)


def make_interaction(user=None, filesize_limit=8 * 1024 * 1024):
    return SimpleNamespace(
        user=user or FakeUser(),
        filesize_limit=filesize_limit,
        response=SimpleNamespace(
            send_message=AsyncMock(),
            defer=AsyncMock(),
            is_done=lambda: False,
        ),
        followup=SimpleNamespace(send=AsyncMock()),
    )


class FeedbackModalContractTests(unittest.TestCase):
    def test_modal_stays_within_discord_five_component_limit(self):
        modal = feedback_module.FeedbackModal(feedback_module.Feedback(FakeBot()))
        self.assertEqual(len(modal.children), 5)

    def test_feedback_view_has_stable_persistent_button_ids(self):
        bot = FakeBot()
        view = feedback_module.FeedbackView(bot, FakeUser())
        ids = {item.custom_id for item in view.children}
        self.assertIn("feedback_open_thread", ids)

        close_view = feedback_module.CloseThreadView(bot, None, None)
        self.assertIn("feedback_close_thread", {item.custom_id for item in close_view.children})
        confirm_view = feedback_module.ConfirmCloseView(bot, None, None, None)
        self.assertEqual(
            {item.custom_id for item in confirm_view.children},
            {"feedback_confirm_yes", "feedback_confirm_no"},
        )


class FeedbackSubmissionTests(unittest.IsolatedAsyncioTestCase):
    async def test_invalid_category_and_empty_description_are_rejected_before_io(self):
        bot = FakeBot()
        cog = feedback_module.Feedback(bot)

        invalid = make_interaction()
        await cog._submit_feedback(invalid, category="other", description="Please help")
        invalid.response.send_message.assert_awaited_once()
        self.assertIn("Ideas or Bugs", invalid.response.send_message.await_args.args[0])
        invalid.response.defer.assert_not_awaited()

        empty = make_interaction()
        await cog._submit_feedback(empty, category="ideas", description="  ")
        empty.response.send_message.assert_awaited_once()
        self.assertIn("description", empty.response.send_message.await_args.args[0].lower())
        empty.response.defer.assert_not_awaited()

    async def test_missing_feedback_channel_returns_simple_system_failure(self):
        cog = feedback_module.Feedback(FakeBot(channel=None))
        interaction = make_interaction()
        with patch.object(feedback_module.database, "execute_db_operation", new=AsyncMock()):
            await cog._submit_feedback(interaction, category="bug", description="Bug report")

        interaction.response.defer.assert_awaited_once()
        interaction.followup.send.assert_awaited_once_with(
            "The feedback system isn't working right now.",
            ephemeral=True,
        )

    async def test_success_splits_long_text_and_attaches_multiple_images(self):
        channel = FakeTextChannel()
        user = FakeUser(456, "Vireon")
        bot = FakeBot(channel=channel)
        cog = feedback_module.Feedback(bot)
        interaction = make_interaction(user=user)
        images = [
            FakeUpload("first.png", "image/png", b"first"),
            FakeUpload("second.webp", "image/webp", b"second"),
        ]

        with (
            patch.object(feedback_module.discord, "TextChannel", FakeTextChannel),
            patch.object(feedback_module.database, "execute_db_operation", new=AsyncMock()) as db_operation,
        ):
            await cog._submit_feedback(
                interaction,
                category=" BUG ",
                description=("Long report line. " * 500),
                images=images,
            )

        channel.send.assert_awaited_once()
        payload = channel.send.await_args.kwargs
        embeds = payload["embeds"]
        files = payload["files"]
        self.assertGreaterEqual(len(embeds), 4)
        self.assertLessEqual(len(embeds), 10)
        self.assertEqual(len(files), 2)
        self.assertTrue(all(len(embed.description or "") <= 3800 for embed in embeds))
        self.assertTrue(any("attachment://" in (embed.image.url or "") for embed in embeds))
        self.assertIn(456, cog.pending_users)
        self.assertEqual(cog.message_user_map[9001], 456)
        self.assertIn("Thanks for your feedback", interaction.followup.send.await_args.args[0])
        db_operation.assert_awaited_once()
        for upload_file in files:
            upload_file.close()

    async def test_unsupported_image_is_rejected_without_publishing(self):
        channel = FakeTextChannel()
        cog = feedback_module.Feedback(FakeBot(channel=channel))
        interaction = make_interaction()
        upload = FakeUpload("script.exe", "application/octet-stream", b"not-an-image")

        with (
            patch.object(feedback_module.discord, "TextChannel", FakeTextChannel),
            patch.object(feedback_module.database, "execute_db_operation", new=AsyncMock()),
        ):
            await cog._submit_feedback(interaction, category="ideas", description="Idea", images=[upload])

        channel.send.assert_not_awaited()
        interaction.followup.send.assert_awaited_once()
        self.assertIn("not supported", interaction.followup.send.await_args.args[0])
        self.assertEqual(upload.read_calls, 0)

    async def test_upload_size_and_empty_content_are_rejected(self):
        for upload, limit, expected in (
            (FakeUpload("large.png", data=b"larger than limit"), 4, "upload limit"),
            (FakeUpload("empty.png", data=b""), 100, "empty or could not be read"),
        ):
            with self.subTest(filename=upload.filename):
                channel = FakeTextChannel()
                cog = feedback_module.Feedback(FakeBot(channel=channel))
                interaction = make_interaction(filesize_limit=limit)
                with (
                    patch.object(feedback_module.discord, "TextChannel", FakeTextChannel),
                    patch.object(feedback_module.database, "execute_db_operation", new=AsyncMock()),
                ):
                    await cog._submit_feedback(
                        interaction, category="ideas", description="Idea", images=[upload]
                    )
                channel.send.assert_not_awaited()
                self.assertIn(expected, interaction.followup.send.await_args.args[0])

    async def test_valid_category_aliases_map_to_idea_and_bug_embeds(self):
        for category, title in (("idea", "Idea"), ("ideas", "Idea"), ("bug", "Bug"), ("bugs", "Bug")):
            with self.subTest(category=category):
                channel = FakeTextChannel()
                cog = feedback_module.Feedback(FakeBot(channel=channel))
                interaction = make_interaction()
                with (
                    patch.object(feedback_module.discord, "TextChannel", FakeTextChannel),
                    patch.object(feedback_module.database, "execute_db_operation", new=AsyncMock()),
                ):
                    await cog._submit_feedback(interaction, category=category, description="Details")
                self.assertIn(title, channel.send.await_args.kwargs["embeds"][0].title)


class FeedbackMessageForwardingTests(unittest.IsolatedAsyncioTestCase):
    async def test_prepare_message_data_preserves_embeds_and_converts_attachments(self):
        attachment = SimpleNamespace(to_file=AsyncMock(return_value="converted-file"))
        embed = object()
        message = SimpleNamespace(attachments=[attachment], embeds=[embed])
        files, embeds = await feedback_module.Feedback(FakeBot())._prepare_message_data(message)
        self.assertEqual(files, ["converted-file"])
        self.assertEqual(embeds, [embed])
        attachment.to_file.assert_awaited_once()

    async def test_prepare_message_data_handles_messages_without_media(self):
        files, embeds = await feedback_module.Feedback(FakeBot())._prepare_message_data(
            SimpleNamespace(attachments=[], embeds=[])
        )
        self.assertIsNone(files)
        self.assertIsNone(embeds)


if __name__ == "__main__":
    unittest.main()
