import unittest
import time
from cancel_window.order_iceberg_detection import OrderIcebergDetection

class TestOrderIcebergDetection(unittest.TestCase):

    def setUp(self):
        self.detector = OrderIcebergDetection(retention_ms=300_000)
        self.now = int(time.time() * 1000)

    def _register_event(self, orderid, offset_ms, event_type, size=1.0, side="bid", price=100.0):
        self.detector.register_event(
            orderid=orderid,
            timestamp=self.now + offset_ms,
            event_type=event_type,
            price=price,
            size=size,
            side=side
        )

    def test_empty_detector_has_zero_score(self):
        """
        Baseline behavior
        """
        self.assertEqual(self.detector.get_iceberg_score(), 0.0)
        self.assertEqual(self.detector.detect_icebergs(), [])

    def test_single_reduction_no_iceberg(self):
        """
        Minimum reduction gating
        """
        self._register_event("order1", 0, "REDUCTION")
        self._register_event("order1", 100, "CANCEL_SPOOF")
        self.assertEqual(self.detector.detect_icebergs(), [])
        self.assertEqual(self.detector.get_iceberg_score(), 0.0)

    def test_multiple_reductions_without_cancel_spoof(self):
        """
        Cancel type validation
        """
        self._register_event("order2", 0, "REDUCTION")
        self._register_event("order2", 100, "REDUCTION")
        self._register_event("order2", 200, "CANCEL")  # Not CANCEL_SPOOF
        self.assertEqual(self.detector.detect_icebergs(), [])
        self.assertEqual(self.detector.get_iceberg_score(), 0.0)

    def test_valid_iceberg_detection(self):
        """
        Core iceberg logic
        """
        self._register_event("order3", 0, "REDUCTION", size=0.5)
        self._register_event("order3", 100, "REDUCTION", size=0.3)
        self._register_event("order3", 200, "CANCEL_SPOOF", size=0.0)
        icebergs = self.detector.detect_icebergs()
        self.assertEqual(len(icebergs), 1)
        iceberg = icebergs[0]
        self.assertEqual(iceberg['orderid'], "order3")
        self.assertEqual(iceberg['side'], "bid")
        self.assertEqual(iceberg['reductions'], 2)
        self.assertAlmostEqual(iceberg['total_size'], 0.8)
        self.assertEqual(iceberg['duration'], 200)
        self.assertGreater(self.detector.get_iceberg_score(), 0.0)

    def test_multiple_icebergs_score_accumulation(self):
        """
        Score aggregation
        """
        for i in range(3):
            oid = f"order{i}"
            self._register_event(oid, 0, "REDUCTION")
            self._register_event(oid, 100, "REDUCTION")
            self._register_event(oid, 200, "CANCEL_SPOOF")
        icebergs = self.detector.detect_icebergs()
        self.assertEqual(len(icebergs), 3)
        self.assertAlmostEqual(self.detector.get_iceberg_score(), 0.6)

    def test_score_caps_at_one(self):
        """
        Score normalization
        """
        for i in range(20):
            oid = f"order{i}"
            self._register_event(oid, 0, "REDUCTION")
            self._register_event(oid, 100, "REDUCTION")
            self._register_event(oid, 200, "CANCEL_SPOOF")
        score = self.detector.get_iceberg_score()
        self.assertEqual(score, 1.0)

    def test_prune_removes_old_events(self):
        """
        Time-window pruning
        """
        old_ts = self.now - 400_000  # older than retention window
        self.detector.register_event("old_order", old_ts, "REDUCTION", 100.0, 1.0, "ask")
        self.assertEqual(len(self.detector.events), 0)

    def test_mixed_order_ids_are_separated(self):
        """
        Order ID isolation
        """
        self._register_event("orderA", 0, "REDUCTION")
        self._register_event("orderA", 100, "REDUCTION")
        self._register_event("orderA", 200, "CANCEL_SPOOF")

        self._register_event("orderB", 0, "REDUCTION")
        self._register_event("orderB", 100, "CANCEL_SPOOF")  # only one reduction

        icebergs = self.detector.detect_icebergs()
        self.assertEqual(len(icebergs), 1)
        self.assertEqual(icebergs[0]['orderid'], "orderA")

    def test_side_is_preserved_in_output(self):
        """
        Side attribution
        """
        self._register_event("orderX", 0, "REDUCTION", side="ask")
        self._register_event("orderX", 100, "REDUCTION", side="ask")
        self._register_event("orderX", 200, "CANCEL_SPOOF", side="ask")
        iceberg = self.detector.detect_icebergs()[0]
        self.assertEqual(iceberg['side'], "ask")

if __name__ == "__main__":
    unittest.main()
