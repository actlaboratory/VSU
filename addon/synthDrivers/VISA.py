# Copyright (C) 2021 Yukio Nozawa, ACT Laboratory
# Copyright (C) 2023 yamahubuki, ACT Laboratory

import wx
from . import _visa
import addonHandler
import gui
from synthDriverHandler import SynthDriver, synthIndexReached, synthDoneSpeaking
from autoSettingsUtils.driverSetting import BooleanDriverSetting, NumericDriverSetting
import speech
from logHandler import log
from speech.commands import (
	IndexCommand,
	BreakCommand,
	PitchCommand,
	RateCommand,
	VolumeCommand,
	PhonemeCommand,
)

try:
	addonHandler.initTranslation()
except BaseException:
	def _(x): return x


class SynthDriver(SynthDriver):
	name = "VISA"
	description = "VISA - Voicevox Interface Synthesizer Addon"

	supportedSettings = (
		SynthDriver.VoiceSetting(),
		SynthDriver.RateSetting(),
		SynthDriver.PitchSetting(),
		SynthDriver.InflectionSetting(),
		SynthDriver.VolumeSetting(),
	)
	supportedCommands = {
		IndexCommand,
		BreakCommand,
		PitchCommand,
		RateCommand,
		VolumeCommand,
	}
	supportedNotifications = {synthIndexReached, synthDoneSpeaking}

	@classmethod
	def check(cls):
		return True

	def __init__(self):
		try:
			_visa.initialize(self._onIndexReached)
		except _hiss.EngineError as e:
			wx.CallAfter(errmsg, e)
			raise e
		# end error

	def speak(self, speechSequence):
		_visa.speak(speechSequence)

	def cancel(self):
		_visa.stop()

	def pause(self, switch):
		_visa.pause(switch)

	def _get_rate(self):
		return _visa.getRate()

	def _set_rate(self, rate):
		_visa.setRate(rate)

	def _get_pitch(self):
		return _visa.getPitch()

	def _set_pitch(self, pitch):
		_visa.setPitch(pitch)

	def _get_inflection(self):
		return _visa.getInflection()

	def _set_inflection(self, inflection):
		_visa.setInflection(inflection)

	def _get_volume(self):
		return _visa.getVolume()

	def _set_volume(self, volume):
		return _visa.setVolume(volume)


	def _onIndexReached(self, index):
		if index is not None:
			synthIndexReached.notify(synth=self, index=index)
		else:
			synthDoneSpeaking.notify(synth=self)

	def terminate(self):
		_visa.terminate()

	def _get_availableVoices(self):
		return _visa.get_availableVoices()

	def _get_voice(self):
		return _visa.getVoice()

	def _set_voice(self, voice):
		_visa.setVoice(voice)

	def isSpeaking(self):
		return _visa.isSpeaking

def errmsg(e):
	print(e)
	reason = _(
		"An unknown error has occurred. Please contact ACT Laboratory for further assistance.")
	msgs = [
		_("Failed to load VISA."),
		_("Error code: %(code)d") % {"code": e.code},
		reason
	]
	gui.messageBox("\n".join(msgs), _("Error"))
