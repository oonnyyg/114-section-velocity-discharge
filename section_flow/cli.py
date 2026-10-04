"""命令行入口：读取 JSON 断面数据，输出 CSV 分段明细与 JSON 汇总。"""

from __future__ import annotations

import argparse
import csv
import json
import sys

from .core import SectionError, compute_section

CSV_FIELDS = [
    "section_id", "segment_index", "x_left", "x_right", "width",
    "depth_left", "depth_right",
    "mean_velocity_left", "mean_velocity_right",
    "area", "discharge",
]


def run(input_path, csv_path, json_path):
    with open(input_path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    raw_sections = data.get("sections") if isinstance(data, dict) else None
    if not isinstance(raw_sections, list):
        raise SystemExit("输入 JSON 必须包含 sections 数组")

    results = []
    errors = []
    for index, raw in enumerate(raw_sections):
        section_id = raw.get("id") if isinstance(raw, dict) else None
        try:
            results.append(compute_section(raw))
        except SectionError as exc:
            errors.append({"index": index, "section_id": section_id, "error": str(exc)})

    _write_csv(csv_path, results)
    summary = _build_summary(results, errors)
    _write_json(json_path, summary)
    for error in errors:
        print(f"断面 {error['section_id']!r}（第 {error['index']} 个）无效：{error['error']}",
              file=sys.stderr)
    return 0 if results else 1


def _write_csv(path, results):
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for result in results:
            for seg in result.segments:
                writer.writerow({
                    "section_id": result.section_id,
                    "segment_index": seg.index,
                    "x_left": seg.x_left,
                    "x_right": seg.x_right,
                    "width": seg.x_right - seg.x_left,
                    "depth_left": seg.depth_left,
                    "depth_right": seg.depth_right,
                    "mean_velocity_left": seg.mean_velocity_left,
                    "mean_velocity_right": seg.mean_velocity_right,
                    "area": seg.area,
                    "discharge": seg.discharge,
                })


def _build_summary(results, errors):
    sections = []
    for result in results:
        sections.append({
            "section_id": result.section_id,
            "verticals": [
                {
                    "position": v.position,
                    "depth": v.depth,
                    "mean_velocity": v.mean_velocity,
                }
                for v in result.verticals
            ],
            "area": result.area,
            "discharge": result.discharge,
            "mean_velocity": result.mean_velocity,
            "note": result.note,
        })
    return {"sections": sections, "errors": errors}


def _write_json(path, summary):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="section_flow",
        description="河道断面流量核算：由分层流速生成面积、净流量与分段贡献",
    )
    parser.add_argument("input", help="输入 JSON 文件路径")
    parser.add_argument("--csv", default="segments.csv", help="CSV 分段明细输出路径")
    parser.add_argument("--json", default="summary.json", help="JSON 汇总输出路径")
    args = parser.parse_args(argv)
    return run(args.input, args.csv, args.json)


if __name__ == "__main__":
    sys.exit(main())
