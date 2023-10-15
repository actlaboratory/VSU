import wx
import addonHandler

try:
    addonHandler.initTranslation()
except BaseException:
    def _(x): return x


class OnlineRegDialog(wx.Dialog):
    def __init__(self):
        wx.Dialog.__init__(self, None, -1, _("Online registration"), size=(200, 150))
        name = _("Enter your serial number suplied by ACT Laboratory")
        label = wx.StaticText(self, wx.ID_ANY, label=name, name=name)
        self.serial = wx.TextCtrl(self, wx.ID_ANY, name=name)
        ok = wx.Button(self, wx.ID_OK, _("OK"))
        ok.SetDefault()
        cancel = wx.Button(self, wx.ID_CANCEL, _("Cancel"))
        isz = wx.BoxSizer(wx.VERTICAL)
        isz.Add(label, 1, wx.EXPAND)
        isz.Add(self.serial, 1, wx.EXPAND)
        bsz = wx.BoxSizer(wx.HORIZONTAL)
        bsz.Add(ok, 1, wx.EXPAND)
        bsz.Add(cancel, 1, wx.EXPAND)
        msz = wx.BoxSizer(wx.VERTICAL)
        msz.Add(isz, 1, wx.EXPAND)
        msz.Add(bsz, 1, wx.EXPAND)
        self.SetSizer(msz)

    def GetData(self):
        return self.serial.GetValue()
