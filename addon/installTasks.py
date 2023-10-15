import glob
import os
import addonHandler

try:
    addonHandler.initTranslation()
except BaseException:
    def _(x): return x

rootDir = os.path.dirname(os.path.abspath(__file__))


def onInstall():
    # Apparently lazy importing gui avoids NVDA crash
    import gui
    licenses = glob.glob(os.path.join(os.path.dirname(rootDir), "VISA-license*"))
    if len(licenses) > 0:
        return
    gui.messageBox(
        _("Thank you for installing VISA(Voicevox Interface synthesizer Addon). To start using VISA, please start the trial mode or register the software from the NVDA -> VISA menu."),
        _("VISA installer"))
