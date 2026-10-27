"""Unit tests for private S3-compatible media storage helpers."""
import hashlib
import os
import unittest
from unittest.mock import Mock, patch

from helpers import media_storage


class MediaStorageConfigurationTests(unittest.TestCase):
    def test_storage_is_disabled_without_bucket(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(media_storage.is_configured())

    def test_endpoint_requires_complete_credentials(self):
        with patch.dict(os.environ, {
            "S3_BUCKET": "private-assets",
            "S3_ENDPOINT_URL": "https://objects.example.test",
            "S3_ACCESS_KEY_ID": "access",
        }, clear=True):
            self.assertFalse(media_storage.is_configured())
        with patch.dict(os.environ, {
            "S3_BUCKET": "private-assets",
            "S3_ENDPOINT_URL": "https://objects.example.test",
            "S3_ACCESS_KEY_ID": "access",
            "S3_SECRET_ACCESS_KEY": "secret",
        }, clear=True):
            self.assertTrue(media_storage.is_configured())

    def test_public_assets_need_a_separate_bucket_and_https_base(self):
        with patch.dict(os.environ, {"S3_BUCKET": "private-assets"}, clear=True):
            self.assertFalse(media_storage.is_configured(private=False))
        with patch.dict(os.environ, {
            "S3_PUBLIC_BUCKET": "generated-public",
            "S3_PUBLIC_BASE_URL": "http://cdn.example.test",
        }, clear=True):
            self.assertFalse(media_storage.is_configured(private=False))
        with patch.dict(os.environ, {
            "S3_PUBLIC_BUCKET": "generated-public",
            "S3_PUBLIC_BASE_URL": "https://cdn.example.test/assets",
        }, clear=True):
            self.assertTrue(media_storage.is_configured(private=False))

    def test_aws_bucket_can_use_runtime_credentials(self):
        with patch.dict(os.environ, {"S3_BUCKET": "private-assets"}, clear=True):
            self.assertTrue(media_storage.is_configured())

    def test_namespace_and_extension_are_safe(self):
        self.assertEqual(media_storage._namespace("../panel images/✨"), "panelimages")
        self.assertEqual(media_storage._extension("page.PNG"), ".png")
        self.assertEqual(media_storage._extension("no-extension"), ".img")

    def test_signed_url_lifetime_is_bounded(self):
        with patch.dict(os.environ, {"S3_SIGNED_URL_TTL_SECONDS": "1"}, clear=True):
            self.assertEqual(media_storage._url_ttl(), 60)
        with patch.dict(os.environ, {"S3_SIGNED_URL_TTL_SECONDS": "999999"}, clear=True):
            self.assertEqual(media_storage._url_ttl(), 3600)
        with patch.dict(os.environ, {"S3_SIGNED_URL_TTL_SECONDS": "invalid"}, clear=True):
            self.assertEqual(media_storage._url_ttl(), 900)


class MediaStorageUploadTests(unittest.IsolatedAsyncioTestCase):
    async def test_upload_returns_registry_metadata_without_network_access(self):
        client = Mock()
        data = b"not-a-real-image-but-upload-payload"
        with (
            patch.dict(os.environ, {"S3_BUCKET": "private-assets"}, clear=True),
            patch("helpers.media_storage._client", return_value=client),
        ):
            stored = await media_storage.store_image(
                data,
                namespace="panels",
                filename="manga.PNG",
                content_type="image/png",
            )

        self.assertIsNotNone(stored)
        self.assertEqual(stored.bucket, "private-assets")
        self.assertTrue(stored.key.startswith("panels/"))
        self.assertTrue(stored.key.endswith(".png"))
        self.assertEqual(stored.content_type, "image/png")
        self.assertEqual(stored.size_bytes, len(data))
        self.assertEqual(stored.sha256, hashlib.sha256(data).hexdigest())
        self.assertTrue(stored.is_private)
        client.put_object.assert_called_once()
        self.assertEqual(client.put_object.call_args.kwargs["CacheControl"], "private, no-store")

    async def test_public_image_returns_stable_registered_url(self):
        stored = media_storage.StoredImage(
            bucket="generated-public",
            key="generated/three-by-three/asset.png",
            content_type="image/png",
            size_bytes=123,
            sha256="a" * 64,
            is_private=False,
        )
        with (
            patch("helpers.media_storage.is_configured", return_value=True),
            patch("helpers.media_storage.store_image", new_callable=__import__("unittest").mock.AsyncMock, return_value=stored) as store,
            patch("helpers.media_storage.create_asset", new_callable=__import__("unittest").mock.AsyncMock, return_value=42) as create,
            patch("helpers.media_storage.asset_url", new_callable=__import__("unittest").mock.AsyncMock, return_value="https://cdn.example.test/generated/asset.png") as asset_url,
        ):
            url = await media_storage.store_public_image(
                b"generated-grid-bytes",
                namespace="generated/three-by-three",
                filename="grid.png",
                content_type="image/png",
                uploaded_by=7,
                guild_id=9,
            )

        self.assertEqual(url, "https://cdn.example.test/generated/asset.png")
        store.assert_awaited_once()
        self.assertFalse(store.await_args.kwargs["private"])
        create.assert_awaited_once_with(
            stored,
            namespace="generated/three-by-three",
            uploaded_by=7,
            guild_id=9,
        )
        asset_url.assert_awaited_once_with(42)

    async def test_public_upload_uses_public_bucket(self):
        client = Mock()
        data = b"generated-grid-bytes"
        with (
            patch.dict(os.environ, {
                "S3_PUBLIC_BUCKET": "generated-public",
                "S3_PUBLIC_BASE_URL": "https://cdn.example.test/assets",
            }, clear=True),
            patch("helpers.media_storage._client", return_value=client),
        ):
            stored = await media_storage.store_image(
                data,
                namespace="generated/three-by-three",
                filename="grid.png",
                content_type="image/png",
                private=False,
            )

        self.assertEqual(stored.bucket, "generated-public")
        self.assertFalse(stored.is_private)
        self.assertTrue(stored.key.startswith("generated/three-by-three/"))
        client.put_object.assert_called_once()
        self.assertEqual(client.put_object.call_args.kwargs["Bucket"], "generated-public")

    async def test_non_image_payload_is_rejected(self):
        with patch.dict(os.environ, {"S3_BUCKET": "private-assets"}, clear=True):
            with self.assertRaises(ValueError):
                await media_storage.store_image(
                    b"payload",
                    namespace="panels",
                    filename="content.txt",
                    content_type="text/plain",
                )


if __name__ == "__main__":
    unittest.main()
