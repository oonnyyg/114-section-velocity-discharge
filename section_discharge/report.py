"""CSV 分段明细与 JSON 汇总输出。"""

from __future__ import annotations

import csv
import io
import json

from .core import SectionResult


def segments_csv(results: list[SectionResult]) -> str:
    """生成所有断面的分段明细 CSV（米、平方米、立方米每秒）。"""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(
        [
            "section_id",
            "segment_index",
            "x_left_m",
            "x_right_m",
            "width_m",
            "wet_area_m2",
            "discharge_m3s",
        ]
    )
    for result in results:
        for seg in result.segments:
            writer.writerow(
                [
                    result.section_id,
                    seg.index,
                    f"{seg.x_left:.6g}",
                    f"{seg.x_right:.6g}",
                    f"{seg.width:.6g}",
                    f"{seg.wet_area:.6g}",
                    f"{seg.discharge:.6g}",
                ]
            )
    return buffer.getvalue()


def summary_json(results: list[SectionResult], errors: list[dict]) -> str:
    """生成 JSON 汇总：各断面总量、垂线平均流速及无效断面报告。"""
    payload = {
        "units": {
            "length": "m",
            "velocity": "m/s",
            "area": "m^2",
            "discharge": "m^3/s",
        },
        "sections": [
            {
                "id": r.section_id,
                "wet_area": r.wet_area,
                "discharge": r.discharge,
                "mean_velocity": r.mean_velocity,
                "note": r.note,
                "verticals": [
                    {"x": v.x, "depth": v.depth, "mean_velocity": v.mean_velocity}
                    for v in r.verticals
                ],
            }
            for r in results
        ],
        "invalid_sections": errors,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
