import unittest
import pandas as pd
from greenops.pipeline import (generate_world, validate_data, features, FEATURES,
                              chronological_masks, reserve_simulation, waste_service_deadline,
                              transition_action)


class PipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data, cls.labels, cls.state = generate_world(42, 35)

    def test_seed_is_reproducible(self):
        other, _, _ = generate_world(42, 35)
        pd.testing.assert_frame_equal(self.data, other)

    def test_occupancy_quality_and_duplicate_guard(self):
        self.assertEqual(validate_data(self.data)["rows"], 35*24*4)
        self.assertGreater(self.data.water_l.isna().sum(), 0)
        with self.assertRaises(ValueError):
            validate_data(pd.concat([self.data, self.data.iloc[:1]]))

    def test_labels_excluded(self):
        forbidden = {"is_fault", "event_id", "kind"}
        self.assertFalse(forbidden.intersection(self.data.columns))
        self.assertFalse(forbidden.intersection(FEATURES))

    def test_future_change_cannot_change_origin_features(self):
        origin = pd.Timestamp("2025-01-14T00:00:00Z")
        before = features(self.data, 24)
        changed = self.data.copy()
        changed.loc[changed.observed_at > origin, ["energy_kwh", "water_l", "occupied_beds", "temperature_c"]] = 900
        after = features(changed, 24)
        b = before[before.origin_time <= origin][FEATURES].reset_index(drop=True)
        a = after[after.origin_time <= origin][FEATURES].reset_index(drop=True)
        pd.testing.assert_frame_equal(a, b)

    def test_split_purges_cross_boundary_targets(self):
        f = features(self.data, 24)
        tr, va, te, info = chronological_masks(f, self.data.observed_at)
        self.assertLess(f.loc[tr, "target_time"].max(), f.loc[va, "origin_time"].min())
        self.assertLess(f.loc[va, "target_time"].max(), f.loc[te, "origin_time"].min())
        self.assertGreater((~(tr|va|te)).sum(), 0)

    def test_reserve_mass_balance_and_non_depleting(self):
        self.assertEqual(reserve_simulation(30000, 3000)["hours_to_depletion"], 10)
        self.assertAlmostEqual(reserve_simulation(30000, 3000, excess_lph=500)["hours_to_depletion"], 30000/3500)
        self.assertIsNone(reserve_simulation(30000, 3000, inflow_lph=4000)["hours_to_depletion"])
        with self.assertRaises(ValueError):
            reserve_simulation(-1, 3000)

    def test_waste_age_overrides_fill_and_missing_stays_unknown(self):
        result = waste_service_deadline(30, 2, 23)
        self.assertEqual(result["service_within_hours"], 1)
        result = waste_service_deadline(30, 2, None)
        self.assertEqual(result["age_status"], "unknown")
        self.assertIsNone(result["hours_to_configured_age_limit"])

    def test_action_requires_valid_order_and_verification(self):
        self.assertEqual(transition_action("open", "acknowledged"), "acknowledged")
        with self.assertRaises(ValueError):
            transition_action("open", "closed", "proof")
        with self.assertRaises(ValueError):
            transition_action("resolved", "verified")
        self.assertEqual(transition_action("resolved", "verified", "stable readings"), "verified")


if __name__ == "__main__":
    unittest.main()
