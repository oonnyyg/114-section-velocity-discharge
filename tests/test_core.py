import math
import unittest

from section_flow.core import SectionError, compute_section, mean_vertical_velocity


def vertical(position, depth, samples=None):
    raw = {"position": position, "depth": depth}
    if samples is not None:
        raw["samples"] = samples
    return raw


def sample(rel, vel):
    return {"rel_depth": rel, "velocity": vel}


class MeanVelocityTest(unittest.TestCase):
    def test_uneven_spacing_uses_integration_not_arithmetic_mean(self):
        samples = [sample(0.0, 1.0), sample(0.1, 0.5), sample(1.0, 0.0)]
        # 线性插值积分：0.1*(1+0.5)/2 + 0.9*(0.5+0)/2 = 0.075 + 0.225
        self.assertAlmostEqual(mean_vertical_velocity(samples), 0.3)
        self.assertNotAlmostEqual(mean_vertical_velocity(samples), (1.0 + 0.5 + 0.0) / 3)

    def test_unsorted_samples_are_sorted(self):
        samples = [sample(1.0, 0.0), sample(0.0, 2.0)]
        self.assertAlmostEqual(mean_vertical_velocity(samples), 1.0)

    def test_missing_endpoints_rejected(self):
        with self.assertRaises(SectionError):
            mean_vertical_velocity([sample(0.0, 1.0), sample(0.5, 1.0)])

    def test_duplicate_and_out_of_range_rejected(self):
        with self.assertRaises(SectionError):
            mean_vertical_velocity([sample(0.0, 1.0), sample(0.0, 2.0), sample(1.0, 1.0)])
        with self.assertRaises(SectionError):
            mean_vertical_velocity([sample(0.0, 1.0), sample(1.2, 1.0)])

    def test_non_finite_rejected(self):
        with self.assertRaises(SectionError):
            mean_vertical_velocity([sample(0.0, 1.0), sample(1.0, float("nan"))])


class SectionTest(unittest.TestCase):
    def test_constant_velocity_section(self):
        section = {
            "id": "rect",
            "verticals": [
                vertical(0.0, 0.0),
                vertical(10.0, 2.0, [sample(0.0, 1.5), sample(1.0, 1.5)]),
                vertical(20.0, 0.0),
            ],
        }
        result = compute_section(section)
        self.assertAlmostEqual(result.area, 20.0)
        # 干垂线平均流速约定为零，向湿垂线线性过渡：
        # 每段 ∫u d = 10 * (1.5*2)/3 = 10，两段共 20
        self.assertAlmostEqual(result.discharge, 20.0)
        self.assertAlmostEqual(result.mean_velocity, 1.0)

    def test_segment_discharge_integrates_product_not_trapezoid_of_products(self):
        # 干-湿交界：d0=0,u0=0；d1=2,u1=1，宽度 10
        # 乘积积分 = 10 * (u1*d1) / 3 = 20/3；端点流量梯形 = 10 * (u1*d1)/2 = 10
        section = {
            "id": "wet-dry",
            "verticals": [
                vertical(0.0, 0.0),
                vertical(10.0, 2.0, [sample(0.0, 1.0), sample(1.0, 1.0)]),
                vertical(20.0, 0.0),
            ],
        }
        result = compute_section(section)
        self.assertAlmostEqual(result.segments[0].discharge, 20.0 / 3.0)
        self.assertAlmostEqual(result.segments[0].area, 10.0)
        self.assertAlmostEqual(result.discharge, 40.0 / 3.0)

    def test_backflow_keeps_negative_sign(self):
        section = {
            "id": "backflow",
            "verticals": [
                vertical(0.0, 0.0),
                vertical(5.0, 1.0, [sample(0.0, 2.0), sample(1.0, 2.0)]),
                vertical(10.0, 1.0, [sample(0.0, -1.0), sample(1.0, -1.0)]),
                vertical(15.0, 0.0),
            ],
        }
        result = compute_section(section)
        # 中段：u、d 均线性，∫u d = 5*(2*1 + (-1)*1)/3 + 5*(2*1+(-1)*1)/6
        mid = result.segments[1]
        self.assertAlmostEqual(mid.discharge, 5 * (2.0 + -1.0) / 2.0)
        self.assertLess(result.segments[2].discharge, 0.0)
        self.assertGreater(result.discharge, 0.0)
        self.assertAlmostEqual(result.mean_velocity, result.discharge / result.area)

    def test_all_dry_section_has_null_mean_velocity(self):
        section = {"id": "dry", "verticals": [vertical(0.0, 0.0), vertical(5.0, 0.0)]}
        result = compute_section(section)
        self.assertEqual(result.area, 0.0)
        self.assertEqual(result.discharge, 0.0)
        self.assertIsNone(result.mean_velocity)
        self.assertIsNotNone(result.note)

    def test_invalid_sections_rejected(self):
        with self.assertRaises(SectionError):
            compute_section({"verticals": [vertical(0.0, 0.0)]})
        with self.assertRaises(SectionError):
            compute_section({"verticals": [vertical(0.0, 0.0), vertical(0.0, 0.0)]})
        with self.assertRaises(SectionError):
            compute_section({"verticals": [vertical(0.0, 1.0), vertical(5.0, 0.0)]})
        with self.assertRaises(SectionError):
            compute_section({"verticals": [vertical(0.0, 0.0), vertical(5.0, -1.0)]})
        with self.assertRaises(SectionError):
            compute_section({"verticals": [vertical(0.0, 0.0), vertical(5.0, 0.0, [sample(0.0, 1.0), sample(1.0, 1.0)])]})


if __name__ == "__main__":
    unittest.main()
