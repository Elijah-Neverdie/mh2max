# -*- coding: utf-8 -*-
"""Pick-or-type helpers for missing standardize slots (no busy-wait)."""
from __future__ import print_function

from maya import cmds


def _short(n):
    if not n:
        return ""
    return n.split("|")[-1].split(":")[-1]


def _resolve_name(name):
    name = (name or "").strip()
    if not name:
        return None
    if cmds.objExists(name):
        return cmds.ls(name, long=True)[0]
    hits = cmds.ls(name, long=True) or []
    if hits:
        return hits[0]
    hits = cmds.ls("*" + name, long=True) or []
    exact = [h for h in hits if _short(h) == name]
    if exact:
        return exact[0]
    return hits[0] if hits else None


def prompt_slot(slot_label, expect_types=("transform", "joint"), default_name=""):
    """Ask user to pick selection, type a name, or skip.

    Returns node long name, or None if skipped / cancelled.
    """
    choice = cmds.confirmDialog(
        title=u"标准化 — 指定节点",
        message=u"无法自动找到：%s\n\n请选择操作：" % slot_label,
        button=[u"从选择拾取", u"输入名称", u"跳过"],
        defaultButton=u"从选择拾取",
        cancelButton=u"跳过",
        dismissString=u"跳过",
    )
    if choice == u"跳过":
        return None
    if choice == u"从选择拾取":
        sel = cmds.ls(sl=True, long=True) or []
        if not sel:
            cmds.warning(u"当前没有选择，已跳过：%s" % slot_label)
            return None
        n = sel[0]
        t = cmds.nodeType(n)
        if expect_types and t not in expect_types and t not in ("transform", "joint"):
            cmds.warning(u"类型不匹配 %s (%s)，已跳过" % (_short(n), t))
            return None
        return n
    # 输入名称
    res = cmds.promptDialog(
        title=u"输入节点名",
        message=u"%s" % slot_label,
        text=default_name or "",
        button=[u"确定", u"取消"],
        defaultButton=u"确定",
        cancelButton=u"取消",
        dismissString=u"取消",
    )
    if res != u"确定":
        return None
    node = _resolve_name(cmds.promptDialog(q=True, text=True))
    if not node:
        cmds.warning(u"找不到节点，已跳过：%s" % slot_label)
    return node
