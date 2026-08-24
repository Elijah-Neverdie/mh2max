# -*- coding: utf-8 -*-
"""mh2max one-click installer (Maya module + MetaHumanForMaya + Max export config)."""
from __future__ import print_function

import glob
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile

MH2MAX_MIN_MAYA = 2022
MH2MAX_MIN_MAX = 2022
MH_MIN_MAYA = 2024  # MetaHumanForMaya.mod ships 2024+

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.dirname(os.path.abspath(__file__))
RESOLVE_PS1 = os.path.join(TOOLS, "resolve_shortcut.ps1")
VENDOR_DIR = os.path.join(ROOT, "vendor")
MH_ZIP_GLOB = "MetaHumanForMaya*.zip"
CONFIG_DIR = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "mh2max")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")


def _norm(p):
    return os.path.normpath(os.path.abspath(p)) if p else ""


def _pause(msg=u"\n按 Enter 退出…"):
    try:
        raw_input(msg)
    except NameError:
        input(msg)


def _print_header():
    print("=" * 60)
    print(" mh2max 一键安装 / 配置")
    print(" 仓库：%s" % ROOT)
    print("=" * 60)


def resolve_path(user_input):
    p = (user_input or "").strip().strip('"').strip("'")
    if not p:
        return None
    if os.path.isdir(p):
        return _norm(p)
    if os.path.isfile(p):
        if p.lower().endswith(".lnk"):
            return _resolve_lnk(p)
        return _norm(p)
    return None


def _resolve_lnk(path):
    ps = os.path.join(TOOLS, "resolve_shortcut.ps1")
    if not os.path.isfile(ps):
        return _norm(path)
    try:
        out = subprocess.check_output(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                ps,
                "-Path",
                path,
            ],
            stderr=subprocess.STDOUT,
            universal_newlines=True,
        )
        target = (out or "").strip().splitlines()
        target = target[-1].strip() if target else ""
        return _norm(target) if target and os.path.exists(target) else None
    except Exception as ex:
        print("[warn] 快捷方式解析失败：%s" % ex)
        return None


def _maya_from_exe(exe):
    exe = _norm(exe)
    if not exe or not os.path.isfile(exe):
        return None
    base = os.path.basename(exe).lower()
    if base not in ("maya.exe", "mayabatch.exe"):
        return None
    m = re.search(r"Maya(\d{4})", exe.replace("/", "\\"), re.I)
    if not m:
        return None
    ver = int(m.group(1))
    root = os.path.dirname(os.path.dirname(exe))
    return {"product": "maya", "version": ver, "exe": exe, "root": root}


def _max_from_exe(exe):
    exe = _norm(exe)
    if not exe or not os.path.isfile(exe):
        return None
    if os.path.basename(exe).lower() != "3dsmax.exe":
        return None
    m = re.search(r"3ds Max (\d{4})", exe.replace("/", "\\"), re.I)
    ver = int(m.group(1)) if m else 0
    if not ver:
        m2 = re.search(r"3dsMax\\(\d{2})\.", exe.replace("/", "\\"), re.I)
        if m2:
            ver = 2000 + int(m2.group(1))
    if ver < MH2MAX_MIN_MAX:
        return None
    root = os.path.dirname(exe)
    return {"product": "max", "version": ver, "exe": exe, "root": root}


def _identify_resolved(path):
    path = _norm(path)
    if not path:
        return None
    if os.path.isdir(path):
        for name in ("maya.exe", "3dsmax.exe"):
            cand = os.path.join(path, name)
            if os.path.isfile(cand):
                path = cand
                break
            cand = os.path.join(path, "bin", name)
            if os.path.isfile(cand):
                path = cand
                break
    if os.path.isfile(path):
        hit = _maya_from_exe(path) or _max_from_exe(path)
        if hit:
            return hit
    return None


def _scan_program_files():
    hits = {"maya": [], "max": []}
    roots = [
        os.environ.get("ProgramFiles"),
        os.environ.get("ProgramFiles(x86)"),
        r"C:\Program Files",
        r"C:\Program Files (x86)",
    ]
    seen = set()
    for root in roots:
        if not root or not os.path.isdir(root):
            continue
        autodesk = os.path.join(root, "Autodesk")
        if not os.path.isdir(autodesk):
            continue
        for exe in glob.glob(os.path.join(autodesk, "Maya*", "bin", "maya.exe")):
            info = _maya_from_exe(exe)
            if info and info["exe"] not in seen:
                seen.add(info["exe"])
                hits["maya"].append(info)
        for exe in glob.glob(os.path.join(autodesk, "3ds Max *", "3dsmax.exe")):
            info = _max_from_exe(exe)
            if info and info["exe"] not in seen:
                seen.add(info["exe"])
                hits["max"].append(info)
    for key in hits:
        hits[key].sort(key=lambda x: x["version"], reverse=True)
    return hits


def _scan_env():
    hits = {"maya": [], "max": []}
    for y in range(2027, 2021, -1):
        for key, product, name in (
            ("MAYA_LOCATION_%s" % y, "maya", "maya.exe"),
            ("ADSK_3DSMAX_x64_%s" % y, "max", "3dsmax.exe"),
        ):
            val = os.environ.get(key)
            if not val:
                continue
            exe = val if val.lower().endswith(".exe") else os.path.join(val, name)
            info = _maya_from_exe(exe) if product == "maya" else _max_from_exe(exe)
            if info:
                hits[product].append(info)
    mh = os.environ.get("MH2MAX_EXE")
    if mh:
        info = _max_from_exe(mh if mh.lower().endswith(".exe") else os.path.join(mh, "3dsmax.exe"))
        if info:
            hits["max"].append(info)
    for key in hits:
        uniq = []
        seen = set()
        for item in hits[key]:
            if item["exe"] not in seen:
                seen.add(item["exe"])
                uniq.append(item)
        hits[key] = sorted(uniq, key=lambda x: x["version"], reverse=True)
    return hits


def merge_installs(a, b):
    out = {"maya": list(a.get("maya") or []), "max": list(a.get("max") or [])}
    for product in ("maya", "max"):
        seen = {x["exe"] for x in out[product]}
        for item in b.get(product) or []:
            if item["exe"] not in seen:
                seen.add(item["exe"])
                out[product].append(item)
        out[product].sort(key=lambda x: x["version"], reverse=True)
    return out


def detect_installs():
    return merge_installs(_scan_program_files(), _scan_env())


def prompt_custom_install(product_label, min_ver):
    print("")
    print("未检测到受支持的 %s（需要 %s+）。" % (product_label, min_ver))
    print("请粘贴 Maya / 3ds Max 快捷方式路径，或 exe / 安装目录的完整路径。")
    print("支持多层嵌套 .lnk；将自动解析到最终 maya.exe / 3dsmax.exe。")
    while True:
        try:
            raw = raw_input("路径（留空跳过）：").strip()
        except (EOFError, KeyboardInterrupt):
            return None
        if not raw:
            return None
        resolved = resolve_path(raw)
        if not resolved:
            print("路径无效，请重试。")
            continue
        info = _identify_resolved(resolved)
        if not info:
            print("未能识别为 Maya 或 3ds Max 可执行文件。")
            continue
        if info["version"] < min_ver:
            print("版本 %s 低于最低要求 %s，无法安装。" % (info["version"], min_ver))
            continue
        print("已识别：%s %s\n  %s" % (info["product"], info["version"], info["exe"]))
        return info


def _maya_modules_dir():
    docs = os.path.join(os.path.expanduser("~"), "Documents")
    return os.path.join(docs, "maya", "modules")


def install_mh2max_module(maya_modules=None):
    maya_modules = _norm(maya_modules or _maya_modules_dir())
    if not os.path.isdir(maya_modules):
        os.makedirs(maya_modules)
    mod_path = os.path.join(maya_modules, "mh2max.mod")
    root = ROOT.replace("\\", "/")
    content = "+ mh2max 1.3.3 %s\nplug-ins: plug-ins\nscripts: scripts\n" % root
    with open(mod_path, "w", encoding="utf-8") as fh:
        fh.write(content)
    print("[ok] mh2max.mod -> %s" % mod_path)
    return mod_path


def _find_mh_zip():
    if not os.path.isdir(VENDOR_DIR):
        return None
    zips = sorted(glob.glob(os.path.join(VENDOR_DIR, MH_ZIP_GLOB)))
    return zips[-1] if zips else None


def install_metahuman(maya_modules=None):
    zpath = _find_mh_zip()
    if not zpath:
        print("[skip] 未找到 vendor/%s" % MH_ZIP_GLOB)
        print("       请从 GitHub Release 下载 MetaHumanForMaya 压缩包放入 vendor 目录。")
        return False
    maya_modules = _norm(maya_modules or _maya_modules_dir())
    if not os.path.isdir(maya_modules):
        os.makedirs(maya_modules)

    dest_folder = os.path.join(maya_modules, "MetaHumanForMaya")
    dest_mod = os.path.join(maya_modules, "MetaHumanForMaya.mod")
    print("[..] 解压 MetaHumanForMaya（较大，请稍候）…")
    print("     来源：%s" % zpath)

    tmp = os.path.join(CONFIG_DIR, "_mh_extract")
    if os.path.isdir(tmp):
        shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp)

    with zipfile.ZipFile(zpath, "r") as zf:
        zf.extractall(tmp)

    # zip layout: MetaHumanForMaya/ + MetaHumanForMaya.mod at root
    src_folder = os.path.join(tmp, "MetaHumanForMaya")
    src_mod = os.path.join(tmp, "MetaHumanForMaya.mod")
    if not os.path.isdir(src_folder):
        # maybe files at zip root
        if os.path.isfile(os.path.join(tmp, "plugin", "MetaHumanForMaya.py")):
            src_folder = tmp
        else:
            raise RuntimeError("压缩包内找不到 MetaHumanForMaya 文件夹")

    if os.path.isdir(dest_folder):
        print("[..] 移除旧 MetaHumanForMaya …")
        shutil.rmtree(dest_folder, ignore_errors=True)
    shutil.copytree(src_folder, dest_folder)
    if os.path.isfile(src_mod):
        shutil.copy2(src_mod, dest_mod)
    elif os.path.isfile(os.path.join(ROOT, "vendor", "MetaHumanForMaya.mod")):
        shutil.copy2(os.path.join(ROOT, "vendor", "MetaHumanForMaya.mod"), dest_mod)

    shutil.rmtree(tmp, ignore_errors=True)
    print("[ok] MetaHumanForMaya -> %s" % dest_folder)
    print("[ok] MetaHumanForMaya.mod -> %s" % dest_mod)
    return True


def write_config(installs, max_choice=None):
    if not os.path.isdir(CONFIG_DIR):
        os.makedirs(CONFIG_DIR)
    cfg = {}
    if os.path.isfile(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
                cfg = json.load(fh) or {}
        except Exception:
            cfg = {}

    cfg["mh2max_root"] = ROOT
    cfg["maya_modules_dir"] = _maya_modules_dir()
    cfg["maya_installs"] = [
        {"version": x["version"], "exe": x["exe"], "root": x["root"]} for x in installs.get("maya", [])
    ]
    cfg["max_installs"] = [
        {"version": x["version"], "exe": x["exe"], "root": x["root"]} for x in installs.get("max", [])
    ]

    max_list = installs.get("max") or []
    if max_choice:
        cfg["max_exe"] = max_choice["exe"]
        cfg["max_version"] = max_choice["version"]
    elif max_list:
        cfg["max_exe"] = max_list[0]["exe"]
        cfg["max_version"] = max_list[0]["version"]

    with open(CONFIG_PATH, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, ensure_ascii=False, indent=2)
    print("[ok] 配置 -> %s" % CONFIG_PATH)
    if cfg.get("max_exe"):
        print("     默认导出 Max：%s (%s)" % (cfg.get("max_version"), cfg.get("max_exe")))


def _print_detected(installs):
    print("\n--- 检测到的安装 ---")
    if installs.get("maya"):
        for i, m in enumerate(installs["maya"], 1):
            flag = "ok" if m["version"] >= MH2MAX_MIN_MAYA else "!"
            print("  [%s] Maya %s  %s" % (flag, m["version"], m["exe"]))
    else:
        print("  (无 Maya)")
    if installs.get("max"):
        for i, m in enumerate(installs["max"], 1):
            flag = "ok" if m["version"] >= MH2MAX_MIN_MAX else "!"
            print("  [%s] 3ds Max %s  %s" % (flag, m["version"], m["exe"]))
    else:
        print("  (无 3ds Max)")


def choose_max_export(installs):
    max_list = [m for m in (installs.get("max") or []) if m["version"] >= MH2MAX_MIN_MAX]
    if not max_list:
        extra = prompt_custom_install("3ds Max", MH2MAX_MIN_MAX)
        if extra:
            installs.setdefault("max", []).append(extra)
            max_list = [extra]
    if not max_list:
        return None
    if len(max_list) == 1:
        print("\n默认 Max 导出版本：%s" % max_list[0]["version"])
        return max_list[0]
    print("\n选择「一键导出至 Max」使用的 3ds Max 版本：")
    for i, m in enumerate(max_list, 1):
        print("  [%s] 3ds Max %s" % (i, m["version"]))
    print("  [Enter] 使用最新版 (%s)" % max_list[0]["version"])
    try:
        raw = raw_input("请选择：").strip()
    except (EOFError, KeyboardInterrupt):
        return max_list[0]
    if not raw:
        return max_list[0]
    if raw.isdigit():
        idx = int(raw)
        if 1 <= idx <= len(max_list):
            return max_list[idx - 1]
    return max_list[0]


def main():
    _print_header()
    installs = detect_installs()
    _print_detected(installs)

    print("\n安装选项（直接 Enter = 全部安装）：")
    print("  [1] 仅 mh2max Maya 模块")
    print("  [2] 仅 MetaHumanForMaya（需 vendor 压缩包）")
    print("  [3] 仅配置 Max 导出版本")
    print("  [A] 全部（默认）")
    try:
        choice = raw_input("请选择 [A/1/2/3]：").strip().lower()
    except (EOFError, KeyboardInterrupt):
        choice = "a"
    if not choice:
        choice = "a"

    do_mh2max = choice in ("a", "1")
    do_mh = choice in ("a", "2")
    do_max_cfg = choice in ("a", "3")

    maya_ok = [m for m in installs.get("maya", []) if m["version"] >= MH2MAX_MIN_MAYA]
    if not maya_ok and (do_mh2max or do_mh):
        extra = prompt_custom_install("Maya", MH2MAX_MIN_MAYA)
        if extra:
            installs.setdefault("maya", []).append(extra)
            maya_ok = [extra]
        elif do_mh2max or do_mh:
            print("[error] 无可用 Maya，无法安装 Maya 侧组件。")
            _pause()
            return 1

    if do_mh:
        mh_supported = [m for m in installs.get("maya", []) if m["version"] >= MH_MIN_MAYA]
        if not mh_supported:
            print("[warn] MetaHumanForMaya 官方模块支持 Maya %s+；当前 Maya 可能无法加载该插件。" % MH_MIN_MAYA)

    max_choice = None
    if do_max_cfg or choice == "a":
        max_choice = choose_max_export(installs)

    print("\n--- 开始安装 ---")
    if do_mh2max:
        install_mh2max_module()
    if do_mh:
        install_metahuman()
    write_config(installs, max_choice=max_choice)

    print("\n完成。请重启 Maya 后使用 MH2Max / MetaHuman 菜单。")
    print("Max 导出版本可在 %s 修改 max_exe。" % CONFIG_PATH)
    _pause()
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
