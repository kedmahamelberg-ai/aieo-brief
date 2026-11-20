import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import prepare_weekly_review
import weekly_review_gate


class WeeklyReviewGateTests(unittest.TestCase):
    def approved_root(self, root: Path, release_id: str = "2026-W46") -> None:
        path = root / "data/weekly-overviews/approved" / f"{release_id}.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({
            "release_id": release_id,
            "human_approved_at": "2026-11-16T15:39:42+00:00",
            "markets": {"status": "ready", "human_approved": True},
            "research": {"status": "ready", "human_approved": True},
        }), encoding="utf-8")

    def test_approved_current_week_skips_review_before_model_setup(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.approved_root(root)
            output = root / "github-output"
            with patch.object(weekly_review_gate, "ROOT", root), \
                 patch.object(weekly_review_gate, "current_release_id", return_value="2026-W46"), \
                 patch.dict(os.environ, {"GITHUB_OUTPUT": str(output), "REOPEN_APPROVED": "false"}):
                weekly_review_gate.main()
            self.assertIn("prepare=false", output.read_text())

            output.write_text("")
            with patch.object(prepare_weekly_review, "ROOT", root), \
                 patch.object(prepare_weekly_review, "inputs", return_value=({"release_id": "2026-W46"}, {})), \
                 patch.object(prepare_weekly_review, "dbmaps", side_effect=AssertionError("model setup reached")), \
                 patch.dict(os.environ, {"GITHUB_OUTPUT": str(output), "REOPEN_APPROVED": "false",
                                         "EXPECTED_RELEASE_ID": "2026-W46"}):
                prepare_weekly_review.main()
            self.assertIn("needs_review=false", output.read_text())
            self.assertIn("ready=false", output.read_text())

    def test_new_week_and_explicit_recheck_can_prepare(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.approved_root(root)
            output = root / "github-output"
            with patch.object(weekly_review_gate, "ROOT", root), \
                 patch.object(weekly_review_gate, "current_release_id", return_value="2026-W47"), \
                 patch.dict(os.environ, {"GITHUB_OUTPUT": str(output), "REOPEN_APPROVED": "false"}):
                weekly_review_gate.main()
            self.assertIn("prepare=true", output.read_text())

            output.write_text("")
            with patch.object(weekly_review_gate, "ROOT", root), \
                 patch.object(weekly_review_gate, "current_release_id", return_value="2026-W46"), \
                 patch.dict(os.environ, {"GITHUB_OUTPUT": str(output), "REOPEN_APPROVED": "true"}):
                weekly_review_gate.main()
            self.assertIn("prepare=true", output.read_text())

    def test_invalid_approval_fails_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.approved_root(root)
            path = root / "data/weekly-overviews/approved/2026-W46.json"
            value = json.loads(path.read_text())
            value["research"]["human_approved"] = False
            path.write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError, "Invalid owner approval"):
                weekly_review_gate.approved_for_release(root, "2026-W46")

    def test_feed_identity_must_match_release(self):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                pass

            def read(self):
                return json.dumps({"release_id": "2026-W47", "release": {"release_id": "2026-W46"}}).encode()

        with patch.object(weekly_review_gate, "urlopen", return_value=Response()):
            with self.assertRaisesRegex(ValueError, "identity is invalid"):
                weekly_review_gate.current_release_id("https://observatory.example")


if __name__ == "__main__":
    unittest.main()
