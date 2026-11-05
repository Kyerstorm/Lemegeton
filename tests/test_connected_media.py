import unittest

from cogs.media.connected_media import (
    ConnectedMedia,
    DiscussionHomeView,
    _display_year,
    _tmdb_title,
    normalize_title,
    validate_https_url,
)
from cogs.media.franchise import Franchise


class ConnectedMediaHelperTests(unittest.TestCase):
    def test_title_normalization_is_case_and_punctuation_insensitive(self):
        self.assertEqual(normalize_title("The King's Avatar: 2"), normalize_title("the king s avatar 2"))
        self.assertEqual(normalize_title(""), "")

    def test_https_urls_are_validated_without_embedded_credentials(self):
        self.assertEqual(validate_https_url("https://example.com/title"), "https://example.com/title")
        for value in ("http://example.com", "javascript:alert(1)", "https://user:password@example.com/title", "not a url"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_https_url(value)
        with self.assertRaises(ValueError):
            validate_https_url(None, required=True)

    def test_community_relationship_urls_are_canonicalized_safely(self):
        self.assertEqual(
            Franchise._relationship_url_key("https://www.AniList.co/manga/123/title/"),
            "anilist.co/manga/123/title",
        )
        self.assertEqual(Franchise._relationship_url_key("http://anilist.co/manga/123"), "")

    def test_tmdb_picker_handles_movie_and_video_categories(self):
        item = {"title": "Example Film", "release_date": "2024-04-01", "name": "Example TV"}
        self.assertEqual(_tmdb_title(item, "MOVIE"), "Example Film")
        self.assertEqual(_tmdb_title(item, "COLLECTION"), "Example Film")
        self.assertEqual(_tmdb_title(item, "VIDEOS_MOVIE"), "Example Film")
        self.assertEqual(_display_year(item, "COLLECTION"), "2024")

    def test_discussion_view_uses_a_named_select_reference(self):
        view = DiscussionHomeView(ConnectedMedia(None), owner_id=123)
        self.assertIs(view.type_select, view.children[0])


if __name__ == "__main__":
    unittest.main()
