# -*- coding: utf-8 -*-
"""Open MeshToMetahuman Maya -> UE controller livelink panel."""
from __future__ import print_function

import importlib.util
import os

from maya import cmds

_SCRIPT_CANDIDATES = [
    r"D:/Unreal Projects/MeshToMetahuman/Import/YjMale/scripts/maya_ue_ctrl_livelink.py",
    os.path.join(
        os.environ.get("USERPROFILE") or "",
        "Unreal Projects",
        "MeshToMetahuman",
        "Import",
        "YjMale",
        "scripts",
        "maya_ue_ctrl_livelink.py",
    ),
]


def _find_script():
    for path in _SCRIPT_CANDIDATES:
        if path and os.path.isfile(path):
            return os.path.normpath(path)
    return None


def _load_module():
    path = _find_script()
    if not path:
        raise RuntimeError(
            u"找不到 maya_ue_ctrl_livelink.py\n"
            u"请确认 MeshToMetahuman 工程在：\n"
            u"D:/Unreal Projects/MeshToMetahuman"
        )
    spec = importlib.util.spec_from_file_location("maya_ue_ctrl_livelink", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(u"无法加载: %s" % path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def show_sync_ui():
    mod = _load_module()
    if hasattr(mod, "show_ui"):
        mod.show_ui()
        return
    raise RuntimeError("maya_ue_ctrl_livelink.py 缺少 show_ui()")


def reset_controllers(push_ue=True):
    mod = _load_module()
    if hasattr(mod, "reset_controllers"):
        return mod.reset_controllers(push_ue=push_ue)
    raise RuntimeError("maya_ue_ctrl_livelink.py 缺少 reset_controllers()")
