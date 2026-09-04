# -*- coding: utf-8 -*-
"""Check GitHub Releases for a newer mh2max version."""
from __future__ import print_function

import json
import os
import re
import ssl
import sys

try:
    from urllib.request import Request, urlopen
except ImportError:
    from urllib2 import Request, urlopen  # type: ignore

from maya import cmds

from . import __version__ as LOCAL_VERSION

GITHUB_REPO = "Elijah-Neverdie/mh2max"
API_LATEST = "https://api.github.com/repos/%s/releases/latest" % GITHUB_REPO
RELEASES_PAGE = "https://github.com/%s/releases" % GITHUB_REPO


def _parse_ver(s):
    s = (s or "").strip()
    if s.startswith("v") or s.startswith("V"):
        s = s[1:]
    parts = []
    for p in re.split(r"[^\d]+", s):
        if p.isdigit():
            parts.append(int(p))
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:4])


def fetch_latest_release(timeout=12):
    """Return dict {tag, name, url, body} or raise."""
    req = Request(
        API_LATEST,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "mh2max-maya/%s" % LOCAL_VERSION,
        },
    )
    ctx = ssl.create_default_context()
    raw = urlopen(req, timeout=timeout, context=ctx).read()
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", "replace")
    data = json.loads(raw)
    tag = data.get("tag_name") or data.get("name") or ""
    return {
        "tag": tag,
        "name": data.get("name") or tag,
        "url": data.get("html_url") or RELEASES_PAGE,
        "body": (data.get("body") or "")[:1200],
        "published": data.get("published_at") or "",
    }


def check_for_update():
    """Compare local version to GitHub latest. Returns status dict."""
    local = _parse_ver(LOCAL_VERSION)
    try:
        rel = fetch_latest_release()
    except Exception as ex:
        return {
            "ok": False,
            "error": str(ex),
            "local": LOCAL_VERSION,
            "latest": None,
        }
    remote = _parse_ver(rel["tag"])
    newer = remote > local
    return {
        "ok": True,
        "local": LOCAL_VERSION,
        "latest": rel["tag"],
        "newer": newer,
        "same": remote == local,
        "url": rel["url"],
        "name": rel["name"],
        "body": rel["body"],
    }


def run_check_update_ui():
    cmds.progressWindow(
        title=u"检查更新",
        progress=10,
        status=u"正在查询 GitHub Releases…",
        isInterruptable=False,
        minValue=0,
        maxValue=100,
    )
    try:
        cmds.refresh(force=True)
        info = check_for_update()
        cmds.progressWindow(edit=True, progress=100, status=u"完成")
    finally:
        try:
            cmds.progressWindow(endProgress=True)
        except Exception:
            pass

    if not info.get("ok"):
        cmds.confirmDialog(
            title=u"检查更新",
            message=u"无法连接 GitHub：\n%s\n\n本机版本：%s\n发布页：\n%s"
            % (info.get("error") or u"未知错误", LOCAL_VERSION, RELEASES_PAGE),
            button=[u"打开发布页", u"关闭"],
            defaultButton=u"打开发布页",
        )
        # if user picked open — confirmDialog returns button label
        # re-ask simply via open always option below
        try:
            cmds.launch(web=RELEASES_PAGE)
        except Exception:
            pass
        return info

    if info.get("newer"):
        choice = cmds.confirmDialog(
            title=u"发现新版本",
            message=u"本机：%s\n最新：%s\n\n请到 GitHub Releases 下载更新包并覆盖安装目录。\n\n%s"
            % (info["local"], info["latest"], (info.get("body") or "")[:400]),
            button=[u"打开发布页", u"关闭"],
            defaultButton=u"打开发布页",
            cancelButton=u"关闭",
            dismissString=u"关闭",
        )
        if choice == u"打开发布页":
            try:
                cmds.launch(web=info.get("url") or RELEASES_PAGE)
            except Exception:
                pass
    elif info.get("same"):
        cmds.confirmDialog(
            title=u"检查更新",
            message=u"已是最新版本：%s" % info["local"],
            button=[u"确定"],
        )
    else:
        cmds.confirmDialog(
            title=u"检查更新",
            message=u"本机 %s 新于远程 %s（开发中？）"
            % (info["local"], info["latest"]),
            button=[u"确定"],
        )
    return info
