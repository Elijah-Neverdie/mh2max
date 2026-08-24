# -*- coding: utf-8 -*-
"""Read/write mh2max user config (%LOCALAPPDATA%\\mh2max\\config.json)."""
from __future__ import print_function

import json
import os
import re

CONFIG_DIR = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "mh2max")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")


def _ensure_dir():
    if CONFIG_DIR and not os.path.isdir(CONFIG_DIR):
        os.makedirs(CONFIG_DIR)


def load_config():
    if not os.path.isfile(CONFIG_PATH):
        return {}
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_config(data):
    _ensure_dir()
    with open(CONFIG_PATH, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    return CONFIG_PATH


def get_max_exe(config=None):
    cfg = config if config is not None else load_config()
    exe = (cfg.get("max_exe") or "").strip()
    if exe and os.path.isfile(exe):
        return exe
    return None


def get_max_version(config=None):
    cfg = config if config is not None else load_config()
    try:
        return int(cfg.get("max_version") or 0)
    except (TypeError, ValueError):
        return 0


def max_version_from_path(path):
    if not path:
        return 0
    m = re.search(r"3ds Max (\d{4})", path.replace("/", "\\"), re.I)
    if m:
        return int(m.group(1))
    m = re.search(r"3dsMax\\(\d{2})\.", path.replace("/", "\\"), re.I)
    if m:
        return 2000 + int(m.group(1))
    return 0
