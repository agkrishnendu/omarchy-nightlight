"""Generating hyprsunset.conf from the day's sunset, and reading it back."""

import re
import shutil
from datetime import date, timedelta

from . import config, hyprsunset, sun


def resolve_settings(options):
    """Schedule settings from `options` (any attributes named like DEFAULTS
    keys), else the last used settings, else DEFAULTS."""
    saved = (config.read_json(config.SCHEDULE_STATE) or {}).get("settings", {})
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


def needs_update(settings, today=None):
    today = today or date.today()
    state = config.read_json(config.SCHEDULE_STATE) or {}
    try:
        ours = config.CONF.read_text().startswith(config.MARKER)
    except OSError:
        ours = False
    return (not ours
            or state.get("date") != today.isoformat()
            or state.get("settings") != settings
            or state.get("weather_mtime") != weather_mtime())


def render_conf(settings, lat, lon, set_at):
    blocks = [
        (settings["off_time"], "identity = true"),
        (f"{set_at:%H:%M}", f"temperature = {settings['evening_temp']}"),
    ]
    # Skip the late profile when it would land at or after the morning off time
    oh, om = map(int, settings["off_time"].split(":"))
    until_off = (oh * 60 + om - (set_at.hour * 60 + set_at.minute)) % 1440
    if 0 < settings["late_after"] < until_off:
        late_at = set_at + timedelta(minutes=settings["late_after"])
        blocks.append((f"{late_at:%H:%M}", f"temperature = {settings['late_temp']}"))
    profiles = "".join(f"\nprofile {{\n    time = {t}\n    {body}\n}}\n" for t, body in blocks)
    return (f"{config.MARKER} — edits will be overwritten.\n"
            f"# Location {lat:.3f},{lon:.3f}; sunset today {set_at:%H:%M}\n"
            f"{profiles}")


def update(settings, force=False, today=None):
    """Regenerate hyprsunset.conf; restart hyprsunset if it changed.

    Returns whether the file changed.
    """
    today = today or date.today()
    if not force and not needs_update(settings, today):
        return False
    lat, lon = sun.location()
    conf = render_conf(settings, lat, lon, sun.sunset(lat, lon, today))
    path = config.CONF

    # Keep whatever the user had before we first took over the file
    if path.exists() and not path.read_text().startswith(config.MARKER) and not config.CONF_BACKUP.exists():
        shutil.copy2(path, config.CONF_BACKUP)

    changed = not path.exists() or path.read_text() != conf
    if changed:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(conf)
    config.write_json(config.SCHEDULE_STATE, {"date": today.isoformat(), "settings": settings,
                                              "weather_mtime": weather_mtime()})
    if changed and hyprsunset.pid() is not None:
        hyprsunset.restart()
    return changed


def parse_profiles(text):
    """[(minutes since midnight, kelvin or None for identity)] from a
    hyprsunset.conf, sorted by time."""
    profiles = []
    for block in re.findall(r"profile\s*\{(.*?)\}", text, re.S):
        t = re.search(r"time\s*=\s*(\d{1,2}):(\d{2})", block)
        if not t:
            continue
        temp = re.search(r"temperature\s*=\s*(\d+)", block)
        if re.search(r"identity\s*=\s*true", block) or not temp:
            kelvin = None
        else:
            kelvin = int(temp.group(1))
        profiles.append((int(t.group(1)) * 60 + int(t.group(2)), kelvin))
    return sorted(profiles)


def load_profiles():
    try:
        return parse_profiles(config.CONF.read_text())
    except OSError:
        return []
