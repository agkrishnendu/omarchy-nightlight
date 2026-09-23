import time
import unittest
from datetime import datetime

import helpers
from nightlight import config, override, profiles, schedule


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


class RestoringTheSchedule(helpers.SandboxTest):
    """Dropping an override owes the screen its scheduled temperature, and the
    debt outlives a failed IPC call."""

    def setUp(self):
        super().setUp()
        self.write_conf()

    def scheduled(self):
        now = datetime.now()
        occ = schedule.occurrences(profiles.load_profiles(), now)
        return schedule.active_and_next(occ, now)[0][1]

    def owed(self):
        return config.PENDING_RESTORE.exists()

    def test_failed_resume_is_retried_until_it_lands(self):
        override.set_temperature("2700", "1h")
        self.apply_fails = True
        self.assertFalse(override.resume())
        self.assertFalse(config.OVERRIDE.exists())
        self.assertTrue(self.owed())

        # Still failing: every sync tries again
        override.enforce()
        self.assertEqual(self.applied[-1], self.scheduled())
        self.assertTrue(self.owed())

        self.apply_fails = False
        override.enforce()
        self.assertEqual(self.applied[-1], self.scheduled())
        self.assertFalse(self.owed())

    def test_failed_expiry_is_retried(self):
        override.set_temperature("2700", "1h")
        ov = config.read_json(config.OVERRIDE, override.override_schema)
        ov["until"] = time.time() - 1
        config.write_json(config.OVERRIDE, ov)

        self.apply_fails = True
        override.enforce()
        self.assertFalse(config.OVERRIDE.exists())
        self.assertTrue(self.owed())

        self.apply_fails = False
        override.enforce()
        self.assertEqual(self.applied[-1], self.scheduled())
        self.assertFalse(self.owed())

    def test_a_successful_resume_owes_nothing(self):
        override.set_temperature("2700", "1h")
        self.assertTrue(override.resume())
        self.assertFalse(self.owed())
        override.enforce()
        self.assertEqual(len(self.applied), 2)  # no needless re-apply

    def test_a_new_override_replaces_the_owed_restore(self):
        self.apply_fails = True
        override.resume()
        self.assertTrue(self.owed())
        self.apply_fails = False
        override.set_temperature("2700", "1h")
        self.assertFalse(self.owed())
        override.enforce()
        self.assertEqual(self.applied[-1], 2700)

    def test_an_unreadable_override_falls_back_to_the_schedule(self):
        override.set_temperature("2700", "1h")
        config.OVERRIDE.write_text('{"temperature": 2700, "unt')
        with helpers.quiet():
            override.enforce()
        self.assertEqual(self.applied[-1], self.scheduled())
        self.assertFalse(self.owed())

    def test_reading_a_junk_override_owes_the_schedule(self):
        # status runs before enforce, so the discard must leave the debt behind
        override.set_temperature("2700", "1h")
        config.OVERRIDE.write_text("not json at all")
        with helpers.quiet():
            self.assertIsNone(override.current())
        self.assertTrue(self.owed())
        override.enforce()
        self.assertEqual(self.applied[-1], self.scheduled())
        self.assertFalse(self.owed())

    def test_nothing_is_owed_without_a_schedule(self):
        config.CONF.unlink()
        self.apply_fails = True
        self.assertTrue(override.resume())
        self.assertFalse(self.owed())
        self.assertEqual(self.applied, [])


if __name__ == "__main__":
    unittest.main()
