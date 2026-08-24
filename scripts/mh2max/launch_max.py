# -*- coding: utf-8 -*-
"""Find 3ds Max installs, read user config, launch export job."""
from __future__ import print_function

import glob
import os
import re
import subprocess

from .app_config import (
    get_max_exe,
    get_max_version,
    load_config,
    max_version_from_path,
    save_config,
)

CANDIDATES = [
    r"C:\Program Files\Autodesk\3ds Max 2027\3dsmax.exe",
    r"C:\Program Files\Autodesk\3ds Max 2026\3dsmax.exe",
    r"C:\Program Files\Autodesk\3ds Max 2025\3dsmax.exe",
    r"C:\Program Files\Autodesk\3ds Max 2024\3dsmax.exe",
    r"C:\Program Files\Autodesk\3ds Max 2023\3dsmax.exe",
    r"C:\Program Files\Autodesk\3ds Max 2022\3dsmax.exe",
]

MIN_MAX_VERSION = 2022


def _version_from_path(path):
    return max_version_from_path(path)


def _dedupe_exes(found):
    uniq = []
    seen = set()
    for p in found:
        n = os.path.normcase(os.path.abspath(p))
        if n not in seen and os.path.isfile(p):
            seen.add(n)
            uniq.append(p)
    uniq.sort(key=_version_from_path, reverse=True)
    return uniq


def find_all_3dsmax():
    """Return list of {exe, version} newest first."""
    found = []
    cfg = load_config()
    for item in cfg.get("max_installs") or []:
        exe = (item.get("exe") or "").strip()
        if exe and os.path.isfile(exe):
            found.append(exe)

    for key in (
        "MH2MAX_EXE",
        "ADSK_3DSMAX_x64_2027",
        "ADSK_3DSMAX_x64_2026",
        "ADSK_3DSMAX_x64_2025",
        "ADSK_3DSMAX_x64_2024",
        "ADSK_3DSMAX_x64_2023",
        "ADSK_3DSMAX_x64_2022",
    ):
        env = os.environ.get(key)
        if not env:
            continue
        exe = env if env.lower().endswith(".exe") else os.path.join(env, "3dsmax.exe")
        if os.path.isfile(exe):
            found.append(exe)

    for p in CANDIDATES:
        if os.path.isfile(p):
            found.append(p)

    root = r"C:\Program Files\Autodesk"
    if os.path.isdir(root):
        for match in glob.glob(os.path.join(root, "3ds Max *", "3dsmax.exe")):
            found.append(match)

    out = []
    for exe in _dedupe_exes(found):
        ver = _version_from_path(exe)
        if ver >= MIN_MAX_VERSION:
            out.append({"exe": exe, "version": ver})
    return out


def find_3dsmax():
    """Return path to configured or newest 3dsmax.exe."""
    cfg_exe = get_max_exe()
    if cfg_exe:
        return cfg_exe
    installs = find_all_3dsmax()
    return installs[0]["exe"] if installs else None


def find_3dsmax_info():
    exe = find_3dsmax()
    if not exe:
        return {"exe": None, "version": 0}
    return {"exe": exe, "version": _version_from_path(exe)}


def set_preferred_max(exe):
    """Persist Max export target for one-click pipeline."""
    exe = os.path.abspath(exe) if exe else None
    if not exe or not os.path.isfile(exe):
        raise RuntimeError("无效的 3dsmax.exe：%s" % exe)
    ver = _version_from_path(exe)
    if ver < MIN_MAX_VERSION:
        raise RuntimeError("3ds Max %s 低于最低要求 %s" % (ver, MIN_MAX_VERSION))
    cfg = load_config()
    cfg["max_exe"] = exe
    cfg["max_version"] = ver
    save_config(cfg)
    return {"exe": exe, "version": ver}


def expected_max_save_paths(char, out_dir, max_year):
    """Return Max scene paths the one-click pipeline will try to archive.

    - Current Max year always gets ``<char>_face_rigged_max<year>.max``.
    - When running Max > 2024, a ``_max2024.max`` copy is attempted via saveAsVersion
      (skipped at save time if the host Max cannot down-save that far).
    - When the host is already 2024, only the single ``_max2024.max`` archive is written.
    """
    base = os.path.join(out_dir, char + "_face_rigged")
    year = int(max_year or 0)
    if year == 2024:
        return [base + "_max2024.max"]
    if year > 2024:
        return [base + "_max%d.max" % year, base + "_max2024.max"]
    if year > 0:
        return [base + "_max%d.max" % year]
    return [base + "_maxXXXX.max"]


def launch_max(job_ms, max_exe=None):
    """Start a fresh Max that runs job_ms after startup (empty scene then pipeline)."""
    exe = max_exe or find_3dsmax()
    if not exe:
        raise RuntimeError(
            u"找不到 3dsmax.exe。请运行 install.bat 配置，或设置 MH2MAX_EXE / config.json。"
        )
    if not os.path.isfile(job_ms):
        raise RuntimeError("任务脚本不存在: %s" % job_ms)
    args = [exe, "-U", "MAXScript", job_ms]
    try:
        subprocess.Popen(args, close_fds=True)
    except TypeError:
        subprocess.Popen(args)
    return exe
