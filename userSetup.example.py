# -*- coding: utf-8 -*-
"""Copy the block below into Documents/maya/scripts/userSetup.py (create if missing).

Defers mh2max menu install until after Maya UI is up (avoids blocking the splash).
"""
from __future__ import print_function

try:
    import maya.utils as utils

    def _mh2max_install_menu():
        try:
            import mh2max.menu as menu

            menu.install()
        except Exception as ex:
            print("[mh2max] menu install deferred failed:", ex)

    utils.executeDeferred(_mh2max_install_menu, lowestPriority=True)
except Exception:
    pass
