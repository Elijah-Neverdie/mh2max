# -*- coding: utf-8 -*-
"""Install MetaHuman tools as a top-level menu (never touch File menu)."""
from __future__ import print_function

import importlib
import sys

from maya import cmds
import maya.mel as mel

# Dedicated top-level menu — do NOT install into mainFileMenu
# (File menu uses postMenuCommand=buildFileMenu; injecting items breaks it).
MENU_NAME = "mh2maxMenu"
OLD_FILE_SUBMENU = "mh2max_fileMenu"
OLD_FILE_DIVIDER = "mh2max_fileDiv"


def reload_package():
    mods = [n for n in list(sys.modules) if n == "mh2max" or n.startswith("mh2max.")]
    for name in sorted(mods, reverse=True):
        try:
            importlib.reload(sys.modules[name])
        except Exception:
            pass


def _on_export(*_args):
    # Instant feedback before reload (avoids blank freeze)
    try:
        cmds.progressWindow(
            title=u"导出至 3ds Max",
            progress=0,
            status=u"正在启动导出…",
            isInterruptable=False,
            minValue=0,
            maxValue=100,
        )
        cmds.refresh(force=True)
    except Exception:
        pass
    try:
        reload_package()
        from mh2max.pipeline import run_export_ui

        run_export_ui()
    finally:
        try:
            cmds.progressWindow(endProgress=True)
        except Exception:
            pass


def _on_detect(*_args):
    reload_package()
    from mh2max.detect import detect_scene

    info = detect_scene()
    if not info.get("ok"):
        cmds.confirmDialog(
            title="MetaHuman",
            message="\n".join(info.get("errors") or ["未检测到"]),
            button=[u"确定"],
        )
        return
    msg = u"角色：%s\n体型：%s\n头：%s\n身：%s\nCTRL：%s" % (
        info.get("character"),
        info.get("body_type"),
        info.get("head"),
        info.get("body") or u"（无）",
        info.get("ctrl_count"),
    )
    cmds.confirmDialog(title="MetaHuman", message=msg, button=[u"确定"])


def _on_import_mh(*_args):
    # Instant feedback before reload / heavy imports (avoids 2–3s frozen menu click)
    try:
        cmds.waitCursor(state=True)
    except Exception:
        pass
    try:
        cmds.progressWindow(
            title=u"导入 MH",
            progress=0,
            status=u"正在启动导入…",
            isInterruptable=False,
            minValue=0,
            maxValue=100,
        )
        cmds.refresh(force=True)
    except Exception:
        pass
    try:
        reload_package()
        try:
            cmds.progressWindow(edit=True, status=u"正在打开导入界面…", progress=20)
        except Exception:
            pass
        from mh2max.import_ue58 import run_import_mh_ui

        run_import_mh_ui()
    finally:
        try:
            cmds.progressWindow(endProgress=True)
        except Exception:
            pass
        try:
            cmds.waitCursor(state=False)
        except Exception:
            pass


def _restore_file_menu():
    """Remove leftover mh2max items from File and force Maya to rebuild it."""
    for item in (OLD_FILE_SUBMENU, OLD_FILE_DIVIDER):
        if cmds.menuItem(item, exists=True):
            try:
                cmds.deleteUI(item, menuItem=True)
            except Exception:
                pass
    # Also clear any orphaned children if submenu still exists as UI
    try:
        if cmds.menu(OLD_FILE_SUBMENU, exists=True):
            cmds.deleteUI(OLD_FILE_SUBMENU, menu=True)
    except Exception:
        pass

    if not cmds.menu("MayaWindow|mainFileMenu", exists=True):
        return
    try:
        # Ensure postMenuCommand is the stock rebuild
        cmds.menu("MayaWindow|mainFileMenu", edit=True, postMenuCommand="buildFileMenu();")
        mel.eval("buildFileMenu();")
        print("[mh2max] File menu restored via buildFileMenu()")
    except Exception as ex:
        print("[mh2max] File menu restore failed:", ex)


def uninstall():
    _restore_file_menu()
    for name in (MENU_NAME, "mh2maxTopMenu"):
        if cmds.menu(name, exists=True):
            try:
                cmds.deleteUI(name, menu=True)
            except Exception:
                pass


def _add_menu_items(parent):
    cmds.menuItem(
        parent=parent,
        label=u"导入 MH",
        command=_on_import_mh,
        annotation=u"导入 UE 5.6+ DCC Export zip（head.dna + body.dna）并装配",
    )
    cmds.menuItem(
        parent=parent,
        label=u"导出至 3ds Max",
        command=_on_export,
        annotation=u"未装配则自动装配，再导出到 3ds Max",
    )
    cmds.menuItem(parent=parent, label=u"检测当前角色", command=_on_detect)


def install():
    if cmds.about(batch=True):
        return
    if not cmds.window("MayaWindow", exists=True):
        cmds.evalDeferred(install, lowestPriority=True)
        return

    # Always scrub File menu first (fixes previous broken installs)
    _restore_file_menu()

    if cmds.menu(MENU_NAME, exists=True):
        try:
            cmds.deleteUI(MENU_NAME, menu=True)
        except Exception:
            pass

    # Prefer Epic MetaHuman menu if present; else own top-level menu
    parent = None
    if cmds.menu("MetaHuman", exists=True):
        parent = "MetaHuman"
        # divider + our tools inside Epic menu
        try:
            cmds.menuItem(divider=True, dividerLabel="mh2max", parent=parent)
        except Exception:
            pass
        _add_menu_items(parent)
        print("[mh2max] items installed under MetaHuman menu")
        return

    menu = cmds.menu(MENU_NAME, label="MH2Max", parent="MayaWindow", tearOff=True)
    _add_menu_items(menu)
    print("[mh2max] top-level MH2Max menu installed")
