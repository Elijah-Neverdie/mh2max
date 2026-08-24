# -*- coding: utf-8 -*-
"""One-click orchestrator with Maya progress UI."""
from __future__ import print_function

import os
import traceback

from maya import cmds

from .assemble import assemble_character, find_assets, open_assembled
from .detect import default_output_dir, detect_scene
from .export_maya import dump_limits, export_character_fbx, export_morphs, write_job_files
from .launch_max import (
    expected_max_save_paths,
    find_3dsmax_info,
    find_all_3dsmax,
    get_max_exe,
    launch_max,
    set_preferred_max,
)
from .progress_ui import ProgressUI, end_busy, show_busy


def run_export(out_dir=None, launch=True, face_only=True, progress_ui=None, info=None, max_exe=None):
    """Export FBX + morphs + job files; show foreground ProgressUI throughout."""
    info = info or detect_scene()
    if not info.get("ok"):
        raise RuntimeError("\n".join(info.get("errors") or ["未检测到 MetaHuman"]))

    out_dir = out_dir or default_output_dir(info)
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)

    char = info.get("character") or "MetaHuman"
    log_path = os.path.join(out_dir, "mh2max_maya.log")
    open(log_path, "w", encoding="utf-8").write("")
    paths = {
        "out_dir": out_dir,
        "limits": os.path.join(out_dir, "face_ctrl_limits.txt"),
        "fbx": os.path.join(out_dir, char + "_to_max.fbx"),
        "morph_face": os.path.join(out_dir, "MorphTargets", "Face"),
        "morph_root": os.path.join(out_dir, "MorphTargets"),
        "save_max_base": os.path.join(out_dir, char + "_face_rigged"),
        "log_max": os.path.join(out_dir, "mh2max_max.log"),
        "log_maya": log_path,
    }

    own_ui = progress_ui is None
    ui = progress_ui or ProgressUI(u"导出至 3ds Max", 5, use_native_busy=False)
    if not own_ui:
        ui.reset(title=u"导出至 3ds Max", total=5)
    ui.raise_window()
    ui.log(u"输出目录：%s" % out_dir)
    ui.log(u"角色：%s  体型：%s" % (char, info.get("body_type") or "?"))

    try:
        # 1) limits
        ui.step(u"导出面部控制器限位")
        ui.event(u"正在写入 face_ctrl_limits.txt…")
        ui.set_percent(5)
        nlim = dump_limits(paths["limits"])
        ui.log(u"限位条目：%s → %s" % (nlim, paths["limits"]))
        ui.set_percent(12)

        # 2) morphs (long) — single-axis + corner combo residuals (v1.3.1+)
        ui.step(u"导出面部 Morph（单轴 + 角落残差 / 子网格）")
        ui.event(u"准备导出 Face / Teeth / Saliva / 眼部 Morph（含 combo 残差）…")
        ui.raise_window()

        def cb(i, total, name):
            if ui.cancelled:
                return False
            # Morph phase occupies roughly 12%..78%
            total = max(1, int(total))
            pct = 12.0 + 66.0 * (float(i) / float(total))
            ui.set_percent(pct)
            ui.event(u"导出表情 Morph %s/%s：%s" % (i, total, name))
            if i == 1 or i == total or (i % 5 == 0):
                ui.log(u"Morph %s/%s  %s" % (i, total, name))
            return True

        morph = export_morphs(out_dir, log_path, progress_cb=cb, face_only=face_only)
        folders = morph.get("folders") or []
        ui.log(
            u"Morph 完成：导出 %s / 跳过 %s / 失败 %s / 共 %s"
            % (morph.get("exported"), morph.get("skipped"), morph.get("failed"), morph.get("total"))
        )
        if folders:
            ui.log(u"Morph 子网格：%s" % u"、".join(folders))
        combo_n = morph.get("combo_exported") or 0
        if combo_n:
            ui.log(u"角落残差 combo：导出 %s 项" % combo_n)
        ui.set_percent(80)

        # 3) FBX
        ui.step(u"导出角色 FBX")
        ui.event(u"正在导出 FBX（网格 / 骨骼 / 控制器）…")
        ui.raise_window()
        fbx = export_character_fbx(paths["fbx"], info, log_path)
        ui.log(u"FBX：%s bytes → %s" % (fbx.get("bytes"), paths["fbx"]))
        ui.set_percent(90)

        # 4) job files
        ui.step(u"写入 Max 任务脚本")
        ui.event(u"正在写入 job.json / MaxScript…")
        json_path, job_ms = write_job_files(out_dir, info, paths)
        ui.log(u"任务：%s" % job_ms)
        ui.set_percent(95)

        # 5) launch Max
        ui.step(u"启动 3ds Max")
        exe = None
        if launch:
            ui.event(u"正在启动 3ds Max 并自动装配…")
            ui.raise_window()
            exe = launch_max(job_ms, max_exe=max_exe)
            ui.log(u"已启动：%s" % (exe or u"（未知）"))
        else:
            ui.event(u"跳过启动 Max（未找到可执行文件）")
            ui.log(u"未启动 Max；可稍后手动运行：%s" % job_ms)

        ui.set_percent(100)
        ui.event(u"导出完成")
        ui.log(u"全部完成")
        return {
            "info": info,
            "paths": paths,
            "limits": nlim,
            "morph": morph,
            "fbx": fbx,
            "job_ms": job_ms,
            "job_json": json_path,
            "max_exe": exe,
        }
    except Exception:
        ui.event(u"导出失败")
        ui.log(traceback.format_exc()[-1200:])
        raise
    finally:
        end_busy()
        try:
            ui.raise_window()
        except Exception:
            pass


def _ensure_assembled(assets=None):
    """Prefer an already-assembled scene (UE MetaHuman for Maya or DHI). Only fall back to DHI assemble."""
    info = detect_scene()
    if info.get("ok"):
        return info

    assets = assets or find_assets()

    try:
        if assets.get("can_assemble"):
            cmds.waitCursor(state=True)
            try:
                assemble_character(assets)
            finally:
                cmds.waitCursor(state=False)
        elif assets.get("can_open"):
            open_assembled(assets["assembled"])
        else:
            lines = list((info or {}).get("errors") or [u"未检测到 MetaHuman"])
            lines.append(u"")
            lines.append(u"当前场景不是已装配的 MetaHuman（需要 head_lod0_mesh + 面部 CTRL）。")
            lines.append(u"")
            lines.append(u"请先用「导入 MH」导入并装配 UE DCC Export。")
            scene = assets.get("scene") or cmds.file(q=True, sn=True) or ""
            if scene:
                lines.extend([u"", u"当前场景：", scene])
            cmds.confirmDialog(title=u"MetaHuman → 3ds Max", message=u"\n".join(lines), button=[u"确定"])
            return None
    except Exception:
        tb = traceback.format_exc()
        cmds.confirmDialog(title=u"自动装配失败", message=tb[-2000:], button=[u"确定"])
        return None

    info = detect_scene()
    if not info.get("ok"):
        cmds.confirmDialog(
            title=u"MetaHuman → 3ds Max",
            message=u"\n".join(info.get("errors") or [u"装配后仍未检测到头部"]),
            button=[u"确定"],
        )
        return None
    return info


def _pick_max_for_export(max_info):
    """When multiple Max installs exist, let user pick export target."""
    installs = find_all_3dsmax()
    if len(installs) <= 1:
        return max_info
    from maya import cmds

    cur_exe = (max_info or {}).get("exe") or get_max_exe()
    lines = [u"检测到多个 3ds Max，请选择「一键导出」使用的版本：", u""]
    for i, item in enumerate(installs, 1):
        mark = u" ← 当前" if cur_exe and item.get("exe") == cur_exe else u""
        lines.append(u"  %s. 3ds Max %s%s" % (i, item.get("version"), mark))
    lines.append(u"")
    lines.append(u"输入序号后确定（留空=使用当前默认）。")
    result = cmds.promptDialog(
        title=u"选择 3ds Max 导出版本",
        message=u"\n".join(lines),
        button=[u"确定", u"取消"],
        defaultButton=u"确定",
        cancelButton=u"取消",
        dismissString=u"取消",
        text="1",
    )
    if result != u"确定":
        return max_info
    raw = (cmds.promptDialog(query=True, text=True) or "").strip()
    if not raw:
        return max_info
    if not raw.isdigit():
        return max_info
    idx = int(raw)
    if idx < 1 or idx > len(installs):
        return max_info
    picked = installs[idx - 1]
    set_preferred_max(picked["exe"])
    return {"exe": picked["exe"], "version": picked["version"]}


def run_export_ui():
    # Instant feedback — close leftover blank native progress / old import win
    end_busy()
    show_busy(u"正在检测场景中的 MetaHuman…", title=u"导出至 3ds Max")
    try:
        info = _ensure_assembled()
    finally:
        end_busy()
    if not info:
        return

    out_dir = default_output_dir(info)
    body = info.get("body_type") or "unknown"
    char = info.get("character") or "MetaHuman"
    max_info = find_3dsmax_info()
    if len(find_all_3dsmax()) > 1:
        max_info = _pick_max_for_export(max_info)
    max_exe = max_info.get("exe") or u"（未找到 3ds Max，将只导出文件）"
    max_ver = max_info.get("version") or "?"
    save_paths = expected_max_save_paths(char, out_dir, max_info.get("version") or 0)
    save_hint = u"\n".join(save_paths)
    if max_ver and int(max_ver) > 2024:
        save_hint += u"\n（_max2024 在 Max 装配结束时尝试 saveAsVersion 归档，不支持则跳过）"
    msg = (
        u"角色：%s\n体型：%s\n头部：%s\n身体：%s\n控制器：%s\n\n输出目录：\n%s\n\n3ds Max（最新）：%s\n%s\n\n将导出 FBX + 面部 Morph（单轴+角落残差）+ 限位，并启动空场景 Max 自动装配。\n\nMax 场景归档：\n%s"
        % (
            char,
            body,
            os.path.basename(info.get("head") or "-"),
            os.path.basename(info.get("body") or u"（无，仅头）"),
            info.get("ctrl_count"),
            out_dir,
            max_ver,
            max_exe,
            save_hint,
        )
    )
    choice = cmds.confirmDialog(
        title=u"MetaHuman → 3ds Max",
        message=msg,
        button=[u"开始导出", u"选择目录", u"取消"],
        defaultButton=u"开始导出",
        cancelButton=u"取消",
        dismissString=u"取消",
    )
    if choice == u"取消":
        return
    if choice == u"选择目录":
        picked = cmds.fileDialog2(dialogStyle=2, fileMode=3, caption=u"选择 Max 输出目录", startingDirectory=out_dir)
        if not picked:
            return
        out_dir = picked[0]

    # Foreground progress window BEFORE any long work (morphs can take minutes)
    end_busy()
    ui = ProgressUI(u"导出至 3ds Max", 5, use_native_busy=False)
    ui.event(u"准备导出…")
    ui.status(u"导出至 3ds Max")
    ui.log(u"用户确认开始导出")
    ui.log(u"输出：%s" % out_dir)
    ui.set_percent(2)
    ui.raise_window()

    launch = bool(max_info.get("exe"))
    try:
        result = run_export(
            out_dir=out_dir,
            launch=launch,
            face_only=True,
            progress_ui=ui,
            info=info,
            max_exe=max_info.get("exe"),
        )
        save_paths = expected_max_save_paths(char, out_dir, max_info.get("version") or 0)
        done = (
            u"Maya 导出完成。\n\n体型：%s\n限位：%s\nMorph：导出 %s / 跳过 %s / 失败 %s（含 combo %s）\n子网格：%s\nFBX：%s bytes\n\nMax 场景归档（装配完成后写入）：\n%s\n"
            % (
                result["info"].get("body_type"),
                result["limits"],
                result["morph"]["exported"],
                result["morph"]["skipped"],
                result["morph"]["failed"],
                result["morph"].get("combo_exported") or 0,
                u"、".join(result["morph"].get("folders") or []),
                result["fbx"]["bytes"],
                u"\n".join(save_paths),
            )
        )
        if launch:
            done += u"\n已启动 3ds Max %s（将显示装配进度条，完成后弹窗确认）。" % max_ver
        else:
            done += u"\n未找到 3ds Max。可稍后在 Max 中运行：\n" + result["job_ms"]
        cmds.confirmDialog(title=u"MetaHuman → 3ds Max", message=done, button=[u"确定"])
    except Exception:
        tb = traceback.format_exc()
        cmds.confirmDialog(title=u"导出失败", message=tb[-2000:], button=[u"确定"])
        raise


def run_one_click(start_path=None, out_dir=None, launch=True, face_only=True):
    """Headless: assemble if needed, then export and optionally launch Max. No dialogs."""
    info = detect_scene()
    if not info.get("ok"):
        assets = find_assets(start_path)
        if assets.get("can_assemble"):
            assemble_character(assets)
        elif assets.get("can_open"):
            open_assembled(assets["assembled"])
        else:
            raise RuntimeError(
                "场景未装配，且找不到 DNA + 身体模板。start=%s dna=%s body=%s"
                % (start_path, assets.get("dna"), assets.get("body"))
            )
        info = detect_scene()
        if not info.get("ok"):
            raise RuntimeError("\n".join(info.get("errors") or [u"装配后仍未检测到 MetaHuman"]))
    dest = out_dir or default_output_dir(info)
    return run_export(out_dir=dest, launch=launch, face_only=face_only, info=info)
