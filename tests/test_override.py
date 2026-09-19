import time
import unittest

import helpers
from nightlight import config, override


class Override(helpers.SandboxTest):
    def setUp(self):
        super().setUp()
        self.write_conf()

    def stored(self):
        return config.read_json(config.OVERRIDE)

    def age(self, **fields):
        ov = self.stored()
        ov.update(fields)
        config.write_json(config.OVERRIDE, ov)

    def test_set_applies_and_records(self):
        self.assertTrue(override.set_temperature("2700", "1h"))
        self.assertEqual(self.applied, [2700])
        ov = self.stored()
        self.assertEqual((ov["temperature"], ov["hold"]), (2700, "1h"))
        self.assertAlmostEqual(ov["until"], time.time() + 3600, delta=5)

    def test_off_is_identity(self):
        override.set_temperature("off", "1h")
        self.assertEqual(self.applied, [None])
        self.assertIsNone(self.stored()["temperature"])

    def test_temperature_is_clamped(self):
        override.set_temperature("50", "1h")
        self.assertEqual(self.applied, [1000])

    def test_enforce_is_quiet_when_nothing_changed(self):
        override.set_temperature("2700", "1h")
        override.enforce()
        self.assertEqual(self.applied, [2700])

    def test_enforce_reapplies_after_drift(self):
        override.set_temperature("2700", "1h")
        self.hyprsunset_temp = 3400  # e.g. the keybinding toggle
        override.enforce()
        self.assertEqual(self.applied, [2700, 2700])

    def test_enforce_reapplies_off_after_hyprsunset_restart(self):
        override.set_temperature("off", "1h")
        self.hyprsunset_pid = 5678
        override.enforce()
        self.assertEqual(self.applied, [None, None])

    def test_enforce_reapplies_after_profile_switch(self):
        override.set_temperature("off", "1h")
        self.age(applied_at=time.time() - 2 * 86400)
        override.enforce()
        self.assertEqual(self.applied, [None, None])

    def test_expired_override_is_cleared_and_schedule_restored(self):
        override.set_temperature("2700", "1h")
        self.age(until=time.time() - 1)
        self.assertIsNone(override.current())
        override.enforce()
        self.assertFalse(config.OVERRIDE.exists())
        self.assertEqual(len(self.applied), 2)  # the override, then the schedule

    def test_resume(self):
        override.set_temperature("2700", "1h")
        override.resume()
        self.assertFalse(config.OVERRIDE.exists())
        self.assertEqual(len(self.applied), 2)


if __name__ == "__main__":
    unittest.main()
