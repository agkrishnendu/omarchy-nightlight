# Sunset Night Light for Omarchy

An [Omarchy](https://omarchy.org) shell plugin that warms your screen at your
local sunset instead of at fixed times. It also adds a bar icon that shows what
the night light is doing and lets you override it.

- **Follows the sun.** Every day it works out sunset for your location and
  schedules [hyprsunset](https://github.com/hyprwm/hyprsunset):
  - 3400K at sunset
  - 2700K three hours later
  - off at 07:00

  All of these are configurable.
- **Bar icon.** A moon appears in the evening, or while an override is on, and
  is hidden during the day. It is highlighted while an override is on and
  shows a warning if hyprsunset stops responding.
- **Popup.** Shows today's schedule, preset buttons (Off, the scheduled
  temperatures), a temperature slider, and how long to hold an override: until
  the next scheduled change, for an hour, or until morning. *Resume schedule*
  ends an override.
- **Overrides persist.** hyprsunset normally drops a manual temperature at its
  next scheduled switch. The plugin re-applies an override until it expires,
  even across hyprsunset restarts.

## Install

```bash
omarchy plugin add https://github.com/<you>/omarchy-nightlight.git --enable
```

It needs `hyprsunset` and `python3`, which Omarchy already ships. You don't
need to change your autostart or add a systemd timer. The plugin starts
hyprsunset and refreshes the schedule by itself while the shell is running.

To update, run `omarchy plugin update krisag.nightlight`, then
`omarchy restart shell`. Without the restart, the shell's hot reload can leave
the old copy of the widget running alongside the new one.

### Remove the built-in night light toggle (recommended)

Omarchy's indicators widget has its own night light toggle, which switches
between 4000K and 6500K and ignores the schedule. To hide it, list the other
indicators on the `omarchy.indicators` entry in `~/.config/omarchy/shell.json`:

```json
{ "id": "omarchy.indicators", "items": ["Dictation", "ScreenRecording", "Reminder", "Dnd", "StayAwake"] }
```

The `omarchy toggle nightlight` keybinding still works. A temperature set with
it lasts until the next scheduled change.

## Using it

| On the bar icon | Does |
|-----------------|------|
| Left click      | Open the popup |
| Right click     | Turn off until the next scheduled change, or resume the schedule if an override is on |
| Middle click    | Refresh |

The icon is hidden during the day. To open the popup anyway, for example from
a keybinding, run:

```bash
omarchy-shell krisag.nightlight open    # also: close, toggle, refresh, resume
```

## Settings

Edit these in the Omarchy settings panel, or on the plugin's entry in
`shell.json`:

| Key | Default | Meaning |
|-----|---------|---------|
| `eveningTemperature` | `3400` | Kelvin applied at sunset |
| `lateTemperature` | `2700` | Kelvin applied later in the evening |
| `lateAfterMinutes` | `180` | Minutes after sunset to switch to the late temperature; `0` disables it |
| `offTime` | `"07:00"` | When the filter turns off in the morning |

### Location

The plugin uses the location set in Omarchy's weather widget (click the place
name in the weather popup). Without one, it detects your location from your IP
address through wttr.in and caches the result.

## Command line

The widget is a thin front end to the bundled `nightlight-schedule` script,
which you can also run yourself:

```bash
S=~/.config/omarchy/plugins/krisag.nightlight/nightlight-schedule
$S status                         # now 3400K, 2700K at 21:18
$S set 2700 --until morning       # --until next | morning | 1h | 30m | HH:MM
$S set off                        # off until the next scheduled change
$S resume                         # back to the schedule
$S restart                        # if hyprsunset stops answering
$S status --json                  # what the widget reads
```

## How it works

- On each run it writes `~/.config/hypr/hyprsunset.conf` with the day's
  profiles, but only when the date, your settings or the weather location has
  changed. It restarts hyprsunset only if the file actually changed.
- The widget runs `nightlight-schedule sync` every 30 seconds and again right
  after each scheduled change. `sync` does three things:
  1. starts hyprsunset if it isn't running
  2. refreshes the profiles when needed
  3. re-applies an active override
- Its state is kept in `~/.local/state/nightlight-schedule/`: the override,
  the last settings used, and the cached coordinates.

## Uninstall

```bash
omarchy plugin remove krisag.nightlight
```

On its first run the plugin backs up your original `hyprsunset.conf` to
`hyprsunset.conf.pre-nightlight`. To restore it:

```bash
mv ~/.config/hypr/hyprsunset.conf.pre-nightlight ~/.config/hypr/hyprsunset.conf
pkill -x hyprsunset; omarchy toggle nightlight   # restart it with the old config
rm -rf ~/.local/state/nightlight-schedule
```

## License

MIT
