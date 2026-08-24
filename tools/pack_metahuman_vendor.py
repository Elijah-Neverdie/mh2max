# -*- coding: utf-8 -*-
"""Pack MetaHumanForMaya from %USERPROFILE%/Documents/maya/modules to vendor zip."""
from __future__ import print_function

import os
import shutil
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VENDOR = os.path.join(ROOT, "vendor")
MODULES = os.path.join(os.path.expanduser("~"), "Documents", "maya", "modules")
SRC = os.path.join(MODULES, "MetaHumanForMaya")
MOD = os.path.join(MODULES, "MetaHumanForMaya.mod")
OUT = os.path.join(VENDOR, "MetaHumanForMaya-1.3.1-win64.zip")


def main():
    if not os.path.isdir(SRC):
        print("Missing:", SRC)
        return 1
    if not os.path.isfile(MOD):
        print("Missing:", MOD)
        return 1
    if not os.path.isdir(VENDOR):
        os.makedirs(VENDOR)
    shutil.copy2(MOD, os.path.join(VENDOR, "MetaHumanForMaya.mod"))

    out_tmp = OUT + ".tmp"
    if os.path.isfile(out_tmp):
        os.remove(out_tmp)
    if os.path.isfile(OUT):
        try:
            os.remove(OUT)
        except OSError:
            out_tmp = OUT.replace(".zip", "-%s.zip" % os.getpid())

    count = 0
    print("Packing to", out_tmp)
    with zipfile.ZipFile(out_tmp, "w", zipfile.ZIP_DEFLATED) as zf:
        for base, _dirs, files in os.walk(SRC):
            for name in files:
                full = os.path.join(base, name)
                arc = os.path.join("MetaHumanForMaya", os.path.relpath(full, SRC))
                zf.write(full, arc)
                count += 1
                if count % 500 == 0:
                    print("  files:", count)
        zf.write(MOD, "MetaHumanForMaya.mod")
    if out_tmp != OUT and os.path.isfile(OUT):
        print("Target locked; kept:", out_tmp)
    elif out_tmp != OUT:
        os.replace(out_tmp, OUT)
    final = OUT if os.path.isfile(OUT) else out_tmp
    size_mb = os.path.getsize(final) / (1024.0 * 1024.0)
    print("Done: %d files, %.1f MB -> %s" % (count + 1, size_mb, final))
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
