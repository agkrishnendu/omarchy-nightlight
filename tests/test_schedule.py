import unittest
from datetime import date, datetime, timezone

import helpers  # noqa: F401  (puts src/ on sys.path)
from nightlight import profiles, schedule, sun

PROFILES = profiles.parse_profiles(helpers.PROFILES_CONF)


def at(text):
    return datetime.fromisoformat(text)


def resolve(hold, now):
    now = at(now)
    return schedule.hold_until(hold, now, schedule.occurrences(PROFILES, now))


class ActiveAndNext(unittest.TestCase):
    def check(self, now, active, next_at):
        now = at(now)
        a, n = schedule.active_and_next(schedule.occurrences(PROFILES, now), now)
        self.assertEqual(a[1], active)
        self.assertEqual(n[0], at(next_at))

    def test_after_midnight_is_still_late_evening(self):
        self.check("2026-09-19 02:00", 2700, "2026-09-19 07:00")

    def test_daytime_is_off(self):
        self.check("2026-09-19 12:00", None, "2026-09-19 18:18")

    def test_evening(self):
        self.check("2026-09-19 19:00", 3400, "2026-09-19 21:18")

    def test_switch_minute_belongs_to_new_profile(self):
        self.check("2026-09-19 18:18", 3400, "2026-09-19 21:18")

    def test_no_profiles(self):
        now = at("2026-09-19 12:00")
        self.assertEqual(schedule.active_and_next(schedule.occurrences([], now), now), (None, None))


class HoldUntil(unittest.TestCase):
    def test_next(self):
        self.assertEqual(resolve("next", "2026-09-19 19:00"), at("2026-09-19 21:18"))

    def test_morning_from_evening_is_tomorrow(self):
        self.assertEqual(resolve("morning", "2026-09-19 19:00"), at("2026-09-20 07:00"))

    def test_morning_after_midnight_is_today(self):
        self.assertEqual(resolve("morning", "2026-09-19 02:00"), at("2026-09-19 07:00"))

    def test_durations(self):
        self.assertEqual(resolve("1h", "2026-09-19 19:00"), at("2026-09-19 20:00"))
        self.assertEqual(resolve("30m", "2026-09-19 23:45"), at("2026-09-20 00:15"))

    def test_clock_time_rolls_over_to_tomorrow(self):
        self.assertEqual(resolve("22:30", "2026-09-19 19:00"), at("2026-09-19 22:30"))
        self.assertEqual(resolve("06:00", "2026-09-19 19:00"), at("2026-09-20 06:00"))

    def test_bad_value(self):
        with self.assertRaises(ValueError):
            resolve("soon", "2026-09-19 19:00")


class Sunset(unittest.TestCase):
    def test_bengaluru_equinox(self):
        # 18:18 IST, checked against published sunset tables
        s = sun.sunset(12.983, 77.583, date(2026, 9, 19)).astimezone(timezone.utc)
        self.assertEqual((s.hour, s.minute), (12, 48))


if __name__ == "__main__":
    unittest.main()
