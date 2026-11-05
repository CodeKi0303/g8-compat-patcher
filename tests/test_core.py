"""Public tests contain no firmware; optional equivalence tests use local files."""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import zipfile

from g8_patcher import core


class InputBoundaryTests(unittest.TestCase):
    def test_unknown_profile_does_not_read_or_create_files(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "not-created"
            with self.assertRaisesRegex(core.PatcherError, "Unknown profile"):
                core.build_package(Path(temp) / "missing.zip", output, "unsupported")
            self.assertFalse(output.exists())

    def test_missing_original_is_an_expected_error(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(core.PatcherError, "Cannot read original"):
                core.validate_source(Path(temp) / "missing.zip")

    def test_untrusted_zip_is_rejected_before_zip_parser(self):
        # A small hostile archive must not reach decompression/path handling.
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "wrong.zip"
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("../../unexpected.bin", b"untrusted")
            with mock.patch.object(core.zipfile, "ZipFile") as parser:
                with self.assertRaisesRegex(core.PatcherError, "does not match"):
                    core.validate_source(source)
                parser.assert_not_called()
            self.assertFalse((Path(temp).parent / "unexpected.bin").exists())

    def test_same_size_wrong_digest_is_rejected_before_zip_parser(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "wrong.zip"
            source.write_bytes(b"0" * core.SOURCE["zipBytes"])
            with mock.patch.object(core.zipfile, "ZipFile") as parser:
                with self.assertRaisesRegex(core.PatcherError, "does not match"):
                    core.validate_source(source)
                parser.assert_not_called()

    def test_original_read_is_bounded(self):
        stream = mock.MagicMock()
        stream.__enter__.return_value = stream
        stream.read.return_value = b"x" * (core.SOURCE["zipBytes"] + 1)
        with mock.patch.object(Path, "open", return_value=stream):
            with self.assertRaises(core.PatcherError):
                core.validate_source(Path("oversized.zip"))
        stream.read.assert_called_once_with(core.SOURCE["zipBytes"] + 1)

    def test_profile_metadata_is_not_shared_mutable_state(self):
        first = core.list_profiles()
        expected = core.list_profiles()
        self.assertEqual([item["id"] for item in expected], ["kishi-xbox", "kishi-ps"])
        self.assertTrue(all("changes" not in item for item in expected))
        first[0]["outputSha256"] = "0" * 64
        self.assertEqual(core.list_profiles(), expected)


@unittest.skipUnless(os.environ.get("G8_TEST_ORIGINAL_ZIP"),
                     "Set G8_TEST_ORIGINAL_ZIP for real official ZIP tests")
class OriginalIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = Path(os.environ["G8_TEST_ORIGINAL_ZIP"])
        cls.original_bytes = cls.original.read_bytes()
        # Failure here should fail the integration run, not silently skip it.
        cls.main = core.validate_source(cls.original)

    def test_repacked_original_is_not_accepted_as_official_archive(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "repacked.zip"
            with zipfile.ZipFile(io.BytesIO(self.original_bytes)) as original:
                with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as repacked:
                    for name in original.namelist():
                        repacked.writestr(name, original.read(name))
            with self.assertRaisesRegex(core.PatcherError, "does not match"):
                core.build_package(path, Path(temp) / "output")
            self.assertFalse((Path(temp) / "output").exists())

    def test_one_changed_original_byte_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "changed.zip"
            data = bytearray(self.original_bytes)
            data[-1] ^= 1
            path.write_bytes(data)
            with self.assertRaisesRegex(core.PatcherError, "does not match"):
                core.validate_source(path)

    def test_profiles_create_pinned_main_only_packages(self):
        with tempfile.TemporaryDirectory() as temp:
            for profile in core.list_profiles():
                with self.subTest(profile=profile["id"]):
                    result = core.build_package(self.original, Path(temp), profile["id"])
                    archive_path = Path(result["archive"])
                    self.assertTrue(archive_path.is_absolute())
                    self.assertTrue(archive_path.name.endswith(
                        "gamesir-g8_firmware_" + profile["packageSelectionVersion"] + ".zip"))
                    with zipfile.ZipFile(archive_path) as archive:
                        self.assertEqual(archive.namelist(), ["G6C_ISP.bin"])
                        self.assertIsNone(archive.testzip())
                        main = archive.read("G6C_ISP.bin")
                    self.assertEqual(len(main), core.SOURCE["mainBytes"])
                    self.assertEqual(hashlib.sha256(main).hexdigest(), profile["outputSha256"])
                    self.assertEqual(result["main_sha256"], profile["outputSha256"])
                    self.assertEqual(result["main_bytes"], len(main))
                    report = json.loads(Path(result["report"]).read_text("utf-8"))
                    self.assertEqual(report["output"]["mainSha256"], profile["outputSha256"])
                    self.assertEqual(report["verification"]["changedBytes"], 182)
                    self.assertNotIn(str(self.original), json.dumps(report))
            self.assertEqual(self.original.read_bytes(), self.original_bytes)

    def test_repeated_builds_have_identical_zip_bytes_and_distinct_paths(self):
        with tempfile.TemporaryDirectory() as temp:
            first = core.build_package(self.original, Path(temp))
            second = core.build_package(self.original, Path(temp))
            self.assertNotEqual(first["archive"], second["archive"])
            self.assertEqual(Path(first["archive"]).read_bytes(), Path(second["archive"]).read_bytes())
            self.assertEqual(first["archive_sha256"], second["archive_sha256"])

    def test_existing_output_file_is_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "reserved"
            output.write_bytes(b"user-owned-file")
            with self.assertRaisesRegex(core.PatcherError, "output directory"):
                core.build_package(self.original, output)
            self.assertEqual(output.read_bytes(), b"user-owned-file")

    def test_write_failure_cleans_only_newly_created_output(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            sentinel = output / "keep.txt"
            sentinel.write_bytes(b"user-data")
            with mock.patch.object(core.os, "fsync", side_effect=OSError("simulated write failure")):
                with self.assertRaisesRegex(core.PatcherError, "Cannot finish writing"):
                    core.build_package(self.original, output)
            self.assertEqual(list(output.iterdir()), [sentinel])
            self.assertEqual(sentinel.read_bytes(), b"user-data")
            self.assertEqual(self.original.read_bytes(), self.original_bytes)

    @unittest.skipUnless(os.environ.get("G8_TEST_REFERENCE_DIR"),
                         "Set G8_TEST_REFERENCE_DIR to retained candidate parent directory")
    def test_generated_firmware_equals_previously_tested_binary_byte_for_byte(self):
        root = Path(os.environ["G8_TEST_REFERENCE_DIR"])
        references = {
            "kishi-xbox": root / "129.60-1.5-kishi-xbox-name-v5" /
                "G8-129.60-1.5-kishi-xbox-name-v5.experimental.bin",
            "kishi-ps": root / "129.60-1.5-kishi-ps5-v4" /
                "G8-129.60-1.5-kishi-ps5-v4.experimental.bin",
        }
        with tempfile.TemporaryDirectory() as temp:
            for identifier, reference in references.items():
                with self.subTest(profile=identifier):
                    result = core.build_package(self.original, Path(temp), identifier)
                    with zipfile.ZipFile(result["archive"]) as archive:
                        main = archive.read("G6C_ISP.bin")
                    self.assertEqual(main, reference.read_bytes())


if __name__ == "__main__":
    unittest.main()
