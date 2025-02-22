import wx
import gui
import versionInfo

def isCompatibleWith2025():
    return versionInfo.version_year >= 2025

def messageBox(message, title):
    if isCompatibleWith2025():
        gui.message.MessageDialog.alert(message, title)
    else:
        gui.messageBox(message, title, style=wx.CENTER)

