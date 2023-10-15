from __future__ import unicode_literals
import os
import globalPluginHandler
import gui
import wx
import addonHandler
import globalVars
import config
import synthDriverHandler
from logHandler import log
from .constants import *
from . import updater


try:
    addonHandler.initTranslation()
except BaseException:
    def _(x): return x


confspec = {
    "checkForUpdatesOnStartup": "boolean(default=True)",
}
config.conf.spec["VISA_global"] = confspec


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
    scriptCategory = _("VISA")

    def __init__(self, *args, **kwargs):
        super(GlobalPlugin, self).__init__(*args, **kwargs)
        if globalVars.appArgs.secure:
            return
        # end secure screen
        if self.getUpdateCheckSetting() is True:
            self.autoUpdateChecker = updater.AutoUpdateChecker()
            self.autoUpdateChecker.autoUpdateCheck(mode=updater.AUTO)
        # end update check
        lgc.init()
        self._setupMenu()

    def terminate(self):
        super(GlobalPlugin, self).terminate()
        lgc.free()
        try:
            gui.mainFrame.sysTrayIcon.menu.Remove(self.rootMenuItem)
        except BaseException:
            pass

    def _setupMenu(self):
        self.rootMenu = wx.Menu()
        self.offlineRegMenu = wx.Menu()

        self.trialItem = self.rootMenu.Append(wx.ID_ANY, _("Start &trial"), _(
            "Starts trial version."))
        gui.mainFrame.sysTrayIcon.Bind(
            wx.EVT_MENU, self.trial, self.trialItem)

        self.onlineRegItem = self.rootMenu.Append(wx.ID_ANY, _("O&nline registration"), _(
            "Register the software online and activate the full features."))
        gui.mainFrame.sysTrayIcon.Bind(
            wx.EVT_MENU, self.onlineReg, self.onlineRegItem)

        self.getInfoItem = self.offlineRegMenu.Append(wx.ID_ANY, _(
            "&Get information about registration"), _("Get required information from this computer."))
        gui.mainFrame.sysTrayIcon.Bind(
            wx.EVT_MENU, self.offlineRegGetInfo, self.getInfoItem)

        self.registerFileItem = self.offlineRegMenu.Append(wx.ID_ANY, _("Register license &file"), _(
            "Register the license given from ACT Laboratory and unlock the full features of the software."))
        gui.mainFrame.sysTrayIcon.Bind(
            wx.EVT_MENU, self.offlineRegRegister, self.registerFileItem)

        self.rootMenu.AppendSubMenu(self.offlineRegMenu, _(
            "O&ffline registration"))

        self.showLicenseInfoItem = self.rootMenu.Append(wx.ID_ANY, _("&Show license information"), _(
            "Display the currently registered license information."))
        gui.mainFrame.sysTrayIcon.Bind(
            wx.EVT_MENU, self.showLicenseInfo, self.showLicenseInfoItem)

        self.updateCheckToggleItem = self.rootMenu.Append(
            wx.ID_ANY,
            self.updateCheckToggleString(),
            _("Toggles update checking on startup.")
        )
        gui.mainFrame.sysTrayIcon.Bind(
            wx.EVT_MENU, self.toggleUpdateCheck, self.updateCheckToggleItem)

        self.updateCheckPerformItem = self.rootMenu.Append(
            wx.ID_ANY,
            _("Check for updates"),
            _("Checks for new updates manually.")
        )
        gui.mainFrame.sysTrayIcon.Bind(
            wx.EVT_MENU, self.performUpdateCheck, self.updateCheckPerformItem)

        self.rootMenuItem = gui.mainFrame.sysTrayIcon.menu.Insert(
            2, wx.ID_ANY, _("VISA"), self.rootMenu)

        self.updateMenuState()

    def updateCheckToggleString(self):
        return _("Disable checking for updates on startup") if self.getUpdateCheckSetting() is True else _("Enable checking for updates on startup")

    def onlineReg(self, evt):
        dlg = online.OnlineRegDialog()
        while(True):
            dlg.Centre()
            ret = dlg.ShowModal()
            if ret == wx.ID_CANCEL:
                return
            # end cancel
            serial = dlg.GetData()
            if lgc.requestOnlineRegistration(serial):
                break
            # end succeeds?
        # end serial input loop
        self.updateMenuState()

    def offlineRegGetInfo(self, evt):
        code = lgc.getOfflineRegInfo()
        title = _("Offline registration information")
        msg = _(
            "Your offline registration code is \"%(code)s\" . The code has been copied to your clipboard.\nNext steps:\nPlease enter the code exactly to the offline registration form and get your license file.\nOnce you've obtained your license file, you can register it from the VISA menu -> Offline registration -> Register license file.") % {"code": code}
        gui.messageBox(msg, title)

    def offlineRegRegister(self, evt):
        with wx.FileDialog(None, _("choose license file"), wildcard=_("license file") + "(*.dat)|*.dat", style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST) as fd:
            if fd.ShowModal() == wx.ID_CANCEL:
                return
            # end cancel
            fname = fd.GetPath()
        # end with dialog
        lgc.offlineRegRegister(fname)
        self.updateMenuState()

    def trial(self, evt):
        lgc.requestTrial()
        self.updateMenuState()

    def showLicenseInfo(self, evt):
        lgc.showLicenseInfo()

    def updateMenuState(self):
        la = lgc.isLicenseActive()
        self.onlineRegItem.Enable(not la)
        self.getInfoItem.Enable(not la)
        self.registerFileItem.Enable(not la)
        self.trialItem.Enable(not (la or lgc.hasTrialStarted()))

    def toggleUpdateCheck(self, evt):
        changed = not self.getUpdateCheckSetting()
        self.setUpdateCheckSetting(changed)
        msg = _("Updates will be checked automatically when launching NVDA.") if changed is True else _("Updates will not be checked when launching NVDA.")
        self.updateCheckToggleItem.SetItemLabel(self.updateCheckToggleString())
        gui.messageBox(msg, _("Settings changed"))

    def performUpdateCheck(self, evt):
        updater.AutoUpdateChecker().autoUpdateCheck(mode=updater.MANUAL)

    def getUpdateCheckSetting(self):
        return config.conf["VISA_global"]["checkForUpdatesOnStartup"]

    def setUpdateCheckSetting(self, val):
        config.conf["VISA_global"]["checkForUpdatesOnStartup"] = val
