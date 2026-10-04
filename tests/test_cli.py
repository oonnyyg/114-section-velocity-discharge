import csv
import json
import tempfile
import unittest
from pathlib import Path

from section_flow.cli import main


class CliTest(unittest.TestCase):
    def test_invalid_section_reported_independently(self):
        payload = {
            "sections": [
                {
                    "id": "ok",
                    "verticals": [
                        {"position": 0.0, "depth": 0.0},
                        {"position": 4.0, "depth": 1.0,
                         "samples": [{"rel_depth": 0.0, "velocity": 1.0},
                                     {"rel_depth": 1.0, "velocity": 1.0}]},
                        {"position": 8.0, "depth": 0.0},
                    ],
                },
                {"id": "bad", "verticals": [{"position": 0.0, "depth": 0.0}]},
            ]
        }
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            input_path = tmp / "in.json"
            input_path.write_text(json.dumps(payload), encoding="utf-8")
            csv_path = tmp / "seg.csv"
            json_path = tmp / "sum.json"
            code = main([str(input_path), "--csv", str(csv_path), "--json", str(json_path)])
            self.assertEqual(code, 0)
            summary = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual([s["section_id"] for s in summary["sections"]], ["ok"])
            self.assertEqual(len(summary["errors"]), 1)
            self.assertEqual(summary["errors"][0]["section_id"], "bad")
            with csv_path.open(encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 2)
            self.assertTrue(all(row["section_id"] == "ok" for row in rows))
            ok = summary["sections"][0]
            self.assertAlmostEqual(ok["area"], 4.0)
            self.assertAlmostEqual(ok["discharge"], 8.0 / 3.0)


if __name__ == "__main__":
    unittest.main()
