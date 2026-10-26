"""Regression tests for command error classification, replies, and safe logging."""
import logging
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import discord
from discord import app_commands
from discord.ext import commands

from helpers import command_error_handler as error_handler


def _callback():
    """Representative command callback used to test source-module exclusions."""


def _callback_for_module(module_name):
    def callback():
        return None
    callback.__module__ = module_name
    return callback


class FakeInteraction:
    def __init__(self, *, command_name="example", responded=False, callback_module=None):
        callback = _callback_for_module(callback_module) if callback_module else _callback
        self.command = SimpleNamespace(name=command_name, qualified_name=command_name, callback=callback)
        self.user = SimpleNamespace(id=101)
        self.guild = SimpleNamespace(id=202)
        self.guild_id = 202
        self.channel = SimpleNamespace(id=303)
        self.channel_id = 303
        self.id = 404
        self.response = SimpleNamespace(
            is_done=Mock(return_value=responded),
            send_message=AsyncMock(),
        )
        self.followup = SimpleNamespace(send=AsyncMock())


class FakeContext:
    def __init__(self, *, command_name="legacy-example"):
        self.command = SimpleNamespace(name=command_name, qualified_name=command_name, callback=_callback)
        self.author = SimpleNamespace(id=101)
        self.guild = SimpleNamespace(id=202)
        self.guild_id = 202
        self.channel = SimpleNamespace(id=303)
        self.channel_id = 303
        self.message = SimpleNamespace(id=505)
        self.send = AsyncMock()


class WrappedCommandError(Exception):
    def __init__(self, original):
        super().__init__("wrapper message")
        self.original = original


class ErrorMessageClassificationTests(unittest.IsolatedAsyncioTestCase):
    def test_unexpected_application_errors_include_the_complete_feedback_process(self):
        message = error_handler.application_error_message(RuntimeError("internal secret"))
        self.assertIn("/feedback", message)
        self.assertIn("Bugs", message)
        self.assertIn("what happened", message)
        self.assertIn("media URL", message)
        self.assertIn("screenshot", message)
        self.assertNotIn("internal secret", message)

    def test_application_check_failure_is_explained_without_claiming_a_bug(self):
        message = error_handler.application_error_message(app_commands.CheckFailure())
        self.assertIn("current context", message)
        self.assertNotIn("Choose **Bugs**", message)

    def test_application_missing_permissions_are_explained(self):
        error = app_commands.MissingPermissions(["manage_guild"])
        message = error_handler.application_error_message(error)
        self.assertIn("missing permissions", message)
        self.assertIn("permissions", message)

    def test_prefix_permission_error_is_explained(self):
        error = commands.MissingPermissions(["manage_guild"])
        message = error_handler.prefix_error_message(error)
        self.assertIn("missing permissions", message)

    def test_prefix_invalid_arguments_are_not_reported_as_a_bot_bug(self):
        async def sample_command(ctx, required):
            return None

        command = commands.Command(sample_command)
        parameter = command.params["required"]
        message = error_handler.prefix_error_message(commands.MissingRequiredArgument(parameter))
        self.assertIn("arguments", message)
        self.assertNotIn("Choose **Bugs**", message)

    def test_prefix_unknown_command_is_ignored(self):
        self.assertIsNone(error_handler.prefix_error_message(commands.CommandNotFound("typo")))

    def test_wrapped_exceptions_are_unwrapped_for_safe_classification(self):
        error = WrappedCommandError(app_commands.CheckFailure())
        self.assertIn("current context", error_handler.application_error_message(error))


class ErrorContextTests(unittest.IsolatedAsyncioTestCase):
    def test_log_context_has_identifiers_but_no_message_content(self):
        interaction = FakeInteraction()
        context = error_handler._make_context(interaction, "test")
        self.assertEqual(context.command, "example")
        self.assertEqual(context.user_id, 101)
        self.assertEqual(context.guild_id, 202)
        self.assertEqual(context.channel_id, 303)
        self.assertEqual(context.interaction_id, 404)
        self.assertNotIn("content", context.as_log_fields())

    def test_feedback_and_anilist_modules_are_excluded(self):
        for module in error_handler.EXCLUDED_COG_MODULES:
            with self.subTest(module=module):
                interaction = FakeInteraction(callback_module=module)
                self.assertTrue(error_handler.is_excluded_command(interaction))

    def test_regular_command_module_is_not_excluded(self):
        self.assertFalse(error_handler.is_excluded_command(FakeInteraction()))


class ApplicationCommandErrorHandlingTests(unittest.IsolatedAsyncioTestCase):
    async def test_initial_reply_is_private_and_contains_reporting_steps(self):
        interaction = FakeInteraction()
        await error_handler.handle_application_command_error(interaction, RuntimeError("secret"))
        interaction.response.send_message.assert_awaited_once()
        args, kwargs = interaction.response.send_message.await_args
        self.assertIn("/feedback", args[0])
        self.assertTrue(kwargs["ephemeral"])
        self.assertNotIn("secret", args[0])
        interaction.followup.send.assert_not_awaited()

    async def test_deferred_interaction_uses_followup(self):
        interaction = FakeInteraction(responded=True)
        await error_handler.handle_application_command_error(interaction, RuntimeError("secret"))
        interaction.response.send_message.assert_not_awaited()
        interaction.followup.send.assert_awaited_once()
        self.assertTrue(interaction.followup.send.await_args.kwargs["ephemeral"])

    async def test_excluded_cog_is_logged_without_generic_response(self):
        interaction = FakeInteraction(callback_module="cogs.social.feedback")
        await error_handler.handle_application_command_error(interaction, RuntimeError("failure"))
        interaction.response.send_message.assert_not_awaited()
        interaction.followup.send.assert_not_awaited()

    async def test_logging_contains_ids_and_exception_metadata(self):
        interaction = FakeInteraction()
        with self.assertLogs(error_handler.logger, level=logging.ERROR) as captured:
            await error_handler.handle_application_command_error(interaction, RuntimeError("private exception"))
        joined = "\n".join(captured.output)
        self.assertIn("command=example", joined)
        self.assertIn("user_id=101", joined)
        self.assertIn("guild_id=202", joined)
        self.assertIn("RuntimeError", joined)


class PrefixCommandErrorHandlingTests(unittest.IsolatedAsyncioTestCase):
    async def test_unexpected_failure_sends_feedback_guidance_without_pings(self):
        context = FakeContext()
        await error_handler.handle_prefix_command_error(context, RuntimeError("secret"))
        context.send.assert_awaited_once()
        args, kwargs = context.send.await_args
        self.assertIn("/feedback", args[0])
        self.assertIn("Bugs", args[0])
        self.assertFalse(kwargs["allowed_mentions"].everyone)
        self.assertEqual(kwargs["allowed_mentions"].users, False)

    async def test_unknown_prefix_command_does_not_send_a_response(self):
        context = FakeContext()
        await error_handler.handle_prefix_command_error(context, commands.CommandNotFound("typo"))
        context.send.assert_not_awaited()


class ComponentErrorHandlingTests(unittest.IsolatedAsyncioTestCase):
    async def test_component_failure_uses_private_feedback_guidance(self):
        interaction = FakeInteraction(responded=True)
        await error_handler.handle_component_error(
            interaction, RuntimeError("button failure"), component="button", source=FakeContext()
        )
        interaction.response.send_message.assert_not_awaited()
        interaction.followup.send.assert_awaited_once()
        message = interaction.followup.send.await_args.args[0]
        self.assertIn("/feedback", message)
        self.assertIn("Bugs", message)


    async def test_feedback_aware_view_handles_button_callback_failures(self):
        interaction = FakeInteraction(responded=True)
        view = error_handler.FeedbackAwareView()
        item = SimpleNamespace(label="Refresh", custom_id="refresh")
        try:
            await view.on_error(interaction, RuntimeError("private callback detail"), item)
        finally:
            view.stop()

        interaction.followup.send.assert_awaited_once()
        message = interaction.followup.send.await_args.args[0]
        self.assertIn("/feedback", message)
        self.assertNotIn("private callback detail", message)


    async def test_feedback_aware_modal_handles_submission_failures(self):
        interaction = FakeInteraction(responded=True)
        modal = error_handler.FeedbackAwareModal(title="Test modal")
        await modal.on_error(interaction, RuntimeError("private modal detail"))

        interaction.followup.send.assert_awaited_once()
        message = interaction.followup.send.await_args.args[0]
        self.assertIn("/feedback", message)
        self.assertNotIn("private modal detail", message)

    async def test_modal_failure_respects_excluded_source_module(self):
        interaction = FakeInteraction()
        source = SimpleNamespace(callback=_callback_for_module("cogs.social.feedback"))
        await error_handler.handle_modal_error(interaction, RuntimeError("modal failure"), source=source)
        interaction.response.send_message.assert_not_awaited()
        interaction.followup.send.assert_not_awaited()
