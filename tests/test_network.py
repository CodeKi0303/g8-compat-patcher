"""Acquisition boundaries: validate before saving, reject untrusted redirects."""
import hashlib
import io
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from g8_patcher import network
from g8_patcher.core import PatcherError


class Response(io.BytesIO):
    status = 200
    url = "https://ota.xiaoji.com/download/test.zip"


class DownloadTests(unittest.TestCase):
    def test_failed_save_is_removed_so_retry_can_succeed(self):
        data = b"fixture content"
        source = {"url": Response.url, "zipBytes": len(data), "zipSha256": hashlib.sha256(data).hexdigest()}
        original_open = Path.open

        @contextmanager
        def failing_open(path, mode="r", *args, **kwargs):
            with original_open(path, mode, *args, **kwargs) as stream:
                yield stream
                if mode == "xb":
                    raise OSError("simulated disk flush failure")

        with tempfile.TemporaryDirectory() as tmp, patch.object(network, "SOURCE", source), \
                patch.object(network.urllib.request, "build_opener") as factory, \
                patch.object(network, "validate_source"):
            factory.return_value.open.side_effect = [Response(data), Response(data)]
            with patch.object(Path, "open", failing_open), self.assertRaises(PatcherError):
                network.download_original(Path(tmp))
            self.assertEqual(list(Path(tmp).iterdir()), [])
            result = network.download_original(Path(tmp))
            self.assertEqual(result.read_bytes(), data)

    def test_failed_new_readback_is_removed_but_existing_file_is_preserved(self):
        data = b"fixture content"
        source = {"url": Response.url, "zipBytes": len(data), "zipSha256": hashlib.sha256(data).hexdigest()}
        with tempfile.TemporaryDirectory() as tmp, patch.object(network, "SOURCE", source), \
                patch.object(network.urllib.request, "build_opener") as factory, \
                patch.object(network, "validate_source", side_effect=PatcherError("bad readback")):
            factory.return_value.open.return_value = Response(data)
            with self.assertRaises(PatcherError):
                network.download_original(Path(tmp))
            self.assertEqual(list(Path(tmp).iterdir()), [])
            existing = Path(tmp) / "test.zip"
            existing.write_bytes(b"keep me")
            factory.reset_mock()
            with self.assertRaises(PatcherError):
                network.download_original(Path(tmp))
            self.assertEqual(existing.read_bytes(), b"keep me")
            factory.assert_not_called()

    def test_redirect_rejects_http_credentials_and_foreign_host(self):
        for url in ("http://ota.xiaoji.com/a", "https://evil.example/a",
                    "https://ota.xiaoji.com.evil.example/a", "https://x@ota.xiaoji.com/a",
                    "https://ota.xiaoji.com:444/a", "https://ota.xiaoji.com:bad/a",
                    "https://[invalid/a"):
            with self.subTest(url=url), self.assertRaises(PatcherError):
                network._check_url(url)

    def test_wrong_body_never_creates_file(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(network.urllib.request, "build_opener") as factory:
            factory.return_value.open.return_value = Response(b"not a firmware ZIP")
            with self.assertRaises(PatcherError):
                network.download_original(Path(tmp))
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_bounded_read_and_output_verification(self):
        data = b"fixture content"
        source = {"url": Response.url, "zipBytes": len(data), "zipSha256": hashlib.sha256(data).hexdigest()}
        with tempfile.TemporaryDirectory() as tmp, patch.object(network, "SOURCE", source), \
                patch.object(network.urllib.request, "build_opener") as factory, \
                patch.object(network, "validate_source") as validate:
            factory.return_value.open.return_value = Response(data)
            result = network.download_original(Path(tmp))
            self.assertEqual(result.read_bytes(), data)
            validate.assert_called_once_with(result)
            # A valid saved original requires no second network request.
            factory.reset_mock()
            self.assertEqual(network.download_original(Path(tmp)), result)
            factory.assert_not_called()

    def test_oversized_body_is_rejected(self):
        data = b"abc"
        source = {"url": Response.url, "zipBytes": 3, "zipSha256": hashlib.sha256(data).hexdigest()}
        with tempfile.TemporaryDirectory() as tmp, patch.object(network, "SOURCE", source), \
                patch.object(network.urllib.request, "build_opener") as factory:
            factory.return_value.open.return_value = Response(data + b"excess")
            with self.assertRaises(PatcherError):
                network.download_original(Path(tmp))
            self.assertEqual(list(Path(tmp).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
