"""Talking to hyprsunset over hyprctl, and starting/stopping it."""

import re
import shutil
import subprocess
import time


def hyprctl(*args):
    """Output of `hyprctl hyprsunset ARGS`, or None if IPC is unreachable."""
    try:
        r = subprocess.run(["hyprctl", "hyprsunset", *args],
                           capture_output=True, text=True, timeout=3)
    except (OSError, subprocess.TimeoutExpired):
        return None
    out = r.stdout.strip()
    if r.returncode != 0 or out.startswith("Couldn't connect"):
        return None
    return out


def current_temp():
    """Temperature hyprsunset reports, or None if its IPC is unreachable.

    After `identity` it keeps reporting the previous temperature, so this
    can't tell whether the filter is off — the schedule/override decide that.
    """
    m = re.search(r"\d+", hyprctl("temperature") or "")
    return int(m.group()) if m else None


def pid():
    r = subprocess.run(["pgrep", "-x", "hyprsunset"], capture_output=True, text=True)
    pids = r.stdout.split()
    return int(pids[0]) if pids else None


def apply(temp):
    """Set hyprsunset to `temp` kelvin, or identity (off) when None."""
    if temp is None:
        return hyprctl("identity") == "ok"
    return hyprctl("temperature", str(temp)) == "ok"


def start():
    # Start it in its own systemd scope so it outlives whoever launched us
    if shutil.which("uwsm-app"):
        subprocess.run(["uwsm-app", "-t", "service", "--", "hyprsunset"], check=False)
    else:
        subprocess.Popen(["hyprsunset"], start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(50):
        if current_temp() is not None:
            break
        time.sleep(0.1)
    # A fresh hyprsunset applies its profile at the end of boot, clobbering
    # anything set before then
    time.sleep(1)


def stop():
    subprocess.run(["pkill", "-x", "hyprsunset"], check=False)
    for _ in range(50):
        if pid() is None:
            break
        time.sleep(0.1)
    time.sleep(0.5)  # let the compositor release the CTM manager


def restart():
    stop()
    start()
