import csv
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class CliTests(unittest.TestCase):
    def run_cli(self, payload):
        with tempfile.TemporaryDirectory() as tmp:
            input_path = Path(tmp) / "in.json"
            csv_path = Path(tmp) / "out.csv"
            json_path = Path(tmp) / "out.json"
            input_path.write_text(json.dumps(payload), encoding="utf-8")
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "section_discharge",
                    str(input_path),
                    "--csv",
                    str(csv_path),
                    "--json",
                    str(json_path),
                ],
                capture_output=True,
                text=True,
            )
            return proc, csv_path.read_text(encoding="utf-8"), json_path.read_text(encoding="utf-8")

    def test_invalid_section_isolated_and_outputs_written(self):
        payload = {
            "sections": [
                {
                    "id": "good",
                    "verticals": [
                        {"x": 0.0, "depth": 0.0},
                        {"x": 2.0, "depth": 1.0, "samples": [[0.0, 0.8], [0.3, 1.0], [1.0, 0.4]]},
                        {"x": 4.0, "depth": 0.0},
                    ],
                },
                {
                    "id": "bad",
                    "verticals": [
                        {"x": 0.0, "depth": 0.0},
                        {"x": 1.0, "depth": -0.5},
                    ],
                },
            ]
        }
        proc, csv_text, json_text = self.run_cli(payload)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("bad", proc.stderr)
        rows = list(csv.DictReader(io.StringIO(csv_text)))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["section_id"], "good")
        summary = json.loads(json_text)
        self.assertEqual([s["id"] for s in summary["sections"]], ["good"])
        self.assertEqual(summary["invalid_sections"][0]["id"], "bad")
        vertical = summary["sections"][0]["verticals"][1]
        # 平均流速 = 0.3*(0.8+1.0)/2 + 0.7*(1.0+0.4)/2 = 0.27 + 0.49
        self.assertAlmostEqual(vertical["mean_velocity"], 0.76)

    def test_dry_section_mean_velocity_is_null(self):
        payload = {
            "sections": [
                {
                    "id": "dry",
                    "verticals": [
                        {"x": 0.0, "depth": 0.0},
                        {"x": 3.0, "depth": 0.0},
                    ],
                }
            ]
        }
        proc, _, json_text = self.run_cli(payload)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        section = json.loads(json_text)["sections"][0]
        self.assertIsNone(section["mean_velocity"])
        self.assertEqual(section["discharge"], 0.0)
        self.assertIsNotNone(section["note"])


if __name__ == "__main__":
    unittest.main()
