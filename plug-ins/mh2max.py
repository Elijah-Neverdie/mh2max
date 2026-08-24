# -*- coding: utf-8 -*-
"""Maya plugin stub. UI is installed later from userSetup so splash is not blocked."""
from __future__ import print_function

import sys

import maya.OpenMayaMPx as omp

PLUGIN_VENDOR = "mh2max"
PLUGIN_VERSION = "1.3.3"


def initializePlugin(mobject):
    omp.MFnPlugin(mobject, PLUGIN_VENDOR, PLUGIN_VERSION, "Any")
    sys.stdout.write("[mh2max] plugin registered (menu comes from userSetup)\n")


def uninitializePlugin(mobject):
    omp.MFnPlugin(mobject)
    try:
        import mh2max.menu as menu

        menu.uninstall()
    except Exception:
        pass
    sys.stdout.write("[mh2max] plugin unloaded\n")
