"""命令行入口模块。"""

from __future__ import annotations

import argparse
import json
import sys

from .core import SectionError, compute_section, parse_section
from .report import segments_csv, summary_json


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="section_discharge",
        description="河道断面流量核算：由垂线分层流速计算面积、净流量与分段贡献",
    )
    parser.add_argument("input", help="输入 JSON 文件路径（UTF-8）")
    parser.add_argument("--csv", help="分段明细 CSV 输出路径（默认输出到标准输出）")
    parser.add_argument("--json", dest="json_path", help="JSON 汇总输出路径（默认输出到标准输出）")
    args = parser.parse_args(argv)

    with open(args.input, encoding="utf-8") as fh:
        data = json.load(fh)
    raw_sections = data.get("sections") if isinstance(data, dict) else None
    if not isinstance(raw_sections, list) or not raw_sections:
        print("输入 JSON 必须包含非空的 sections 数组", file=sys.stderr)
        return 2

    results = []
    errors = []
    for i, raw in enumerate(raw_sections):
        section_id = raw.get("id", f"section-{i}") if isinstance(raw, dict) else f"section-{i}"
        try:
            results.append(compute_section(parse_section(raw, i)))
        except SectionError as exc:
            errors.append({"id": str(section_id), "error": str(exc)})

    csv_text = segments_csv(results)
    json_text = summary_json(results, errors)
    if args.csv:
        with open(args.csv, "w", encoding="utf-8", newline="") as fh:
            fh.write(csv_text)
    else:
        sys.stdout.write(csv_text)
    if args.json_path:
        with open(args.json_path, "w", encoding="utf-8") as fh:
            fh.write(json_text)
    else:
        sys.stdout.write(json_text)
    for err in errors:
        print(f"断面 {err['id']} 无效：{err['error']}", file=sys.stderr)
    return 0 if results else 1


if __name__ == "__main__":
    raise SystemExit(main())
