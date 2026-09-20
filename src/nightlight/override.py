"""Manual overrides, and keeping them applied until they expire.

hyprsunset drops a manual temperature at its next profile switch, so the
override lives in config.OVERRIDE and `enforce` puts it back.

Dropping an override owes the screen the scheduled temperature. That debt is
recorded in config.PENDING_RESTORE before the override goes away and cleared
only once hyprsunset accepts the temperature, so a failed IPC call is retried
by the next `enforce` instead of leaving the override on screen until the next
scheduled transition.
"""

from datetime import datetime

from . import config, hyprsunset, profiles, schedule


def override_schema(ov):
    """Validate an override file: anything we couldn't have written is junk."""
    config.check(isinstance(ov, dict), "expected an object")
    config.check_version(ov)
    # null means "off", but callers index ov["temperature"], so it must be present
    config.check("temperature" in ov, "missing temperature")
    temp = ov["temperature"]
    config.check(temp is None or config.is_int(temp, *config.KELVIN_RANGE),
                 f"bad temperature {temp!r}")
    config.check(isinstance(ov.get("hold"), str), f"bad hold {ov.get('hold')!r}")
    for key in ("until", "applied_at"):
        config.check(config.is_timestamp(ov.get(key)), f"bad {key} {ov.get(key)!r}")
    pid = ov.get("pid")
    config.check(pid is None or config.is_int(pid, 1), f"bad pid {pid!r}")
    return ov


def restore_schema(state):
    config.check(isinstance(state, dict), "expected an object")
    config.check_version(state)
    config.check(config.is_number(state.get("since")), f"bad since {state.get('since')!r}")
    return state


def current(now=None):
    """The active override dict, or None if there is none or it expired."""
    now = now or datetime.now()
    ov = _stored(now)
    if ov and ov["until"] <= now.timestamp():
        return None
    return ov


def set_temperature(value, hold):
    """Override with `value` kelvin (or "off") until `hold` (see
    schedule.hold_until). Returns whether hyprsunset took it."""
    now = datetime.now()
    low, high = config.KELVIN_RANGE
    temp = None if value == "off" else max(low, min(high, int(value)))
    until = schedule.hold_until(hold, now, schedule.occurrences(profiles.load_profiles(), now))
    ok = hyprsunset.apply(temp)
    config.write_json(config.OVERRIDE, config.versioned({
        "temperature": temp,
        "hold": hold,
        "until": until.timestamp(),
        # 0 makes the next enforce retry if hyprsunset didn't take it
        "applied_at": now.timestamp() if ok else 0,
        "pid": hyprsunset.pid(),
    }))
    # This override replaces whatever we still owed the schedule
    config.PENDING_RESTORE.unlink(missing_ok=True)
    return ok


def resume():
    """Drop any override and go back to the scheduled temperature."""
    now = datetime.now()
    occ = schedule.occurrences(profiles.load_profiles(), now)
    # Record the debt first: if we die between here and a successful apply, the
    # next enforce still knows the screen is owed its scheduled temperature.
    _owe_restore(now)
    config.OVERRIDE.unlink(missing_ok=True)
    return _restore_schedule(occ, now)


def enforce():
    """Expire a finished override, re-apply a live one hyprsunset undid, or
    retry a restore that didn't land."""
    now = datetime.now()
    occ = schedule.occurrences(profiles.load_profiles(), now)
    ov = _stored(now)
    if ov is None:
        if config.read_json(config.PENDING_RESTORE, restore_schema) is not None:
            _restore_schedule(occ, now)
        return
    if ov["until"] <= now.timestamp():
        _owe_restore(now)
        config.OVERRIDE.unlink(missing_ok=True)
        _restore_schedule(occ, now)
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
            config.write_json(config.OVERRIDE, config.versioned(ov))


def _stored(now):
    """The override file as written, or None.

    An unreadable file is discarded by read_json. Whatever it said, the screen
    may still be holding that override, so we owe it the scheduled temperature
    and let the next enforce apply it — even on a read-only path like status,
    which would otherwise discard the file before enforce ever saw it.
    """
    existed = config.OVERRIDE.exists()
    ov = config.read_json(config.OVERRIDE, override_schema)
    if ov is None and existed:
        _owe_restore(now)
    return ov


def _owe_restore(now):
    config.write_json(config.PENDING_RESTORE, config.versioned({"since": now.timestamp()}))


def _restore_schedule(occ, now):
    """Apply the scheduled temperature, keeping the debt until hyprsunset
    takes it. Returns whether the screen is now where the schedule wants it."""
    active, _ = schedule.active_and_next(occ, now)
    if active is None or hyprsunset.apply(active[1]):
        config.PENDING_RESTORE.unlink(missing_ok=True)
        return True
    return False
