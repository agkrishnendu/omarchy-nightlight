"""Command-line interface.

  nightlight-schedule status [--json]
  nightlight-schedule set <kelvin|off> [--until next|morning|1h|30m|HH:MM] [--json]
  nightlight-schedule resume [--json]
  nightlight-schedule restart [--json]      # hyprsunset stopped answering IPC
  nightlight-schedule sync [schedule options] [--json]
  nightlight-schedule update [schedule options] [--force]

Schedule options (remembered until changed):
  --evening-temp K  --late-temp K  --late-after MINUTES  --off-time HH:MM
"""

import argparse
import re

from . import config, hyprsunset, override, profiles, status


def sync(settings):
    """Everything the widget's poll needs; returns a problem string or None."""
    problem = None
    try:
        profiles.update(settings)
    except Exception as e:
        problem = str(e)
    if hyprsunset.pid() is None and config.CONF.exists():
        hyprsunset.start()
    override.enforce()
    return problem


def hhmm(value):
    if not re.fullmatch(r"([01]?\d|2[0-3]):[0-5]\d", value):
        raise argparse.ArgumentTypeError("expected HH:MM")
    h, m = value.split(":")
    return f"{int(h):02d}:{m}"


def parser():
    p = argparse.ArgumentParser(prog="nightlight-schedule",
                                description="hyprsunset sunset schedule and overrides")
    sub = p.add_subparsers(dest="cmd", required=True)

    schedule_opts = argparse.ArgumentParser(add_help=False)
    schedule_opts.add_argument("--evening-temp", dest="evening_temp", type=int)
    schedule_opts.add_argument("--late-temp", dest="late_temp", type=int)
    schedule_opts.add_argument("--late-after", dest="late_after", type=int,
                               help="minutes after sunset to switch to the late temperature; 0 disables")
    schedule_opts.add_argument("--off-time", dest="off_time", type=hhmm)

    up = sub.add_parser("update", parents=[schedule_opts], help="regenerate today's profiles")
    up.add_argument("--force", action="store_true")
    sub.add_parser("sync", parents=[schedule_opts],
                   help="keep hyprsunset, profiles and override current").add_argument("--json", action="store_true")
    for name in ("status", "resume", "restart"):
        sub.add_parser(name).add_argument("--json", action="store_true")
    sp = sub.add_parser("set", help="override the temperature")
    sp.add_argument("value", help="kelvin, or 'off'")
    sp.add_argument("--until", default="next",
                    help="next (profile switch, default), morning, 1h, 30m or HH:MM")
    sp.add_argument("--json", action="store_true")
    return p


def main(argv=None):
    p = parser()
    args = p.parse_args(argv)

    if args.cmd == "update":
        if profiles.update(profiles.resolve_settings(args), force=args.force):
            print("profiles updated")
            override.enforce()
        status.print_report(False)
        return 0

    ok, problem = True, None
    if args.cmd == "set":
        if args.value != "off" and not args.value.isdigit():
            p.error("value must be kelvin or 'off'")
        try:
            ok = override.set_temperature(args.value, args.until)
        except ValueError as e:
            p.error(str(e))
    elif args.cmd == "resume":
        ok = override.resume()
    elif args.cmd == "restart":
        hyprsunset.restart()
        override.enforce()
    elif args.cmd == "sync":
        problem = sync(profiles.resolve_settings(args))

    status.print_report(args.json, problem)
    return 0 if ok else 1

