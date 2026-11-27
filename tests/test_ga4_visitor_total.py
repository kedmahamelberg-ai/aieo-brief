import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from refresh_visitor_total import HOST, report_request, snapshot


class VisitorReport(unittest.TestCase):
    def test_cumulative_total_is_scoped_to_the_brief(self):
        req = report_request("2026-11-25")
        self.assertEqual(req["dimensionFilter"]["filter"]["stringFilter"]["value"], HOST)
        self.assertEqual(req["metrics"], [{"name": "totalUsers"}])
        self.assertNotIn("dimensions", req)
        report = {"rowCount": 1, "metricHeaders": [{"name": "totalUsers"}],
                  "rows": [{"metricValues": [{"value": "409"}]}]}
        self.assertEqual(snapshot(report, "2026-11-25", "2026-11-27")["count"], 409)
        for bad in ({}, dict(report, metadata={"subjectToThresholding": True})):
            with self.assertRaises(ValueError):
                snapshot(bad, "2026-11-25", "2026-11-27")
