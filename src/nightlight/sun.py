"""Where we are and when the sun sets there."""

import json
import math
import urllib.request
from datetime import datetime, timedelta, timezone

from . import config


def coords_schema(cached):
    """Validate cached coordinates: a bad cache would produce a bad schedule."""
    config.check(isinstance(cached, list) and len(cached) == 2,
                 f"expected [lat, lon], got {cached!r}")
    lat, lon = cached
    config.check(config.is_number(lat, -90, 90), f"bad latitude {lat!r}")
    config.check(config.is_number(lon, -180, 180), f"bad longitude {lon!r}")
    return [float(lat), float(lon)]


def location():
    """(lat, lon) from the Omarchy weather widget's setting, else IP
    detection via wttr.in, else the last cached coordinates."""
    try:
        d = json.loads(config.WEATHER_LOC.read_text())
        return float(d["latitude"]), float(d["longitude"])
    except Exception:
        pass
    try:
        with urllib.request.urlopen("https://wttr.in/?format=j1", timeout=10) as r:
            area = json.load(r)["nearest_area"][0]
        coords = float(area["latitude"]), float(area["longitude"])
        config.write_json(config.CACHE, coords)
        return coords
    except Exception:
        pass
    cached = config.read_json(config.CACHE, coords_schema)
    if cached is None:
        raise RuntimeError("no location: set one in the weather widget, or connect to the internet")
    return tuple(cached)


def sunset(lat, lon, day):
    """Local sunset time (NOAA solar position algorithm)."""
    n = day.timetuple().tm_yday
    g = 2 * math.pi / 365 * (n - 1)
    eqtime = 229.18 * (0.000075 + 0.001868 * math.cos(g) - 0.032077 * math.sin(g)
                       - 0.014615 * math.cos(2 * g) - 0.040849 * math.sin(2 * g))
    decl = (0.006918 - 0.399912 * math.cos(g) + 0.070257 * math.sin(g)
            - 0.006758 * math.cos(2 * g) + 0.000907 * math.sin(2 * g)
            - 0.002697 * math.cos(3 * g) + 0.00148 * math.sin(3 * g))
    phi = math.radians(lat)
    cos_ha = (math.cos(math.radians(90.833)) / (math.cos(phi) * math.cos(decl))
              - math.tan(phi) * math.tan(decl))
    ha = math.degrees(math.acos(max(-1.0, min(1.0, cos_ha))))
    utc_minutes = 720 - 4 * (lon - ha) - eqtime
    utc = datetime(day.year, day.month, day.day, tzinfo=timezone.utc) + timedelta(minutes=utc_minutes)
    return utc.astimezone()
