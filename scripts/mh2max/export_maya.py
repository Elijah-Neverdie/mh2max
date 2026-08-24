# -*- coding: utf-8 -*-
"""Maya-side export: limits, morph OBJs, assembled FBX, Max job file."""
from __future__ import print_function

import hashlib
import json
import os
import time

from maya import cmds, mel

from .detect import (
    GUI_SKIP,
    MESH_JOBS,
    resolve,
    short_name,
)
from .poses import POSE_JOBS


def _log(log_path, msg):
    line = "[%s] %s" % (time.strftime("%H:%M:%S"), msg)
    print(line)
    folder = os.path.dirname(log_path)
    if not os.path.isdir(folder):
        os.makedirs(folder)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def _ensure_plugin(name):
    try:
        if not cmds.pluginInfo(name, q=True, loaded=True):
            cmds.loadPlugin(name)
        return True
    except Exception:
        return False


def dump_limits(path):
    rows = []
    ctrls = (cmds.ls("CTRL_*", type="transform") or []) + (cmds.ls("*:CTRL_*", type="transform") or [])
    for ctrl in sorted(list(dict.fromkeys(ctrls))):
        short = short_name(ctrl)
        parents = cmds.listRelatives(ctrl, parent=True) or []
        frm = ""
        for p in parents:
            ps = short_name(p)
            if ps.startswith("FRM_"):
                frm = ps
                break
        if not frm:
            guess = "FRM_" + short[5:] if short.startswith("CTRL_") else ""
            if guess and resolve(guess):
                frm = guess

        def lim(axis):
            en = cmds.transformLimits(ctrl, q=True, **{"e" + axis: True})
            vals = cmds.transformLimits(ctrl, q=True, **{axis: True})
            return vals[0], vals[1], int(en[0]), int(en[1])

        xmin, xmax, exmin, exmax = lim("tx")
        ymin, ymax, eymin, eymax = lim("ty")
        zmin, zmax, ezmin, ezmax = lim("tz")
        rows.append(
            "\t".join(
                [
                    short,
                    frm,
                    str(xmin),
                    str(xmax),
                    str(exmin),
                    str(exmax),
                    str(ymin),
                    str(ymax),
                    str(eymin),
                    str(eymax),
                    str(zmin),
                    str(zmax),
                    str(ezmin),
                    str(ezmax),
                ]
            )
        )
    folder = os.path.dirname(path)
    if not os.path.isdir(folder):
        os.makedirs(folder)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(rows) + "\n")
    return len(rows)


def _set_ctrl(attr, value):
    if "." not in attr:
        return False
    node, plug = attr.split(".", 1)
    real = resolve(node) or (node if cmds.objExists(node) else None)
    if not real:
        return False
    full = real + "." + plug
    if not cmds.objExists(full) and not cmds.attributeQuery(plug, node=real, exists=True):
        return False
    try:
        cmds.setAttr(real + "." + plug, float(value))
        return True
    except Exception:
        return False


def _export_obj(mesh, path):
    folder = os.path.dirname(path)
    if not os.path.isdir(folder):
        os.makedirs(folder)
    cmds.select(mesh, r=True)
    cmds.file(
        path,
        force=True,
        options="groups=0;ptgroups=0;materials=0;smoothing=1;normals=1",
        type="OBJexport",
        pr=True,
        es=True,
    )


def _attr_valid(attr, value):
    """True when attr exists, is settable and value is inside transform limits."""
    if "." not in attr:
        return False
    node, plug = attr.split(".", 1)
    real = resolve(node)
    if not real:
        return False
    full = real + "." + plug
    try:
        if cmds.getAttr(full, l=True) or not cmds.getAttr(full, se=True):
            return False
        axis = plug[-1].lower()
        lo, hi = cmds.transformLimits(real, q=True, **{"t" + axis: True})
        en = cmds.transformLimits(real, q=True, **{"et" + axis: True})
        if en[0] and value < lo - 0.001:
            return False
        if en[1] and value > hi + 0.001:
            return False
    except Exception:
        return False
    return True


def _slider_axes():
    """Enumerate every settable GUI slider axis with its limit range.

    Returns [(attr, [poseValues...]), ...] using short (namespace-free) names.
    Rig-agnostic: works for both legacy DHI and UE 5.8 MetaHuman control sets,
    so renamed/locked tongue controls never produce failed exports again.
    """
    axes = []
    seen = set()
    for n in sorted(set(cmds.ls("CTRL_*", type="transform") or [])):
        short = short_name(n)
        if short in seen:
            continue
        if any(short == g or short.startswith(g) for g in GUI_SKIP):
            continue
        if "Switch" in short or short.endswith("Gui"):
            continue
        seen.add(short)
        for ax in ("X", "Y"):
            full = n + ".translate" + ax
            try:
                if cmds.getAttr(full, l=True) or not cmds.getAttr(full, se=True):
                    continue
                en = cmds.transformLimits(n, q=True, **{"et" + ax.lower(): True})
                lo, hi = cmds.transformLimits(n, q=True, **{"t" + ax.lower(): True})
                if not (en[0] or en[1]):
                    continue  # free axis = not a pose slider
            except Exception:
                continue
            vals = []
            if hi > 0.5:
                vals.append(1)
            if lo < -0.5:
                vals.append(-1)
            if vals:
                axes.append((short + ".translate" + ax, vals))
    return axes


def _mesh_sig(mesh):
    """Cheap deformation signature: component sums of world-space points."""
    import maya.api.OpenMaya as om2

    sl = om2.MSelectionList()
    sl.add(mesh)
    dag = sl.getDagPath(0)
    dag.extendToShape()
    pts = om2.MFnMesh(dag).getPoints(om2.MSpace.kWorld)
    sx = sy = sz = sa = 0.0
    for p in pts:
        sx += p.x
        sy += p.y
        sz += p.z
        sa += abs(p.x) + abs(p.y) + abs(p.z)
    return (sx, sy, sz, sa)


def _sig_moved(a, b, eps=5e-3):
    return any(abs(a[i] - b[i]) > eps for i in range(4))


def _mesh_shape(mesh):
    shapes = cmds.listRelatives(mesh, shapes=True, ni=True, fullPath=True) or []
    return shapes[0] if shapes else mesh


def _get_points(mesh):
    import maya.api.OpenMaya as om2

    sl = om2.MSelectionList()
    sl.add(_mesh_shape(mesh))
    return om2.MFnMesh(sl.getDagPath(0)).getPoints(om2.MSpace.kWorld)


def _combo_pairs(poses):
    """Within-control 2D corner combos derived from a folder's single-axis poses.

    RigLogic evaluates corner poses (e.g. CTRL_C_mouth at X=-1,Y=-1) with
    non-linear correctives; Max Morpher sums the X and Y targets linearly.
    For every control that deforms this mesh on both GUI axes we bake the
    bilinear corner residual (corner - X - Y + neutral) as an extra target.
    """
    by_ctrl = {}
    for attr, v in poses:
        node, plug = attr.split(".", 1)
        if plug in ("translateX", "translateY"):
            by_ctrl.setdefault(node, {}).setdefault(plug[-1], []).append(v)
    combos = []
    for node in sorted(by_ctrl):
        axes = by_ctrl[node]
        for vx in axes.get("X", []):
            for vy in axes.get("Y", []):
                combos.append((node, vx, vy))
    return combos


MORPH_BAKE_VERSION = "1.3.1"


def _zero_all_sliders(log_path):
    """Force every GUI slider axis to 0 before baking any target.

    A single controller left non-zero (e.g. the artist testing an open jaw
    while export runs) contaminates EVERY baked OBJ, and skip-if-exists then
    preserves the bad files forever. This was the root cause of Max poses not
    matching Maya at identical controller positions.
    """
    dirty = 0
    for attr, _vals in _slider_axes():
        node, plug = attr.split(".", 1)
        real = resolve(node)
        if not real:
            continue
        try:
            if abs(cmds.getAttr(real + "." + plug)) > 1e-4:
                dirty += 1
                cmds.setAttr(real + "." + plug, 0.0)
        except Exception:
            pass
    if dirty:
        _log(log_path, "zeroed %s non-neutral slider axes before bake" % dirty)
    return dirty


def _check_bake_version(out_dir, log_path):
    """Purge every baked OBJ once when the bake logic changes version.

    OBJs baked by older (buggy) logic pass the skip-if-exists size check, so a
    version stamp is the only reliable way to invalidate them in one-click use.
    """
    root = os.path.join(out_dir, "MorphTargets")
    stamp = os.path.join(root, "mh2max_bake.version")
    old = None
    try:
        with open(stamp, "r", encoding="utf-8") as f:
            old = f.read().strip()
    except Exception:
        pass
    if old != MORPH_BAKE_VERSION:
        purged = 0
        if os.path.isdir(root):
            for folder in os.listdir(root):
                sub = os.path.join(root, folder)
                if not os.path.isdir(sub):
                    continue
                for fn in os.listdir(sub):
                    if fn.lower().endswith(".obj"):
                        try:
                            os.remove(os.path.join(sub, fn))
                            purged += 1
                        except Exception:
                            pass
        _log(
            log_path,
            "bake version %s -> %s: purged %s stale objs for full rebake"
            % (old, MORPH_BAKE_VERSION, purged),
        )
    if not os.path.isdir(root):
        os.makedirs(root)
    with open(stamp, "w", encoding="utf-8") as f:
        f.write(MORPH_BAKE_VERSION)


def build_pose_jobs(out_dir, log_path):
    """Scan the live rig: which slider pose deforms which MESH_JOBS mesh.

    Replaces the hand-written POSE_JOBS tables (whose stale control names caused
    20 failed morphs and 67 uncovered sliders on UE 5.8 rigs). Result is cached
    in <out_dir>/mh2max_posejobs.json keyed by the slider/mesh fingerprint.
    """
    axes = _slider_axes()
    meshes = [(folder, resolve(mesh_name)) for folder, mesh_name in MESH_JOBS]
    meshes = [(f, m) for f, m in meshes if m]
    key_src = json.dumps([MORPH_BAKE_VERSION, axes, [f for f, _ in meshes]], sort_keys=True)
    key = hashlib.md5(key_src.encode("utf-8")).hexdigest()

    cache_path = os.path.join(out_dir, "mh2max_posejobs.json")
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            cached = json.load(f)
        if cached.get("key") == key:
            _log(log_path, "posejobs cache hit (%s)" % cache_path)
            return {f: [tuple(p) for p in ps] for f, ps in cached["jobs"].items()}
    except Exception:
        pass

    _log(log_path, "posejobs scan: axes=%s meshes=%s" % (len(axes), len(meshes)))
    base = {}
    for folder, mesh in meshes:
        base[folder] = _mesh_sig(mesh)
    jobs = {folder: [] for folder, _ in meshes}
    for attr, vals in axes:
        for v in vals:
            if not _set_ctrl(attr, v):
                _log(log_path, "posejobs skip unsettable %s=%s" % (attr, v))
                continue
            for folder, mesh in meshes:
                if _sig_moved(base[folder], _mesh_sig(mesh)):
                    jobs[folder].append((attr, v))
            _set_ctrl(attr, 0)
    for folder, _ in meshes:
        _log(log_path, "posejobs %s=%s" % (folder, len(jobs[folder])))
    try:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump({"key": key, "jobs": jobs}, f, ensure_ascii=False, indent=1)
    except Exception as ex:
        _log(log_path, "posejobs cache write fail %s" % ex)
    return jobs


def _export_combo_objs(combo_jobs, log_path, progress_cb=None, done=0, total=0):
    """Bake corner residual targets: corner - Xpose - Ypose + neutral.

    The residual mesh is synthesized on a temporary duplicate and exported as
    a normal OBJ target. Max wires it to |x|*|y| (bilinear weight), so at the
    corner the full RigLogic shape is reproduced while single-axis motion is
    untouched. Residuals below 0.01cm max displacement are skipped (control
    has no meaningful corner corrective).
    """
    import maya.api.OpenMaya as om2

    exported = failed = skipped = 0
    neutral = {}
    pose_pts = {}

    def posed_points(mesh, attr, val):
        key = (mesh, attr, val)
        if key not in pose_pts:
            _set_ctrl(attr, val)
            pose_pts[key] = _get_points(mesh)
            _set_ctrl(attr, 0)
        return pose_pts[key]

    for i, (mesh, folder, ctrl, vx, vy, path) in enumerate(combo_jobs):
        if progress_cb:
            if not progress_cb(done + i + 1, total, os.path.basename(path)):
                break
        if os.path.isfile(path) and os.path.getsize(path) > 1000:
            skipped += 1
            continue
        ax = ctrl + ".translateX"
        ay = ctrl + ".translateY"
        try:
            if mesh not in neutral:
                neutral[mesh] = _get_points(mesh)
            p0 = neutral[mesh]
            px = posed_points(mesh, ax, vx)
            py = posed_points(mesh, ay, vy)
            if not (_set_ctrl(ax, vx) and _set_ctrl(ay, vy)):
                raise RuntimeError("unsettable %s/%s" % (ax, ay))
            pc = _get_points(mesh)
            _set_ctrl(ax, 0)
            _set_ctrl(ay, 0)
            pts = []
            max_d = 0.0
            for k in range(len(p0)):
                # residual displacement δ = (corner-neutral) - (X-neutral) - (Y-neutral)
                ddx = pc[k].x - px[k].x - py[k].x + p0[k].x
                ddy = pc[k].y - px[k].y - py[k].y + p0[k].y
                ddz = pc[k].z - px[k].z - py[k].z + p0[k].z
                pts.append((p0[k].x + ddx, p0[k].y + ddy, p0[k].z + ddz))
                d = max(abs(ddx), abs(ddy), abs(ddz))
                if d > max_d:
                    max_d = d
            res = om2.MPointArray(pts)
            if max_d < 0.01:
                skipped += 1
                continue
            dup = cmds.duplicate(mesh, rr=True, name="mh2max_comboTmp")[0]
            try:
                sl = om2.MSelectionList()
                sl.add(_mesh_shape(dup))
                om2.MFnMesh(sl.getDagPath(0)).setPoints(res, om2.MSpace.kWorld)
                _export_obj(dup, path)
                exported += 1
            finally:
                cmds.delete(dup)
        except Exception as ex:
            failed += 1
            _set_ctrl(ax, 0)
            _set_ctrl(ay, 0)
            _log(log_path, "combo fail %s: %s" % (path, ex))
    if combo_jobs:
        _log(
            log_path,
            "combo residuals exported=%s skipped=%s failed=%s"
            % (exported, skipped, failed),
        )
    return exported, failed, skipped


def export_morphs(out_dir, log_path, progress_cb=None, face_only=True):
    """Bake per-head-part Morph OBJs for one-click Max assembly.

    face_only=True (default for 一键导出): export every MESH_JOBS head part
    (Face/Teeth/Saliva/eyes/…). Max keeps FACIAL joints at FBX bind pose, so
    each deforming mesh must carry its own Morpher — skipping Saliva etc. leaves
    gingiva frozen while the jaw Morph opens the mouth.

    face_only=False is reserved for a future full-body morph pass; today it
    still walks the same MESH_JOBS table.
    """
    _ensure_plugin("objExport")
    # Neutral scene + fresh bake when logic changed: both are hard requirements
    # for targets that byte-for-byte reproduce the Maya rig.
    _zero_all_sliders(log_path)
    _check_bake_version(out_dir, log_path)
    # Live-rig pose scan first (control names differ across MetaHuman versions);
    # static POSE_JOBS is only a fallback, filtered against the actual rig.
    try:
        pose_map = build_pose_jobs(out_dir, log_path)
        pose_src = "scan"
    except Exception as ex:
        _log(log_path, "posejobs scan failed, fallback to static tables: %s" % ex)
        pose_map = {}
        for folder, plist in POSE_JOBS:
            pose_map[folder] = [(a, v) for a, v in plist if _attr_valid(a, v)]
        pose_src = "static-filtered"
    _log(log_path, "pose source=%s" % pose_src)
    exported = failed = skipped = 0
    jobs = []
    # Always export the full head-part table (MESH_JOBS). face_only no longer
    # drops Saliva/EyeShell — that was the gingiva bug in the one-click path.
    _ = face_only  # kept for API compatibility with pipeline.run_export
    for folder, mesh_name in MESH_JOBS:
        poses = pose_map.get(folder) or []
        mesh = resolve(mesh_name)
        if not mesh:
            _log(log_path, "skip mesh missing %s (%s)" % (folder, mesh_name))
            continue
        dest = os.path.join(out_dir, "MorphTargets", folder)
        if not os.path.isdir(dest):
            os.makedirs(dest)
        for attr, value in poses:
            base = attr + str(value)
            # Prefix non-Face targets so Max import names do not collide with Face morphs
            fname = (folder + "_" + base) if folder != "Face" else base
            jobs.append((mesh, folder, attr, value, os.path.join(dest, fname + ".obj")))

    # Corner-combo residual targets (bilinear correctives for 2D controls)
    combo_jobs = []
    for folder, mesh_name in MESH_JOBS:
        mesh = resolve(mesh_name)
        if not mesh:
            continue
        dest = os.path.join(out_dir, "MorphTargets", folder)
        for ctrl, vx, vy in _combo_pairs(pose_map.get(folder) or []):
            base = "%s.comboX%dY%d" % (ctrl, vx, vy)
            fname = (folder + "_" + base) if folder != "Face" else base
            combo_jobs.append((mesh, folder, ctrl, vx, vy, os.path.join(dest, fname + ".obj")))

    # Purge stale OBJs from previous exports (renamed/removed poses) so Max
    # never imports targets that no longer match the live rig.
    want = set(os.path.normcase(p) for _m, _f, _a, _v, p in jobs)
    want.update(os.path.normcase(p) for _m, _f, _c, _x, _y, p in combo_jobs)
    purged = 0
    for folder, _mesh_name in MESH_JOBS:
        dest = os.path.join(out_dir, "MorphTargets", folder)
        if not os.path.isdir(dest):
            continue
        for fn in os.listdir(dest):
            if not fn.lower().endswith(".obj"):
                continue
            full = os.path.join(dest, fn)
            if os.path.normcase(full) not in want:
                try:
                    os.remove(full)
                    purged += 1
                except Exception as ex:
                    _log(log_path, "purge fail %s: %s" % (full, ex))
    if purged:
        _log(log_path, "purged stale morph objs=%s" % purged)

    total = len(jobs) + len(combo_jobs)
    _log(
        log_path,
        "morph jobs=%s combos=%s folders=%s"
        % (len(jobs), len(combo_jobs), ",".join(f for f, _ in MESH_JOBS)),
    )
    for i, (mesh, folder, attr, value, path) in enumerate(jobs):
        if progress_cb:
            if not progress_cb(i + 1, total, os.path.basename(path)):
                break
        if os.path.isfile(path) and os.path.getsize(path) > 1000:
            skipped += 1
            continue
        if not _set_ctrl(attr, value):
            failed += 1
            _log(log_path, "skip attr %s" % attr)
            continue
        try:
            _export_obj(mesh, path)
            exported += 1
        except Exception as ex:
            failed += 1
            _log(log_path, "fail %s: %s" % (path, ex))
        _set_ctrl(attr, 0)

    exported_c, failed_c, skipped_c = _export_combo_objs(
        combo_jobs, log_path, progress_cb=progress_cb, done=len(jobs), total=total
    )
    exported += exported_c
    failed += failed_c
    skipped += skipped_c

    # reset all used attrs
    for poses in pose_map.values():
        for attr, _value in poses:
            _set_ctrl(attr, 0)
    return {
        "exported": exported,
        "failed": failed,
        "skipped": skipped,
        "total": total,
        "single_exported": exported - exported_c,
        "combo_exported": exported_c,
        "combo_skipped": skipped_c,
        "folders": [f for f, _ in MESH_JOBS],
    }


def _unique(seq):
    seen = set()
    out = []
    for n in seq:
        if n and n not in seen and cmds.objExists(n):
            seen.add(n)
            out.append(n)
    return out


def export_character_fbx(path, info, log_path):
    _ensure_plugin("fbxmaya")
    sel = []
    for key in ("head", "body", "body_grp", "head_grp", "gui", "gui_grp", "combined", "flipflops"):
        n = info.get(key)
        if n:
            sel.append(n)
    for n in (info.get("head_parts") or {}).values():
        sel.append(n)

    # All visible lod0 meshes (head/body parts); skip combined duplicates later in Max
    for n in (cmds.ls("*lod0*", type="transform", long=True) or []) + (
        cmds.ls("*:*lod0*", type="transform", long=True) or []
    ):
        s = short_name(n).lower()
        if "combined" in s or "flipflop" in s:
            continue
        shapes = cmds.listRelatives(n, shapes=True, ni=True) or []
        if any(cmds.nodeType(sh) == "mesh" for sh in shapes):
            sel.append(n)

    for n in (
        "GRP_faceGUI",
        "CTRL_faceGUI",
        "FRM_faceGUI",
        "headGui_grp",
        "headRig_grp",
        "geometry_grp",
        "rig",
        "joints_grp",
        "root",
        "DHIbody:root",
        "MHBody:root",
        "MHHead:spine_04",
        "pelvis",
        "DHIbody:pelvis",
        "MHBody:pelvis",
        "spine_04",
        "head",
        "Main",
        "Group",
        "AxisCorrect_BodyYupToZup",
    ):
        r = resolve(n)
        if r:
            sel.append(r)
    sel.extend(cmds.ls("CTRL_*", type="transform") or [])
    sel.extend(cmds.ls("*:CTRL_*", type="transform") or [])
    sel.extend(cmds.ls("FRM_*", type="transform") or [])
    sel.extend(cmds.ls("*:FRM_*", type="transform") or [])

    # Full skeleton (body + face) including MHBody / MHHead namespaces
    for j in cmds.ls(type="joint", long=True) or []:
        sel.append(j)

    uniq = _unique(sel)
    extra = []
    for r in list(uniq):
        extra.extend(cmds.listRelatives(r, ad=True, f=True) or [])
    uniq = _unique(uniq + extra)
    cmds.select(uniq, r=True, ne=True)

    folder = os.path.dirname(path)
    if not os.path.isdir(folder):
        os.makedirs(folder)
    fbx = path.replace("\\", "/")
    try:
        mel.eval("FBXExportSmoothingGroups -v true")
        mel.eval("FBXExportSmoothMesh -v false")
        mel.eval("FBXExportSkins -v true")
        mel.eval("FBXExportShapes -v false")
        mel.eval("FBXExportInputConnections -v false")
        mel.eval("FBXExportBakeComplexAnimation -v false")
        mel.eval("FBXExportCameras -v false")
        mel.eval("FBXExportLights -v false")
        mel.eval("FBXExportEmbeddedTextures -v false")
        mel.eval('FBXExport -f "%s" -s' % fbx)
    except Exception as ex:
        _log(log_path, "FBXExport MEL failed, cmds.file: %s" % ex)
        cmds.file(fbx, force=True, options="v=0;", type="FBX export", pr=True, es=True)
    size = os.path.getsize(path) if os.path.isfile(path) else 0
    _log(log_path, "fbx selected=%s bytes=%s" % (len(cmds.ls(sl=True) or []), size))
    return {"selected": len(uniq), "bytes": size, "path": path}


def _ms_escape(s):
    return (s or "").replace("\\", "\\\\").replace('"', '\\"')


def write_job_files(out_dir, info, paths):
    job = {
        "character": info.get("character"),
        "body_type": info.get("body_type"),
        "maya_up": info.get("maya_up"),
        "linear_unit": info.get("linear_unit"),
        "nodes": {
            "head": short_name(info.get("head")) or "head_lod0_mesh",
            "body": short_name(info.get("body")) or "",
            "body_grp": short_name(info.get("body_grp")) or "body_lod0_grp",
            "head_grp": short_name(info.get("head_grp")) or "head_grp",
            "gui": short_name(info.get("gui")) or "CTRL_faceGUI",
            "gui_grp": short_name(info.get("gui_grp")) or "GRP_faceGUI",
            "combined": short_name(info.get("combined")) or "",
            "flipflops": short_name(info.get("flipflops")) or "",
        },
        "bbox": info.get("bbox"),
        "world": info.get("world"),
        "paths": paths,
        "gui_skip": list(GUI_SKIP),
    }
    json_path = os.path.join(out_dir, "mh2max_job.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(job, f, ensure_ascii=False, indent=2)

    plugin_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    pipeline_ms = os.path.join(plugin_root, "max", "mh2max_pipeline.ms")
    job_ms = os.path.join(out_dir, "mh2max_job.ms")
    n = job["nodes"]
    p = paths
    body = n["body"]
    combined = n["combined"]
    ms = u"""-- auto-generated by mh2max
-- -U MAXScript runs after Max UI exists. Use .NET timer (global tick fn) to paint first frame.
global mh2max_outDir = @"%s"
global mh2max_fbx = @"%s"
global mh2max_morphDir = @"%s"
global mh2max_morphRoot = @"%s"
global mh2max_limits = @"%s"
global mh2max_saveBase = @"%s"
global mh2max_log = @"%s"
global mh2max_head = "%s"
global mh2max_body = "%s"
global mh2max_bodyGrp = "%s"
global mh2max_headGrp = "%s"
global mh2max_gui = "%s"
global mh2max_guiGrp = "%s"
global mh2max_combined = "%s"
global mh2max_character = "%s"
global mh2max_bodyType = "%s"
global mh2max_pipelinePath = @"%s"
global mh2max_bootDone = false
global mh2max_bootTimer = undefined

fn mh2max_runPipeline = (
    if mh2max_bootDone == true then return false
    mh2max_bootDone = true
    try (
        try ( completeRedraw() ) catch ()
        fileIn mh2max_pipelinePath
    ) catch (
        messageBox ("mh2max 启动失败:\\n" + (getCurrentException() as string)) title:"mh2max"
    )
    true
)

fn mh2max_onBootTick = (
    try (
        if mh2max_bootTimer != undefined then (
            mh2max_bootTimer.stop()
            dotNet.removeAllEventHandlers mh2max_bootTimer
        )
    ) catch ()
    mh2max_bootTimer = undefined
    mh2max_runPipeline()
)

try (
    mh2max_bootTimer = dotNetObject "System.Windows.Forms.Timer"
    dotNet.addEventHandler mh2max_bootTimer "Tick" mh2max_onBootTick
    mh2max_bootTimer.Interval = 1000
    mh2max_bootTimer.Start()
) catch (
    mh2max_runPipeline()
)
""" % (
        out_dir,
        p["fbx"],
        p["morph_face"],
        p.get("morph_root") or os.path.join(out_dir, "MorphTargets"),
        p["limits"],
        p["save_max_base"],
        p["log_max"],
        n["head"],
        body,
        n["body_grp"],
        n["head_grp"],
        n["gui"],
        n["gui_grp"],
        combined,
        info.get("character") or "MetaHuman",
        info.get("body_type") or "unknown",
        pipeline_ms,
    )
    with open(job_ms, "w", encoding="utf-8") as f:
        f.write(ms)
    return json_path, job_ms
