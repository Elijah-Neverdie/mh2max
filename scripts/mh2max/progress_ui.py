# -*- coding: utf-8 -*-
"""Non-blocking Maya progress UI with step index / total and live status text."""
from __future__ import print_function

import sys
import time
import traceback

from maya import cmds, utils


def _qt_process_events():
    try:
        from PySide2 import QtWidgets  # type: ignore

        app = QtWidgets.QApplication.instance()
        if app:
            app.processEvents()
            return
    except Exception:
        pass
    try:
        from PySide6 import QtWidgets  # type: ignore

        app = QtWidgets.QApplication.instance()
        if app:
            app.processEvents()
    except Exception:
        pass


def show_busy(status=u"请稍候…", title=u"导入 MH"):
    """Instant native progress strip (works before custom windows)."""
    try:
        cmds.progressWindow(
            title=title,
            progress=0,
            status=status,
            isInterruptable=False,
            minValue=0,
            maxValue=100,
        )
    except Exception:
        try:
            cmds.progressWindow(edit=True, status=status, progress=0)
        except Exception:
            pass
    try:
        cmds.refresh(force=True)
    except Exception:
        pass
    _qt_process_events()
    try:
        utils.processIdleEvents()
    except Exception:
        pass


def update_busy(status, progress=None):
    try:
        kw = {"status": status}
        if progress is not None:
            kw["progress"] = max(0, min(100, int(progress)))
        cmds.progressWindow(edit=True, **kw)
    except Exception:
        pass
    _qt_process_events()
    try:
        utils.processIdleEvents()
    except Exception:
        pass


def end_busy():
    try:
        cmds.progressWindow(endProgress=True)
    except Exception:
        pass


class ProgressUI(object):
    """Progress that keeps Maya responsive via refresh + processIdleEvents."""

    WIN = "mh2maxProgressWin"
    TXT = "mh2maxProgressTxt"
    EVT = "mh2maxProgressEvt"
    BAR = "mh2maxProgressBar"
    PCT = "mh2maxProgressPct"
    LOG = "mh2maxProgressLog"

    def __init__(self, title, total, use_native_busy=False):
        self.title = title
        self.total = max(1, int(total))
        self.index = 0
        self.cancelled = False
        self.use_native_busy = bool(use_native_busy)
        self._lines = []
        self._fraction = 0.0  # 0..1 within overall
        self._last_event = u""
        # Kill blank native progressWindow leftovers that confuse users
        end_busy()
        self._build()

    def _build(self):
        if cmds.window(self.WIN, exists=True):
            cmds.deleteUI(self.WIN)
        cmds.window(
            self.WIN,
            title=self.title,
            widthHeight=(580, 400),
            sizeable=True,
            retain=False,
        )
        cmds.columnLayout(adjustableColumn=True, rowSpacing=6, columnAttach=("both", 10))
        cmds.text(label=self.title, align="left", font="boldLabelFont", height=24)
        self._status = cmds.text(
            self.TXT, label=u"准备中…  0/%s" % self.total, align="left", height=22
        )
        self._event = cmds.text(
            self.EVT, label=u"当前：等待开始", align="left", height=22, font="boldLabelFont"
        )
        cmds.rowLayout(numberOfColumns=2, columnWidth2=(480, 70), adjustableColumn=1)
        cmds.progressBar(self.BAR, maxValue=1000, width=470, height=22)
        cmds.text(self.PCT, label=u"0%", align="right", width=60)
        cmds.setParent("..")
        cmds.scrollField(self.LOG, editable=False, wordWrap=True, height=240, font="fixedWidthFont")
        cmds.button(label=u"取消", command=self._on_cancel, height=28)
        cmds.showWindow(self.WIN)
        self.raise_window()
        self._pump()

    def raise_window(self):
        if not cmds.window(self.WIN, exists=True):
            return
        try:
            cmds.showWindow(self.WIN)
        except Exception:
            pass
        try:
            cmds.setFocus(self.WIN)
        except Exception:
            pass
        self._pump()

    def reset(self, title=None, total=None):
        if title:
            self.title = title
            try:
                cmds.window(self.WIN, edit=True, title=title)
            except Exception:
                pass
        if total is not None:
            self.total = max(1, int(total))
        self.index = 0
        self.cancelled = False
        self._fraction = 0.0
        self.status(u"准备中…  0/%s" % self.total)
        self.event(u"等待开始")
        self.set_percent(0)
        self.raise_window()

    def _on_cancel(self, *_args):
        self.cancelled = True
        self.log(u"用户取消")

    def _pump(self):
        try:
            cmds.refresh(force=True)
        except Exception:
            pass
        try:
            utils.processIdleEvents()
        except Exception:
            pass
        _qt_process_events()

    def set_percent(self, pct):
        """pct: 0..100"""
        pct = max(0, min(100, float(pct)))
        self._fraction = pct / 100.0
        if cmds.window(self.WIN, exists=True):
            try:
                cmds.progressBar(self.BAR, edit=True, progress=int(pct * 10))
                cmds.text(self.PCT, edit=True, label=u"%s%%" % int(pct))
            except Exception:
                pass
        if self.use_native_busy:
            try:
                update_busy(u"%s%%  %s" % (int(pct), getattr(self, "_last_event", u"")), pct)
            except Exception:
                pass
        self._pump()

    def event(self, msg):
        """Show the currently running action (headline under status)."""
        self._last_event = msg
        if cmds.window(self.WIN, exists=True):
            try:
                cmds.text(self.EVT, edit=True, label=u"当前：%s" % msg)
            except Exception:
                pass
        if self.use_native_busy:
            try:
                update_busy(msg[:80], int(self._fraction * 100))
            except Exception:
                pass
        self._pump()

    def status(self, msg):
        """Update step headline without advancing the step counter."""
        if cmds.window(self.WIN, exists=True):
            try:
                cmds.text(self.TXT, edit=True, label=msg)
            except Exception:
                pass
        self._pump()

    def log(self, msg):
        line = "[%s] %s" % (time.strftime("%H:%M:%S"), msg)
        print(line)
        sys.stdout.flush()
        self._lines.append(line)
        if len(self._lines) > 300:
            self._lines = self._lines[-300:]
        if cmds.window(self.WIN, exists=True):
            try:
                cmds.scrollField(self.LOG, edit=True, text="\n".join(self._lines))
            except Exception:
                pass
        self._pump()

    def step(self, label):
        if self.cancelled:
            raise RuntimeError(u"用户取消导入")
        self.index += 1
        # Map major steps onto percent ranges
        base = (100.0 * (self.index - 1)) / float(self.total)
        status = u"步骤 %s/%s：%s" % (self.index, self.total, label)
        self.log(status)
        self.status(status)
        self.event(label)
        self.set_percent(base)
        self.raise_window()
        return True

    def step_progress(self, done, total, label=None):
        """Sub-progress within the current major step (done/total)."""
        if self.cancelled:
            raise RuntimeError(u"用户取消导入")
        total = max(1, int(total))
        done = max(0, min(total, int(done)))
        step_span = 100.0 / float(self.total)
        base = step_span * max(0, self.index - 1)
        pct = base + step_span * (float(done) / float(total))
        if label:
            self.event(u"%s（%s/%s）" % (label, done, total))
        self.set_percent(pct)

    def close(self):
        self._pump()
        end_busy()
        if cmds.window(self.WIN, exists=True):
            try:
                cmds.deleteUI(self.WIN)
            except Exception:
                pass


def run_steps(title, steps, ui=None):
    """
    steps: list of (label, callable)
    callable receives ProgressUI and may raise.
    Returns last callable result (or None).
    """
    own = ui is None
    if own:
        ui = ProgressUI(title, len(steps))
    else:
        ui.reset(title=title, total=len(steps))
    end_busy()  # avoid blank native progressWindow overlapping our UI
    result = None
    try:
        for label, fn in steps:
            ui.step(label)
            try:
                result = fn(ui)
            except Exception:
                ui.log(traceback.format_exc()[-1500:])
                raise
        ui.set_percent(100)
        ui.event(u"全部完成")
        ui.log(u"全部完成")
        return result
    finally:
        try:
            ui._pump()
        except Exception:
            pass
        end_busy()
        if own:
            pass
