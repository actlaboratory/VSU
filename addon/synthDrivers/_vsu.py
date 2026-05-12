# Copyright (C) 2021 Yukio Nozawa, ACT Laboratory
# Copyright (c)2022 Hiroki Fujii,ACT laboratory All rights reserved.
# Copyright (C) 2023-2026 yamahubuki, ACT Laboratory

import json
import os
import re
import requests
import time
import nvwave
import threading
import queue
from collections import OrderedDict
from pathlib import Path
from synthDriverHandler import VoiceInfo
from speech.commands import IndexCommand, BreakCommand, PitchCommand
import config
from logHandler import log

import urllib.request
import urllib.parse

# Import local VOICEVOX server
try:
	from . import _voicevox_server as voicevox_server
	HAS_BUNDLED_VOICEVOX = True
except ImportError:
	HAS_BUNDLED_VOICEVOX = False
	log.warning("Bundled VOICEVOX not available, will try external VOICEVOX")


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
voicevox_local_server = None
_server_ready = threading.Event()
_server_init_error = None

class BgThread(threading.Thread):
	def __init__(self):
		super().__init__(
			name=f"{self.__class__.__module__}.{self.__class__.__qualname__}",
			daemon=True)

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


def _start_server_bg():
	"""バックグラウンドでVOICEVOXサーバーを起動する"""
	global voicevox_local_server, _server_init_error
	try:
		addon_dir = Path(__file__).parent.parent
		core_dir = addon_dir / "voicevox_core"
		if not core_dir.exists():
			log.warning(f"VOICEVOX core directory not found: {core_dir}")
			return
		voicevox_local_server = voicevox_server.VoicevoxServer(core_dir, port=50021)
		voicevox_local_server.start()
		if voicevox_local_server.is_running():
			log.info("Bundled VOICEVOX server started successfully on port 50021")
		else:
			log.error("Server thread is not running after start()")
			voicevox_local_server = None
	except RuntimeError as e:
		log.warning(f"Bundled VOICEVOX server cannot be used: {e}")
		_server_init_error = e
		voicevox_local_server = None
	except Exception as e:
		log.error(f"Failed to start bundled VOICEVOX server: {e}", exc_info=True)
		_server_init_error = e
		voicevox_local_server = None
	finally:
		_server_ready.set()


def initialize(indexCallback=None):
	global bgThread, bgQueue, player, onIndexReached, _server_ready, _server_init_error

	_server_ready.clear()
	_server_init_error = None

	if HAS_BUNDLED_VOICEVOX:
		threading.Thread(target=_start_server_bg, daemon=True, name="VSU.ServerInit").start()
	else:
		log.info("Bundled VOICEVOX not available (import failed)")
		_server_ready.set()

	outputDevice = config.conf["audio"]["outputDevice"]
	player = nvwave.WavePlayer(
		channels=1,
		samplesPerSec=SAMPLE_RATE,
		bitsPerSample=16,
		outputDevice=outputDevice
	)
	onIndexReached = indexCallback
	bgQueue = queue.Queue()
	bgThread = BgThread()
	bgThread.start()


def terminate():
	global bgThread, bgQueue, player, onIndexReached, voicevox_local_server
	stop()
	bgQueue.put((None, None, None))
	bgThread.join()
	bgThread = None
	bgQueue = None
	player.close()
	player = None
	onIndexReached = None

	# Stop bundled VOICEVOX server
	if voicevox_local_server:
		try:
			log.info("Stopping bundled VOICEVOX server")
			voicevox_local_server.stop()
		except Exception as e:
			log.error(f"Error stopping VOICEVOX server: {e}", exc_info=True)
		voicevox_local_server = None


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


def _wait_for_server(timeout=180):
	"""サーバーの初期化完了を待つ。失敗時は例外を送出する。"""
	if not _server_ready.wait(timeout=timeout):
		raise RuntimeError("VOICEVOX server did not start within timeout")
	if _server_init_error:
		raise RuntimeError(f"VOICEVOX server failed to start: {_server_init_error}")


def getWave(text, port = 50021):
	global voice
	global rate
	global temporaryPitch
	global inflection
	global volume

	_wait_for_server()

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
	query_data["speedScale"]=max(0.5, rate / 50.0)
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

	_wait_for_server()

	# Retry up to 3 times with increasing delays to handle server startup
	max_retries = 3
	for synth_i in range(max_retries):
		try:
			r = getSession().get(f"http://localhost:{ port }/speakers", timeout=(10, 300))
			if r.status_code == 200:
				lst = r.json()
				break
		except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
			# Server might still be starting up
			if synth_i < max_retries - 1:
				# Exponential backoff: 0.1s, 0.2s, 0.4s, 0.8s, then cap at 1s
				wait_time = min(0.1 * (2 ** min(synth_i, 3)), 1.0)
				log.debug(f"Connection to VOICEVOX failed (attempt {synth_i + 1}/{max_retries}), retrying in {wait_time}s...")
				time.sleep(wait_time)
			else:
				raise
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
