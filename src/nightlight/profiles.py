"""Generating hyprsunset.conf from the day's sunset, and reading it back."""

import re
from datetime import date, timedelta

from . import config, hyprsunset, sun


def state_schema(state):
    """Validate the schedule state file, settings included: a file we couldn't
    have written is no basis for deciding hyprsunset.conf is up to date."""
    config.check(isinstance(state, dict), "expected an object")
    config.check_version(state)
    config.check(isinstance(state.get("date"), str), f"bad date {state.get('date')!r}")
    mtime = state.get("weather_mtime")
    config.check(mtime is None or config.is_number(mtime), f"bad weather_mtime {mtime!r}")
    settings = state.get("settings")
    config.check(isinstance(settings, dict), f"bad settings {settings!r}")
    check_settings(settings)
    return state


def check_settings(settings):
    """Raise ValueError unless every schedule setting is present and in range."""
    low, high = config.KELVIN_RANGE
    for key in ("evening_temp", "late_temp"):
        config.check(config.is_int(settings.get(key), low, high),
                     f"bad {key} {settings.get(key)!r}")
    config.check(config.is_int(settings.get("late_after"), 0, 1439),
                 f"bad late_after {settings.get('late_after')!r}")
    config.check(config.is_hhmm(settings.get("off_time")),
                 f"bad off_time {settings.get('off_time')!r}")


def read_state():
    return config.read_json(config.SCHEDULE_STATE, state_schema)


def resolve_settings(options):
    """Schedule settings from `options` (any attributes named like DEFAULTS
    keys), else the last used settings, else DEFAULTS."""
    saved = (read_state() or {}).get("settings", {})
    settings = {}
    for key, default in config.DEFAULTS.items():
        value = getattr(options, key, None)
        settings[key] = value if value is not None else saved.get(key, default)
    return settings


def weather_mtime():
    try:
        return config.WEATHER_LOC.stat().st_mtime
    except OSError:
        return None


def managed():
    """Whether hyprsunset.conf is ours to rewrite. It only becomes ours when
    the user enables the plugin (see lifecycle.enable)."""
    try:
        return config.CONF.read_text().startswith(config.MARKER)
    except OSError:
        return False


def needs_update(settings, today=None):
    today = today or date.today()
    state = read_state() or {}
    return (not managed()
            or state.get("date") != today.isoformat()
            or state.get("settings") != settings
            or state.get("weather_mtime") != weather_mtime())


def render_conf(settings, lat, lon, set_at):
    check_settings(settings)
    oh, om = map(int, settings["off_time"].split(":"))
    until_off = (oh * 60 + om - (set_at.hour * 60 + set_at.minute)) % 1440
    # The morning off time bounds the night, so a profile landing on or after
    # it is dropped rather than emitted at a minute another profile already
    # owns: hyprsunset would pick between them arbitrarily, and the schedule
    # could not be put in order. When sunset itself falls on the off time there
    # is no night window at all, and the day is simply left off.
    blocks = [(settings["off_time"], "identity = true")]
    if until_off > 0:
        blocks.append((f"{set_at:%H:%M}", f"temperature = {settings['evening_temp']}"))
        if 0 < settings["late_after"] < until_off:
            late_at = set_at + timedelta(minutes=settings["late_after"])
            blocks.append((f"{late_at:%H:%M}", f"temperature = {settings['late_temp']}"))
    profiles = "".join(f"\nprofile {{\n    time = {t}\n    {body}\n}}\n" for t, body in blocks)
    return (f"{config.MARKER} — edits will be overwritten.\n"
            f"# Location {lat:.3f},{lon:.3f}; sunset today {set_at:%H:%M}\n"
            f"{profiles}")


def update(settings, force=False, today=None):
    """Regenerate hyprsunset.conf; restart hyprsunset if it changed.

    Refuses to replace a hyprsunset.conf the plugin doesn't manage: taking
    it over needs the user's consent, via lifecycle.enable. Returns whether
    the file changed.
    """
    today = today or date.today()
    path = config.CONF
    if path.exists() and not managed():
        raise RuntimeError("hyprsunset.conf isn't managed by the plugin; enable it first")
    if not force and not needs_update(settings, today):
        return False
    lat, lon = sun.location()
    conf = render_conf(settings, lat, lon, sun.sunset(lat, lon, today))

    changed = not path.exists() or path.read_text() != conf
    if changed:
        config.write_text(path, conf)
    config.write_json(config.SCHEDULE_STATE, config.versioned(
        {"date": today.isoformat(), "settings": settings, "weather_mtime": weather_mtime()}))
    if changed and hyprsunset.pid() is not None:
        hyprsunset.restart()
    return changed


def parse_profiles(text):
    """[(minutes since midnight, kelvin or None for identity)] from a
    hyprsunset.conf, sorted by time.

    Two profiles on the same minute collapse to the last one declared, so the
    result can always be ordered by time alone.
    """
    profiles = {}
    for block in re.findall(r"profile\s*\{(.*?)\}", text, re.S):
        t = re.search(r"time\s*=\s*(\d{1,2}):(\d{2})", block)
        if not t:
            continue
        temp = re.search(r"temperature\s*=\s*(\d+)", block)
        if re.search(r"identity\s*=\s*true", block) or not temp:
            kelvin = None
        else:
            kelvin = int(temp.group(1))
        profiles[int(t.group(1)) * 60 + int(t.group(2))] = kelvin
    return sorted(profiles.items())


def load_profiles():
    try:
        return parse_profiles(config.CONF.read_text())
    except OSError:
        return []
