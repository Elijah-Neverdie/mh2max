# -*- coding: utf-8 -*-
"""Find latest 3ds Max and launch / hand off the generated job MaxScript."""
from __future__ import print_function

import glob
import os
import re
import subprocess

CANDIDATES = [
    r"C:\Program Files\Autodesk\3ds Max 2027\3dsmax.exe",
    r"C:\Program Files\Autodesk\3ds Max 2026\3dsmax.exe",
    r"C:\Program Files\Autodesk\3ds Max 2025\3dsmax.exe",
    r"C:\Program Files\Autodesk\3ds Max 2024\3dsmax.exe",
    r"C:\Program Files\Autodesk\3ds Max 2023\3dsmax.exe",
    r"C:\Program Files\Autodesk\3ds Max 2022\3dsmax.exe",
]


def _version_from_path(path):
    m = re.search(r"3ds Max (\d{4})", path.replace("/", "\\"), re.I)
    return int(m.group(1)) if m else 0


def find_3dsmax():
    """Return path to the newest installed 3dsmax.exe."""
    found = []
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

    # Scan Autodesk folder for any 3ds Max NNNN
    root = r"C:\Program Files\Autodesk"
    if os.path.isdir(root):
        for match in glob.glob(os.path.join(root, "3ds Max *", "3dsmax.exe")):
            found.append(match)

    # unique, newest first
    uniq = []
    seen = set()
    for p in found:
        n = os.path.normcase(os.path.abspath(p))
        if n not in seen and os.path.isfile(p):
            seen.add(n)
            uniq.append(p)
    if not uniq:
        return None
    uniq.sort(key=_version_from_path, reverse=True)
    return uniq[0]


def find_3dsmax_info():
    exe = find_3dsmax()
    if not exe:
        return {"exe": None, "version": 0}
    return {"exe": exe, "version": _version_from_path(exe)}


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
        raise RuntimeError("找不到 3dsmax.exe。请安装 3ds Max 2022+，或设置环境变量 MH2MAX_EXE。")
    if not os.path.isfile(job_ms):
        raise RuntimeError("任务脚本不存在: %s" % job_ms)
    # Start Max with a short boot script. Job.ms only arms a deferred callback so
    # Nitrous viewports finish initializing before heavy assembly (avoids black UI).
    args = [exe, "-U", "MAXScript", job_ms]
    try:
        subprocess.Popen(args, close_fds=True)
    except TypeError:
        # older Python on some Maya builds
        subprocess.Popen(args)
    return exe
