# -*- coding: utf-8 -*-
"""Find DNA/body beside the current scene and assemble via DHI Character Importer."""
from __future__ import print_function

import os
import sys

from maya import cmds

SKIP_DNA = ("character.rotate.dna",)
BODY_RIG_SUFFIX = "_body_rig.ma"


def _norm(path):
    return os.path.normpath(path) if path else ""


def _is_char_dna(name):
    n = (name or "").lower()
    if not n.endswith(".dna"):
        return False
    if n.endswith("_rl.dna") or n.endswith(".rotate.dna"):
        return False
    if n in SKIP_DNA:
        return False
    return True


def _listdir(folder):
    try:
        return os.listdir(folder)
    except Exception:
        return []


def find_dhi_root():
    env = os.environ.get("MH2MAX_DHI_ROOT") or os.environ.get("DHI_ROOT")
    if env:
        env = env.strip().strip('"')
        if os.path.isfile(os.path.join(env, "importer.py")):
            return env
        nested = os.path.join(env, "DHI")
        if os.path.isfile(os.path.join(nested, "importer.py")):
            return nested
    try:
        import DHI

        p = os.path.dirname(os.path.abspath(DHI.__file__))
        if os.path.isfile(os.path.join(p, "importer.py")):
            return p
    except Exception:
        pass
    hints = [
        r"D:\Megascans Library\support\plugins\maya\7.3\MSLiveLink\DHI",
        r"D:\Megascans Library\support\plugins\maya\7.2\MSLiveLink\DHI",
        r"C:\Program Files\Quixel\MSLiveLink\DHI",
    ]
    for p in hints:
        if os.path.isfile(os.path.join(p, "importer.py")):
            return p
    for raw in list(sys.path):
        if not raw:
            continue
        if os.path.isfile(os.path.join(raw, "importer.py")) and os.path.basename(raw) == "DHI":
            return raw
        nested = os.path.join(raw, "DHI", "importer.py")
        if os.path.isfile(nested):
            return os.path.join(raw, "DHI")
    maya_plugins = os.path.join(r"D:\Megascans Library\support\plugins", "maya")
    if os.path.isdir(maya_plugins):
        for ver in _listdir(maya_plugins):
            p = os.path.join(maya_plugins, ver, "MSLiveLink", "DHI", "importer.py")
            if os.path.isfile(p):
                return os.path.dirname(p)
    return None


def _candidate_dirs(start):
    out = []
    seen = set()
    d = _norm(start) if start else ""
    for _ in range(5):
        if not d or not os.path.isdir(d) or d.lower() in seen:
            break
        seen.add(d.lower())
        out.append(d)
        for sub in ("SourceAssets", "MaxExport"):
            p = os.path.join(d, sub)
            if os.path.isdir(p) and p.lower() not in seen:
                seen.add(p.lower())
                out.append(p)
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return out


def find_assets(start_path=None):
    """Locate DNA, body rig, maps, and a previously assembled .mb near the scene."""
    scene = cmds.file(q=True, sn=True) or ""
    starts = []
    hinted_body = None
    if start_path:
        sp = os.path.abspath(start_path)
        if os.path.isdir(sp):
            starts.append(sp)
        elif os.path.isfile(sp):
            starts.append(os.path.dirname(sp))
            if sp.lower().endswith(BODY_RIG_SUFFIX):
                hinted_body = sp
        else:
            parent = os.path.dirname(sp)
            if parent:
                starts.append(parent)
    if scene:
        starts.append(os.path.dirname(os.path.abspath(scene)))
    try:
        ws = cmds.workspace(q=True, rd=True)
        if ws:
            starts.append(ws)
    except Exception:
        pass

    dirs = []
    seen = set()
    for s in starts:
        for d in _candidate_dirs(s):
            key = d.lower()
            if key not in seen:
                seen.add(key)
                dirs.append(d)

    dna = None
    body = hinted_body
    maps = None
    assembled = None
    char_dir = None

    if not body and scene and os.path.isfile(scene) and os.path.basename(scene).lower().endswith(BODY_RIG_SUFFIX):
        body = os.path.abspath(scene)

    for d in dirs:
        names = _listdir(d)
        if maps is None:
            m = os.path.join(d, "maps")
            if os.path.isdir(m):
                maps = m
        for fn in names:
            full = os.path.join(d, fn)
            low = fn.lower()
            if dna is None and _is_char_dna(fn):
                dna = full
            if body is None and low.endswith(BODY_RIG_SUFFIX):
                body = full
            if assembled is None and (
                low.endswith("_assembled.mb") or low.endswith("_assembled.ma")
            ):
                assembled = full
        parent_name = os.path.basename(os.path.dirname(d))
        if os.path.basename(d).lower() == "sourceassets":
            char_dir = os.path.dirname(d)
            prefer = os.path.join(d, parent_name + ".dna")
            if os.path.isfile(prefer):
                dna = prefer
            mx = os.path.join(char_dir, "MaxExport", parent_name + "_assembled.mb")
            if os.path.isfile(mx):
                assembled = mx
        if os.path.basename(d).lower() == "maxexport":
            char_dir = os.path.dirname(d)
            mx = os.path.join(d, os.path.basename(char_dir) + "_assembled.mb")
            if os.path.isfile(mx):
                assembled = mx

    if dna and not char_dir:
        src = os.path.dirname(dna)
        if os.path.basename(src).lower() == "sourceassets":
            char_dir = os.path.dirname(src)
        else:
            char_dir = src

    character = None
    if dna:
        character = os.path.splitext(os.path.basename(dna))[0]
    elif char_dir:
        character = os.path.basename(char_dir)
    elif body:
        character = os.path.basename(os.path.dirname(os.path.dirname(body))) or "MetaHuman"

    out_dir = None
    if char_dir:
        out_dir = os.path.join(char_dir, "MaxExport")
    elif assembled:
        out_dir = os.path.dirname(assembled)
    elif scene:
        out_dir = os.path.join(os.path.dirname(os.path.abspath(scene)), "MaxExport")

    if not assembled and character and out_dir:
        guess = os.path.join(out_dir, character + "_assembled.mb")
        if os.path.isfile(guess):
            assembled = guess

    return {
        "scene": scene,
        "dna": dna,
        "body": body,
        "maps": maps,
        "assembled": assembled,
        "character": character or "MetaHuman",
        "char_dir": char_dir,
        "out_dir": out_dir,
        "dhi": find_dhi_root(),
        "can_assemble": bool(dna and body),
        "can_open": bool(assembled and os.path.isfile(assembled)),
    }


def ensure_dhi_ready():
    dhi = find_dhi_root()
    if not dhi:
        raise RuntimeError(
            "找不到 DHI Character Importer（Quixel MSLiveLink）。"
            "请确认 Megascans Maya 插件已安装，或设置环境变量 MH2MAX_DHI_ROOT。"
        )
    parent = os.path.dirname(dhi)
    for p in (parent, dhi):
        if p not in sys.path:
            sys.path.insert(0, p)

    plat = "Windows"
    try:
        import platform as _pf

        if _pf.system() == "Linux":
            plat = "Linux"
    except Exception:
        pass
    ver = str(cmds.about(version=True) or "2022").split(".")[0]
    py_map = {"2022": "python3", "2023": "python397", "2024": "python3108", "2025": "python311"}
    pydna = os.path.join(dhi, "plugins", plat, "pydna", py_map.get(ver, "python3"))
    pydnac = os.path.join(dhi, "plugins", plat, ver)
    for p in (pydna, pydnac):
        if os.path.isdir(p) and p not in sys.path:
            sys.path.append(p)
    plugin_dir = os.path.join(dhi, "plugins", plat, ver)
    if os.path.isdir(plugin_dir):
        cur = os.environ.get("MAYA_PLUG_IN_PATH", "")
        if plugin_dir not in cur.split(os.pathsep):
            os.environ["MAYA_PLUG_IN_PATH"] = plugin_dir + os.pathsep + cur

    try:
        from DHI.PluginLoader import load as dhi_load

        dhi_load()
    except Exception:
        pass
    for plug in (
        "mayaHIK",
        "stereoCamera",
        "ikSpringSolver",
        "matrixNodes",
        "fbxmaya",
        "objExport",
        "embeddedRL4",
        "MayaUE4RBFPlugin" + ver,
        "MayaUERBFPlugin",
    ):
        try:
            if not cmds.pluginInfo(plug, q=True, loaded=True):
                cmds.loadPlugin(plug)
        except Exception:
            pass
    return dhi


def open_assembled(path):
    if not path or not os.path.isfile(path):
        raise RuntimeError("已装配场景不存在：%s" % path)
    cmds.waitCursor(state=True)
    try:
        cmds.file(path.replace("\\", "/"), o=True, f=True, prompt=False, ignoreVersion=True)
    finally:
        cmds.waitCursor(state=False)
    return path


def assemble_character(assets=None):
    assets = assets or find_assets()
    dna = assets.get("dna")
    body = assets.get("body")
    if not dna or not os.path.isfile(dna):
        raise RuntimeError("找不到角色 DNA（*.dna）。请打开 SourceAssets 里的身体模板，或浏览 DNA。")
    if not body or not os.path.isfile(body):
        raise RuntimeError("找不到身体模板（*_body_rig.ma）。")
    maps = assets.get("maps")
    if not maps or not os.path.isdir(maps):
        guess = os.path.join(os.path.dirname(dna), "maps")
        maps = guess if os.path.isdir(guess) else os.path.dirname(dna)

    dhi = ensure_dhi_ready()
    plat = "Windows"
    try:
        import platform as _pf

        if _pf.system() == "Linux":
            plat = "Linux"
    except Exception:
        pass
    common = os.path.join(dhi, "assets", "MH.2", plat)
    if not os.path.isdir(common):
        common = os.path.join(dhi, "assets", "MH.2", "Windows")

    message = {
        "character": {
            "characterAssets": {
                "dnaPath": dna.replace("\\", "/"),
                "bodyPath": body.replace("\\", "/"),
                "mapsDirPath": maps.replace("\\", "/"),
            },
            "common": {
                "shadersDirPath": common.replace("\\", "/"),
                "masksDirPath": common.replace("\\", "/"),
                "headMapsPath": common.replace("\\", "/"),
                "scene_orientation": "y",
            },
        }
    }

    from DHI.importer import CharacterImporter
    from DHI.characterConfig import CharacterConfig

    importer = CharacterImporter()
    importer.character_config = CharacterConfig(message["character"])
    importer.execute()

    if not cmds.objExists("head_lod0_mesh"):
        raise RuntimeError("DHI 装配结束，但场景里仍没有 head_lod0_mesh。请看 Script Editor 里的 DHI 报错。")
    ctrls = cmds.ls("CTRL_*", type="transform") or []
    if len(ctrls) < 20:
        raise RuntimeError("DHI 装配结束，但面部控制器不足。请看 Script Editor。")

    char = assets.get("character") or os.path.splitext(os.path.basename(dna))[0]
    out_dir = assets.get("out_dir") or os.path.join(os.path.dirname(dna), "MaxExport")
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    mb = os.path.join(out_dir, char + "_assembled.mb")
    cmds.file(rename=mb.replace("\\", "/"))
    cmds.file(save=True, type="mayaBinary", force=True)
    assets["assembled"] = mb
    assets["out_dir"] = out_dir
    return assets
