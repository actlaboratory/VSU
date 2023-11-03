# Copyright (C) 2021 Yukio Nozawa, ACT Laboratory
# Copyright (C) 2023 yamahubuki, ACT Laboratory

import wx
from . import _vsu
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
	name = "VSU"
	description = "VSU - Voicevox Synthesizer Unit"

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
			_vsu.initialize(self._onIndexReached)
		except BaseException as e:
			wx.CallAfter(errmsg, e)
			raise e
		# end error

	def speak(self, speechSequence):
		_vsu.speak(speechSequence)

	def cancel(self):
		_vsu.stop()

	def pause(self, switch):
		_vsu.pause(switch)

	def _get_rate(self):
		return _vsu.getRate()

	def _set_rate(self, rate):
		_vsu.setRate(rate)

	def _get_pitch(self):
		return _vsu.getPitch()

	def _set_pitch(self, pitch):
		_vsu.setPitch(pitch)

	def _get_inflection(self):
		return _vsu.getInflection()

	def _set_inflection(self, inflection):
		_vsu.setInflection(inflection)

	def _get_volume(self):
		return _vsu.getVolume()

	def _set_volume(self, volume):
		return _vsu.setVolume(volume)


	def _onIndexReached(self, index):
		if index is not None:
			synthIndexReached.notify(synth=self, index=index)
		else:
			synthDoneSpeaking.notify(synth=self)

	def terminate(self):
		_vsu.terminate()

	def _get_availableVoices(self):
		return _vsu.get_availableVoices()

	def _get_voice(self):
		return _vsu.getVoice()

	def _set_voice(self, voice):
		_vsu.setVoice(voice)

	def isSpeaking(self):
		return _vsu.isSpeaking

def errmsg(e):
	msgs = [
		_("Failed to load VSU."),
		str(e)
	]
	gui.messageBox("\n".join(msgs), _("Error"))
