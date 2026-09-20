"""manifest.json: the widget settings the QML front end and the CLI share.

`omarchy plugin validate` covers the manifest's own shape; this checks the
parts the plugin's own code depends on, so a typo here fails a test rather
than a user's bar.
"""

import json
import unittest
from pathlib import Path

import helpers  # noqa: F401  (puts src/ on sys.path)
from nightlight import config, profiles

MANIFEST = json.loads((Path(__file__).resolve().parents[1] / "manifest.json").read_text())
WIDGET = MANIFEST["barWidget"]
SCHEMA = {entry["key"]: entry for entry in WIDGET["schema"]}
# Widget setting -> the CLI option and config.DEFAULTS key it is passed as
SETTINGS = {
    "eveningTemperature": "evening_temp",
    "lateTemperature": "late_temp",
    "lateAfterMinutes": "late_after",
    "offTime": "off_time",
}


class Manifest(unittest.TestCase):
    def test_entry_point_exists(self):
        root = Path(__file__).resolve().parents[1]
        self.assertTrue((root / MANIFEST["entryPoints"]["barWidget"]).is_file())
        self.assertTrue((root / "src/nightlight-schedule.py").is_file())

    def test_every_setting_is_declared_and_defaulted_consistently(self):
        self.assertEqual(set(WIDGET["defaults"]), set(SCHEMA))
        self.assertEqual(set(SCHEMA), set(SETTINGS))
        for key, entry in SCHEMA.items():
            with self.subTest(key=key):
                self.assertEqual(WIDGET["defaults"][key], entry["defaultValue"])

    def test_widget_defaults_match_the_cli_defaults(self):
        for widget_key, cli_key in SETTINGS.items():
            with self.subTest(key=widget_key):
                self.assertEqual(WIDGET["defaults"][widget_key], config.DEFAULTS[cli_key])

    def test_the_declared_range_is_one_the_backend_accepts(self):
        for widget_key, cli_key in SETTINGS.items():
            entry = SCHEMA[widget_key]
            if entry["type"] != "integer":
                continue
            for value in (entry["min"], entry["max"], entry["defaultValue"]):
                with self.subTest(key=widget_key, value=value):
                    profiles.check_settings({**config.DEFAULTS, cli_key: value})


if __name__ == "__main__":
    unittest.main()
