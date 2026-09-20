"""Shared test setup: import from src/ and sandbox every state path."""

import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nightlight import config  # noqa: E402

PROFILES_CONF = """\
profile {
    time = 07:00
    identity = true
}

profile {
    time = 18:18
    temperature = 3400
}

profile {
    time = 21:18
    temperature = 2700
}
"""


def quiet():
    """Swallow the warning config.read_json prints when it discards a file."""
    return contextlib.redirect_stderr(io.StringIO())


class SandboxTest(unittest.TestCase):
    """Points every config path at a temp dir and stubs out hyprsunset, so
    tests never touch the real screen or ~/.config."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        paths = {
            "CONF": root / "hypr/hyprsunset.conf",
            "CONF_BACKUP": root / "hypr/hyprsunset.conf.pre-nightlight",
            "WEATHER_LOC": root / "weather.json",
            "STATE": root / "state",
            "CACHE": root / "state/coords.json",
            "OVERRIDE": root / "state/override.json",
            "SCHEDULE_STATE": root / "state/schedule.json",
            "PENDING_RESTORE": root / "state/restore-pending.json",
        }
        for name, path in paths.items():
            patcher = mock.patch.object(config, name, path)
            patcher.start()
            self.addCleanup(patcher.stop)

        # A fake hyprsunset: remembers the last applied value, never restarts.
        # Set apply_fails to make its IPC reject every temperature.
        self.applied = []
        self.apply_fails = False
        self.hyprsunset_temp = 3400
        self.hyprsunset_pid = 1234
        stubs = {
            "apply": self._apply,
            "current_temp": lambda: self.hyprsunset_temp,
            "pid": lambda: self.hyprsunset_pid,
            "restart": mock.Mock(),
            "start": mock.Mock(),
            "stop": mock.Mock(),
        }
        from nightlight import hyprsunset
        for name, fn in stubs.items():
            patcher = mock.patch.object(hyprsunset, name, fn)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.restart = hyprsunset.restart
        self.start = hyprsunset.start
        self.stop = hyprsunset.stop

        # Never look up a real location
        from nightlight import sun
        patcher = mock.patch.object(sun, "location", return_value=(12.983, 77.583))
        patcher.start()
        self.addCleanup(patcher.stop)

    def _apply(self, temp):
        self.applied.append(temp)
        if self.apply_fails:
            return False
        if temp is not None:
            self.hyprsunset_temp = temp
        return True

    def write_conf(self, text=PROFILES_CONF):
        config.CONF.parent.mkdir(parents=True, exist_ok=True)
        config.CONF.write_text(text)
