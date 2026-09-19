"""The status report: JSON for the widget, a line of text for people."""

import json
from datetime import datetime

from . import hyprsunset, override, profiles, schedule


def report(problem=None):
    now = datetime.now()
    profs = profiles.load_profiles()
    active, nxt = schedule.active_and_next(schedule.occurrences(profs, now), now)
    ov = override.current(now)
    temp = hyprsunset.current_temp()
    scheduled = active[1] if active else None
    return {
        "ok": temp is not None,
        "running": hyprsunset.pid() is not None,
        "problem": problem,
        "temperature": temp,
        "effective": ov["temperature"] if ov else scheduled,
        "night": scheduled is not None,
        "scheduled": {"time": active[0].strftime("%H:%M"), "temperature": scheduled} if active else None,
        "next": {"time": nxt[0].strftime("%H:%M"), "temperature": nxt[1],
                 "epoch": int(nxt[0].timestamp())} if nxt else None,
        "override": {
            "temperature": ov["temperature"],
            "hold": ov["hold"],
            "until": int(ov["until"]),
            "untilLabel": datetime.fromtimestamp(ov["until"]).strftime("%H:%M"),
        } if ov else None,
        "profiles": [{"time": f"{m // 60:02d}:{m % 60:02d}", "temperature": k} for m, k in profs],
        "presets": sorted({k for _, k in profs if k is not None}, reverse=True),
    }


def kelvin_label(k):
    return "off" if k is None else f"{k}K"


def describe(s):
    lines = []
    if s["problem"]:
        lines.append(f"problem: {s['problem']}")
    if not s["running"]:
        lines.append("hyprsunset is not running")
    elif not s["ok"]:
        lines.append("hyprsunset is running but not answering IPC (try: nightlight-schedule restart)")
    line = f"now {kelvin_label(s['effective'])}"
    if s["override"]:
        line += f" (override until {s['override']['untilLabel']})"
    elif s["next"]:
        line += f", {kelvin_label(s['next']['temperature'])} at {s['next']['time']}"
    lines.append(line)
    return "\n".join(lines)


def print_report(as_json, problem=None):
    s = report(problem)
    print(json.dumps(s) if as_json else describe(s))
