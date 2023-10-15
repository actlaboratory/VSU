# Copyright (C) 2021 Yukio Nozawa, ACT Laboratory
# Copyright (C) 2023 yamahubuki, ACT Laboratory


import os
import wx
from collections import OrderedDict
from . import _visa
import threading
import addonHandler
import gui
import languageHandler
from synthDriverHandler import SynthDriver, VoiceInfo, synthIndexReached, synthDoneSpeaking
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
		SynthDriver.RateSetting(minStep=10),
		NumericDriverSetting(
			"rateBoost",
			_("Rate boos&t"),
			availableInSettingsRing=True,
			defaultVal=0,
			displayName=pgettext('synth setting', 'RateBoost')
		),
		SynthDriver.PitchSetting(minStep=25),
		NumericDriverSetting(
			"inflection",
			_("&Inflection"),
			availableInSettingsRing=True,
			defaultVal=2,
			minVal=0,
			maxVal=3,
			normalStep=1,
			displayName=pgettext('synth setting', 'Inflection')
		),
		SynthDriver.VolumeSetting(minStep=10),
		BooleanDriverSetting(
			"pauseBetweenWords",
			_("&Pause between words"),
			defaultVal=True
		),
		NumericDriverSetting(
			"pauseLength",
			_("Pause &Length"),
			defaultVal=7,
			minVal=0,
			maxVal=99,
			normalStep=1
		),
		BooleanDriverSetting(
			"guess",
			_("&Guess unknown word pronunciations"),
			defaultVal=True,
			availableInSettingsRing=True,
			displayName=pgettext(
				'synth setting', 'Guess unknown word pronunciations')
		),
		BooleanDriverSetting(
			"highFreqEmphasis",
			_("&Emphasize high frequencies"),
			defaultVal=False
		),
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

	def _get_pauseBetweenWords(self):
		return _visa.getPause()

	def _set_pauseBetweenWords(self, pause):
		_visa.setPause(pause)

	def _get_pauseLength(self):
		return _visa.getPauseLength()

	def _set_pauseLength(self, pauseLength):
		_visa.setPauseLength(pauseLength)

	def _get_guess(self):
		return _visa.getGuess()

	def _set_guess(self, guess):
		_visa.setGuess(guess)

	def _get_highFreqEmphasis(self):
		return _visa.getHighFreqEmphasis()

	def _set_highFreqEmphasis(self, e):
		_visa.setHighFreqEmphasis(e)

	def _onIndexReached(self, index):
		if index is not None:
			synthIndexReached.notify(synth=self, index=index)
		else:
			synthDoneSpeaking.notify(synth=self)

	def terminate(self):
		_visa.terminate()

	def _get_availableVoices(self):
		availableVoices = OrderedDict()
		availableVoices["1"] = VoiceInfo("1", "Keiko", "ja")
		availableVoices["2"] = VoiceInfo("2", "Takashi", "ja")
		return availableVoices

	def _get_voice(self):
		return _visa.getVoice()

	def _set_voice(self, voice):
		_visa.setVoice(voice)

	def _get_rateBoost(self):
		return _visa.getRateBoost()

	def _set_rateBoost(self, boost):
		_visa.setRateBoost(boost)

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
