import glob
import os
import addonHandler

try:
    addonHandler.initTranslation()
except BaseException:
    def _(x): return x

rootDir = os.path.dirname(os.path.abspath(__file__))


def onInstall():
	pass
