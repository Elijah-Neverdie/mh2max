# -*- coding: utf-8 -*-
"""Standardize a non-MetaHuman Maya face/body rig for mh2max export.

Hard rules:
  * Never rename existing controllers or joints.
  * Show body/face controllers when present; report when missing.
  * Missing slots can be filled by user pick/type.
  * List face panel must not overlap the character bbox.
"""
from __future__ import print_function

import json
import math

from maya import cmds, mel

from .detect import MESH_JOBS, resolve, short_name
from .standardize_ui import prompt_slot

META_NODE = "mh2max_meta"
UI_GRP = "mh2max_ui_grp"
PANEL_ROOT = "mh2max_facePanel"
PROP_MAP = "mh2max_std_map"
PROP_FLAG = "mh2max_standardized"


def _ensure_meta():
    if not cmds.objExists(META_NODE):
        cmds.createNode("network", name=META_NODE)
    return META_NODE


def _load_map():
    n = _ensure_meta()
    raw = cmds.getAttr(n + "." + PROP_MAP) if cmds.attributeQuery(PROP_MAP, n=n, exists=True) else None
    if not raw:
        # try userProp on transform fallback
        if cmds.objExists(META_NODE):
            try:
                raw = cmds.getAttr(META_NODE + "." + PROP_MAP)
            except Exception:
                raw = None
    if isinstance(raw, (list, tuple)) and raw:
        raw = raw[0]
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except Exception:
        return {}


def _save_map(data):
    n = _ensure_meta()
    if not cmds.attributeQuery(PROP_MAP, n=n, exists=True):
        cmds.addAttr(n, ln=PROP_MAP, dt="string")
    if not cmds.attributeQuery(PROP_FLAG, n=n, exists=True):
        cmds.addAttr(n, ln=PROP_FLAG, at="bool")
    cmds.setAttr(n + "." + PROP_MAP, json.dumps(data, ensure_ascii=False), type="string")
    cmds.setAttr(n + "." + PROP_FLAG, True)


def mapped_resolve(logical_name, data=None):
    """Resolve logical MH name via standardize map, then scene resolve."""
    data = data if data is not None else _load_map()
    meshes = (data.get("meshes") or {})
    real = meshes.get(logical_name) or logical_name
    return resolve(real) or (real if cmds.objExists(real) else None)


def can_standardize():
    """True if scene looks like FRM + *_Ctrl custom MH-style GUI, or has any face-ish ctrls."""
    frms = cmds.ls("FRM_*", type="transform") or []
    paired = 0
    for f in frms:
        kids = cmds.listRelatives(f, c=True, type="transform") or []
        if any(short_name(k).endswith("_Ctrl") for k in kids):
            paired += 1
    if paired >= 10:
        return True, u"检测到 MetaHuman 式 FRM + *_Ctrl（%s 对）" % paired
    # any face GUI root
    for n in ("FRM_faceGUI", "FaceGUI_Ctrl", "faceGUI"):
        if cmds.objExists(n):
            return True, u"检测到面部 GUI：%s" % n
    # body master present — still allow with user pick
    for n in ("Master_Ctrl", "COG_Ctrl", "World"):
        if cmds.objExists(n):
            return True, u"检测到身体层级：%s（面部可能需手动指定）" % n
    return False, u"未识别到可标准化的角色控制器结构"


def _find_first(names):
    for n in names:
        if cmds.objExists(n):
            return cmds.ls(n, long=True)[0]
    return None


def _find_mesh_heuristic(keywords, prefer_contains=None):
    """Pick largest mesh transform matching keywords."""
    best = None
    best_n = -1
    for m in cmds.ls(type="mesh") or []:
        parents = cmds.listRelatives(m, p=True, f=True) or []
        if not parents:
            continue
        tr = parents[0]
        sn = short_name(tr).lower()
        if not any(k in sn for k in keywords):
            continue
        if prefer_contains and prefer_contains not in sn:
            # still allow but lower priority via vert count only
            pass
        try:
            nv = int(cmds.polyEvaluate(tr, v=True) or 0)
        except Exception:
            nv = 0
        if nv > best_n:
            best_n = nv
            best = tr
    return best


def _outbound_drive_score(node):
    """Higher = more likely the true Maya BS/rig driver (not a Max-facing proxy).

    Real custom drivers (`*_Ctrl`) usually own outbound animCurves / direct plugs.
    Proxies (`CTRL_*`) either drive those originals via connectAttr, or (on stock MH)
    are themselves the drivers — both cases are handled by inventory pairing.
    """
    if not node or not cmds.objExists(node):
        return -1
    score = 0
    sn = short_name(node)
    # Prefer classic custom naming as the driven/real side of a FRM pair
    if sn.endswith("_Ctrl") and not sn.startswith("CTRL_"):
        score += 50
    if sn.startswith("CTRL_"):
        score += 5  # stock MH / already-standardized handle
    for ax in ("translateX", "translateY", "translateZ"):
        plug = node + "." + ax
        try:
            outs = cmds.listConnections(plug, s=False, d=True, plugs=True) or []
        except Exception:
            outs = []
        for dst in outs:
            score += 8
            dl = (dst or "").lower()
            if "blendshape" in dl or "weight" in dl or "riglogic" in dl:
                score += 40
            if "animcurve" in dl or dl.endswith("input"):
                score += 10
        try:
            ins = cmds.listConnections(plug, s=True, d=False, plugs=True) or []
        except Exception:
            ins = []
        # Driven by another transform → this node is NOT the artist-facing Max driver
        for src in ins:
            score -= 15
            if ".translate" in (src or ""):
                score -= 25
        try:
            if cmds.getAttr(plug, se=True) and not cmds.getAttr(plug, l=True):
                score += 2
        except Exception:
            pass
    return score


def _pick_real_driver(candidates, stem):
    """Choose the Maya-side real driver among FRM children / aliases."""
    if not candidates:
        return None
    exact = None
    scored = []
    for c in candidates:
        sn = short_name(c)
        if sn == stem + "_Ctrl":
            exact = c
        scored.append((_outbound_drive_score(c), c))
    scored.sort(key=lambda x: x[0], reverse=True)
    # Exact custom name wins if it scores near the top (or no better candidate)
    if exact is not None:
        best_s, best_n = scored[0]
        exact_s = _outbound_drive_score(exact)
        if exact_s >= best_s - 20:
            return exact
    return scored[0][1]


def inventory():
    """Heuristic inventory of body/face/meshes. Does not rename anything."""
    inv = {
        "body_root": _find_first(["Master_Ctrl", "COG_Ctrl", "root", "World"]),
        "face_gui": _find_first(["FRM_faceGUI", "FaceGUI_Ctrl", "CTRL_faceGUI", "GRP_faceGUI"]),
        "face_ctrls": [],
        "frm_pairs": [],  # (frm, real_ctrl, logical_ctrl)
        "meshes": {},
        "extra_meshes": [],
        "missing": [],
        "found": [],
        "driver_notes": [],
    }
    frms = cmds.ls("FRM_*", type="transform") or []
    for f in frms:
        fs = short_name(f)
        if not fs.startswith("FRM_"):
            continue
        stem = fs[4:]  # C_jaw
        kids = cmds.listRelatives(f, c=True, type="transform") or []
        candidates = []
        for k in kids:
            ks = short_name(k)
            if ks.startswith("CTRL_"):
                continue  # Max-facing / already proxy — not the "real" custom driver
            if ks == stem + "_Ctrl" or ks.endswith("_Ctrl"):
                candidates.append(k)
        # Also accept stem-named child without _Ctrl suffix if it drives BS
        if not candidates:
            for k in kids:
                ks = short_name(k)
                if ks.startswith("CTRL_") or ks.startswith("FRM_") or ks.startswith("TEXT_"):
                    continue
                if _outbound_drive_score(k) >= 20:
                    candidates.append(k)
        real = _pick_real_driver(candidates, stem)
        if real:
            logical = "CTRL_" + stem
            inv["frm_pairs"].append((f, real, logical))
            inv["face_ctrls"].append(real)
            inv["driver_notes"].append(
                u"%s → real=%s (score=%s) proxy=%s"
                % (stem, short_name(real), _outbound_drive_score(real), logical)
            )

    # also existing CTRL_*
    for c in (cmds.ls("CTRL_*", type="transform") or []):
        if c not in inv["face_ctrls"]:
            inv["face_ctrls"].append(c)

    mesh_guess = {
        "head_lod0_mesh": _find_mesh_heuristic(["head"], prefer_contains="head"),
        "teeth_lod0_mesh": _find_mesh_heuristic(["teeth"]),
        "eyelashes_lod0_mesh": _find_mesh_heuristic(["eyelash", "lashes"]),
        "eyeshell_lod0_mesh": _find_mesh_heuristic(["eyes", "eye"]),
        "body": _find_mesh_heuristic(["body"], prefer_contains="body"),
    }
    # prefer SM_Male_Head over Eyes for head
    head_alt = _find_first(["SM_Male_Head_01", "head_lod0_mesh"])
    if head_alt:
        mesh_guess["head_lod0_mesh"] = head_alt
    teeth_alt = _find_first(["SM_Male_Teeth_01", "teeth_lod0_mesh"])
    if teeth_alt:
        mesh_guess["teeth_lod0_mesh"] = teeth_alt
    lash_alt = _find_first(["SM_Male_Eyelash_01", "eyelashes_lod0_mesh"])
    if lash_alt:
        mesh_guess["eyelashes_lod0_mesh"] = lash_alt
    body_alt = _find_first(["SM_Male_Body_01"])
    if body_alt:
        mesh_guess["body"] = body_alt
        mesh_guess["m_med_unw_body_lod0_mesh"] = body_alt

    for k, v in mesh_guess.items():
        if v:
            inv["meshes"][k] = v
            inv["found"].append(u"%s → %s" % (k, short_name(v)))
        else:
            inv["missing"].append(k)

    # Full character mesh set (legs/hands/clothes) — Body_01 alone is often torso-only
    extra = []
    seen = set(short_name(v).lower() for v in inv["meshes"].values() if v)
    for m in cmds.ls(type="mesh") or []:
        parents = cmds.listRelatives(m, p=True, f=True) or []
        if not parents:
            continue
        tr = parents[0]
        sn = short_name(tr)
        low = sn.lower()
        if low in seen or low.startswith("mh2max_"):
            continue
        if any(
            t in low
            for t in (
                "leg",
                "hand",
                "foot",
                "shoe",
                "pant",
                "top",
                "cloth",
                "sock",
                "body",
                "hair",
                "brow",
                "beard",
                "mustache",
            )
        ) or sn.startswith(("SM_", "SP_", "OS_", "SK_")):
            try:
                nv = int(cmds.polyEvaluate(tr, v=True) or 0)
            except Exception:
                nv = 0
            if nv < 50:
                continue
            extra.append(tr)
            seen.add(low)
    inv["extra_meshes"] = extra
    if extra:
        inv["found"].append(u"附加网格 × %s（腿/手/服装等）" % len(extra))

    if inv["body_root"]:
        inv["found"].append(u"身体主控 → %s" % short_name(inv["body_root"]))
    else:
        inv["missing"].append("body_root")

    if inv["face_gui"]:
        inv["found"].append(u"面部 GUI → %s" % short_name(inv["face_gui"]))
    else:
        inv["missing"].append("face_gui")

    if inv["frm_pairs"] or len(inv["face_ctrls"]) >= 10:
        inv["found"].append(u"面部控制器 × %s" % len(inv["face_ctrls"]))
    else:
        inv["missing"].append("face_ctrls")

    return inv


def _unhide_chain(node):
    if not node or not cmds.objExists(node):
        return
    cur = node
    while cur:
        try:
            if cmds.attributeQuery("visibility", n=cur, exists=True):
                if cmds.getAttr(cur + ".v", lock=True):
                    cmds.setAttr(cur + ".v", lock=False)
                cmds.setAttr(cur + ".v", True)
            cmds.showHidden(cur)
        except Exception:
            pass
        parents = cmds.listRelatives(cur, p=True, f=True) or []
        cur = parents[0] if parents else None


def _pump_ui():
    """Force Maya to paint progressWindow (confirmDialog leaves only a busy cursor otherwise)."""
    try:
        cmds.refresh(force=True)
    except Exception:
        pass
    try:
        from maya import utils as maya_utils

        maya_utils.processIdleEvents()
    except Exception:
        pass
    try:
        from PySide2 import QtWidgets  # type: ignore

        app = QtWidgets.QApplication.instance()
        if app:
            app.processEvents()
            return
    except Exception:
        pass
    try:
        from PySide6 import QtWidgets  # type: ignore

        app = QtWidgets.QApplication.instance()
        if app:
            app.processEvents()
    except Exception:
        pass


def _prog(status, progress=None, title=None):
    """Update or open Maya progressWindow. progress 0..100."""
    try:
        exists = False
        try:
            exists = bool(cmds.progressWindow(q=True, exists=True))
        except Exception:
            exists = False
        if exists:
            kw = {"status": status}
            if progress is not None:
                kw["progress"] = int(max(0, min(100, progress)))
            cmds.progressWindow(edit=True, **kw)
        else:
            cmds.progressWindow(
                title=title or u"标准化角色",
                progress=int(progress or 0),
                status=status,
                isInterruptable=False,
                minValue=0,
                maxValue=100,
            )
        _pump_ui()
    except Exception:
        pass


def _prog_end():
    try:
        if cmds.progressWindow(q=True, exists=True):
            cmds.progressWindow(endProgress=True)
    except Exception:
        pass
    _pump_ui()


def _prog_begin(status=u"开始标准化…", progress=0, title=u"标准化角色"):
    """Always tear down then open a fresh progress strip (survives confirmDialog)."""
    _prog_end()
    try:
        cmds.progressWindow(
            title=title,
            progress=int(progress or 0),
            status=status,
            isInterruptable=False,
            minValue=0,
            maxValue=100,
        )
        _pump_ui()
    except Exception:
        pass


def show_controllers(inv):
    """Unhide body/face controllers and fit the view."""
    targets = []
    if inv.get("body_root"):
        _unhide_chain(inv["body_root"])
        targets.append(inv["body_root"])
    if inv.get("face_gui"):
        _unhide_chain(inv["face_gui"])
        targets.append(inv["face_gui"])
    for _frm, real, _log in inv.get("frm_pairs") or []:
        _unhide_chain(real)
    # also unhide CTRL_* proxies under FRM
    for c in cmds.ls("CTRL_*", type="transform") or []:
        try:
            if cmds.getAttr(c + ".v") is False:
                cmds.setAttr(c + ".v", True)
        except Exception:
            pass
        _unhide_chain(c)
    # nurbs curves on
    try:
        for panel in cmds.getPanel(type="modelPanel") or []:
            cmds.modelEditor(panel, e=True, nurbsCurves=True, controllers=True)
    except Exception:
        pass
    if targets:
        try:
            cmds.select(targets, r=True)
            cmds.viewFit(targets)
        except Exception:
            try:
                mel.eval("FitSelected;")
            except Exception:
                pass
    try:
        cmds.refresh(force=True)
    except Exception:
        pass
    return targets


def _ctrl_axis_enabled(node, axis):
    """Return (lo, hi, enabled) for translate axis."""
    kw = {"tx": ("tx", "etx"), "ty": ("ty", "ety"), "tz": ("tz", "etz")}[axis]
    try:
        vals = cmds.transformLimits(node, q=True, **{kw[0]: True})
        en = cmds.transformLimits(node, q=True, **{kw[1]: True})
        enabled = bool(en[0] or en[1]) and abs(float(vals[1]) - float(vals[0])) > 1e-6
        return float(vals[0]), float(vals[1]), enabled
    except Exception:
        return -1.0, 1.0, False


def _copy_shapes_onto(src, dst):
    """Instance/duplicate nurbs shapes from src onto dst for viewport picking."""
    shapes = cmds.listRelatives(src, shapes=True, ni=True, f=True) or []
    if not shapes:
        return 0
    n = 0
    for sh in shapes:
        try:
            dup = cmds.duplicate(sh, rr=True)[0]
            # duplicate of a shape may return the shape or its transform
            if cmds.nodeType(dup) == "transform":
                dshapes = cmds.listRelatives(dup, shapes=True, f=True) or []
                for ds in dshapes:
                    cmds.parent(ds, dst, shape=True, add=True)
                cmds.delete(dup)
            else:
                cmds.parent(dup, dst, shape=True, r=True)
            n += 1
        except Exception:
            try:
                # fallback: parent shape under dst as instance
                cmds.parent(sh, dst, shape=True, add=True)
                n += 1
            except Exception:
                pass
    return n


def _ensure_proxy_drive(proxy, real):
    for attr in ("translateX", "translateY", "translateZ"):
        src = proxy + "." + attr
        dst = real + "." + attr
        try:
            if cmds.isConnected(src, dst):
                continue
            if cmds.listConnections(dst, s=True, d=False):
                continue
            cmds.connectAttr(src, dst, f=True)
        except Exception:
            pass


def _mark_original_driven(real):
    """Hide original *_Ctrl so Max/Maya artists only pick CTRL_* Morph handles.

    After connectAttr, originals are driven (feel stuck / limited). Keep the node
    (no rename) but make it non-pickable, non-exported-looking, and locked.
    """
    if not real or not cmds.objExists(real):
        return
    try:
        for sh in cmds.listRelatives(real, shapes=True, ni=True) or []:
            try:
                cmds.setAttr(sh + ".visibility", False)
            except Exception:
                pass
            try:
                # template: visible in X-ray-ish but not selectable in viewport
                if cmds.attributeQuery("template", n=sh, exists=True):
                    cmds.setAttr(sh + ".template", True)
            except Exception:
                pass
        if cmds.attributeQuery("overrideEnabled", n=real, exists=True):
            cmds.setAttr(real + ".overrideEnabled", True)
            cmds.setAttr(real + ".overrideDisplayType", 2)  # Reference
        try:
            cmds.setAttr(real + ".visibility", False)
        except Exception:
            pass
        # Soft-lock so FBX/Max sees them as non-animatable decor
        for ax in ("tx", "ty", "tz", "rx", "ry", "rz", "sx", "sy", "sz"):
            try:
                cmds.setAttr(real + "." + ax, lock=True)
            except Exception:
                pass
    except Exception:
        pass


def create_ctrl_proxies(inv, progress_cb=None):
    """Create CTRL_* under FRM that drive existing *_Ctrl without renaming.

    Proxies keep a visible curve shape (copied from the original) so Max can show/pick them.
    """
    created = []
    skipped = []
    repaired = []
    pairs = inv.get("frm_pairs") or []
    total = max(1, len(pairs))
    for i, (frm, real, logical) in enumerate(pairs):
        if progress_cb and (i % 8 == 0 or i + 1 == total):
            progress_cb(
                u"创建 CTRL 代理 %s/%s：%s" % (i + 1, total, logical),
                20 + int(50.0 * i / total),
            )
        if cmds.objExists(logical):
            proxy = cmds.ls(logical, long=True)[0]
            if short_name(proxy) == short_name(real):
                skipped.append(logical)
                continue
            # repair: older run made empty hidden dummies — add shapes + unhide
            shapes = cmds.listRelatives(proxy, shapes=True, ni=True) or []
            if not shapes:
                _copy_shapes_onto(real, proxy)
                repaired.append(logical)
            try:
                cmds.setAttr(proxy + ".visibility", True)
            except Exception:
                pass
            _ensure_proxy_drive(proxy, real)
            _mark_original_driven(real)
            skipped.append(logical)
            continue
        # create proxy under same FRM
        proxy = cmds.group(em=True, name=logical, parent=frm)
        cmds.xform(proxy, os=True, t=(0, 0, 0), ro=(0, 0, 0))
        for ax, (q, e) in (("tx", ("tx", "etx")), ("ty", ("ty", "ety")), ("tz", ("tz", "etz"))):
            try:
                vals = cmds.transformLimits(real, q=True, **{q: True})
                en = cmds.transformLimits(real, q=True, **{e: True})
                cmds.transformLimits(proxy, **{q: vals, e: en})
            except Exception:
                pass
        _copy_shapes_onto(real, proxy)
        _ensure_proxy_drive(proxy, real)
        _mark_original_driven(real)
        try:
            cmds.setAttr(proxy + ".visibility", True)
        except Exception:
            pass
        created.append(proxy)
    return created, skipped, repaired


def _character_bbox(inv):
    nodes = []
    for k in ("head_lod0_mesh", "body", "m_med_unw_body_lod0_mesh"):
        n = inv.get("meshes", {}).get(k)
        if n and cmds.objExists(n):
            nodes.append(n)
    if not nodes:
        for m in cmds.ls(type="mesh") or []:
            p = cmds.listRelatives(m, p=True, f=True) or []
            if p:
                nodes.append(p[0])
            if len(nodes) > 12:
                break
    if not nodes:
        return (-10, 0, -10, 10, 170, 10)
    bb = cmds.exactWorldBoundingBox(nodes)
    return tuple(bb)


def _place_panel_no_overlap(panel, inv):
    """Place panel to the +X outside of character bbox."""
    xmin, ymin, zmin, xmax, ymax, zmax = _character_bbox(inv)
    width = max(1.0, xmax - xmin)
    height = max(1.0, ymax - ymin)
    margin = max(5.0, width * 0.25)
    # panel size estimate
    px = xmax + margin
    py = ymin + height * 0.55
    pz = (zmin + zmax) * 0.5
    for _ in range(8):
        cmds.xform(panel, ws=True, t=(px, py, pz))
        pbb = cmds.exactWorldBoundingBox(panel)
        # expand panel bb a bit
        overlap = not (
            pbb[3] < xmin or pbb[0] > xmax or pbb[4] < ymin or pbb[1] > ymax or pbb[5] < zmin or pbb[2] > zmax
        )
        if not overlap:
            return True
        px += margin
    return False


def _make_1d_ctrl(name, parent, length=2.0):
    curve = cmds.curve(
        name=name,
        d=1,
        p=[(0, 0, 0), (0, length, 0)],
    )
    if parent:
        curve = cmds.parent(curve, parent)[0]
    cmds.transformLimits(curve, ty=(0, 1), ety=(True, True))
    cmds.transformLimits(curve, tx=(0, 0), etx=(True, True))
    cmds.transformLimits(curve, tz=(0, 0), etz=(True, True))
    return curve


def _make_2d_ctrl(name, parent, size=1.5):
    s = size
    curve = cmds.curve(
        name=name,
        d=1,
        p=[(-s, -s, 0), (s, -s, 0), (s, s, 0), (-s, s, 0), (-s, -s, 0)],
    )
    if parent:
        curve = cmds.parent(curve, parent)[0]
    cmds.transformLimits(curve, tx=(-1, 1), etx=(True, True))
    cmds.transformLimits(curve, ty=(-1, 1), ety=(True, True))
    cmds.transformLimits(curve, tz=(0, 0), etz=(True, True))
    return curve


def build_list_face_panel(inv, driver_nodes):
    """Build a scroll-like vertical list of 1D/2D CTRLs that drive driver_nodes.

    driver_nodes: list of existing transforms to drive (not renamed).
    """
    if cmds.objExists(PANEL_ROOT):
        cmds.delete(PANEL_ROOT)
    if not cmds.objExists(UI_GRP):
        cmds.group(em=True, name=UI_GRP, world=True)
    panel = cmds.group(em=True, name=PANEL_ROOT, parent=UI_GRP)
    # title null
    row_y = 0.0
    spacing = 2.2
    created = []
    for i, real in enumerate(driver_nodes):
        sn = short_name(real)
        # logical name
        if sn.endswith("_Ctrl"):
            logical = "CTRL_" + sn[:-5]
        elif sn.startswith("CTRL_"):
            logical = sn
        else:
            logical = "CTRL_" + sn
        if cmds.objExists(logical):
            logical = logical + "_mh2"

        tx_lo, tx_hi, tx_on = _ctrl_axis_enabled(real, "tx")
        ty_lo, ty_hi, ty_on = _ctrl_axis_enabled(real, "ty")
        # if no limits, assume ty 1D
        if not tx_on and not ty_on:
            ty_on = True
            ty_lo, ty_hi = 0.0, 1.0

        if tx_on and ty_on:
            ctrl = _make_2d_ctrl(logical, panel, size=0.8)
        else:
            ctrl = _make_1d_ctrl(logical, panel, length=1.5)
            if tx_on and not ty_on:
                # rotate to horizontal? keep ty as primary — reconnect tx
                pass
        cmds.xform(ctrl, os=True, t=(0, -row_y, 0))
        # label
        try:
            loc = cmds.spaceLocator(name=sn + "_lbl")[0]
            cmds.parent(loc, panel)
            cmds.xform(loc, os=True, t=(2.5, -row_y, 0))
            cmds.setAttr(loc + ".localScale", 0.01, 0.01, 0.01)
        except Exception:
            pass

        # connect matching axes
        for ax, on in (("translateX", tx_on), ("translateY", ty_on), ("translateZ", False)):
            if not on:
                continue
            try:
                dst = real + "." + ax
                if cmds.listConnections(dst, s=True, d=False):
                    continue
                cmds.connectAttr(ctrl + "." + ax, dst, f=True)
            except Exception:
                pass
        created.append(ctrl)
        row_y += spacing
        if i > 80:
            break

    _place_panel_no_overlap(panel, inv)
    return panel, created


def _fill_missing_with_user(inv):
    """Prompt user for critical missing slots."""
    slots = []
    if "body_root" in inv["missing"]:
        slots.append(("body_root", u"身体主控制器（如 Master_Ctrl）", ("transform",)))
    if "face_gui" in inv["missing"]:
        slots.append(("face_gui", u"面部控制器面板根（如 FRM_faceGUI）", ("transform",)))
    if "head_lod0_mesh" in inv["missing"] or not inv["meshes"].get("head_lod0_mesh"):
        slots.append(("head_lod0_mesh", u"头部网格", ("transform",)))
    if "body" in inv["missing"] or not inv["meshes"].get("body"):
        slots.append(("body", u"身体网格（可跳过）", ("transform",)))

    user_set = {}
    for key, label, types in slots:
        node = prompt_slot(label, expect_types=types)
        if not node:
            continue
        user_set[key] = node
        if key in ("head_lod0_mesh", "body", "teeth_lod0_mesh"):
            inv["meshes"][key] = node
            if key == "body":
                inv["meshes"]["m_med_unw_body_lod0_mesh"] = node
        elif key == "body_root":
            inv["body_root"] = node
        elif key == "face_gui":
            inv["face_gui"] = node
        if key in inv["missing"]:
            inv["missing"].remove(key)
        inv["found"].append(u"（用户）%s → %s" % (key, short_name(node)))
    return user_set


def standardize_scene(interactive=True):
    """Run full standardize. Returns result dict."""
    own_prog = False
    try:
        # confirmDialog 会关掉/挡住 progressWindow；确认前先关掉，确认后再重建
        _prog_end()

        ok, reason = can_standardize()
        if not ok and interactive:
            go = cmds.confirmDialog(
                title=u"标准化",
                message=reason + u"\n\n仍要手动指定关键节点并继续吗？",
                button=[u"继续", u"取消"],
                defaultButton=u"继续",
                cancelButton=u"取消",
                dismissString=u"取消",
            )
            if go != u"继续":
                return {"ok": False, "cancelled": True, "message": reason}
        elif not ok:
            return {"ok": False, "message": reason}

        if interactive:
            warn = cmds.confirmDialog(
                title=u"标准化",
                message=u"将显示控制器并建立导出用 CTRL 代理（不改原控制器/骨骼名称）。\n建议先另存场景。\n\n继续？",
                button=[u"继续", u"取消"],
                defaultButton=u"继续",
                cancelButton=u"取消",
                dismissString=u"取消",
            )
            if warn != u"继续":
                return {"ok": False, "cancelled": True}

        own_prog = True
        _prog_begin(u"开始标准化…", 0, title=u"标准化角色")

        _prog(u"盘点场景节点与网格…", 5)
        inv = inventory()
        if interactive:
            # 补全对话框期间不能挂着假进度条，关掉后重建
            _prog_end()
            own_prog = False
            _fill_missing_with_user(inv)
            own_prog = True
            _prog_begin(u"继续标准化…", 15, title=u"标准化角色")

        proxy_created, proxy_skipped, proxy_repaired = [], [], []
        panel = None
        panel_ctrls = []

        def _cb(status, pct):
            _prog(status, pct)

        if inv.get("frm_pairs"):
            _prog(u"创建面部 CTRL 代理（不改原名）…", 20)
            proxy_created, proxy_skipped, proxy_repaired = create_ctrl_proxies(
                inv, progress_cb=_cb
            )
        elif len(inv.get("face_ctrls") or []) < 5:
            drivers = list(inv.get("face_ctrls") or [])
            if not drivers and interactive:
                _prog_end()
                own_prog = False
                node = prompt_slot(
                    u"任一面部控制器（将扫描同级 FRM 子控件）", expect_types=("transform",)
                )
                own_prog = True
                _prog_begin(u"继续标准化…", 25, title=u"标准化角色")
                if node:
                    parent = (cmds.listRelatives(node, p=True, f=True) or [None])[0]
                    grand = (
                        (cmds.listRelatives(parent, p=True, f=True) or [None])[0]
                        if parent
                        else None
                    )
                    roots = [grand or parent or node]
                    for r in roots:
                        if not r:
                            continue
                        for k in cmds.listRelatives(r, ad=True, type="transform") or []:
                            if short_name(k).endswith("_Ctrl"):
                                drivers.append(k)
            if drivers:
                inv["face_ctrls"] = drivers
                _prog(u"构建列表面板…", 40)
                panel, panel_ctrls = build_list_face_panel(inv, drivers)
            else:
                inv["missing"].append("face_ctrls")
        else:
            _prog(u"构建列表面板…", 40)
            panel, panel_ctrls = build_list_face_panel(inv, inv["face_ctrls"])

        _prog(u"写入标准化映射…", 78)
        data = {
            "meshes": {k: short_name(v) for k, v in (inv.get("meshes") or {}).items() if v},
            "extra_meshes": [short_name(v) for v in (inv.get("extra_meshes") or []) if v],
            "body_root": short_name(inv.get("body_root")) if inv.get("body_root") else "",
            "face_gui": short_name(inv.get("face_gui")) if inv.get("face_gui") else "",
            "proxies": [short_name(p) for p in proxy_created],
            "panel": PANEL_ROOT if panel else "",
        }
        _save_map(data)

        _prog(u"显示身体/面部控制器…", 88)
        show_controllers(inv)
        _prog(u"刷新视口…", 96)
        try:
            cmds.refresh(force=True)
        except Exception:
            pass

        lines = [
            u"标准化完成（未改原控制器/骨骼名）",
            u"识别：%s" % reason if ok else u"",
            u"找到：",
        ]
        lines.extend(u"  • " + x for x in inv.get("found") or [])
        if inv.get("missing"):
            lines.append(u"仍缺失：")
            lines.extend(u"  • " + x for x in inv["missing"])
        lines.append(
            u"CTRL 代理：新建 %s / 修复 %s / 已有 %s"
            % (len(proxy_created), len(proxy_repaired), len(proxy_skipped))
        )
        if panel:
            lines.append(
                u"已创建列表面板：%s（×%s，已避让角色）" % (PANEL_ROOT, len(panel_ctrls))
            )

        msg = u"\n".join([L for L in lines if L])
        _prog(u"完成", 100)
        return {
            "ok": True,
            "message": msg,
            "inventory": inv,
            "map": data,
            "proxy_created": len(proxy_created),
            "proxy_repaired": len(proxy_repaired),
            "panel": panel,
        }
    finally:
        if own_prog:
            _prog_end()
