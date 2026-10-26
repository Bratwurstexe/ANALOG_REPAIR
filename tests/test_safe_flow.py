import unittest

import cv2
import numpy as np

from analogrepair.pipeline import SafeDIS


class _Failing:
    """A DIS stand-in that raises the error seen on Linux CI."""

    def calc(self, *_):
        raise cv2.error("inv_scale_x > 0")


class SafeDISTest(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(1)
        self.frame = (rng.random((96, 128)) * 255).astype(np.uint8)
        self.moved = np.roll(self.frame, 3, axis=1)

    def test_flow_is_measured(self):
        flow = SafeDIS(cv2.DISOPTICAL_FLOW_PRESET_FAST).calc(self.frame, self.moved)
        self.assertEqual(flow.shape, (96, 128, 2))
        self.assertGreater(float(np.median(flow[20:-20, 20:-20, 0])), 1.5)

    def test_a_failure_is_retried_with_a_fresh_instance(self):
        flow = SafeDIS(cv2.DISOPTICAL_FLOW_PRESET_FAST)
        flow.dis = _Failing()
        result = flow.calc(self.frame, self.moved)
        self.assertGreater(float(np.median(result[20:-20, 20:-20, 0])), 1.5)

    def test_a_lasting_failure_counts_as_still(self):
        flow = SafeDIS(cv2.DISOPTICAL_FLOW_PRESET_FAST)
        original = cv2.DISOpticalFlow_create
        try:
            cv2.DISOpticalFlow_create = lambda preset: _Failing()
            flow.dis = _Failing()
            result = flow.calc(self.frame, self.moved)
        finally:
            cv2.DISOpticalFlow_create = original
        self.assertEqual(result.shape, (96, 128, 2))
        self.assertFalse(result.any())

    def test_frames_of_different_size_are_matched(self):
        smaller = cv2.resize(self.moved, (64, 48), interpolation=cv2.INTER_AREA)
        flow = SafeDIS(cv2.DISOPTICAL_FLOW_PRESET_FAST).calc(self.frame, smaller)
        self.assertEqual(flow.shape, (96, 128, 2))


if __name__ == "__main__":
    unittest.main()
