import wx
import gui
try:
    import buildVersion as _versionInfo
except ImportError:
    import versionInfo as _versionInfo

def isCompatibleWith2025():
    return _versionInfo.version_year >= 2025

def messageBox(message, title, error=False):
    if isCompatibleWith2025():
        def impl():
            # 親をmainFrameにするとMessageDialogが画面中央に配置される
            dialogType = gui.message.DialogType.ERROR if error else gui.message.DialogType.STANDARD
            dlg = gui.message.MessageDialog(gui.mainFrame, message, title, dialogType)
            dlg.ShowModal()
        gui.guiHelper.wxCallOnMain(impl)
    else:
        icon = wx.ICON_ERROR if error else wx.ICON_INFORMATION
        gui.messageBox(message, title, style=wx.CENTER | wx.OK | icon)


def yesno(message, title, defaultNo=False):
    if isCompatibleWith2025():
        def impl():
            dlg = gui.message.MessageDialog(gui.mainFrame, message, title, buttons=gui.message.DefaultButtonSet.YES_NO)
            if defaultNo:
                dlg.setDefaultFocus(gui.message.ReturnCode.NO)
            return dlg.ShowModal() == gui.message.ReturnCode.YES
        return gui.guiHelper.wxCallOnMain(impl)
    else:
        style = wx.CENTER | wx.YES | wx.NO | wx.ICON_INFORMATION
        if defaultNo:
            style |= wx.NO_DEFAULT
        return gui.messageBox(message, title, style=style) == wx.YES
