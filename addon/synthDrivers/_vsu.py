# Copyright (C) 2021 Yukio Nozawa, ACT Laboratory
# Copyright (c)2022 Hiroki Fujii,ACT laboratory All rights reserved.
# Copyright (C) 2023 yamahubuki, ACT Laboratory

import json
import re
import requests
import time
import nvwave
import threading
import queue
from collections import OrderedDict
from synthDriverHandler import VoiceInfo
from speech.commands import IndexCommand, BreakCommand, PitchCommand
import config
from logHandler import log

import urllib.request
import urllib.parse


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
pitch = 50
temporaryPitch = 50
inflection = 50
volume = 100
voice = "1"
voices_cash = None
session = None

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
			except BaseException as e:
				print(e)
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

def _speak(text):
	# When set not to read symbols, NVDA sends blank string. Directly passing it makes fs2 dll crash.
	if text == "  ":
		return
	# end
	global isSpeaking
	isSpeaking = True
	for elem in preprocess_patterns:
		text = re.sub(elem[0], elem[1], text)
	# end replace

	try:
		wave = getWave(text)
	except Exception as e:
		log.error(e)
		isSpeaking = False
		raise e
	player.feed(wave,onDone=None)
	player.idle()
	isSpeaking = False

def _break(item):
	sec = item.time / 1000
	player.feed(b"\0" * int(SAMPLE_RATE * sec) * 2)  # 16bits, so multiply by 2
	player.idle()

def speak(speechSequence):
	global isSpeaking
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
			if item[0] != _speak and item[0] != _break:
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
	global bgThread, bgQueue, player, onIndexReached
	# 利用可能な音声を取得する、voicevoxの起動チェックも兼ねる
	get_availableVoices(useCache = False)
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
	global bgThread, bgQueue, player, onIndexReached
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
	if newrate <1:
		newrate = 1
	global rate
	rate = newrate


def getRate():
	return rate


def setPitch(newpitch):
	global pitch, temporaryPitch
	if newpitch < 1:
		newpitch = 1
	pitch = newpitch
	temporaryPitch = newpitch


def getPitch():
	return pitch


def _setTemporaryPitch(temppitch):
	if temppitch < 1:
		temppitch = 1
	global temporaryPitch
	temporaryPitch = _fixBoundary(temppitch)


def setInflection(newinflection):
	if newinflection < 1:
		newinflection = 1
	global inflection
	inflection = newinflection


def getInflection():
	return inflection


def setVolume(newvolume):
	global volume
	volume = newvolume


def getVolume():
	return volume


def setVoice(newvoice):
	global voice
	voice = newvoice


def getVoice():
	return voice


def getWave(text, port = 50021):
	global voice
	global rate
	global temporaryPitch
	global inflection
	global volume

	# Internal Server Error(500)が出ることがあるのでリトライする
	# （HTTPAdapterのretryはうまくいかなかったので独自実装）
	# connect timeoutは10秒、read timeoutは3000秒に設定（長文対応）
	# audio_query
	query_payload = {"text": text, "speaker": voice}
	for query_i in range(10):
		r = getSession().post(f"http://localhost:{ port }/audio_query", 
			params=query_payload, timeout=(10.0, 3000.0))
		if r.status_code == 200:
			query_data = r.json()
			break
		time.sleep(0.1)
	else:
		raise exception("Make audio query faild.")

	# synthesis
	synth_payload = {"speaker": voice}
	query_data["speedScale"]=(rate+20) / 50
	query_data["pitchScale"]=(temporaryPitch - 50)*0.0015
	query_data["intonationScale"]=inflection / 50
	query_data["volumeScale"]=volume / 50
	query_data["prePhonemeLength"]=0
	query_data["postPhonemeLength"]=0

	for synth_i in range(10):
		r = getSession().post(f"http://localhost:{ port }/synthesis", params=synth_payload, 
			data=json.dumps(query_data), timeout=(1000.0, 30000.0))
		if r.status_code == 200:
			# wavファイルヘッダ44バイトは切ってから返す
			return r.content[44:]
		time.sleep(0.1)
	else:
		raise exception("speak failed.")


def get_availableVoices(port = 50021, useCache = True):
	global voices_cash
	if useCache and voices_cash:
		return voices_cash

	for synth_i in range(10):
		r = getSession().get(f"http://localhost:{ port }/speakers", timeout=(100, 300))
		if r.status_code == 200:
			lst = r.json()
			break
		time.sleep(0.1)
	else:
		raise Exception("get voice list failed.")

	ret = OrderedDict()
	for speaker in lst:
		for style in speaker["styles"]:
			ret[str(style["id"])] = VoiceInfo(str(style["id"]), speaker["name"] + "(" + style["name"] + ")", "ja")
	voices_cash = ret
	return ret


def getSession():
	global session
	if session:
		return session
	session = requests.Session()
	return session
