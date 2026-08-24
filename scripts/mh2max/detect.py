# -*- coding: utf-8 -*-
"""Detect assembled MetaHuman in the current Maya scene (any DHI body type)."""
from __future__ import print_function

import os
import re

from maya import cmds

GENDERS = ("f", "m")
HEIGHTS = ("srt", "med", "tal")
WEIGHTS = ("nrw", "unw", "ovw")
BODY_CODE_RE = re.compile(
    r"(?:^|:)([fm])_(srt|med|tal)_(nrw|unw|ovw)(?:_|$)", re.I
)
ALL_BODY_TYPES = tuple(
    "%s_%s_%s" % (g, h, w) for g in GENDERS for h in HEIGHTS for w in WEIGHTS
)

HEAD_MESH_NAMES = (
    "head_lod0_mesh",
    "teeth_lod0_mesh",
    "eyeLeft_lod0_mesh",
    "eyeRight_lod0_mesh",
    "eyelashes_lod0_mesh",
    "eyeshell_lod0_mesh",
    "eyeEdge_lod0_mesh",
    "cartilage_lod0_mesh",
    "saliva_lod0_mesh",
)

GUI_SKIP = (
    "CTRL_faceGUI",
    "CTRL_faceTweakersGUI",
    "CTRL_faceGUIfollowHead",
    "CTRL_faceAndEyesAimFollowHeadGUI",
    "CTRL_expressions",
    "CTRL_rigLogic",
    "CTRL_rigLogicSwitch",
    "CTRL_GUIswitch",
    "CTRL_lookAtSwitch",
    "CTRL_convergenceSwitch",
    "CTRL_eyesAimFollowHead",
)

# One-click Morph export/import table. Folder name = MorphTargets/<Folder>/
# and Max OBJ prefix "<Folder>_" (Face has no prefix). Keep Max mh2max_morphMeshJobs
# in sync when adding rows — every head part that deforms under RigLogic must appear
# here, because Max keeps FACIAL joints at FBX bind pose and only Morphers animate them.
MESH_JOBS = (
    ("Face", "head_lod0_mesh"),
    ("EyeLeft", "eyeLeft_lod0_mesh"),
    ("EyeRight", "eyeRight_lod0_mesh"),
    ("Teeth", "teeth_lod0_mesh"),
    ("Saliva", "saliva_lod0_mesh"),
    ("EyeLash", "eyelashes_lod0_mesh"),
    ("EyeShell", "eyeshell_lod0_mesh"),
    ("EyeEdge", "eyeEdge_lod0_mesh"),
    ("Cartilage", "cartilage_lod0_mesh"),
)

# Non-Face folders → OBJ/node name prefix used by Max parseMorphName / target buckets.
MORPH_PREFIXES = tuple(folder + "_" for folder, _mesh in MESH_JOBS if folder != "Face")


def short_name(node):
    if not node:
        return ""
    return node.split("|")[-1].split(":")[-1]


def resolve(name):
    if not name:
        return None
    if cmds.objExists(name):
        return name
    hits = cmds.ls("*" + name, transforms=True, long=True) or []
    exact = [h for h in hits if short_name(h) == name]
    return exact[0] if exact else None


def _bbox(node):
    if not node or not cmds.objExists(node):
        return None
    bb = cmds.exactWorldBoundingBox(node)
    return {
        "min": [bb[0], bb[1], bb[2]],
        "max": [bb[3], bb[4], bb[5]],
        "center": [(bb[0] + bb[3]) * 0.5, (bb[1] + bb[4]) * 0.5, (bb[2] + bb[5]) * 0.5],
    }


def _world_pos(node):
    if not node or not cmds.objExists(node):
        return None
    return list(cmds.xform(node, q=True, ws=True, t=True))


def _find_by_suffix(suffix):
    hits = cmds.ls("*" + suffix, transforms=True, long=True) or []
    exact = [h for h in hits if short_name(h).endswith(suffix)]
    return exact[0] if exact else (hits[0] if hits else None)


def _find_body_mesh():
    meshes = (cmds.ls("*_lod0_mesh", type="transform", long=True) or []) + (
        cmds.ls("*:*_lod0_mesh", type="transform", long=True) or []
    )
    meshes = list(dict.fromkeys(meshes))
    body = []
    for n in meshes:
        s = short_name(n).lower()
        if s in HEAD_MESH_NAMES:
            continue
        if "combined" in s or "flipflop" in s or "hair" in s:
            continue
        if s.endswith("_body_lod0_mesh") or "_body_lod" in s:
            body.append(n)
    if body:
        return sorted(body, key=lambda x: (0 if short_name(x).endswith("_body_lod0_mesh") else 1, x))[0]
    # fallback: first non-head lod0 mesh that looks like a body
    for n in meshes:
        s = short_name(n).lower()
        if s not in HEAD_MESH_NAMES and "body" in s:
            return n
    return None


def _body_code_from_name(node):
    s = short_name(node or "")
    m = BODY_CODE_RE.search(s)
    if m:
        return "%s_%s_%s" % (m.group(1).lower(), m.group(2).lower(), m.group(3).lower())
    return "unknown"


def _character_name():
    scene = cmds.file(q=True, sn=True) or ""
    if scene:
        d = os.path.abspath(scene)
        base = os.path.splitext(os.path.basename(d))[0]
        parent = os.path.basename(os.path.dirname(d))
        # Assembled UE export often saved as scene.mb under MHI_<Name>/
        if base.lower() in ("scene", "untitled", "untitledscene") and parent:
            if parent.lower() not in ("maxexport", "sourceassets", "mh_imports", "documents"):
                # Strip MHI_ prefix from process folder
                if parent.upper().startswith("MHI_"):
                    return parent[4:] or parent
                return parent
        for junk in ("_assembled", "_face", "_rigged", "_body"):
            if base.endswith(junk):
                base = base[: -len(junk)]
        if base and base.lower() not in ("scene", "untitled"):
            return base
    dna = cmds.ls("*.dnaFile", long=True) or cmds.ls("*DNA*", type="transform") or []
    if dna:
        return short_name(dna[0])
    head = resolve("head_lod0_mesh")
    if head:
        ns = head.split("|")[-1]
        if ":" in ns:
            return ns.split(":")[0]
    return "MetaHuman"


def detect_scene():
    head = resolve("head_lod0_mesh")
    gui = resolve("CTRL_faceGUI")
    ctrls = (cmds.ls("CTRL_*", type="transform") or []) + (cmds.ls("*:CTRL_*", type="transform") or [])
    ctrls = list(dict.fromkeys(ctrls))
    body = _find_body_mesh()
    errors = []
    if not head:
        errors.append("场景里没有 head_lod0_mesh，请先用 DHI 装配 MetaHuman。")
    if not gui and len(ctrls) < 20:
        errors.append("场景里没有面部控制器（CTRL_faceGUI / CTRL_*）。")
    if errors:
        return {"ok": False, "errors": errors}

    body_code = _body_code_from_name(body) if body else "unknown"
    combined = _find_by_suffix("_combined_lod0_mesh")
    flipflops = _find_by_suffix("_flipflops_lod0_mesh")
    body_grp = resolve("body_lod0_grp")
    head_grp = resolve("head_grp")
    gui_grp = resolve("GRP_faceGUI") or resolve("headGui_grp")

    head_parts = {}
    for n in HEAD_MESH_NAMES:
        node = resolve(n)
        if node:
            head_parts[n] = node

    info = {
        "ok": True,
        "errors": [],
        "character": _character_name(),
        "body_type": body_code,
        "head": head,
        "body": body,
        "body_grp": body_grp,
        "head_grp": head_grp,
        "combined": combined,
        "flipflops": flipflops,
        "gui": gui,
        "gui_grp": gui_grp,
        "head_parts": head_parts,
        "ctrl_count": len(ctrls),
        "has_body": bool(body),
        "scene": cmds.file(q=True, sn=True) or "",
        "maya_up": (cmds.upAxis(q=True, axis=True) or ["y"])[0],
        "linear_unit": cmds.currentUnit(q=True, linear=True),
        "bbox": {
            "head": _bbox(head),
            "body": _bbox(body),
            "gui": _bbox(gui),
        },
        "world": {
            "head": _world_pos(head),
            "body": _world_pos(body),
            "gui": _world_pos(gui),
            "gui_grp": _world_pos(gui_grp),
            "head_grp": _world_pos(head_grp),
            "body_grp": _world_pos(body_grp),
        },
    }
    return info


def default_output_dir(info):
    scene = info.get("scene") or ""
    if scene:
        d = os.path.dirname(os.path.abspath(scene))
        base = os.path.basename(d).lower()
        if base == "maxexport":
            return d
        if base == "sourceassets":
            return os.path.join(os.path.dirname(d), "MaxExport")
        sibling = os.path.join(d, "MaxExport")
        if os.path.isdir(sibling) or os.path.isdir(os.path.join(d, "SourceAssets")):
            return sibling
        return sibling
    char = info.get("character") or "MetaHuman"
    return os.path.join(os.path.expanduser("~"), "Documents", "mh2max", char)
