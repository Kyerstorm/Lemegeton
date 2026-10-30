"""Regression tests for PostgreSQL transport and /say content retention."""

import ssl
import unittest
from unittest.mock import AsyncMock, patch

import database
from cogs.utilities.say import Say


class PostgreSQLTransportSecurityTests(unittest.TestCase):
    def test_remote_database_uses_tls_by_default(self):
        self.assertTrue(
            database._should_use_postgres_ssl(
                "postgres.example.test", None, "development"
            )
        )

    def test_loopback_database_keeps_local_development_simple(self):
        for host in ("localhost", "127.0.0.1", "::1"):
            with self.subTest(host=host):
                self.assertFalse(
                    database._should_use_postgres_ssl(host, None, "development")
                )

    def test_production_cannot_disable_tls(self):
        with self.assertRaisesRegex(RuntimeError, "cannot be disabled"):
            database._should_use_postgres_ssl(
                "postgres.example.test", "false", "production"
            )

    def test_remote_database_cannot_disable_tls_outside_production(self):
        with self.assertRaisesRegex(RuntimeError, "only be disabled for loopback"):
            database._should_use_postgres_ssl(
                "postgres.example.test", "false", "development"
            )

    def test_invalid_tls_setting_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "POSTGRES_SSL"):
            database._should_use_postgres_ssl(
                "postgres.example.test", "sometimes", "development"
            )

    def test_tls_uses_certificate_and_hostname_verification(self):
        with (
            patch.object(database, "POSTGRES_SSL", True),
            patch.object(database, "POSTGRES_SSL_CA_FILE", None),
            patch.object(database, "POSTGRES_DSN", None),
        ):
            options = database._postgres_connect_kwargs()

        context = options["ssl"]
        self.assertIsInstance(context, ssl.SSLContext)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)


class SayCommandRetentionTests(unittest.IsolatedAsyncioTestCase):
    async def test_say_audit_does_not_store_message_content(self):
        with patch(
            "cogs.utilities.say.execute_db_operation",
            new_callable=AsyncMock,
        ) as execute:
            await Say(None).log_say_command(
                user_id=101,
                guild_id=202,
                channel_id=303,
                is_embed=True,
                reply_to_message_id=404,
            )

        query = execute.await_args.args[1]
        values = execute.await_args.args[2]
        self.assertNotIn("message_content", query)
        self.assertEqual(values[:5], (101, 202, 303, 1, 404))
        self.assertIsInstance(values[5], str)

    async def test_initialization_scrubs_existing_say_message_content(self):
        with patch.object(
            database, "execute_db_operation", new_callable=AsyncMock
        ) as execute:
            await database.init_say_command_logs_table()

        statements = [call.args[1] for call in execute.await_args_list]
        self.assertTrue(
            any(
                "ALTER TABLE say_command_logs ALTER COLUMN message_content DROP NOT NULL"
                in statement
                for statement in statements
            )
        )
        self.assertTrue(
            any(
                "UPDATE say_command_logs SET message_content = NULL WHERE message_content IS NOT NULL"
                in statement
                for statement in statements
            )
        )


if __name__ == "__main__":
    unittest.main()
