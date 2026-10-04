import unittest

from section_discharge.core import (
    Sample,
    SectionError,
    compute_section,
    mean_velocity,
    parse_section,
)


def make_section(verticals, section_id="S1"):
    return parse_section({"id": section_id, "verticals": verticals}, 0)


class MeanVelocityTests(unittest.TestCase):
    def test_uneven_sampling_uses_integration_not_arithmetic_mean(self):
        samples = (
            Sample(0.0, 1.0),
            Sample(0.1, 0.5),
            Sample(1.0, 0.0),
        )
        # 梯形积分：0.1*(1.0+0.5)/2 + 0.9*(0.5+0.0)/2 = 0.075 + 0.225
        self.assertAlmostEqual(mean_velocity(samples), 0.3)
        # 若误用算术平均会得到 0.5
        self.assertNotAlmostEqual(mean_velocity(samples), 0.5)

    def test_negative_velocity_kept(self):
        samples = (Sample(0.0, -0.4), Sample(1.0, -0.2))
        self.assertAlmostEqual(mean_velocity(samples), -0.3)


class ValidationTests(unittest.TestCase):
    def test_wet_vertical_must_cover_zero_and_one(self):
        with self.assertRaises(SectionError):
            make_section(
                [
                    {"x": 0.0, "depth": 0.0},
                    {"x": 1.0, "depth": 1.0, "samples": [[0.2, 1.0], [1.0, 0.5]]},
                    {"x": 2.0, "depth": 0.0},
                ]
            )

    def test_duplicate_sample_depth_rejected(self):
        with self.assertRaises(SectionError):
            make_section(
                [
                    {"x": 0.0, "depth": 0.0},
                    {"x": 1.0, "depth": 1.0, "samples": [[0.0, 1.0], [0.0, 0.5], [1.0, 0.2]]},
                    {"x": 2.0, "depth": 0.0},
                ]
            )

    def test_non_finite_and_duplicate_x_rejected(self):
        with self.assertRaises(SectionError):
            make_section(
                [
                    {"x": 0.0, "depth": 0.0},
                    {"x": 1.0, "depth": float("nan")},
                    {"x": 2.0, "depth": 0.0},
                ]
            )
        with self.assertRaises(SectionError):
            make_section(
                [
                    {"x": 0.0, "depth": 0.0},
                    {"x": 0.0, "depth": 0.0},
                ]
            )

    def test_dry_vertical_with_samples_rejected(self):
        with self.assertRaises(SectionError):
            make_section(
                [
                    {"x": 0.0, "depth": 0.0, "samples": [[0.0, 1.0], [1.0, 0.0]]},
                    {"x": 1.0, "depth": 0.0},
                ]
            )

    def test_bank_endpoints_must_be_dry(self):
        with self.assertRaises(SectionError):
            make_section(
                [
                    {"x": 0.0, "depth": 0.5, "samples": [[0.0, 1.0], [1.0, 0.0]]},
                    {"x": 1.0, "depth": 0.0},
                ]
            )


class ComputeSectionTests(unittest.TestCase):
    def test_segment_integrates_product_not_trapezoid_of_endpoint_flux(self):
        # 干垂线 -> 有水垂线：h 0->2，u 0->1，宽度 3
        # ∫h*u dx = 3*(2*0*0 + 0*1 + 2*0 + 2*2*1)/6 = 3*4/6 = 2.0
        # 若误用端点流量梯形积分会得到 3*(0+2*1)/2 = 3.0
        section = make_section(
            [
                {"x": 0.0, "depth": 0.0},
                {"x": 3.0, "depth": 2.0, "samples": [[0.0, 1.0], [1.0, 1.0]]},
                {"x": 6.0, "depth": 0.0},
            ]
        )
        result = compute_section(section)
        self.assertEqual(len(result.segments), 2)
        self.assertAlmostEqual(result.segments[0].wet_area, 3.0)
        self.assertAlmostEqual(result.segments[0].discharge, 2.0)
        self.assertAlmostEqual(result.wet_area, 6.0)
        self.assertAlmostEqual(result.discharge, 4.0)
        self.assertAlmostEqual(result.mean_velocity, 4.0 / 6.0)

    def test_mixed_positive_and_negative_flow_keeps_sign(self):
        section = make_section(
            [
                {"x": 0.0, "depth": 0.0},
                {"x": 2.0, "depth": 1.0, "samples": [[0.0, 1.0], [1.0, 1.0]]},
                {"x": 4.0, "depth": 1.0, "samples": [[0.0, -1.0], [1.0, -1.0]]},
                {"x": 6.0, "depth": 0.0},
            ]
        )
        result = compute_section(section)
        # 中段两垂线 u 分别为 +1 与 -1：∫h*u dx = 2*(2*1*1 + 1*(-1) + 1*1 + 2*1*(-1))/6 = 0
        self.assertAlmostEqual(result.segments[1].discharge, 0.0)
        # 两侧段符号相反，净流量为零，回流未被截断
        self.assertAlmostEqual(result.segments[0].discharge, 2.0 / 3.0 * 2.0 / 2.0)
        self.assertAlmostEqual(result.discharge, 0.0)
        self.assertAlmostEqual(result.mean_velocity, 0.0)

    def test_dry_section_reports_null_mean_velocity(self):
        section = make_section(
            [
                {"x": 0.0, "depth": 0.0},
                {"x": 5.0, "depth": 0.0},
            ]
        )
        result = compute_section(section)
        self.assertEqual(result.wet_area, 0.0)
        self.assertEqual(result.discharge, 0.0)
        self.assertIsNone(result.mean_velocity)
        self.assertIsNotNone(result.note)
