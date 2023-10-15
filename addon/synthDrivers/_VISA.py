# Copyright (C) 2021 Yukio Nozawa, ACT Laboratory
# Copyright (c)2022 Hiroki Fujii,ACT laboratory All rights reserved.

import json
import os
import re
import requests
import time
import nvwave
import threading
import queue
from ctypes import c_short, cdll, c_char_p, c_wchar_p, c_size_t, c_int, create_string_buffer, byref, POINTER, windll, Structure
from speech.commands import IndexCommand, BreakCommand, PitchCommand
import config
from logHandler import log

SAMPLE_RATE = 24000

preprocess_patterns = [
	(re.compile(r" {2,}"), " "),
	(re.compile(r"\?"), "？"),
]

isSpeaking = False
onIndexReached = None
bgThread = None
bgQueue = None
player = None
rate = 50
rateBoost = 0
pitch = 50
temporaryPitch = 50
inflection = 2
volume = 100
voice = "1"

BUF_SIZE = 8192
rootDir = os.path.dirname(os.path.abspath(os.path.dirname(__file__)))

class BgThread(threading.Thread):
	def __init__(self):
		super().__init__(
			name=f"{self.__class__.__module__}.{self.__class__.__qualname__}")
		self.setDaemon(True)

	def run(self):
		while True:
			func, args, kwargs = bgQueue.get()
			if not func:
				break
			try:
				func(*args, **kwargs)
			except BaseException:
				log.error("Error running function from queue", exc_info=True)
			bgQueue.task_done()


def _execWhenDone(func, *args, mustBeAsync=False, **kwargs):
	global bgQueue
	if mustBeAsync or bgQueue.unfinished_tasks != 0:
		# Either this operation must be asynchronous or There is still an operation in progress.
		# Therefore, run this asynchronously in the background thread.
		bgQueue.put((func, args, kwargs))
	else:
		func(*args, **kwargs)

def _speak(text, tempRate=None, tempPitch=None, tempInflection=None, tempVolume=None):
	# When set not to read symbols, NVDA sends blank string. Directly passing it makes fs2 dll crash.
	if text == "  ":
		return
	# end
	global isSpeaking
	isSpeaking = True
	for elem in preprocess_patterns:
		text = re.sub(elem[0], elem[1], text)
	# end replace

	succeed = True
	while(True):
		# speech cancel対策
		if not isSpeaking:
			break
		try:
			wave = getWave(text,1)
		except exception as e:
			print(e)
			succeed = False
			break
		player.feed(wave)
	# end synthesis loop
	player.idle()
	isSpeaking = False

def _break(item):
	sec = item.time / 1000
	player.feed(b"\0" * int(SAMPLE_RATE * sec) * 2)  # 16bits, so multiply by 2
	player.idle()


def speak(speechSequence):
	for item in speechSequence:
		if isinstance(item, str):
			_execWhenDone(_speak, item, mustBeAsync=True)
		elif isinstance(item, BreakCommand):
			_execWhenDone(_break, item, mustBeAsync=True)
		elif isinstance(item, IndexCommand):
			_execWhenDone(onIndexReached, item.index)
		elif isinstance(item, PitchCommand):
			_execWhenDone(_setTemporaryPitch, item.newValue, mustBeAsync=True)
		else:
			pass
		# end which speech command?
	# end for each command in the sequence
	# notify SynthDoneSpeaking
	_execWhenDone(onIndexReached, None)
	isSpeaking = False


def stop():
	global isSpeaking, bgQueue
	params = []
	try:
		while True:
			item = bgQueue.get_nowait()
			if item[0] != _speak:
				params.append(item)
			bgQueue.task_done()
	except queue.Empty:
		pass
	for item in params:
		bgQueue.put(item)
	isSpeaking = False
	player.stop()


def pause(switch):
	global player
	player.pause(switch)

def initialize(indexCallback=None):
	global hissdll, bgThread, bgQueue, player, onIndexReached
	# TODO: 起動状態チェック

	player = nvwave.WavePlayer(
		channels=1,
		samplesPerSec=SAMPLE_RATE,
		bitsPerSample=16,
		outputDevice=config.conf["speech"]["outputDevice"],
		buffered=False
	)
	onIndexReached = indexCallback
	bgQueue = queue.Queue()
	bgThread = BgThread()
	bgThread.start()


def terminate():
	global bgThread, bgQueue, player, hissdll, onIndexReached
	stop()
	bgQueue.put((None, None, None))
	bgThread.join()
	bgThread = None
	bgQueue = None
	player.close()
	player = None
	onIndexReached = None


def _fixBoundary(val):
	if val < 0:
		val = 0
	if val > 100:
		val = 100
	return val


def setRate(newrate):
	global rate
	rate = newrate


def getRate():
	return rate


def setPitch(newpitch):
	global pitch, temporaryPitch
	pitch = newpitch
	temporaryPitch = newpitch


def getPitch():
	return pitch


def _setTemporaryPitch(temppitch):
	global temporaryPitch
	temporaryPitch = _fixBoundary(temppitch)


def setInflection(newinflection):
	global inflection
	inflection = newinflection


def getInflection():
	return inflection


def setVolume(newvolume):
	global volume
	volume = newvolume


def getVolume():
	return volume


def getPause():
	return True

def setPause(pause):
	pass

def getPauseLength():
	return 0

def setPauseLength(pauseLength):
	pass

def getGuess():
	return True

def setGuess(guess):
	pass

def getHighFreqEmphasis():
	return False

def setHighFreqEmphasis(e):
	pass


def setVoice(newvoice):
	global voice
	voice = newvoice


def getVoice():
	return voice


def setRateBoost(newrateboost):
	global rateBoost
	rateBoost = newrateboost

def getRateBoost():
	return rateBoost


def getWave(text, speaker, port = 50021):
		# Internal Server Error(500)が出ることがあるのでリトライする
		# （HTTPAdapterのretryはうまくいかなかったので独自実装）
		# connect timeoutは10秒、read timeoutは3000秒に設定（長文対応）
		# audio_query
		query_payload = {"text": text, "speaker": speaker}
		for query_i in range(10):
			r = requests.post(f"http://localhost:{ port }/audio_query", 
				params=query_payload, timeout=(10.0, 3000.0))
			if r.status_code == 200:
				query_data = r.json()
				break
			time.sleep(0.3)
		else:
			raise exception("Make audio query faild.")

		# synthesis
		synth_payload = {"speaker": speaker}
		for synth_i in range(10):
			r = requests.post(f"http://localhost:{ port }/synthesis", params=synth_payload, 
				data=json.dumps(query_data), timeout=(1000.0, 30000.0))
			if r.status_code == 200:
				# wavファイルヘッダは切ってから返す
				return r.content[44:]
			time.sleep(0.3)
		else:
			raise exception("speak failed.")
