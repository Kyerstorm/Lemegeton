"""Regression tests for first-use policy consent."""
import unittest
from unittest.mock import AsyncMock, patch

from helpers.terms_consent import (
    GUIDELINES_VERSION,
    POLICY_LINKS,
    PRIVACY_VERSION,
    TERMS_VERSION,
    TermsConsentView,
    build_consent_embed,
    user_has_current_consent,
)


class TermsConsentTests(unittest.TestCase):
    def test_agreement_prompt_links_each_published_policy(self):
        embed = build_consent_embed()
        fields = {field.name: field.value for field in embed.fields}
        self.assertEqual(set(fields), {"Terms of Service", "Privacy Policy", "Community Guidelines"})
        for label, url in POLICY_LINKS.items():
            with self.subTest(policy=label):
                self.assertIn(url, fields[label])
                self.assertIn("github.com/Kyerstorm/Lemegeton", fields[label])
        self.assertEqual(embed.color.value, 0x62676D)

    def test_policy_versions_are_explicit_and_nonempty(self):
        self.assertTrue(TERMS_VERSION)
        self.assertTrue(PRIVACY_VERSION)
        self.assertTrue(GUIDELINES_VERSION)

    def test_agreement_view_exposes_accept_and_decline_controls(self):
        view = TermsConsentView(owner_id=123)
        self.assertEqual(
            [item.label for item in view.children],
            ["Agree & Continue", "Decline"],
        )
        self.assertEqual(view.owner_id, 123)


class ConsentLookupTests(unittest.IsolatedAsyncioTestCase):
    async def test_current_policy_versions_are_required_for_access(self):
        with patch(
            "helpers.terms_consent.database.execute_db_operation",
            new=AsyncMock(return_value=(123,)),
        ) as execute:
            self.assertTrue(await user_has_current_consent(123))
        self.assertEqual(execute.await_args.args[2], (
            123, TERMS_VERSION, PRIVACY_VERSION, GUIDELINES_VERSION,
        ))

    async def test_missing_acceptance_blocks_access(self):
        with patch(
            "helpers.terms_consent.database.execute_db_operation",
            new=AsyncMock(return_value=None),
        ):
            self.assertFalse(await user_has_current_consent(456))


if __name__ == "__main__":
    unittest.main()
