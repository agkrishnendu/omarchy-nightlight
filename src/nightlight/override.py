"""Manual overrides, and keeping them applied until they expire.

hyprsunset drops a manual temperature at its next profile switch, so the
override lives in config.OVERRIDE and `enforce` puts it back.
"""

from datetime import datetime

from . import config, hyprsunset, profiles, schedule


def current(now=None):
    """The active override dict, or None if there is none or it expired."""
    now = now or datetime.now()
    ov = config.read_json(config.OVERRIDE)
    if ov and ov["until"] <= now.timestamp():
        return None
    return ov


def set_temperature(value, hold):
    """Override with `value` kelvin (or "off") until `hold` (see
    schedule.hold_until). Returns whether hyprsunset took it."""
    now = datetime.now()
    temp = None if value == "off" else max(1000, min(20000, int(value)))
    until = schedule.hold_until(hold, now, schedule.occurrences(profiles.load_profiles(), now))
    ok = hyprsunset.apply(temp)
    config.write_json(config.OVERRIDE, {
        "temperature": temp,
        "hold": hold,
        "until": until.timestamp(),
        # 0 makes the next enforce retry if hyprsunset didn't take it
        "applied_at": now.timestamp() if ok else 0,
        "pid": hyprsunset.pid(),
    })
    return ok


def resume():
    """Drop any override and go back to the scheduled temperature."""
    config.OVERRIDE.unlink(missing_ok=True)
    now = datetime.now()
    active, _ = schedule.active_and_next(schedule.occurrences(profiles.load_profiles(), now), now)
    return hyprsunset.apply(active[1]) if active else True


def enforce():
    """Expire a finished override, or re-apply a live one hyprsunset undid."""
    now = datetime.now()
    occ = schedule.occurrences(profiles.load_profiles(), now)
    ov = config.read_json(config.OVERRIDE)
    if ov is None:
        return
    if ov["until"] <= now.timestamp():
        config.OVERRIDE.unlink(missing_ok=True)
        active, _ = schedule.active_and_next(occ, now)
        if active:
            hyprsunset.apply(active[1])
        return

    pid = hyprsunset.pid()
    # An apply within a minute of a profile switch may have raced hyprsunset
    # switching, and identity can't be verified by reading back, so redo it
    switched = any(dt <= now and ov["applied_at"] < dt.timestamp() + 60 for dt, _ in occ)
    drifted = ov["temperature"] is not None and hyprsunset.current_temp() != ov["temperature"]
    if switched or drifted or pid != ov.get("pid"):
        if hyprsunset.apply(ov["temperature"]):
            ov["applied_at"] = now.timestamp()
            ov["pid"] = pid
            config.write_json(config.OVERRIDE, ov)
