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
from concurrent.futures import ThreadPoolExecutor
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
_speech_gen = 0  # stop()のたびにインクリメント。合成完了後に再生をスキップするために使用
rate = 50
pitch = 50
temporaryPitch = 50
inflection = 50
volume = 100
voice = "1"
voices_cash = None
session = None
voicevox_local_server = None
useGpu = False
_server_ready = threading.Event()
_server_init_error = None
_play_queue = None  # 合成済み音声の再生待ちキュー（パイプライン用）
playThread = None
_synthesis_executor = None  # チャンク並列合成用スレッドプール


class PlayThread(threading.Thread):
	"""合成スレッドとは独立して再生だけを担当するスレッド"""
	def __init__(self):
		super().__init__(
			name=f"{self.__class__.__module__}.{self.__class__.__qualname__}",
			daemon=True)

	def run(self):
		global isSpeaking
		while True:
			item = _play_queue.get()
			try:
				if item is None:
					break
				kind = item[0]
				if kind == 'audio':
					_, wave, gen = item
					if gen == _speech_gen:
						player.feed(wave, onDone=None)
						player.idle()
				elif kind == 'break':
					_, sec, gen = item
					if gen == _speech_gen:
						player.feed(b"\0" * int(SAMPLE_RATE * sec) * 2)
						player.idle()
				elif kind == 'index':
					_, idx = item
					onIndexReached(idx)
					if idx is None:
						isSpeaking = False
			except Exception as e:
				log.error(f"PlayThread error: {e}", exc_info=True)
			finally:
				_play_queue.task_done()


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

def _enqueue_index(idx):
	"""IndexCommand をパイプラインの順序を保ちながら再生キューに積む"""
	_play_queue.put(('index', idx))


def _get_audio_query(text, port=50021):
	global voice
	_wait_for_server()
	query_payload = {"text": text, "speaker": voice}
	for _ in range(10):
		r = getSession().post(f"http://localhost:{port}/audio_query",
			params=query_payload, timeout=(10.0, 3000.0))
		if r.status_code == 200:
			return r.json()
		time.sleep(0.1)
	raise Exception("Make audio query failed.")


def _split_audio_query(query_dict):
	"""accent_phrases を pause_mora 境界（句読点）で分割した query_dict のリストを返す"""
	phrases = query_dict.get('accent_phrases', [])
	if not phrases:
		return [query_dict]
	chunks = []
	current = []
	for phrase in phrases:
		current.append(phrase)
		if phrase.get('pause_mora') is not None:
			chunks.append(current)
			current = []
	if current:
		chunks.append(current)
	if len(chunks) <= 1:
		return [query_dict]
	result = []
	for chunk_phrases in chunks:
		q = dict(query_dict)
		q['accent_phrases'] = chunk_phrases
		result.append(q)
	return result


def _synthesize_from_query(query_dict, port=50021):
	global voice
	synth_payload = {"speaker": voice}
	for _ in range(10):
		r = getSession().post(f"http://localhost:{port}/synthesis",
			params=synth_payload,
			data=json.dumps(query_dict),
			timeout=(1000.0, 30000.0))
		if r.status_code == 200:
			return r.content[44:]
		time.sleep(0.1)
	raise Exception("speak failed.")


def _speak(text):
	# When set not to read symbols, NVDA sends blank string. Directly passing it makes fs2 dll crash.
	if text == "  ":
		return
	# end
	my_gen = _speech_gen
	for elem in preprocess_patterns:
		text = re.sub(elem[0], elem[1], text)
	# end replace

	try:
		query = _get_audio_query(text)
	except Exception as e:
		if my_gen != _speech_gen:
			return  # stop()によるセッション切断が原因なのでエラーではない
		log.error(e)
		raise e
	if my_gen != _speech_gen:
		return

	query["speedScale"] = max(0.5, rate / 50.0)
	query["pitchScale"] = (temporaryPitch - 50) * 0.0015
	query["intonationScale"] = inflection / 50
	query["volumeScale"] = volume / 50
	query["prePhonemeLength"] = 0
	query["postPhonemeLength"] = 0

	chunks = _split_audio_query(query)

	def _do_synth(chunk_query, gen):
		if gen != _speech_gen:
			return None
		return _synthesize_from_query(chunk_query)

	futures = [_synthesis_executor.submit(_do_synth, c, my_gen) for c in chunks]
	for fut in futures:
		if my_gen != _speech_gen:
			return
		try:
			wave = fut.result()
		except Exception as e:
			if my_gen != _speech_gen:
				return
			log.error(e)
			raise e
		if wave is None or my_gen != _speech_gen:
			return
		_play_queue.put(('audio', wave, my_gen))


def _break(item):
	sec = item.time / 1000
	_play_queue.put(('break', sec, _speech_gen))

def speak(speechSequence):
	global isSpeaking
	isSpeaking = True
	for item in speechSequence:
		if isinstance(item, str):
			_execWhenDone(_speak, item, mustBeAsync=True)
		elif isinstance(item, BreakCommand):
			_execWhenDone(_break, item, mustBeAsync=True)
		elif isinstance(item, IndexCommand):
			_execWhenDone(_enqueue_index, item.index, mustBeAsync=True)
		elif isinstance(item, PitchCommand):
			_execWhenDone(_setTemporaryPitch, item.newValue, mustBeAsync=True)
		else:
			pass
	_execWhenDone(_enqueue_index, None, mustBeAsync=True)


def stop():
	global isSpeaking, bgQueue, _speech_gen, session
	_speech_gen += 1
	# 進行中リクエストを旧セッションのクローズで中断しつつ、次回用に新セッションを即作成
	old_session = session
	session = requests.Session()
	if old_session is not None:
		try:
			old_session.close()
		except Exception:
			pass
	# 合成待ちキューを空にする
	try:
		while True:
			bgQueue.get_nowait()
			bgQueue.task_done()
	except queue.Empty:
		pass
	# 再生待ちキューを空にして完了通知を積む
	try:
		while True:
			_play_queue.get_nowait()
			_play_queue.task_done()
	except queue.Empty:
		pass
	_play_queue.put(('index', None))  # synthDoneSpeaking を発火させる
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
		voicevox_local_server = voicevox_server.VoicevoxServer(core_dir, port=50021, use_gpu=useGpu)
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
	global bgThread, bgQueue, player, onIndexReached, _server_ready, _server_init_error, _play_queue, playThread, _synthesis_executor

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
	_play_queue = queue.Queue()
	playThread = PlayThread()
	playThread.start()
	_synthesis_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="VSU.Synth")


def terminate():
	global bgThread, bgQueue, player, onIndexReached, voicevox_local_server, _play_queue, playThread, _synthesis_executor
	stop()
	bgQueue.put((None, None, None))
	bgThread.join()
	bgThread = None
	bgQueue = None
	_play_queue.put(None)  # PlayThread 停止シグナル
	playThread.join()
	playThread = None
	_play_queue = None
	player.close()
	player = None
	onIndexReached = None
	if _synthesis_executor:
		_synthesis_executor.shutdown(wait=False)
		_synthesis_executor = None

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


def getUseGpu():
	return useGpu


def setUseGpu(val):
	global useGpu
	useGpu = val
	if voicevox_local_server:
		voicevox_local_server.set_gpu_mode(val)


def _wait_for_server(timeout=180):
	"""サーバーの初期化完了を待つ。失敗時は例外を送出する。"""
	if not _server_ready.wait(timeout=timeout):
		raise RuntimeError("VOICEVOX server did not start within timeout")
	if _server_init_error:
		raise RuntimeError(f"VOICEVOX server failed to start: {_server_init_error}")



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
