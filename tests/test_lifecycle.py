import contextlib
import io
import json
import unittest
from unittest import mock

import helpers
from nightlight import cli, config, lifecycle, sun

USER_CONF = "# my own config\nprofile {\n    time = 20:00\n    temperature = 4000\n}\n"


def run_cli(*argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = cli.main(list(argv))
    return code, out.getvalue()


class BeforeConsent(helpers.SandboxTest):
    def setUp(self):
        super().setUp()
        self.write_conf(USER_CONF)

    def test_sync_leaves_everything_alone(self):
        self.hyprsunset_pid = None
        code, out = run_cli("sync", "--json")
        self.assertEqual(code, 0)
        self.assertEqual(config.CONF.read_text(), USER_CONF)
        self.assertFalse(config.CONF_BACKUP.exists())
        self.start.assert_not_called()
        report = json.loads(out)
        self.assertFalse(report["enabled"])
        self.assertEqual(report["profiles"], [])

    def test_status_does_not_present_the_users_file_as_our_schedule(self):
        _, out = run_cli("status", "--json")
        report = json.loads(out)
        self.assertFalse(report["night"])
        self.assertIsNone(report["next"])

    def test_overrides_are_refused(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            run_cli("set", "2700")
        self.assertEqual(self.applied, [])


class Enable(helpers.SandboxTest):
    def test_backs_up_then_takes_over(self):
        self.write_conf(USER_CONF)
        self.hyprsunset_pid = None
        lifecycle.enable(dict(config.DEFAULTS))
        self.assertEqual(config.CONF_BACKUP.read_text(), USER_CONF)
        self.assertTrue(lifecycle.enabled())
        self.start.assert_called_once()

    def test_without_existing_config(self):
        lifecycle.enable(dict(config.DEFAULTS))
        self.assertTrue(lifecycle.enabled())
        self.assertFalse(config.CONF_BACKUP.exists())

    def test_keeps_the_first_backup_and_a_later_foreign_file(self):
        self.write_conf(USER_CONF)
        config.CONF_BACKUP.write_text("# original\n")
        lifecycle.enable(dict(config.DEFAULTS))
        self.assertEqual(config.CONF_BACKUP.read_text(), "# original\n")
        extra = list(config.CONF_BACKUP.parent.glob(config.CONF_BACKUP.name + ".*"))
        self.assertEqual([p.read_text() for p in extra], [USER_CONF])

    def test_failure_puts_the_users_file_back(self):
        self.write_conf(USER_CONF)
        with mock.patch.object(sun, "location", side_effect=RuntimeError("no location")):
            with self.assertRaises(RuntimeError):
                lifecycle.enable(dict(config.DEFAULTS))
        self.assertEqual(config.CONF.read_text(), USER_CONF)
        self.assertFalse(config.CONF_BACKUP.exists())
        self.assertFalse(lifecycle.enabled())

    def test_cli_reports_a_failed_enable(self):
        with mock.patch.object(sun, "location", side_effect=RuntimeError("no location")):
            _, out = run_cli("enable", "--json")
        report = json.loads(out)
        self.assertFalse(report["enabled"])
        self.assertEqual(report["problem"], "no location")


class Disable(helpers.SandboxTest):
    def test_restores_backup_and_forgets_state(self):
        self.write_conf(USER_CONF)
        lifecycle.enable(dict(config.DEFAULTS))
        config.write_json(config.OVERRIDE, {"temperature": 2700})
        lifecycle.disable()
        self.assertEqual(config.CONF.read_text(), USER_CONF)
        self.assertFalse(config.CONF_BACKUP.exists())
        self.assertFalse(config.OVERRIDE.exists())
        self.assertFalse(config.SCHEDULE_STATE.exists())
        self.assertFalse(lifecycle.enabled())
        self.restart.assert_called()
        self.stop.assert_not_called()

    def test_without_backup_removes_ours_and_stops_hyprsunset(self):
        lifecycle.enable(dict(config.DEFAULTS))
        lifecycle.disable()
        self.assertFalse(config.CONF.exists())
        self.stop.assert_called_once()

    def test_never_touches_a_foreign_config(self):
        self.write_conf(USER_CONF)
        config.CONF_BACKUP.write_text("# stale backup\n")
        lifecycle.disable()
        self.assertEqual(config.CONF.read_text(), USER_CONF)
        self.assertEqual(config.CONF_BACKUP.read_text(), "# stale backup\n")
        self.stop.assert_not_called()
        self.restart.assert_not_called()


if __name__ == "__main__":
    unittest.main()
