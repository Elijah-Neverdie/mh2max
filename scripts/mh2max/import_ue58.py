# -*- coding: utf-8 -*-
"""Import UE 5.6+ DCC Export zip (head.dna + body.dna) into Maya via MetaHuman for Maya."""
from __future__ import print_function

import json
import os
import shutil
import sys
import traceback
import zipfile

from maya import cmds

from .progress_ui import ProgressUI, end_busy, run_steps, update_busy


def _safe_name(name):
    keep = []
    for ch in name or "MetaHuman":
        if ch.isalnum() or ch in ("_", "-", " "):
            keep.append(ch)
    s = "".join(keep).strip().replace(" ", "_")
    return s or "MetaHuman"


def import_dir_for_zip(zip_path):
    """Process folder beside the zip: <zipDir>/MHI_<zipStem>."""
    parent = os.path.dirname(os.path.abspath(zip_path))
    stem = _safe_name(os.path.splitext(os.path.basename(zip_path))[0])
    return os.path.join(parent, "MHI_" + stem)


def unique_import_dir(base_dir):
    """Return base_dir, or base_dir_2 / _3 / ... if names collide."""
    if not os.path.exists(base_dir):
        return base_dir
    parent = os.path.dirname(base_dir)
    name = os.path.basename(base_dir)
    n = 2
    while n < 10000:
        candidate = os.path.join(parent, "%s_%s" % (name, n))
        if not os.path.exists(candidate):
            return candidate
        n += 1
    raise RuntimeError(u"无法生成不重名的过程目录：%s" % base_dir)


def prepare_import_dir(char_dir, overwrite=False, progress=None):
    """Create char_dir empty. If exists: overwrite clears it; else caller should pass a unique path."""
    parent_dir = os.path.dirname(char_dir)
    if parent_dir and not os.path.isdir(parent_dir):
        os.makedirs(parent_dir)
    if os.path.isdir(char_dir):
        if not overwrite:
            raise RuntimeError(u"目录已存在且未选择覆盖：%s" % char_dir)
        if progress:
            progress.log(u"清空已有目录 %s" % char_dir)
        shutil.rmtree(char_dir)
    elif os.path.exists(char_dir):
        raise RuntimeError(u"目标路径已存在且不是文件夹：%s" % char_dir)
    os.makedirs(char_dir)
    return char_dir


def _path_has_non_ascii(path):
    try:
        (path or "").encode("ascii")
        return False
    except UnicodeEncodeError:
        return True


def _ascii_stage_root():
    """ASCII-only work root for MetaHuman RL4 (cannot open DNA under Chinese paths)."""
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("TEMP") or r"C:\Temp"
    root = os.path.join(base, "mh2max", "stage")
    if not os.path.isdir(root):
        os.makedirs(root)
    return root


def _copytree_replace(src, dst):
    if os.path.isdir(dst):
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def stage_assets_for_rl4(assets, progress=None):
    """
    If DNA/maps paths contain non-ASCII (e.g. Y:\\下载\\...), copy required files to
    %LOCALAPPDATA%\\mh2max\\stage\\<name> so createEmbeddedNodeRL4 can open them.
    Keeps assets['char_dir'] as the user-facing MHI folder for scene save.
    """
    head = os.path.abspath(assets["head_dna"])
    body = os.path.abspath(assets["body_dna"])
    maps_dir = os.path.abspath(assets.get("maps_dir") or "")
    masks_dir = os.path.abspath(assets.get("masks_dir") or "")
    char_dir = os.path.abspath(assets["char_dir"])

    needs = any(
        _path_has_non_ascii(p)
        for p in (head, body, maps_dir, masks_dir, char_dir)
        if p
    )
    if not needs:
        assets["head_dna"] = head
        assets["body_dna"] = body
        assets["assemble_dir"] = char_dir
        return assets

    stage = os.path.join(_ascii_stage_root(), _safe_name(assets.get("name") or "MetaHuman"))
    if progress:
        progress.event(u"DNA 路径含非英文，正在复制到临时目录…")
        progress.log(u"DNA 路径含非英文（如「下载」），RL4 无法读取。")
        progress.log(u"正在复制到纯英文临时目录：%s" % stage)
        progress._pump()

    if os.path.isdir(stage):
        shutil.rmtree(stage)
    os.makedirs(stage)

    # DNA + manifest
    for src in (head, body):
        if not os.path.isfile(src):
            raise RuntimeError(u"装配前找不到 DNA：%s" % src)
        shutil.copy2(src, os.path.join(stage, os.path.basename(src)))
    man = os.path.join(char_dir, "ExportManifest.json")
    if os.path.isfile(man):
        shutil.copy2(man, os.path.join(stage, "ExportManifest.json"))
    thumb = assets.get("manifest") or {}
    thumb_name = thumb.get("thumbnail")
    if thumb_name:
        tp = os.path.join(char_dir, thumb_name)
        if os.path.isfile(tp):
            shutil.copy2(tp, os.path.join(stage, thumb_name))

    # Maps / Masks
    staged_maps = os.path.join(stage, "Maps")
    staged_masks = os.path.join(stage, "Masks")
    if maps_dir and os.path.isdir(maps_dir):
        _copytree_replace(maps_dir, staged_maps)
    else:
        os.makedirs(staged_maps)
    if masks_dir and os.path.isdir(masks_dir):
        _copytree_replace(masks_dir, staged_masks)
    else:
        os.makedirs(staged_masks)

    out = dict(assets)
    out["head_dna"] = os.path.join(stage, os.path.basename(head))
    out["body_dna"] = os.path.join(stage, os.path.basename(body))
    out["maps_dir"] = staged_maps
    out["masks_dir"] = staged_masks
    out["assemble_dir"] = stage
    out["char_dir"] = char_dir  # user MHI (may contain Chinese)
    out["staged_from"] = char_dir
    if progress:
        progress.log(u"临时 DNA：%s" % out["head_dna"])
        progress._pump()
    return out


def find_metahuman_for_maya():
    """Return dict with plugin availability and module roots."""
    info = {
        "ok": False,
        "module": None,
        "paths": [],
        "errors": [],
        "imports": {},
    }
    # Common install locations
    candidates = [
        os.path.join(os.path.expanduser("~"), "Documents", "maya", "modules", "MetaHumanForMaya"),
        r"C:\Program Files\Epic Games\MetaHumanForMaya",
        r"C:\Program Files\Epic Games\UE_5.8\Engine\Plugins\Marketplace\MetaHumanForMaya_5.8\Content",
        r"C:\Program Files\Epic Games\UE_5.7\Engine\Plugins\Marketplace\MetaHumanForMaya_5.7\Content",
        r"C:\Program Files\Epic Games\UE_5.6\Engine\Plugins\Marketplace\MetaHumanForMaya_5.6\Content",
    ]
    for env in ("MAYA_MODULE_PATH", "MH_FOR_MAYA_ROOT"):
        raw = os.environ.get(env) or ""
        for part in raw.replace(";", os.pathsep).split(os.pathsep):
            part = part.strip().strip('"')
            if part:
                candidates.append(part)
                candidates.append(os.path.join(part, "MetaHumanForMaya"))

    for c in candidates:
        if not c or not os.path.isdir(c):
            continue
        # Only treat as MetaHuman root if it looks like the plugin (avoid dumping all MAYA_MODULE_PATH)
        looks = (
            os.path.isfile(os.path.join(c, "MetaHumanForMaya.mod"))
            or os.path.isfile(os.path.join(os.path.dirname(c), "MetaHumanForMaya.mod"))
            or os.path.isdir(os.path.join(c, "plugin"))
            or "metahumanformaya" in c.replace("\\", "/").lower()
        )
        if not looks and os.path.basename(c).lower() != "metahumanformaya":
            # still add nested MetaHumanForMaya if present
            nested = os.path.join(c, "MetaHumanForMaya")
            if os.path.isdir(nested):
                c = nested
                looks = True
            else:
                continue
        if c not in info["paths"]:
            info["paths"].append(c)
        if c not in sys.path:
            sys.path.insert(0, c)
        for sub in ("scripts", "python", "Python", "plugin", os.path.join("scripts", "python")):
            p = os.path.join(c, sub)
            if os.path.isdir(p) and p not in sys.path:
                sys.path.insert(0, p)

    # Try loading Maya plugin file if present
    for root in list(info["paths"]):
        plug_py = os.path.join(root, "plugin", "MetaHumanForMaya.py")
        if os.path.isfile(plug_py):
            try:
                if not cmds.pluginInfo("MetaHumanForMaya", q=True, loaded=True):
                    cmds.loadPlugin(plug_py, quiet=True)
            except Exception as ex:
                info["errors"].append("loadPlugin: " + str(ex))

    for name in (
        "mh_character_assembler",
        "meta_human_for_maya",
        "metahuman_for_maya",
        "MetaHumanForMaya",
    ):
        try:
            mod = __import__(name)
            info["imports"][name] = getattr(mod, "__file__", str(mod))
            # Prefer Character Assembler package for scripting
            if info["module"] is None or name == "mh_character_assembler":
                info["module"] = name
            info["ok"] = True
        except Exception as ex:
            info["imports"][name] = str(ex)

    # Prefer explicit assembler import success
    if info["imports"].get("mh_character_assembler", "").startswith("C:") or (
        isinstance(info["imports"].get("mh_character_assembler"), str)
        and "No module" not in str(info["imports"].get("mh_character_assembler", "No module"))
    ):
        if "mh_character_assembler" in sys.modules or info["imports"].get("mh_character_assembler"):
            try:
                __import__("mh_character_assembler")
                info["module"] = "mh_character_assembler"
                info["ok"] = True
            except Exception:
                pass

    # RigLogic plugins often ship with MetaHuman for Maya
    for plug in (
        "embeddedRL4",
        "MayaUE4RBFPlugin2026",
        "MayaUE4RBFPlugin2025",
        "MayaUE4RBFPlugin2024",
        "MayaUERBFPlugin",
    ):
        try:
            if not cmds.pluginInfo(plug, q=True, loaded=True):
                cmds.loadPlugin(plug, quiet=True)
        except Exception:
            pass
    return info


def install_help_message():
    return (
        u"当前 Maya 未检测到 MetaHuman for Maya（Character Assembler）。\n"
        u"UE 5.6+ 导出的 zip（head.dna + body.dna）必须用该插件组装。\n\n"
        u"安装步骤：\n"
        u"1. Fab 添加 MetaHuman for Maya 到库\n"
        u"2. Epic Launcher → 库 → 安装到 UE 5.7 或 5.8\n"
        u"3. 打开：\n"
        u"   UE_X.X\\Engine\\Plugins\\Marketplace\\MetaHumanForMaya_X.X\\Content\n"
        u"4. 解压其中的 zip，复制到：\n"
        u"   C:\\Users\\A\\Documents\\maya\\modules\\\n"
        u"   （应出现 MetaHumanForMaya.mod 与 MetaHumanForMaya 文件夹）\n"
        u"5. 重启 Maya，再点 文件 > MetaHuman > 导入 MH\n\n"
        u"说明：https://www.fab.com/listings/9e3bf55e-d4c3-44fc-a3d4-ec4cb772ec29"
    )


def extract_ue_zip(zip_path, dest_dir=None, progress=None, dest_root=None, overwrite=False):
    """Extract DCC Export zip into sibling MHI_<name> (or dest_dir override)."""
    if not zip_path or not os.path.isfile(zip_path):
        raise RuntimeError(u"zip 不存在：%s" % zip_path)

    # dest_dir = full character folder; dest_root kept only for old callers
    if dest_dir:
        char_dir = dest_dir
    elif dest_root:
        base = _safe_name(os.path.splitext(os.path.basename(zip_path))[0])
        char_dir = os.path.join(dest_root, "MHI_" + base)
    else:
        char_dir = import_dir_for_zip(zip_path)

    # Non-UI safety: if exists and not overwrite, pick a unique sibling name
    if os.path.exists(char_dir) and not overwrite:
        char_dir = unique_import_dir(char_dir)
        if progress:
            progress.log(u"目录已存在，改用 %s" % char_dir)

    parent_dir = os.path.dirname(char_dir)
    if progress:
        progress.event(u"准备输出目录…")
        progress.log(u"准备目录 %s" % char_dir)
    prepare_import_dir(char_dir, overwrite=True, progress=progress)

    if progress:
        progress.event(u"正在解压 zip…")
        progress.log(u"解压到 %s" % char_dir)

    with zipfile.ZipFile(zip_path, "r") as zf:
        names = zf.namelist()
        total = max(1, len(names))
        for i, name in enumerate(names):
            if progress and progress.cancelled:
                raise RuntimeError(u"用户取消导入")
            zf.extract(name, char_dir)
            n = i + 1
            if progress:
                # Update bar frequently; log every ~5% or last file
                if n == 1 or n == total or (n % max(1, total // 20) == 0) or (n % 8 == 0):
                    progress.step_progress(n, total, u"解压文件")
                    if n == 1 or n == total or (n % max(1, total // 10) == 0):
                        progress.log(u"解压 %s/%s  %s" % (n, total, name))

    if progress:
        progress.event(u"整理解压目录…")
        progress.log(u"检查 ExportManifest / DNA…")

    # If zip had a single top-level folder, descend into it
    entries = [e for e in os.listdir(char_dir) if not e.startswith(".")]
    if len(entries) == 1 and os.path.isdir(os.path.join(char_dir, entries[0])):
        inner = os.path.join(char_dir, entries[0])
        if os.path.isfile(os.path.join(inner, "ExportManifest.json")) or os.path.isfile(
            os.path.join(inner, "head.dna")
        ):
            tmp = char_dir + "_tmp_inner"
            os.rename(inner, tmp)
            for item in os.listdir(tmp):
                shutil.move(os.path.join(tmp, item), os.path.join(char_dir, item))
            shutil.rmtree(tmp)

    manifest = {}
    man_path = os.path.join(char_dir, "ExportManifest.json")
    if os.path.isfile(man_path):
        manifest = json.loads(open(man_path, "r", encoding="utf-8").read())

    head = os.path.join(char_dir, (manifest.get("dna") or {}).get("head") or "head.dna")
    body = os.path.join(char_dir, (manifest.get("dna") or {}).get("body") or "body.dna")
    if not os.path.isfile(head):
        raise RuntimeError(u"缺少 head.dna：%s" % char_dir)
    if not os.path.isfile(body):
        raise RuntimeError(u"缺少 body.dna：%s" % char_dir)

    zip_stem = _safe_name(os.path.splitext(os.path.basename(zip_path))[0])
    name = manifest.get("metaHumanName") or zip_stem

    return {
        "char_dir": char_dir,
        "parent_dir": parent_dir,
        "name": name,
        "manifest": manifest,
        "head_dna": os.path.abspath(head),
        "body_dna": os.path.abspath(body),
        "maps_dir": os.path.join(char_dir, (manifest.get("folders") or {}).get("maps") or "Maps"),
        "masks_dir": os.path.join(char_dir, (manifest.get("folders") or {}).get("masks") or "Masks"),
        "engine": manifest.get("exportEngineVersion") or "",
    }


def assemble_with_metahuman_for_maya(assets, progress=None, options=None):
    """Assemble extracted UE export via mh_character_assembler.CharacterImporter.execute."""
    plug = find_metahuman_for_maya()
    if not plug.get("ok"):
        raise RuntimeError(install_help_message())

    try:
        from mh_character_assembler.importer import CharacterImporter
        import mh_character_assembler as mca
    except Exception as ex:
        raise RuntimeError(
            u"无法导入 mh_character_assembler：%s\n\n%s" % (ex, install_help_message())
        )

    if progress:
        progress.event(u"准备 CharacterImporter…")
        progress.log(u"使用 CharacterImporter.execute（mh_character_assembler）")

    # RL4 cannot open DNA under non-ASCII paths (e.g. Y:/下载/...)
    if progress:
        progress.event(u"检查路径 / 复制 DNA 到英文目录…")
    assets = stage_assets_for_rl4(assets, progress=progress)

    # Character Assembler pipeline creates/overwrites the scene
    if progress:
        progress.event(u"新建空场景…")
    cmds.file(new=True, force=True)
    if progress:
        progress.log(u"已新建场景")

    head = assets["head_dna"]
    body = assets["body_dna"]
    maps_dir = assets.get("maps_dir") or os.path.join(assets["char_dir"], "Maps")
    masks_dir = assets.get("masks_dir") or os.path.join(assets["char_dir"], "Masks")
    if not os.path.isdir(maps_dir):
        maps_dir = assets.get("assemble_dir") or assets["char_dir"]
    if not os.path.isdir(masks_dir):
        masks_dir = assets.get("assemble_dir") or assets["char_dir"]

    if not os.path.isfile(head):
        raise RuntimeError(u"head.dna 不存在：\n%s" % head)
    if not os.path.isfile(body):
        raise RuntimeError(u"body.dna 不存在：\n%s" % body)

    message = {
        "headDnaPath": head.replace("\\", "/"),
        "bodyDnaPath": body.replace("\\", "/"),
        "mapsDirPath": maps_dir.replace("\\", "/"),
        "masksDirPath": masks_dir.replace("\\", "/"),
    }
    opts = {
        "import_head": True,
        "import_body": True,
        "import_textures": True,
        "combine_skeletons": False,
        "scene_orientation": "y_up",
    }
    if options:
        opts.update(options)

    if progress:
        progress.log(u"headDna=%s" % head)
        progress.log(u"bodyDna=%s" % body)
        progress.log(u"maps=%s" % maps_dir)
        progress.log(u"options=%s" % opts)
        progress.event(u"装配中：导入头/身/贴图/绑定（可能需数分钟）…")
        progress.log(u"开始 Assemble（可能需数分钟，请勿关闭 Maya）…")
        progress.raise_window()
        progress._pump()

    try:
        importer = CharacterImporter()
        importer.execute(message, opts)
    except Exception as ex:
        msg = str(ex)
        if "DNA file stream" in msg or "dna path" in msg.lower():
            raise RuntimeError(
                u"无法打开 DNA（createEmbeddedNodeRL4）。\n"
                u"常见原因：路径含中文/特殊字符，或 DNA 损坏。\n"
                u"已尝试使用的路径：\n%s\n%s\n\n原始错误：%s"
                % (head, body, msg)
            )
        raise

    if progress:
        progress.event(u"Assemble 完成，正在保存场景…")
        progress.log(u"Assemble 完成")
        progress._pump()

    # Persist assembled scene into user MHI folder (sibling of zip)
    save_dir = assets.get("char_dir") or assets.get("assemble_dir")
    if not os.path.isdir(save_dir):
        os.makedirs(save_dir)
    scene_path = os.path.join(save_dir, "scene.mb")
    try:
        # Maya file rename/save also fails on some non-ASCII paths — fall back to ASCII stage
        try:
            cmds.file(rename=scene_path)
            cmds.file(save=True, type="mayaBinary")
        except Exception:
            alt = os.path.join(assets.get("assemble_dir") or _ascii_stage_root(), "scene.mb")
            cmds.file(rename=alt)
            cmds.file(save=True, type="mayaBinary")
            if alt != scene_path and os.path.isfile(alt):
                try:
                    shutil.copy2(alt, scene_path)
                except Exception:
                    scene_path = alt
        if progress:
            progress.log(u"已保存场景 %s" % scene_path)
            progress._pump()
    except Exception as ex:
        if progress:
            progress.log(u"保存场景失败（可稍后另存）：%s" % ex)

    return {"method": "api", "assets": assets, "options": opts, "scene": scene_path}


def verify_assembled_scene(progress=None):
    """Return verification report for skin / joints / CTRLs / jaw-teeth link."""
    report = {
        "ok": False,
        "head": None,
        "body": None,
        "joints": 0,
        "ctrls": 0,
        "skinned": [],
        "jaw": None,
        "teeth": None,
        "blink_delta": None,
        "jaw_teeth_linked": None,
        "jaw_vert_delta": None,
        "ctrl_limits": {},
        "errors": [],
    }

    def resolve(name):
        if cmds.objExists(name):
            return name
        hits = cmds.ls("*:" + name, transforms=True) or []
        return hits[0] if hits else None

    def sample_verts(mesh, step=None):
        nv = int(cmds.polyEvaluate(mesh, vertex=True) or 0)
        if nv <= 0:
            return []
        step = step or max(1, nv // 40)
        idxs = list(range(0, nv, step))[:40]
        return [cmds.pointPosition("%s.vtx[%d]" % (mesh, i), world=True) for i in idxs]

    def vert_delta(a, b):
        total = 0.0
        for p, q in zip(a, b):
            total += sum(abs(x - y) for x, y in zip(p, q))
        return total

    def sample_bbox(node):
        return [round(v, 5) for v in cmds.exactWorldBoundingBox(node)]

    head = resolve("head_lod0_mesh")
    if not head:
        for n in cmds.ls("*head*lod0*", type="transform") or []:
            short = n.split(":")[-1].lower()
            if "head" in short and "lod0" in short and "combined" not in short:
                shapes = cmds.listRelatives(n, shapes=True, ni=True) or []
                if any(cmds.nodeType(s) == "mesh" for s in shapes):
                    head = n
                    break
    body = resolve("body_lod0_mesh")
    if not body:
        for n in cmds.ls("*body*lod0*", type="transform") or []:
            short = n.split(":")[-1].lower()
            shapes = cmds.listRelatives(n, shapes=True, ni=True) or []
            if (
                "body" in short
                and "lod0" in short
                and "combined" not in short
                and "flipflop" not in short
                and any(cmds.nodeType(s) == "mesh" for s in shapes)
            ):
                body = n
                break

    report["head"] = head
    report["body"] = body
    report["joints"] = len(cmds.ls(type="joint") or [])
    ctrls = (cmds.ls("CTRL_*", type="transform") or []) + (cmds.ls("*:CTRL_*", type="transform") or [])
    report["ctrls"] = len(list(dict.fromkeys(ctrls)))

    for mesh in (head, body):
        if not mesh:
            continue
        hist = cmds.listHistory(mesh) or []
        skins = [h for h in hist if cmds.nodeType(h) == "skinCluster"]
        if skins:
            report["skinned"].append(mesh)

    jaw = resolve("CTRL_C_jaw")
    teeth = resolve("teeth_lod0_mesh")
    if not teeth:
        hits = cmds.ls("*teeth*lod0*", type="transform") or []
        teeth = hits[0] if hits else None
    report["jaw"] = jaw
    report["teeth"] = teeth

    blink = resolve("CTRL_L_eye_blink")
    for ctrl_name, node in (("CTRL_C_jaw", jaw), ("CTRL_L_eye_blink", blink)):
        if not node:
            continue
        try:
            report["ctrl_limits"][ctrl_name] = {
                "ty": cmds.transformLimits(node, q=True, ty=True),
                "ety": cmds.transformLimits(node, q=True, ety=True),
            }
        except Exception as ex:
            report["ctrl_limits"][ctrl_name] = str(ex)

    # Blink deform test (vertex delta — bbox often unchanged)
    if head and blink and cmds.attributeQuery("translateY", node=blink, exists=True):
        try:
            v0 = sample_verts(head)
            cmds.setAttr(blink + ".translateY", 1.0)
            cmds.refresh(force=True)
            if progress:
                progress._pump()
            report["blink_delta"] = vert_delta(v0, sample_verts(head))
            cmds.setAttr(blink + ".translateY", 0.0)
        except Exception as ex:
            report["errors"].append("blink: " + str(ex))

    # Jaw opens -> teeth follow + head verts move
    if jaw and cmds.attributeQuery("translateY", node=jaw, exists=True):
        try:
            if head:
                v0 = sample_verts(head)
            t0 = sample_bbox(teeth) if teeth else None
            cmds.setAttr(jaw + ".translateY", 1.0)
            cmds.refresh(force=True)
            if progress:
                progress._pump()
            if head:
                report["jaw_vert_delta"] = vert_delta(v0, sample_verts(head))
            if teeth and t0:
                t1 = sample_bbox(teeth)
                report["jaw_teeth_linked"] = sum(abs(a - b) for a, b in zip(t0, t1))
            cmds.setAttr(jaw + ".translateY", 0.0)
        except Exception as ex:
            report["errors"].append("jaw_teeth: " + str(ex))

    if not head:
        report["errors"].append(u"未找到头部网格")
    if report["joints"] < 50:
        report["errors"].append(u"关节过少：%s" % report["joints"])
    if report["ctrls"] < 20:
        report["errors"].append(u"面部控制器过少：%s" % report["ctrls"])
    if head and head not in report["skinned"]:
        report["errors"].append(u"头部似乎没有 skinCluster")
    if body and body not in report["skinned"]:
        report["errors"].append(u"身体似乎没有 skinCluster")

    report["ok"] = (
        bool(head)
        and bool(body)
        and report["joints"] >= 50
        and report["ctrls"] >= 20
        and head in report["skinned"]
        and body in report["skinned"]
        and (report.get("blink_delta") or 0) > 0.1
        and (report.get("jaw_teeth_linked") or 0) > 0.1
    )
    return report


def import_ue_zip(zip_path, dest_dir=None, verify=True, dest_root=None, overwrite=False, progress_ui=None):
    """Full import with progress UI. Returns assets + optional verify report."""
    state = {"assets": None, "report": None, "assemble": None, "plugin": None}
    # dest_dir = MHI folder; dest_root legacy → MHI_<zip> under that root
    if dest_dir is None and dest_root:
        base = _safe_name(os.path.splitext(os.path.basename(zip_path or ""))[0])
        dest_dir = os.path.join(dest_root, "MHI_" + base)
    if dest_dir is None:
        dest_dir = import_dir_for_zip(zip_path)

    def s_extract(ui):
        if not zip_path or not os.path.isfile(zip_path):
            raise RuntimeError(u"zip 不存在：%s" % zip_path)
        state["assets"] = extract_ue_zip(
            zip_path, dest_dir=dest_dir, progress=ui, overwrite=overwrite
        )
        a = state["assets"]
        ui.log(u"角色 %s | 引擎 %s" % (a["name"], a.get("engine") or "?"))
        ui.log(u"目录 %s" % a["char_dir"])
        ui.log(u"head=%s" % a["head_dna"])
        ui.log(u"body=%s" % a["body_dna"])

    def s_check(ui):
        ui.event(u"检测 MetaHuman for Maya 插件…")
        state["plugin"] = find_metahuman_for_maya()
        plug = state["plugin"]
        if not plug.get("ok"):
            a = state["assets"] or {}
            raise RuntimeError(
                install_help_message()
                + u"\n\n已解压到：\n%s\n\n装好 MetaHuman for Maya 后，可在 Character Assembler 中打开该目录。"
                % (a.get("char_dir") or dest_dir)
            )
        ui.log(u"MetaHuman for Maya：%s" % plug.get("module"))
        if plug.get("paths"):
            ui.log(u"路径：" + "; ".join(plug["paths"][:3]))

    def s_assemble(ui):
        ui.event(u"装配头部 / 身体 / 贴图 / 绑定…")
        state["assemble"] = assemble_with_metahuman_for_maya(state["assets"], progress=ui)

    def s_verify(ui):
        ui.event(u"验证蒙皮、控制器与联动…")
        if state["assemble"] and state["assemble"].get("method") == "ui":
            ui.log(u"已打开 Character Assembler UI，请在窗口内完成 Assemble 后再点检测")
            return
        state["report"] = verify_assembled_scene(progress=ui)
        r = state["report"]
        ui.log(
            u"验证：head=%s body=%s joints=%s CTRLs=%s skin=%s blinkΔ=%s jaw-teethΔ=%s"
            % (
                r.get("head"),
                r.get("body"),
                r.get("joints"),
                r.get("ctrls"),
                r.get("skinned"),
                r.get("blink_delta"),
                r.get("jaw_teeth_linked"),
            )
        )
        if r.get("errors"):
            for e in r["errors"]:
                ui.log(u"注意：" + e)

    steps = [
        (u"解压 UE DCC Export zip", s_extract),
        (u"检测 MetaHuman for Maya 插件", s_check),
        (u"装配头部 / 身体 / 贴图 / 绑定", s_assemble),
    ]
    if verify:
        steps.append((u"验证蒙皮、控制器与联动", s_verify))

    run_steps(u"导入 MetaHuman（UE DCC Export）", steps, ui=progress_ui)
    return state


def _pick_zip_path():
    """Open a zip picker that reliably lists files (incl. Chinese paths)."""
    start = r"Y:\下载\mod\metahuman"
    if not os.path.isdir(start):
        start = os.path.join(os.path.expanduser("~"), "Documents")
    if not os.path.isdir(start):
        start = os.path.expanduser("~")

    # Prefer Qt dialog — Maya fileDialog2 native filter often hides *.zip on Win/CN paths
    try:
        try:
            from PySide6.QtWidgets import QFileDialog  # type: ignore
        except ImportError:
            from PySide2.QtWidgets import QFileDialog  # type: ignore

        path, _sel = QFileDialog.getOpenFileName(
            None,
            u"选择 UE DCC Export zip（含 head.dna / body.dna）",
            start,
            u"ZIP (*.zip);;All Files (*.*)",
        )
        if path:
            return path
        return None
    except Exception:
        pass

    picked = cmds.fileDialog2(
        dialogStyle=1,
        fileMode=1,
        caption=u"选择 UE DCC Export zip（含 head.dna / body.dna）",
        fileFilter=u"ZIP (*.zip);;All Files (*.*)",
        startingDirectory=start,
        okCaption=u"打开",
        cancelLabel=u"取消",
    )
    if not picked:
        return None
    return picked[0]


def run_import_mh_ui():
    """MH2Max > 导入 MH — after zip pick, always show progress bar + current event."""
    from .progress_ui import ProgressUI, end_busy, show_busy, update_busy

    # Instant strip while opening file dialog
    show_busy(u"请选择 UE DCC Export zip…", title=u"导入 MH")
    try:
        cmds.waitCursor(state=False)
    except Exception:
        pass

    zip_path = None
    try:
        zip_path = _pick_zip_path()
    except Exception as ex:
        end_busy()
        cmds.confirmDialog(title=u"导入 MH", message=u"文件选择失败：%s" % ex, button=[u"确定"])
        raise

    if not zip_path:
        end_busy()
        return

    # —— Zip selected: show progress window immediately ——
    show_busy(u"已选择 zip，正在打开进度窗口…", title=u"导入 MH")
    update_busy(u"已选择：%s" % os.path.basename(zip_path), 5)

    ui = ProgressUI(u"导入 MH", 6)
    ui.raise_window()
    ui.set_percent(5)
    ui.event(u"已选择 zip")
    ui.status(u"已选择文件，准备导入…")
    ui.log(u"已选择：%s" % zip_path)
    ui._pump()

    ui.event(u"检测 MetaHuman for Maya 插件…")
    ui.set_percent(8)
    ui.log(u"正在检测 MetaHuman for Maya…")
    plug = find_metahuman_for_maya()
    warn = u""
    if not plug.get("ok"):
        warn = u"\n\n⚠ 尚未检测到 MetaHuman for Maya：将先解压 zip，装配需装插件后完成。"
        ui.log(u"未检测到 MetaHuman for Maya（将仅解压或稍后装配）")
    else:
        ui.log(u"已检测到 MetaHuman for Maya：%s" % (plug.get("module") or "ok"))

    out_dir = import_dir_for_zip(zip_path)
    ui.event(u"等待确认导入…")
    ui.set_percent(10)
    ui.log(u"默认输出目录：%s" % out_dir)
    ui.raise_window()

    choice = cmds.confirmDialog(
        title=u"导入 MH",
        message=u"将解压并装配（装配时会新建场景，未保存内容丢失）：\n\n%s\n\n输出目录：\n%s%s"
        % (zip_path, out_dir, warn),
        button=[u"开始导入", u"取消"],
        defaultButton=u"开始导入",
        cancelButton=u"取消",
        dismissString=u"取消",
    )
    if choice != u"开始导入":
        ui.log(u"用户取消导入")
        ui.close()
        return

    overwrite = False
    if os.path.exists(out_dir):
        ui.event(u"目录已存在，等待选择…")
        ui.raise_window()
        ov = cmds.confirmDialog(
            title=u"目录已存在",
            message=u"过程目录已存在：\n%s\n\n是否覆盖原文件夹？\n\n是：清空后继续\n否：自动使用不重名后缀（如 MHI_xxx_2）"
            % out_dir,
            button=[u"是", u"否", u"取消"],
            defaultButton=u"否",
            cancelButton=u"取消",
            dismissString=u"取消",
        )
        if ov == u"取消":
            ui.log(u"用户取消导入")
            ui.close()
            return
        if ov == u"是":
            overwrite = True
            ui.log(u"将覆盖：%s" % out_dir)
        else:
            out_dir = unique_import_dir(out_dir)
            ui.log(u"改用新目录：%s" % out_dir)

    ui.raise_window()
    ui.event(u"开始解压与装配…")
    ui.status(u"导入进行中…")
    ui.set_percent(12)
    ui.log(u"开始导入 → %s" % out_dir)
    show_busy(u"解压与装配进行中…", title=u"导入 MH")

    try:
        state = import_ue_zip(
            zip_path, dest_dir=out_dir, verify=True, overwrite=overwrite, progress_ui=ui
        )
        assets = state.get("assets") or {}
        report = state.get("report") or {}
        assemble = state.get("assemble") or {}
        ui.event(u"导入完成")
        ui.set_percent(100)
        ui.raise_window()
        if assemble.get("method") == "ui":
            cmds.confirmDialog(
                title=u"导入 MH",
                message=u"已解压到：\n%s\n\n已打开 Character Assembler。\n请选择角色 %s，勾选 Head/Body/Textures 后 Assemble。\n完成后可用「检测当前角色」。"
                % (assets.get("char_dir"), assets.get("name")),
                button=[u"确定"],
            )
            return
        msg = u"导入完成。\n\n角色：%s\n目录：%s\n头：%s\n身：%s\n关节：%s\nCTRL：%s\n眨眼变形Δ：%s\n张嘴牙齿Δ：%s\n结果：%s" % (
            assets.get("name"),
            assets.get("char_dir"),
            report.get("head"),
            report.get("body"),
            report.get("joints"),
            report.get("ctrls"),
            report.get("blink_delta"),
            report.get("jaw_teeth_linked"),
            u"通过" if report.get("ok") else u"需检查",
        )
        cmds.confirmDialog(title=u"导入 MH", message=msg, button=[u"确定"])
    except Exception as ex:
        tb = traceback.format_exc()
        msg = str(ex)
        try:
            ui.event(u"导入失败")
            ui.log(msg[:500])
        except Exception:
            pass
        if "DNA file stream" in msg or "createEmbeddedNodeRL4" in msg or u"无法打开 DNA" in msg:
            cmds.confirmDialog(
                title=u"导入失败 — DNA 无法打开",
                message=(
                    u"MetaHuman 的 RL4 插件读不到 DNA 文件。\n\n"
                    u"常见原因：过程目录路径含中文（例如「下载」）。\n"
                    u"工具已改为自动复制到英文临时目录再装配；请重试一次导入。\n"
                    u"若仍失败，请把 zip 放到纯英文路径后再导入。\n\n"
                    u"%s"
                )
                % msg[-2800:],
                button=[u"确定"],
            )
        elif u"MetaHuman for Maya" in msg or "mh_character_assembler" in msg:
            cmds.confirmDialog(title=u"导入 MH — 需要插件", message=msg[-3500:], button=[u"确定"])
        else:
            cmds.confirmDialog(title=u"导入失败", message=tb[-2200:], button=[u"确定"])
        raise
    finally:
        end_busy()
