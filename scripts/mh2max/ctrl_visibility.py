# -*- coding: utf-8 -*-
"""Toggle MetaHuman / custom rig controller visibility in the viewport."""
from __future__ import print_function

from maya import cmds

from .detect import short_name

OPT_CTRL_VISIBLE = "mh2max_controllersVisible"

# Roots that may not end with _Ctrl but are controller containers.
_EXTRA_ROOTS = (
    "CTRL_faceGUI",
    "FRM_faceGUI",
    "FaceGUI_Ctrl",
    "COG_Ctrl",
    "Master_Ctrl",
    "GRP_faceGUI",
)


def _resolve(name):
    if not name:
        return None
    if cmds.objExists(name):
        return cmds.ls(name, long=True)[0]
    hits = cmds.ls("*" + name, transforms=True, long=True) or []
    exact = [h for h in hits if short_name(h) == name]
    return exact[0] if exact else (hits[0] if hits else None)


def _has_control_shape(node):
    if not node or not cmds.objExists(node):
        return False
    for sh in cmds.listRelatives(node, shapes=True, ni=True) or []:
        if cmds.nodeType(sh) in ("nurbsCurve", "nurbsSurface", "mesh", "locator"):
            return True
    return False


def list_controllers():
    """Collect face/body controller transforms in the current scene."""
    found = []
    found.extend(cmds.ls("CTRL_*", type="transform", long=True) or [])
    found.extend(cmds.ls("*:CTRL_*", type="transform", long=True) or [])
    found.extend(cmds.ls("*_Ctrl", type="transform", long=True) or [])
    found.extend(cmds.ls("*:*_Ctrl", type="transform", long=True) or [])
    for name in _EXTRA_ROOTS:
        node = _resolve(name)
        if node:
            found.append(node)
    uniq = list(dict.fromkeys(found))
    out = []
    for node in uniq:
        sn = short_name(node)
        if sn.startswith("CTRL_") or sn.endswith("_Ctrl") or sn in _EXTRA_ROOTS:
            if _has_control_shape(node) or sn.startswith("CTRL_") or sn.endswith("_Ctrl"):
                out.append(node)
    return out


def _draw_targets(node):
    """Transform + shapes that may drive viewport draw for a controller."""
    if not node or not cmds.objExists(node):
        return []
    targets = [node]
    targets.extend(cmds.listRelatives(node, shapes=True, ni=True, fullPath=True) or [])
    return targets


def _target_is_shown(target):
    if not target or not cmds.objExists(target):
        return False
    if cmds.attributeQuery("overrideVisibility", node=target, exists=True):
        try:
            if cmds.getAttr(target + ".overrideEnabled") and not cmds.getAttr(
                target + ".overrideVisibility"
            ):
                return False
        except Exception:
            pass
    if cmds.attributeQuery("visibility", node=target, exists=True):
        try:
            if not cmds.getAttr(target + ".visibility"):
                return False
        except Exception:
            pass
    return True


def is_controller_shown(node):
    """True when the controller is drawn in the viewport."""
    if not node or not cmds.objExists(node):
        return False
    targets = _draw_targets(node)
    if not targets:
        return True
    return any(_target_is_shown(t) for t in targets)


def _set_draw_visible(target, visible):
    """Set draw visibility on one transform/shape (handles MH locked visibility)."""
    if not target or not cmds.objExists(target):
        return False
    vis = 1 if visible else 0
    changed = False
    if cmds.attributeQuery("overrideEnabled", node=target, exists=True):
        try:
            cmds.setAttr(target + ".overrideEnabled", True)
            changed = True
        except Exception:
            pass
    if cmds.attributeQuery("overrideVisibility", node=target, exists=True):
        try:
            cmds.setAttr(target + ".overrideVisibility", vis)
            changed = True
        except Exception:
            pass
    if cmds.attributeQuery("visibility", node=target, exists=True):
        try:
            if cmds.getAttr(target + ".visibility", lock=True):
                cmds.setAttr(target + ".visibility", lock=False)
            cmds.setAttr(target + ".visibility", vis)
            changed = True
        except Exception:
            pass
    if cmds.attributeQuery("template", node=target, exists=True) and visible:
        try:
            cmds.setAttr(target + ".template", False)
        except Exception:
            pass
    return changed


def _set_stored_visible(visible):
    try:
        cmds.optionVar(iv=(OPT_CTRL_VISIBLE, 1 if visible else 0))
    except Exception:
        pass


def _ensure_viewport_controls_drawable():
    """MH rigs draw as nurbsCurve; panel Show filters can hide them while attrs say 'visible'."""
    for panel in cmds.getPanel(type="modelPanel") or []:
        try:
            cmds.modelEditor(
                panel,
                e=True,
                nurbsCurves=True,
                locators=True,
                controllers=True,
            )
        except Exception:
            pass
    try:
        focus = cmds.getPanel(withFocus=True)
        if focus and cmds.getPanel(typeOf=focus) == "modelPanel":
            cmds.modelEditor(
                focus,
                e=True,
                nurbsCurves=True,
                locators=True,
                controllers=True,
            )
    except Exception:
        pass


def get_controllers_visible():
    """Return whether controllers are considered shown (menu label source)."""
    try:
        if cmds.optionVar(exists=OPT_CTRL_VISIBLE):
            return bool(cmds.optionVar(q=OPT_CTRL_VISIBLE))
    except Exception:
        pass
    ctrls = list_controllers()
    if not ctrls:
        return True
    shown = sum(1 for c in ctrls if is_controller_shown(c))
    return shown > (len(ctrls) // 2)


def menu_label_for_visible(visible):
    return u"隐藏控制器" if visible else u"显示控制器"


def set_controllers_visible(visible):
    """Show or hide all rig controllers."""
    if visible:
        _ensure_viewport_controls_drawable()
    ctrls = list_controllers()
    changed = 0
    for node in ctrls:
        for target in _draw_targets(node):
            if _set_draw_visible(target, visible):
                changed += 1
    _set_stored_visible(bool(visible))
    try:
        cmds.refresh(force=True)
    except Exception:
        pass
    return len(ctrls), changed


def toggle_controllers():
    """Flip controller visibility; returns new visible state."""
    new_vis = not get_controllers_visible()
    set_controllers_visible(new_vis)
    return new_vis
