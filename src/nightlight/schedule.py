"""Pure time logic over the daily profiles. No I/O, so it's easy to test.

Profiles are [(minutes since midnight, kelvin or None)] as returned by
profiles.parse_profiles; they repeat every day.
"""

import re
from datetime import timedelta


def occurrences(profiles, now):
    """(start datetime, kelvin) for every profile from yesterday through the
    day after tomorrow, sorted."""
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return sorted(((midnight + timedelta(days=d, minutes=m), k)
                   for d in (-1, 0, 1, 2) for m, k in profiles),
                  key=lambda o: o[0])


def active_and_next(occ, now):
    """The occurrence in effect at `now` and the one after it (either may be
    None when there are no profiles)."""
    past = [o for o in occ if o[0] <= now]
    future = [o for o in occ if o[0] > now]
    return (past[-1] if past else None), (future[0] if future else None)


def hold_until(hold, now, occ):
    """Resolve an --until value to the datetime an override ends.

    next     the next profile switch
    morning  the next switch to off
    Nh, Nm   a duration from now
    HH:MM    the next time the clock shows HH:MM
    """
    _, nxt = active_and_next(occ, now)
    if hold == "next":
        return nxt[0] if nxt else now + timedelta(hours=1)
    if hold == "morning":
        off = [dt for dt, k in occ if dt > now and k is None]
        return off[0] if off else hold_until("next", now, occ)
    m = re.fullmatch(r"(\d+)([mh])", hold)
    if m:
        n = int(m.group(1))
        return now + (timedelta(hours=n) if m.group(2) == "h" else timedelta(minutes=n))
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", hold)
    if m:
        at = now.replace(hour=int(m.group(1)), minute=int(m.group(2)), second=0, microsecond=0)
        return at if at > now else at + timedelta(days=1)
    raise ValueError(f"bad --until value: {hold}")
