"""Taking over hyprsunset.conf with the user's consent, and giving it back.

The plugin does nothing until the user enables it from the popup (or with
`nightlight-schedule enable`). Enabling backs up their hyprsunset.conf and
replaces it with the generated schedule; the generated file's marker line is
what records the consent (profiles.managed). Disabling restores the backup and
removes the plugin's state, leaving things as they were before.
"""

import shutil
import time

from . import config, hyprsunset, profiles


def enabled():
    return profiles.managed()


def enable(settings):
    """Back up the user's hyprsunset.conf, generate ours and make sure
    hyprsunset is running with it."""
    conf = config.CONF
    moved_to = None
    if conf.exists() and not profiles.managed():
        # The first backup is the one disable restores; never lose a later
        # foreign file either (e.g. one reset by `omarchy refresh`)
        moved_to = config.CONF_BACKUP
        if moved_to.exists():
            moved_to = moved_to.with_name(f"{moved_to.name}.{int(time.time())}")
        shutil.move(conf, moved_to)
    try:
        profiles.update(settings, force=True)
    except Exception:
        # e.g. no location yet: put the user's file back untouched
        if moved_to is not None:
            shutil.move(moved_to, conf)
        raise
    if hyprsunset.pid() is None:
        hyprsunset.start()


def disable():
    """Restore the user's hyprsunset.conf and forget all plugin state.

    Returns a short description of what was done.
    """
    config.OVERRIDE.unlink(missing_ok=True)
    config.SCHEDULE_STATE.unlink(missing_ok=True)
    config.PENDING_RESTORE.unlink(missing_ok=True)
    if not profiles.managed():
        return "nothing to restore: hyprsunset.conf isn't managed by the plugin"
    if config.CONF_BACKUP.exists():
        shutil.move(config.CONF_BACKUP, config.CONF)
        if hyprsunset.pid() is not None:
            hyprsunset.restart()
        return "restored the previous hyprsunset.conf"
    # There was no config before the plugin, so there's nothing for
    # hyprsunset to follow: remove ours and stop the hyprsunset we started
    config.CONF.unlink()
    hyprsunset.stop()
    return "removed the generated hyprsunset.conf and stopped hyprsunset"
