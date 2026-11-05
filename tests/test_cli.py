"""Exercise the public CLI, without shipping vendor firmware fixtures."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from g8_patcher import cli


ROOT = Path(__file__).resolve().parents[1]


def run_cli(*arguments: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "g8_patcher", *arguments],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )


class CommandLineTests(unittest.TestCase):
    def test_public_profiles_and_version(self):
        result = run_cli("profiles")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual({profile["id"] for profile in json.loads(result.stdout)}, {"kishi-xbox", "kishi-ps"})
        self.assertEqual(result.stderr, "")
        result = run_cli("--version")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("0.1.0", result.stdout)

    def test_source_choice_is_required_and_exclusive(self):
        for arguments in [
            ("build", "--output-dir", "unused"),
            ("build", "--download", "--source", "unused.zip", "--output-dir", "unused"),
        ]:
            with self.subTest(arguments=arguments):
                result = run_cli(*arguments)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")

    def test_unknown_profile_never_downloads(self):
        with patch.object(cli, "download_original") as download, patch("sys.stderr"):
            code = cli.main(["build", "--download", "--profile", "unsupported", "--output-dir", "unused"])
        self.assertEqual(code, 1)
        download.assert_not_called()

    def test_invalid_local_source_fails_without_output(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source = base / "invalid original.zip"
            source.write_bytes(b"not the pinned vendor archive")
            output = base / "result"
            result = run_cli("build", "--source", str(source), "--output-dir", str(output))
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout, "")
            self.assertNotIn("Traceback", result.stderr)
            self.assertFalse(list(output.rglob("*.zip")))

    @unittest.skipUnless(os.environ.get("G8_TEST_ORIGINAL_ZIP"), "Set G8_TEST_ORIGINAL_ZIP for real original integration.")
    def test_real_original_through_public_cli(self):
        with tempfile.TemporaryDirectory(prefix="G8 CLI ") as directory:
            result = run_cli(
                "build", "--source", os.environ["G8_TEST_ORIGINAL_ZIP"],
                "--profile", "kishi-xbox", "--output-dir", directory,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["main_sha256"], "b6b5cc95c7f2d03c877075cc06e6afc396ae3e35c86bbe502710288c3d9c817b")
            self.assertTrue(Path(payload["archive"]).is_file())
            self.assertTrue(Path(payload["report"]).is_file())
            self.assertEqual(result.stderr, "")


if __name__ == "__main__":
    unittest.main()
