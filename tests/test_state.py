"""State files: atomic writes, and reads that reject what we can't have written."""

import json
import os
import unittest
from unittest import mock

import helpers
from nightlight import config, override, profiles, sun


class WriteJson(helpers.SandboxTest):
    def test_replaces_atomically_and_leaves_no_temp_files(self):
        config.write_json(config.OVERRIDE, {"a": 1})
        config.write_json(config.OVERRIDE, {"a": 2})
        self.assertEqual(config.read_json(config.OVERRIDE), {"a": 2})
        self.assertEqual([p.name for p in config.STATE.iterdir()], [config.OVERRIDE.name])

    def test_a_failed_write_keeps_the_previous_file(self):
        config.write_json(config.OVERRIDE, {"a": 1})
        with mock.patch.object(os, "replace", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                config.write_json(config.OVERRIDE, {"a": 2})
        self.assertEqual(config.read_json(config.OVERRIDE), {"a": 1})
        self.assertEqual([p.name for p in config.STATE.iterdir()], [config.OVERRIDE.name])

    def test_a_reader_never_sees_a_partial_file(self):
        config.write_json(config.OVERRIDE, {"a": 1})
        seen = []
        real = os.replace

        def spy(src, dst):
            # Mid-write: the destination still holds the whole previous value
            seen.append(config.read_json(config.OVERRIDE))
            real(src, dst)

        with mock.patch.object(os, "replace", spy):
            config.write_json(config.OVERRIDE, {"a": 2})
        self.assertEqual(seen, [{"a": 1}])


class ReadJson(helpers.SandboxTest):
    def read(self, text, schema=override.override_schema):
        config.STATE.mkdir(parents=True, exist_ok=True)
        config.OVERRIDE.write_text(text)
        with helpers.quiet():
            return config.read_json(config.OVERRIDE, schema)

    def bad_file(self):
        return config.OVERRIDE.with_name(config.OVERRIDE.name + ".bad")

    def test_missing_file(self):
        self.assertIsNone(config.read_json(config.OVERRIDE, override.override_schema))
        self.assertFalse(self.bad_file().exists())

    def test_truncated_json_is_kept_for_diagnosis(self):
        self.assertIsNone(self.read('{"temperature": 2700, "unt'))
        self.assertFalse(config.OVERRIDE.exists())
        self.assertEqual(self.bad_file().read_text(), '{"temperature": 2700, "unt')

    def test_valid_json_of_the_wrong_type(self):
        self.assertIsNone(self.read('[1, 2, 3]'))
        self.assertTrue(self.bad_file().exists())

    def test_missing_field(self):
        # The KeyError from the review: an override without `until`
        self.assertIsNone(self.read('{"temperature": 2700}'))

    def test_field_of_the_wrong_type(self):
        self.assertIsNone(self.read(json.dumps(
            {"temperature": 2700, "hold": "1h", "until": "soon", "applied_at": 0, "pid": 1})))

    def test_field_out_of_range(self):
        self.assertIsNone(self.read(json.dumps(
            {"temperature": 99000, "hold": "1h", "until": 1.0, "applied_at": 0, "pid": 1})))

    def test_a_newer_schema_version_is_not_guessed_at(self):
        self.assertIsNone(self.read(json.dumps(
            {"version": config.SCHEMA_VERSION + 1, "temperature": 2700, "hold": "1h",
             "until": 1.0, "applied_at": 0, "pid": 1})))

    def test_a_legacy_file_without_a_version_is_still_read(self):
        ov = {"temperature": 2700, "hold": "1h", "until": 1.0, "applied_at": 0.0, "pid": 1}
        self.assertEqual(self.read(json.dumps(ov)), ov)

    def test_off_and_a_dead_pid_are_valid(self):
        ov = {"version": config.SCHEMA_VERSION, "temperature": None, "hold": "morning",
              "until": 1.0, "applied_at": 0, "pid": None}
        self.assertEqual(self.read(json.dumps(ov)), ov)


class ScheduleState(helpers.SandboxTest):
    def test_a_malformed_state_file_forces_a_rebuild(self):
        profiles.update(dict(config.DEFAULTS))
        config.SCHEDULE_STATE.write_text('{"date": "2026-09-19", "settings": {"off_time": 99}}')
        with helpers.quiet():
            self.assertTrue(profiles.needs_update(dict(config.DEFAULTS)))
            self.assertEqual(profiles.resolve_settings(object()), dict(config.DEFAULTS))
        self.assertTrue(config.SCHEDULE_STATE.with_name(
            config.SCHEDULE_STATE.name + ".bad").exists())

    def test_settings_are_checked_before_the_config_is_written(self):
        bad = {**config.DEFAULTS, "evening_temp": 12}
        with self.assertRaises(ValueError):
            profiles.update(bad, force=True)
        self.assertFalse(config.CONF.exists())


class Coordinates(helpers.SandboxTest):
    def read(self):
        with helpers.quiet():
            return config.read_json(config.CACHE, sun.coords_schema)

    def test_cached_coordinates_round_trip(self):
        config.write_json(config.CACHE, (12.983, 77.583))
        self.assertEqual(self.read(), [12.983, 77.583])

    def test_coordinates_off_the_globe_are_discarded(self):
        for cached in (["north", 77.583], [91.0, 0.0], [12.983], {"lat": 1}):
            with self.subTest(cached=cached):
                config.write_json(config.CACHE, cached)
                self.assertIsNone(self.read())
                self.assertFalse(config.CACHE.exists())


if __name__ == "__main__":
    unittest.main()
