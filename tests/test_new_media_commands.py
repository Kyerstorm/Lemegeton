"""Focused unit tests for pure logic used by the seven new cogs."""
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from cogs_test.general_commands.airing import filter_schedule
from cogs_test.general_commands.media_night import tally_votes
from cogs_test.general_commands.server_check import collect_checks
from cogs_test.general_commands.server_taste import aggregate_member_interests


class ServerTasteAggregationTests(unittest.TestCase):
    def test_deduplicates_genres_and_filters_spoiler_or_low_rank_tags(self):
        genres, tags = aggregate_member_interests([
            {"media": {"genres": ["Fantasy", "Fantasy"], "tags": [
                {"name": "Magic", "rank": 80, "isMediaSpoiler": False},
                {"name": "Late reveal", "rank": 99, "isMediaSpoiler": True},
                {"name": "Minor trope", "rank": 20, "isMediaSpoiler": False},
            ]}},
            {"media": {"genres": ["Fantasy", "Drama"], "tags": [
                {"name": "Magic", "rank": 75, "isMediaSpoiler": False},
            ]}},
        ])
        self.assertEqual(genres, {"Fantasy", "Drama"})
        self.assertEqual(tags, {"Magic"})

    def test_empty_profile_is_valid_empty_sample(self):
        self.assertEqual(aggregate_member_interests([]), (set(), set()))


class MediaNightVoteTests(unittest.TestCase):
    def test_votes_are_counted_and_invalid_choices_are_ignored(self):
        self.assertEqual(tally_votes({"1": 0, "2": 1, "3": 1, "4": 8, "5": -1}, 3), [1, 2, 0])

    def test_vote_change_uses_latest_choice(self):
        votes = {"123": 0}
        votes["123"] = 2
        self.assertEqual(tally_votes(votes, 3), [0, 0, 1])


class AiringFilterTests(unittest.TestCase):
    def test_filters_bad_and_past_timestamps_and_sorts(self):
        future = datetime.now(timezone.utc) + timedelta(days=40)
        later = int((future + timedelta(days=1)).timestamp())
        earlier = int(future.timestamp())
        entries = [
            {"airingAt": later, "episode": 2, "media": {"season": "FALL", "seasonYear": future.year}},
            {"airingAt": earlier, "episode": 1, "media": {"season": "FALL", "seasonYear": future.year}},
            {"airingAt": 0, "episode": 0, "media": {}},
            {"episode": 9, "media": {}},
        ]
        result = filter_schedule(entries)
        self.assertEqual([entry["airingAt"] for entry in result], [earlier, later])

    def test_season_and_year_filters_are_exact(self):
        timestamp = int((datetime.now(timezone.utc) + timedelta(days=40)).timestamp())
        entries = [
            {"airingAt": timestamp, "media": {"season": "FALL", "seasonYear": 2030}},
            {"airingAt": timestamp + 5, "media": {"season": "SPRING", "seasonYear": 2030}},
        ]
        self.assertEqual(filter_schedule(entries, season="FALL", year=2030), [entries[0]])


class ServerCheckTests(unittest.TestCase):
    def test_reports_missing_current_channel_permissions(self):
        guild_permissions = SimpleNamespace(view_audit_log=False)
        member = SimpleNamespace(guild_permissions=guild_permissions)
        channel = SimpleNamespace(permissions_for=lambda _member: SimpleNamespace(
            view_channel=True,
            send_messages=False,
            embed_links=True,
            read_message_history=True,
        ))
        checks = collect_checks(SimpleNamespace(), channel, member)
        by_name = {name: status for status, name, _ in checks}
        self.assertEqual(by_name["Send messages"], "Needs attention")
        self.assertEqual(by_name["View this channel"], "Healthy")
        self.assertEqual(by_name["Audit-log access"], "Unable to verify")


if __name__ == "__main__":
    unittest.main()
