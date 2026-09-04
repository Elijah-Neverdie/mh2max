# -*- coding: utf-8 -*-
"""Install MetaHuman tools as a top-level menu (never touch File menu)."""
from __future__ import print_function

import importlib
import sys

from maya import cmds
import maya.mel as mel

from . import __version__

# Dedicated top-level menu — do NOT install into mainFileMenu
MENU_NAME = "mh2maxMenu"
OLD_FILE_SUBMENU = "mh2max_fileMenu"
OLD_FILE_DIVIDER = "mh2max_fileDiv"

ITEM_VERSION = "mh2max_mi_version"
ITEM_IMPORT = "mh2max_mi_import"
ITEM_DETECT = "mh2max_mi_detect"
ITEM_EXPORT = "mh2max_mi_export"
ITEM_TOGGLE_CTRL = "mh2max_mi_toggle_ctrl"
ITEM_UE_CTRL_SYNC = "mh2max_mi_ue_ctrl_sync"
ITEM_UPDATE = "mh2max_mi_update"
OPT_EXPORT_READY = "mh2max_exportReady"


def reload_package():
    mods = [n for n in list(sys.modules) if n == "mh2max" or n.startswith("mh2max.")]
    for name in sorted(mods, reverse=True):
        try:
            importlib.reload(sys.modules[name])
        except Exception:
            pass


def _set_export_ready(ready):
    try:
        cmds.optionVar(iv=(OPT_EXPORT_READY, 1 if ready else 0))
    except Exception:
        pass
    _refresh_export_enable()


def is_export_ready():
    try:
        if cmds.optionVar(exists=OPT_EXPORT_READY):
            return bool(cmds.optionVar(q=OPT_EXPORT_READY))
    except Exception:
        pass
    # auto: detect scene if possible without UI
    try:
        from mh2max.detect import detect_scene

        return bool(detect_scene().get("ok"))
    except Exception:
        return False


def _refresh_export_enable():
    if not cmds.menuItem(ITEM_EXPORT, exists=True):
        return
    try:
        cmds.menuItem(ITEM_EXPORT, e=True, enable=is_export_ready())
    except Exception:
        pass


def _on_export(*_args):
    if not is_export_ready():
        cmds.confirmDialog(
            title=u"导出至 3ds Max",
            message=u"请先「检测当前角色」成功，或「导入 MH」成功后再导出。",
            button=[u"确定"],
        )
        return
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
    own_prog = False
    try:
        cmds.progressWindow(
            title=u"检测当前角色",
            progress=5,
            status=u"正在加载模块…",
            isInterruptable=False,
            minValue=0,
            maxValue=100,
        )
        own_prog = True
        cmds.refresh(force=True)
    except Exception:
        pass

    try:
        reload_package()
        try:
            cmds.progressWindow(edit=True, progress=20, status=u"正在分析场景…")
            cmds.refresh(force=True)
        except Exception:
            pass
        from mh2max.detect import detect_scene

        info = detect_scene()
        try:
            cmds.progressWindow(edit=True, progress=55, status=u"检测完成，整理结果…")
        except Exception:
            pass

        if not info.get("ok"):
            if own_prog:
                try:
                    cmds.progressWindow(endProgress=True)
                    own_prog = False
                except Exception:
                    pass
            choice = cmds.confirmDialog(
                title=u"MetaHuman",
                message=u"当前角色非metahuman标准角色，是否标准化项目\n\n"
                + u"\n".join(info.get("errors") or []),
                button=[u"是", u"否"],
                defaultButton=u"是",
                cancelButton=u"否",
                dismissString=u"否",
            )
            if choice != u"是":
                _set_export_ready(False)
                return
            from mh2max.standardize import standardize_scene

            # 进度条由 standardize_scene 在用户点「继续」之后自行打开，
            # 避免 confirmDialog 把菜单里提前开的 progressWindow 弄没却只剩忙光标
            try:
                result = standardize_scene(interactive=True)
            finally:
                try:
                    if cmds.progressWindow(q=True, exists=True):
                        cmds.progressWindow(endProgress=True)
                except Exception:
                    pass
                own_prog = False
            if not result.get("ok"):
                if result.get("cancelled"):
                    return
                cmds.confirmDialog(
                    title=u"标准化失败",
                    message=result.get("message") or u"未知错误",
                    button=[u"确定"],
                )
                _set_export_ready(False)
                return
            try:
                cmds.refresh(force=True)
            except Exception:
                pass
            info = detect_scene()
            if not info.get("ok"):
                cmds.confirmDialog(
                    title=u"标准化",
                    message=(result.get("message") or u"")
                    + u"\n\n标准化后仍未通过检测：\n"
                    + u"\n".join(info.get("errors") or []),
                    button=[u"确定"],
                )
                _set_export_ready(False)
                return
            _set_export_ready(True)
            cmds.confirmDialog(
                title=u"标准化完成",
                message=(result.get("message") or u"")
                + u"\n\n角色：%s\n体型：%s\n头：%s\n身：%s\nCTRL：%s"
                % (
                    info.get("character"),
                    info.get("body_type"),
                    info.get("head"),
                    info.get("body") or u"（无）",
                    info.get("ctrl_count"),
                ),
                button=[u"确定"],
            )
            return

        _set_export_ready(True)
        if own_prog:
            try:
                cmds.progressWindow(edit=True, progress=100, status=u"完成")
                cmds.progressWindow(endProgress=True)
                own_prog = False
            except Exception:
                pass
        msg = u"角色：%s\n体型：%s\n头：%s\n身：%s\nCTRL：%s" % (
            info.get("character"),
            info.get("body_type"),
            info.get("head"),
            info.get("body") or u"（无）",
            info.get("ctrl_count"),
        )
        if info.get("standardized"):
            msg += u"\n（已标准化自定义工程）"
        cmds.confirmDialog(title="MetaHuman", message=msg, button=[u"确定"])
    finally:
        if own_prog:
            try:
                cmds.progressWindow(endProgress=True)
            except Exception:
                pass


def _on_import_mh(*_args):
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
    ok = False
    try:
        reload_package()
        try:
            cmds.progressWindow(edit=True, status=u"正在打开导入界面…", progress=20)
        except Exception:
            pass
        from mh2max.import_ue58 import run_import_mh_ui

        # run_import_mh_ui may not return success flag; detect after
        run_import_mh_ui()
        from mh2max.detect import detect_scene

        ok = bool(detect_scene().get("ok"))
    finally:
        try:
            cmds.progressWindow(endProgress=True)
        except Exception:
            pass
        try:
            cmds.waitCursor(state=False)
        except Exception:
            pass
        _set_export_ready(ok)


def _on_check_update(*_args):
    reload_package()
    from mh2max.update_check import run_check_update_ui

    run_check_update_ui()


def _refresh_toggle_ctrl_label(visible=None):
    if not cmds.menuItem(ITEM_TOGGLE_CTRL, exists=True):
        return
    try:
        reload_package()
        from mh2max.ctrl_visibility import get_controllers_visible, menu_label_for_visible

        if visible is None:
            visible = get_controllers_visible()
        cmds.menuItem(
            ITEM_TOGGLE_CTRL,
            e=True,
            label=menu_label_for_visible(visible),
        )
    except Exception:
        pass


def _on_ue_ctrl_sync(*_args):
    try:
        reload_package()
        from mh2max.ue_ctrl_livelink import show_sync_ui

        show_sync_ui()
    except Exception as ex:
        import traceback

        traceback.print_exc()
        cmds.confirmDialog(
            title=u"UE5控制器同步",
            message=u"打开同步面板失败：\n%s" % ex,
            button=[u"确定"],
        )


def _on_toggle_controllers(*_args):
    try:
        reload_package()
        from mh2max.ctrl_visibility import toggle_controllers, list_controllers

        visible = toggle_controllers()
        _refresh_toggle_ctrl_label(visible)
        count = len(list_controllers())
        state = u"显示" if visible else u"隐藏"
        try:
            msg = u"<hl>mh2max</hl>：已%s控制器（%d）" % (state, count)
            if visible:
                msg += u"<br/>已开启视口 NURBS 曲线显示"
            cmds.inViewMessage(
                amg=msg,
                pos="topCenter",
                fade=True,
            )
        except Exception:
            print("[mh2max] controllers %s (%d)" % (state, count))
    except Exception as ex:
        import traceback

        traceback.print_exc()
        cmds.confirmDialog(
            title=u"显示/隐藏控制器",
            message=u"切换失败：\n%s" % ex,
            button=[u"确定"],
        )


def _restore_file_menu():
    """Remove leftover mh2max items from File and force Maya to rebuild it."""
    for item in (OLD_FILE_SUBMENU, OLD_FILE_DIVIDER):
        if cmds.menuItem(item, exists=True):
            try:
                cmds.deleteUI(item, menuItem=True)
            except Exception:
                pass
    try:
        if cmds.menu(OLD_FILE_SUBMENU, exists=True):
            cmds.deleteUI(OLD_FILE_SUBMENU, menu=True)
    except Exception:
        pass

    if not cmds.menu("MayaWindow|mainFileMenu", exists=True):
        return
    try:
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
    # Top: version label (disabled)
    cmds.menuItem(
        ITEM_VERSION,
        parent=parent,
        label=u"mh2max  v%s" % __version__,
        enable=False,
        annotation=u"当前已安装插件版本",
    )
    cmds.menuItem(divider=True, parent=parent)

    # 1 导入 MH
    cmds.menuItem(
        ITEM_IMPORT,
        parent=parent,
        label=u"导入 MH",
        command=_on_import_mh,
        annotation=u"导入 UE 5.6+ DCC Export（zip 或文件夹）并装配",
    )
    # 2 检测当前角色
    cmds.menuItem(
        ITEM_DETECT,
        parent=parent,
        label=u"检测当前角色",
        command=_on_detect,
        annotation=u"检测 MetaHuman / 自定义角色，必要时标准化",
    )
    # 3 导出至 3ds Max（需检测或导入成功）
    cmds.menuItem(
        ITEM_EXPORT,
        parent=parent,
        label=u"导出至 3ds Max",
        command=_on_export,
        annotation=u"需先检测成功或导入 MH 成功",
        enable=is_export_ready(),
    )

    cmds.menuItem(divider=True, parent=parent)
    cmds.menuItem(
        ITEM_UE_CTRL_SYNC,
        parent=parent,
        label=u"UE5控制器同步",
        command=_on_ue_ctrl_sync,
        annotation=u"打开 Maya → UE Control Rig 控制器同步面板",
    )
    cmds.menuItem(
        ITEM_TOGGLE_CTRL,
        parent=parent,
        label=u"显示控制器",
        command=_on_toggle_controllers,
        annotation=u"显示或隐藏场景中的 MetaHuman / 身体面部控制器",
    )
    cmds.menuItem(divider=True, parent=parent)
    cmds.menuItem(
        ITEM_UPDATE,
        parent=parent,
        label=u"检查更新",
        command=_on_check_update,
        annotation=u"查询 GitHub Releases 是否有新版本",
    )
    _refresh_toggle_ctrl_label()


def install():
    if cmds.about(batch=True):
        return
    if not cmds.window("MayaWindow", exists=True):
        cmds.evalDeferred(install, lowestPriority=True)
        return

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
        try:
            cmds.menuItem(divider=True, dividerLabel="mh2max", parent=parent)
        except Exception:
            pass
        _add_menu_items(parent)
        _refresh_export_enable()
        print("[mh2max] items installed under MetaHuman menu v%s" % __version__)
        return

    menu = cmds.menu(MENU_NAME, label="MH2Max", parent="MayaWindow", tearOff=True)
    _add_menu_items(menu)
    _refresh_export_enable()
    print("[mh2max] top-level MH2Max menu installed v%s" % __version__)
