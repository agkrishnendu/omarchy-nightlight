"""sun.location: weather-widget setting, then a byte-capped wttr.in lookup, then cache."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from nightlight import config, sun


class FakeResponse:
    """Minimal stand-in for what urllib.request.urlopen's context manager yields."""

    def __init__(self, body):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self, n=-1):
        if n < 0 or n > len(self._body):
            n = len(self._body)
        chunk, self._body = self._body[:n], self._body[n:]
        return chunk


def wttr_body(total_len=None):
    """A valid wttr.in j1 payload, padded with a throwaway field to `total_len` bytes."""
    payload = {"nearest_area": [{"latitude": "12.983", "longitude": "77.583"}], "pad": ""}
    base_len = len(json.dumps(payload))
    if total_len is not None:
        payload["pad"] = "x" * (total_len - base_len)
    return json.dumps(payload).encode()


class Location(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        for name, path in {
            "WEATHER_LOC": root / "weather.json",
            "STATE": root / "state",
            "CACHE": root / "state/coords.json",
        }.items():
            patcher = mock.patch.object(config, name, path)
            patcher.start()
            self.addCleanup(patcher.stop)

    def urlopen(self, body):
        return mock.patch("nightlight.sun.urllib.request.urlopen",
                           return_value=FakeResponse(body))

    def test_uses_the_weather_widget_setting_first(self):
        config.WEATHER_LOC.parent.mkdir(parents=True, exist_ok=True)
        config.WEATHER_LOC.write_text(json.dumps({"latitude": 1.0, "longitude": 2.0}))
        with self.urlopen(b"should never be read"):
            self.assertEqual(sun.location(), (1.0, 2.0))

    def test_parses_and_caches_a_response_within_the_cap(self):
        with self.urlopen(wttr_body()):
            self.assertEqual(sun.location(), (12.983, 77.583))
        self.assertEqual(config.read_json(config.CACHE, sun.coords_schema), [12.983, 77.583])

    def test_a_response_exactly_at_the_cap_is_read(self):
        with self.urlopen(wttr_body(sun.WTTR_MAX_BYTES)):
            self.assertEqual(sun.location(), (12.983, 77.583))

    def test_a_response_over_the_cap_is_rejected_before_decoding(self):
        # Not valid JSON: if this ever reached json.loads, it would raise
        # instead of falling through like the cap check does.
        body = b"[" + b"x" * sun.WTTR_MAX_BYTES
        with self.urlopen(body), mock.patch("nightlight.sun.json.loads") as loads:
            with self.assertRaises(RuntimeError):
                sun.location()
            loads.assert_not_called()

    def test_falls_back_to_the_cache_when_the_cap_is_exceeded(self):
        config.write_json(config.CACHE, (12.983, 77.583))
        body = b"x" * (sun.WTTR_MAX_BYTES + 1)
        with self.urlopen(body):
            self.assertEqual(sun.location(), (12.983, 77.583))

    def test_no_location_at_all_is_a_runtime_error(self):
        with self.urlopen(b"x" * (sun.WTTR_MAX_BYTES + 1)):
            with self.assertRaises(RuntimeError):
                sun.location()


if __name__ == "__main__":
    unittest.main()
