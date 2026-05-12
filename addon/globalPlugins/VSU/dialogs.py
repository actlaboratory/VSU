# -*- coding: utf-8 -*-
# Copyright (C) 2026 ACT Laboratory

import addonHandler
import gui
import wx

try:
    addonHandler.initTranslation()
except Exception:
    def _(x): return x


class DownloadProgressDialog(wx.Dialog):
    """進捗バーとキャンセルボタンを持つ汎用ダウンロードダイアログ"""

    def __init__(self, title):
        super().__init__(gui.mainFrame, title=title)
        self._cancelled = False

        sizer = wx.BoxSizer(wx.VERTICAL)

        self._label = wx.StaticText(self, label=_("準備中..."))
        sizer.Add(self._label, flag=wx.ALL | wx.EXPAND, border=10)

        self._gauge = wx.Gauge(self, range=100, size=(400, 20))
        sizer.Add(self._gauge, flag=wx.ALL | wx.EXPAND, border=10)

        cancel_btn = wx.Button(self, wx.ID_CANCEL, _("キャンセル"))
        cancel_btn.Bind(wx.EVT_BUTTON, self._on_cancel)
        sizer.Add(cancel_btn, flag=wx.ALL | wx.ALIGN_CENTER, border=10)

        self.SetSizerAndFit(sizer)
        self.CentreOnParent()

    def _on_cancel(self, evt):
        self._cancelled = True

    @property
    def cancelled(self):
        return self._cancelled

    def set_progress(self, pct, message):
        if not self or not self.IsShown():
            return
        self._label.SetLabel(message)
        self._gauge.SetValue(pct)
