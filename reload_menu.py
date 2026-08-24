# -*- coding: utf-8 -*-
"""Drag into Maya Script Editor: restore File menu + reload MH2Max menu."""
from __future__ import print_function

import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
scripts = os.path.join(ROOT, "scripts")
if scripts not in sys.path:
    sys.path.insert(0, scripts)

import mh2max.menu as menu

menu.reload_package()
import mh2max.menu as menu

menu.install()
print("[mh2max] File menu restored; use top menu MH2Max (or MetaHuman) — 导入 MH")
