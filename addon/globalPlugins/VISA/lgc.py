from ctypes import cdll, c_char_p, c_wchar_p, c_int, create_string_buffer, windll, Structure, POINTER, pointer, byref
import os
import tempfile
import threading
import wx
import zipfile
import addonHandler
from .constants import *
import gui
import updateCheck
from urllib.request import Request, urlopen
from .translate import *

try:
    addonHandler.initTranslation()
except BaseException:
    def _(x): return x

hissdll = None
rootDir = os.path.dirname(os.path.dirname(os.path.abspath(os.path.dirname(__file__))))

trialStarted = False

HISS_RESULT_SUCCEED = 0
HISS_RESULT_SERIAL_LOCAL_VALIDATION = -1004
HISS_RESULT_SERIAL_NOT_FOUND = -1005
HISS_RESULT_SERIAL_REMOTE_VALIDATION = -1006
HISS_RESULT_SERIAL_LOCKED = -1007
HISS_RESULT_RATE_LIMIT = -1008
HISS_RESULT_CONNECTION_ERROR = -1009
HISS_RESULT_INVALID_DATA = -1010
HISS_RESULT_WRITEFILE_FAILED = -1011
HISS_RESULT_CANNOT_GENERATE_UNLOCK_CODE = -1012
HISS_RESULT_OLD_CLIENT = -1013
HISS_RESULT_TRIAL_LIMIT = -1014
HISS_RESULT_SOFTWARE_NOT_FOUND = -1015
HISS_RESULT_ERROR_OPENING_FILE = -1019
HISS_RESULT_ERROR_PARSING_LICENSE_INFO = -1020
HISS_RESULT_INTEGRITY_CHECK_FAILED = -1021

errors = {
    HISS_RESULT_SERIAL_LOCAL_VALIDATION: _("The serial number you typed has an invalid form. It should be 19 characters in total, including the hyphens. Please make sure you're inputting it in Hankaku mode."),
    HISS_RESULT_SERIAL_NOT_FOUND: _("The serial number you typed was not found on the ACT Laboratory server. Please make sure you're using a valid serial number."),
    HISS_RESULT_SERIAL_REMOTE_VALIDATION: _("The serial number you typed was rejected by the ACT Laboratory server. Please contact ACT Laboratory for further information."),
    HISS_RESULT_SERIAL_LOCKED: _("The serial number you typed has been used 3 times within the last 365 days. You cannot use this serial number at the moment."),
    HISS_RESULT_RATE_LIMIT: _("Access to ACT Laboratory server is currently restricted. Please try again later."),
    HISS_RESULT_CONNECTION_ERROR: _("Failed to establish connection to the ACT Laboratory server. Please check if your internet connection is working correctly and try again."),
    HISS_RESULT_INVALID_DATA: _("The ACT Laboratory server has returned an unknown response. Please contact ACT Laboratory for further information."),
    HISS_RESULT_WRITEFILE_FAILED: _("Failed to create license file. Please contact ACT Laboratory for further assistance."),
    HISS_RESULT_CANNOT_GENERATE_UNLOCK_CODE: _("Failed to generate license information for this computer. Please contact ACT Laboratory for further assistance."),
    HISS_RESULT_OLD_CLIENT: _("The ACT Laboratory server has detected that you're using an old version of the add-on. Please update to the latest version and try again."),
    HISS_RESULT_TRIAL_LIMIT: _("You can only enable the trial mode three times within the last 180 days."),
    HISS_RESULT_SOFTWARE_NOT_FOUND: _("The ACT Laboratory server could not recognize the software identification information from your request. Please contact ACT Laboratory for further assistance."),
    HISS_RESULT_ERROR_OPENING_FILE: _("There was an error opening a file."),
    HISS_RESULT_ERROR_PARSING_LICENSE_INFO: _("Failed to parse license information file. The file may be corrupted. Please contact ACT Laboratory for further assistance."),
    HISS_RESULT_INTEGRITY_CHECK_FAILED: _("The response from ACT Laboratory server is corrupted. Please contact ACT Laboratory for further assistance.")}


class VisibleLicenseInfo(Structure):
    _fields_ = [
        ("localLicenseExists", c_int),
        ("localLicenseValid", c_int),
        ("userName", c_char_p),
        ("userEmail", c_char_p),
        ("serialKeyLast", c_char_p),
        ("authorizedAt", c_char_p)
    ]


def produceErrorMessage(code):
    return errors[code] if code in errors else _(
        "An unknown error %(code)d has occurred. Please contact ACT Laboratory for further assistance.") % {"code": code}


def produceRegistrationSuccessMessage():
    gui.messageBox(_("Successfully registered! You can now start using HISS by selecting it from NVDA speech settings."), _("Success"))


def init():
    windll.kernel32.SetDllDirectoryW(os.path.join(rootDir, "data"))
    global hissdll
    hissdll = cdll.LoadLibrary(os.path.join(rootDir, "data", "hiss.dll"))
    windll.kernel32.SetDllDirectoryW(None)
    hissdll.fs2_globalCreate.argtypes = [c_wchar_p]
    hissdll.fs2_requestOnlineRegistration.argtypes = [c_wchar_p]
    hissdll.fs2_getOfflineRegInfo.argtypes = [c_char_p]
    hissdll.fs2_allocateVisibleLicenseInfo.argtypes = [POINTER(POINTER(VisibleLicenseInfo))]
    hissdll.fs2_releaseVisibleLicenseInfo.argtypes = [POINTER(VisibleLicenseInfo)]
    ret = hissdll.fs2_globalCreate(rootDir)
    if ret != HISS_RESULT_SUCCEED:
        raise("HISS globalPlugin initialization failed")


def free():
    hissdll=None

def _callHissdll(attribute, *args):
    if hissdll is None:
        raise SystemError("already unregistered handle")
    f = getattr(hissdll,attribute)
    if not f:
        raise SystemError("unexpected attribute")
    return f(*args)


def getOfflineRegInfo():
    buf = create_string_buffer(256)
    _callHissdll("fs2_getOfflineRegInfo", buf)
    return buf.value.decode("UTF-8")


def requestOnlineRegistration(serial):
    if serial == "":
        gui.messageBox(_("Please input your serial number."), _("Error"))
        return False
    # end no input
    ret = _callHissdll("fs2_requestOnlineRegistration", serial)
    if ret != HISS_RESULT_SUCCEED:
        gui.messageBox(produceErrorMessage(ret), _("Error"))
        return False
    # end error
    produceRegistrationSuccessMessage()
    return True


def requestTrial():
    ret = _callHissdll("fs2_requestTrial")
    if ret != HISS_RESULT_SUCCEED:
        gui.messageBox(produceErrorMessage(ret), _("Error"))
        return False
    # end error
    gui.messageBox(_("Trial mode has been enabled. You can now select HISS from NVDA settings and use full features of the addon for thirty minutes."), _("Success"))
    global trialStarted
    trialStarted = True
    return True


def showLicenseInfo():
    ptr = pointer(VisibleLicenseInfo())
    ret = _callHissdll("fs2_allocateVisibleLicenseInfo", byref(ptr))
    if ret != HISS_RESULT_SUCCEED:
        gui.messageBox(produceErrorMessage(ret), _("Error"))
        return
    # end error
    info = ptr.contents
    messages = [_("Software name: HISS")]
    if info.localLicenseExists == 0:
        messages.extend([_("License: Not registered.")])
    elif info.localLicenseValid == 0:
        messages.extend([_("License: Invalid. Please re-register.")])
    else:
        messages.extend([
            _("Licensed to: %(lt)s(%(email)s)") % {"lt": info.userName.decode("UTF-8"), "email": info.userEmail.decode("UTF-8")},
            _("Serial number: HISS-****-****-%(skl)s") % {"skl": info.serialKeyLast.decode("UTF-8")},
            _("Registered at: %(ra)s") % {"ra": info.authorizedAt.decode("UTF-8")}
        ])
    # end licensed
    gui.messageBox("\n".join(messages), _("License information"))
    _callHissdll("fs2_releaseVisibleLicenseInfo", ptr)


def offlineRegRegister(fname):
    ret = _callHissdll("fs2_registerLicenseFile", fname)
    if ret != HISS_RESULT_SUCCEED:
        gui.messageBox(produceErrorMessage(ret), _("Error"))
        return
    # end error
    if _callHissdll("fs2_validateLicense") != HISS_RESULT_SUCCEED:
        gui.messageBox(_("The license file is not valid. Please contact ACT Laboratory for further assistance."), _("Error"))
        return
    # end error
    produceRegistrationSuccessMessage()


def isLicenseActive():
    return true


def hasTrialStarted():
    return trialStarted


