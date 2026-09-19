"""f.lux-style night light schedule for hyprsunset.

Part of the krisag.nightlight Omarchy shell plugin. Computes today's sunset
for your location and rewrites ~/.config/hypr/hyprsunset.conf with:

  sunset              -> evening temperature
  sunset + late-after -> late temperature (skipped when late-after is 0)
  off-time            -> off (identity)

The bar widget runs `sync` every 30 seconds, which keeps hyprsunset running,
regenerates the profiles when the day, settings or location change, and
re-applies any active override. hyprsunset reverts a manual temperature at its
next profile switch, so an override that outlives a switch is kept in a state
file and re-applied by `sync`.

Modules:
  config      paths, defaults, JSON state helpers
  sun         location lookup and sunset calculation
  hyprsunset  IPC with and process control of hyprsunset
  lifecycle   enabling (with consent) and disabling (restoring the config)
  profiles    generating and reading hyprsunset.conf
  schedule    pure time logic over the daily profiles
  override    manual overrides and keeping them applied
  status      the status report the widget renders
  cli         command-line interface
"""
