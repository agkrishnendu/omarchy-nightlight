import types
import unittest
from datetime import date, datetime

import helpers
from nightlight import config, profiles

SETTINGS = dict(config.DEFAULTS)
TODAY = date(2026, 9, 19)


def settings(**changes):
    return {**SETTINGS, **changes}


class ParseProfiles(unittest.TestCase):
    def test_parses_and_sorts(self):
        text = helpers.PROFILES_CONF.replace("07:00", "23:59")
        self.assertEqual(profiles.parse_profiles(text), [(1098, 3400), (1278, 2700), (1439, None)])

    def test_missing_temperature_counts_as_off(self):
        self.assertEqual(profiles.parse_profiles("profile {\n time = 8:05\n}"), [(485, None)])

    def test_ignores_comments_and_blocks_without_time(self):
        text = "# profile { time = 01:00 }\nprofile {\n temperature = 4000\n}\n"
        self.assertEqual(profiles.parse_profiles(text), [(60, None)])

    def test_profiles_sharing_a_minute_collapse_to_the_last(self):
        text = ("profile {\n time = 18:18\n identity = true\n}\n"
                "profile {\n time = 18:18\n temperature = 3400\n}\n")
        self.assertEqual(profiles.parse_profiles(text), [(1098, 3400)])


class RenderConf(unittest.TestCase):
    set_at = datetime(2026, 9, 19, 18, 18)

    def times(self, s):
        conf = profiles.render_conf(s, 12.983, 77.583, self.set_at)
        self.assertTrue(conf.startswith(config.MARKER))
        return profiles.parse_profiles(conf)

    def test_default_schedule(self):
        self.assertEqual(self.times(SETTINGS), [(420, None), (1098, 3400), (1278, 2700)])

    def test_late_disabled(self):
        self.assertEqual(self.times(settings(late_after=0)), [(420, None), (1098, 3400)])

    def test_late_past_midnight(self):
        self.assertEqual(self.times(settings(late_after=360)), [(18, 2700), (420, None), (1098, 3400)])

    def test_late_skipped_when_it_would_pass_off_time(self):
        self.assertEqual(self.times(settings(late_after=900)), [(420, None), (1098, 3400)])

    def test_off_time_on_sunset_leaves_the_day_off(self):
        # No night window, and no two profiles on one minute to order
        self.assertEqual(self.times(settings(off_time="18:18")), [(1098, None)])

    def test_off_time_a_minute_after_sunset_keeps_a_one_minute_night(self):
        self.assertEqual(self.times(settings(off_time="18:19")), [(1098, 3400), (1099, None)])

    def test_rejects_settings_it_could_not_render(self):
        for bad in (settings(off_time="24:00"), settings(evening_temp=12),
                    settings(late_after=-5), settings(late_temp=None)):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                profiles.render_conf(bad, 12.983, 77.583, self.set_at)


class Update(helpers.SandboxTest):
    def test_refuses_to_overwrite_the_users_config(self):
        self.write_conf("# my own config\n")
        with self.assertRaises(RuntimeError):
            profiles.update(SETTINGS, force=True, today=TODAY)
        self.assertEqual(config.CONF.read_text(), "# my own config\n")

    def test_unchanged_day_and_settings_is_a_no_op(self):
        profiles.update(SETTINGS, today=TODAY)
        self.assertFalse(profiles.needs_update(SETTINGS, TODAY))
        self.assertFalse(profiles.update(SETTINGS, today=TODAY))

    def test_new_day_settings_or_location_trigger_update(self):
        profiles.update(SETTINGS, today=TODAY)
        self.assertTrue(profiles.needs_update(SETTINGS, date(2026, 9, 20)))
        self.assertTrue(profiles.needs_update(settings(evening_temp=3000), TODAY))
        config.WEATHER_LOC.write_text("{}")
        self.assertTrue(profiles.needs_update(SETTINGS, TODAY))

    def test_restarts_hyprsunset_only_when_file_changes(self):
        profiles.update(SETTINGS, today=TODAY)
        self.assertEqual(self.restart.call_count, 1)
        profiles.update(SETTINGS, force=True, today=TODAY)
        self.assertEqual(self.restart.call_count, 1)

    def test_settings_are_remembered(self):
        profiles.update(settings(off_time="06:30"), today=TODAY)
        remembered = profiles.resolve_settings(types.SimpleNamespace())
        self.assertEqual(remembered["off_time"], "06:30")
        given = profiles.resolve_settings(types.SimpleNamespace(off_time="08:00"))
        self.assertEqual(given["off_time"], "08:00")


if __name__ == "__main__":
    unittest.main()
