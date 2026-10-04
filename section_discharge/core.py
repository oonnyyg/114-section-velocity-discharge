"""断面流量核算核心逻辑。

插值假设：
- 同一垂线内，流速随相对深度（0=水面，1=河底）线性变化，
  平均流速为流速剖面在相对深度 [0, 1] 上的积分（即梯形积分），
  对不等距采样同样适用。
- 相邻垂线之间，水深与垂线平均流速分别随横向位置线性变化，
  分段流量为两者乘积在横向上的解析积分。
"""

from __future__ import annotations

import math
from dataclasses import dataclass


class SectionError(ValueError):
    """单个断面输入无效时抛出。"""


def _finite(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SectionError(f"{name} 必须是数值，得到 {value!r}")
    result = float(value)
    if not math.isfinite(result):
        raise SectionError(f"{name} 必须是有限数值，得到 {value!r}")
    return result


@dataclass(frozen=True)
class Sample:
    """一个流速采样点：相对深度 eta（0 水面，1 河底）与流速 v（m/s）。"""

    eta: float
    velocity: float


@dataclass(frozen=True)
class VerticalInput:
    """一条测量垂线。depth == 0 表示干垂线，不得携带采样。"""

    x: float
    depth: float
    samples: tuple[Sample, ...] = ()


def mean_velocity(samples: tuple[Sample, ...]) -> float:
    """对相对深度 [0, 1] 上的线性流速剖面积分，返回垂线平均流速。"""
    total = 0.0
    for left, right in zip(samples, samples[1:]):
        width = right.eta - left.eta
        total += width * (left.velocity + right.velocity) / 2.0
    return total


def parse_vertical(raw: object, index: int) -> VerticalInput:
    """从 JSON 对象解析并校验一条垂线。"""
    if not isinstance(raw, dict):
        raise SectionError(f"垂线 {index} 必须是对象")
    x = _finite(raw.get("x"), f"垂线 {index} 的 x")
    depth = _finite(raw.get("depth"), f"垂线 {index} 的 depth")
    if depth < 0.0:
        raise SectionError(f"垂线 {index} 的水深不能为负：{depth}")
    raw_samples = raw.get("samples")
    if depth == 0.0:
        if raw_samples:
            raise SectionError(f"垂线 {index} 为干垂线（水深为零），不得携带采样")
        return VerticalInput(x=x, depth=depth)
    if not isinstance(raw_samples, list) or len(raw_samples) < 2:
        raise SectionError(f"垂线 {index} 至少需要两个采样点（相对深度 0 与 1）")
    samples: list[Sample] = []
    for j, item in enumerate(raw_samples):
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            raise SectionError(f"垂线 {index} 采样 {j} 必须是 [相对深度, 流速] 二元组")
        eta = _finite(item[0], f"垂线 {index} 采样 {j} 的相对深度")
        vel = _finite(item[1], f"垂线 {index} 采样 {j} 的流速")
        if not 0.0 <= eta <= 1.0:
            raise SectionError(f"垂线 {index} 采样 {j} 的相对深度越界：{eta}")
        if samples and eta <= samples[-1].eta:
            raise SectionError(f"垂线 {index} 的采样相对深度必须严格递增")
        samples.append(Sample(eta=eta, velocity=vel))
    if samples[0].eta != 0.0 or samples[-1].eta != 1.0:
        raise SectionError(f"垂线 {index} 的采样必须覆盖相对深度 0 与 1")
    return VerticalInput(x=x, depth=depth, samples=tuple(samples))


@dataclass(frozen=True)
class SectionInput:
    """一个断面的全部垂线。"""

    section_id: str
    verticals: tuple[VerticalInput, ...]


def parse_section(raw: object, index: int) -> SectionInput:
    """从 JSON 对象解析并校验一个断面。"""
    if not isinstance(raw, dict):
        raise SectionError(f"断面 {index} 必须是对象")
    section_id = raw.get("id", f"section-{index}")
    if not isinstance(section_id, str):
        raise SectionError(f"断面 {index} 的 id 必须是字符串")
    raw_verticals = raw.get("verticals")
    if not isinstance(raw_verticals, list) or len(raw_verticals) < 2:
        raise SectionError(f"断面 {section_id} 至少需要两条垂线")
    verticals = tuple(parse_vertical(item, i) for i, item in enumerate(raw_verticals))
    for prev, cur in zip(verticals, verticals[1:]):
        if cur.x <= prev.x:
            raise SectionError(f"断面 {section_id} 的横向位置必须严格递增")
    if verticals[0].depth != 0.0 or verticals[-1].depth != 0.0:
        raise SectionError(f"断面 {section_id} 两岸端点水深必须为零")
    return SectionInput(section_id=section_id, verticals=verticals)


@dataclass(frozen=True)
class VerticalResult:
    """一条垂线的核算结果。"""

    x: float
    depth: float
    mean_velocity: float


@dataclass(frozen=True)
class SegmentResult:
    """相邻垂线之间一个分段的核算结果。"""

    index: int
    x_left: float
    x_right: float
    width: float
    wet_area: float
    discharge: float


@dataclass(frozen=True)
class SectionResult:
    """一个断面的汇总结果。全干时 mean_velocity 为 None。"""

    section_id: str
    verticals: tuple[VerticalResult, ...]
    segments: tuple[SegmentResult, ...]
    wet_area: float
    discharge: float
    mean_velocity: float | None
    note: str | None


def _segment_integrals(
    width: float, h0: float, h1: float, u0: float, u1: float
) -> tuple[float, float]:
    """返回分段湿面积与有符号流量。

    水深 h 与平均流速 u 均随横向位置线性变化，对乘积 h*u 解析积分：
    ∫ h*u dx = width * (2*h0*u0 + h0*u1 + h1*u0 + 2*h1*u1) / 6
    """
    area = width * (h0 + h1) / 2.0
    discharge = width * (2.0 * h0 * u0 + h0 * u1 + h1 * u0 + 2.0 * h1 * u1) / 6.0
    return area, discharge


def compute_section(section: SectionInput) -> SectionResult:
    """核算单个断面，保留回流负号；全干断面平均流速为 None。"""
    verticals = tuple(
        VerticalResult(
            x=v.x,
            depth=v.depth,
            mean_velocity=mean_velocity(v.samples) if v.samples else 0.0,
        )
        for v in section.verticals
    )
    segments: list[SegmentResult] = []
    total_area = 0.0
    total_discharge = 0.0
    for i, (left, right) in enumerate(zip(verticals, verticals[1:])):
        width = right.x - left.x
        area, discharge = _segment_integrals(
            width, left.depth, right.depth, left.mean_velocity, right.mean_velocity
        )
        segments.append(
            SegmentResult(
                index=i,
                x_left=left.x,
                x_right=right.x,
                width=width,
                wet_area=area,
                discharge=discharge,
            )
        )
        total_area += area
        total_discharge += discharge
    if total_area == 0.0:
        return SectionResult(
            section_id=section.section_id,
            verticals=verticals,
            segments=tuple(segments),
            wet_area=0.0,
            discharge=0.0,
            mean_velocity=None,
            note="全干断面：湿面积为零，平均流速无定义（输出空值）",
        )
    return SectionResult(
        section_id=section.section_id,
        verticals=verticals,
        segments=tuple(segments),
        wet_area=total_area,
        discharge=total_discharge,
        mean_velocity=total_discharge / total_area,
        note=None,
    )
