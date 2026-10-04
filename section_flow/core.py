"""断面流量核心计算。

假设：
相邻采样点之间流速随相对深度线性变化，平均流速为线性插值的积分
（即按采样间距加权的梯形积分，而非算术平均）。
相邻垂线之间，水深与垂线平均流速分别随横向位置线性变化，
分段流量为两者乘积（二次多项式）在分段宽度上的解析积分。
单位：长度米，流速米每秒，面积平方米，流量立方米每秒。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


class SectionError(ValueError):
    """断面数据无效。"""


def _finite(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SectionError(f"{name} 必须是数值，得到 {value!r}")
    result = float(value)
    if not math.isfinite(result):
        raise SectionError(f"{name} 必须是有限数值，得到 {value!r}")
    return result


def mean_vertical_velocity(samples):
    """对单条垂线的分层采样做线性插值积分，返回垂线平均流速。"""
    points = []
    for index, sample in enumerate(samples):
        if not isinstance(sample, dict):
            raise SectionError(f"采样点 {index} 必须是对象")
        rel = _finite(sample.get("rel_depth"), f"采样点 {index} 的 rel_depth")
        vel = _finite(sample.get("velocity"), f"采样点 {index} 的 velocity")
        if not 0.0 <= rel <= 1.0:
            raise SectionError(f"采样点 {index} 的相对深度 {rel} 超出 [0, 1]")
        points.append((rel, vel))
    if not points:
        raise SectionError("有水垂线必须包含流速采样")
    rels = [p[0] for p in points]
    if len(set(rels)) != len(rels):
        raise SectionError("采样相对深度不得重复")
    points.sort()
    if points[0][0] != 0.0 or points[-1][0] != 1.0:
        raise SectionError("有水垂线的采样必须覆盖相对深度 0 与 1")
    total = 0.0
    for (r0, v0), (r1, v1) in zip(points, points[1:]):
        total += (r1 - r0) * (v0 + v1) / 2.0
    return total


@dataclass
class Vertical:
    position: float
    depth: float
    mean_velocity: float


@dataclass
class Segment:
    index: int
    x_left: float
    x_right: float
    depth_left: float
    depth_right: float
    mean_velocity_left: float
    mean_velocity_right: float
    area: float
    discharge: float


@dataclass
class SectionResult:
    section_id: object
    verticals: list = field(default_factory=list)
    segments: list = field(default_factory=list)
    area: float = 0.0
    discharge: float = 0.0
    mean_velocity: float | None = None
    note: str | None = None


def _parse_verticals(raw_verticals):
    if not isinstance(raw_verticals, list) or len(raw_verticals) < 2:
        raise SectionError("每个断面至少需要两条垂线")
    verticals = []
    for index, raw in enumerate(raw_verticals):
        if not isinstance(raw, dict):
            raise SectionError(f"垂线 {index} 必须是对象")
        position = _finite(raw.get("position"), f"垂线 {index} 的 position")
        depth = _finite(raw.get("depth"), f"垂线 {index} 的 depth")
        if depth < 0.0:
            raise SectionError(f"垂线 {index} 的水深不得为负")
        samples = raw.get("samples")
        if depth == 0.0:
            if samples:
                raise SectionError(f"干垂线 {index} 不应携带流速采样")
            mean_velocity = 0.0
        else:
            if samples is None:
                raise SectionError(f"有水垂线 {index} 缺少流速采样")
            mean_velocity = mean_vertical_velocity(samples)
        verticals.append(Vertical(position, depth, mean_velocity))
    positions = [v.position for v in verticals]
    if any(b <= a for a, b in zip(positions, positions[1:])):
        raise SectionError("垂线横向位置必须严格递增")
    if verticals[0].depth != 0.0 or verticals[-1].depth != 0.0:
        raise SectionError("两岸端点垂线水深必须为零")
    return verticals


def _segment_integrals(v0, v1):
    """返回 (面积, 流量)。水深与平均流速均随横向位置线性变化。"""
    width = v1.position - v0.position
    d0, d1 = v0.depth, v1.depth
    u0, u1 = v0.mean_velocity, v1.mean_velocity
    area = width * (d0 + d1) / 2.0
    # ∫0^1 (u0+(u1-u0)s)(d0+(d1-d0)s) ds * width
    discharge = width * (
        u0 * d0
        + (u0 * (d1 - d0) + (u1 - u0) * d0) / 2.0
        + (u1 - u0) * (d1 - d0) / 3.0
    )
    return area, discharge


def compute_section(raw_section):
    """核算单个断面，返回分段明细与汇总。"""
    if not isinstance(raw_section, dict):
        raise SectionError("断面必须是对象")
    section_id = raw_section.get("id")
    verticals = _parse_verticals(raw_section.get("verticals"))
    result = SectionResult(section_id=section_id, verticals=verticals)
    for index, (v0, v1) in enumerate(zip(verticals, verticals[1:])):
        area, discharge = _segment_integrals(v0, v1)
        result.segments.append(Segment(
            index=index,
            x_left=v0.position,
            x_right=v1.position,
            depth_left=v0.depth,
            depth_right=v1.depth,
            mean_velocity_left=v0.mean_velocity,
            mean_velocity_right=v1.mean_velocity,
            area=area,
            discharge=discharge,
        ))
        result.area += area
        result.discharge += discharge
    if result.area > 0.0:
        result.mean_velocity = result.discharge / result.area
    else:
        result.mean_velocity = None
        result.note = "全干断面：面积与流量均为零，平均流速无定义"
    return result
