# Copyright (C) 2021 Yukio Nozawa, ACT Laboratory
# Copyright (c)2022 Hiroki Fujii,ACT laboratory All rights reserved.
# Copyright (C) 2023-2026 yamahubuki, ACT Laboratory

import json
import os
import re
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
from synthDrivers import _sonic

try:
	from . import _voicevox_wrapper as _vw
except ImportError:
	_vw = None


SAMPLE_RATE = 24000
FRAME_RATE = 93.75  # VOICEVOX の音声特徴量のフレームレート（フレーム数/秒）
# ストリーミング合成の区切り（合成前の等速での秒数）。
# sonic で速くすると 1 区間の再生時間が短くなるため、区間を長くすると次の区間の生成が間に合わず途切れる。
# そのため 2 区間目以降も短くしている
STREAMING_FIRST_SEGMENT_SEC = 0.3
STREAMING_SEGMENT_SEC = 0.3
MAX_SONIC_SPEED = 4.0  # 速さ100のときの sonic による速度倍率

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
_voicevox_core = None  # VoicevoxCore インスタンス
useGpu = False
_core_ready = threading.Event()
_core_init_error = None
_play_queue = None  # 合成済み音声の再生待ちキュー（パイプライン用）
playThread = None
_synthesis_executor = None  # チャンク並列合成用スレッドプール


def _speed_scales():
	"""現在の速さ設定から (VOICEVOX の speedScale, sonic の速度倍率) を返す。
	VOICEVOX 側で速くすると聞き取りにくくなるため、等速より速い分は sonic で処理する。
	等速より遅い場合だけ VOICEVOX の speedScale を使う。
	50 より上は指数的に変化させ、50で等速、75で2倍速、100で4倍速とする。"""
	if rate > 50:
		return 1.0, MAX_SONIC_SPEED ** ((rate - 50) / 50.0)
	return max(0.5, rate / 50.0), 1.0


class _SpeedChanger:
	"""sonic で PCM の再生速度を変える。速度倍率が 1.0 以下のときは素通しする。
	1 発話の音声を連続したストリームとして流し、区間の継ぎ目で音が歪まないようにする。"""

	def __init__(self, speed):
		self._stream = None
		if speed > 1.0:
			_sonic.initialize()
			self._stream = _sonic.SonicStream(SAMPLE_RATE, 1)
			self._stream.speed = speed

	def process(self, pcm, final):
		"""16bit モノラル PCM を書き込み、変換済みの PCM を返す。final=True で残りを吐き出す。"""
		if self._stream is None:
			return pcm
		if pcm:
			self._stream.writeShort(pcm, len(pcm) // 2)
		if final:
			self._stream.flush()
		return bytes(self._stream.readShort())


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
					# idle=False のときは後続の音声が続くので、途切れないよう idle() しない
					_, wave, gen, idle = item
					if gen == _speech_gen:
						if wave:
							player.feed(wave, onDone=None)
						if idle:
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


def _get_audio_query(text):
	global voice
	_wait_for_core()
	style_id = int(voice)
	_voicevox_core.ensure_model_loaded(style_id)
	return _voicevox_core.create_audio_query(text, style_id)


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


def _synthesize_from_query(query_dict):
	global voice
	wav = _voicevox_core.synthesis(query_dict, int(voice))
	return wav[44:]  # WAVヘッダ44バイトをスキップ


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
			return  # stop()による中断が原因なのでエラーではない
		log.error(e)
		raise e
	if my_gen != _speech_gen:
		return

	speedScale, sonicSpeed = _speed_scales()
	query["speedScale"] = speedScale
	query["pitchScale"] = (temporaryPitch - 50) * 0.0015
	query["intonationScale"] = inflection / 50
	query["volumeScale"] = volume / 50
	query["prePhonemeLength"] = 0
	query["postPhonemeLength"] = 0

	style_id = int(voice)
	if _voicevox_core.supports_streaming(style_id):
		try:
			feature = _voicevox_core.create_audio_feature(query, style_id)
		except Exception as e:
			if my_gen != _speech_gen:
				return
			log.error(e)
			raise e
		_speak_streaming(feature, my_gen, _SpeedChanger(sonicSpeed))
	else:
		_speak_chunked(query, my_gen, _SpeedChanger(sonicSpeed))


def _split_segments(total, first, step):
	"""総フレーム数 total を、先頭 first フレーム、以降 step フレームずつの [start, end) に区切る"""
	bounds = []
	start = 0
	end = min(first, total)
	while start < total:
		bounds.append((start, end))
		start = end
		end = min(start + step, total)
	return bounds


def _speak_streaming(feature, my_gen, changer):
	"""ストリーミング音声合成。区間ごとに先頭から順にレンダリングし、できたものから再生する。
	コア内部で推論は直列化されるため、並列に投げても速くならず、先頭区間が後回しになることがある。"""
	segments = _split_segments(
		len(feature),
		max(1, round(STREAMING_FIRST_SEGMENT_SEC * FRAME_RATE)),
		max(1, round(STREAMING_SEGMENT_SEC * FRAME_RATE)),
	)
	try:
		for i, (start, end) in enumerate(segments):
			if my_gen != _speech_gen:
				return
			try:
				pcm = feature.render(start, end)
			except Exception as e:
				if my_gen != _speech_gen:
					return
				log.error(e)
				raise e
			if my_gen != _speech_gen:
				return
			last = i == len(segments) - 1
			_play_queue.put(('audio', changer.process(pcm, last), my_gen, last))
	finally:
		feature.close()


def _speak_chunked(query, my_gen, changer):
	"""旧形式VVM向け。句読点で分割したチャンクを並列合成して順に再生する"""
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
		# チャンクは句読点で区切られているので、チャンクごとに flush しても歪みにくい
		_play_queue.put(('audio', changer.process(wave, True), my_gen, True))


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
	global isSpeaking, bgQueue, _speech_gen
	_speech_gen += 1
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


def _init_core_bg():
	"""バックグラウンドで VoicevoxCore を初期化する"""
	global _voicevox_core, _core_init_error
	try:
		if _vw is None:
			log.warning("VOICEVOX wrapper not available")
			return
		addon_dir = Path(__file__).parent.parent
		core_dir = addon_dir / "voicevox_core"
		if not core_dir.exists():
			log.warning(f"VOICEVOX core directory not found: {core_dir}")
			return
		acceleration_mode = _vw.VOICEVOX_ACCELERATION_MODE_AUTO if useGpu else _vw.VOICEVOX_ACCELERATION_MODE_CPU
		core = _vw.VoicevoxCore(core_dir)
		core.initialize(acceleration_mode=acceleration_mode)
		vvms_dir = core_dir / "models" / "vvms"
		if not vvms_dir.exists() or not any(vvms_dir.glob("*.vvm")):
			raise FileNotFoundError(f"No .vvm files found in: {vvms_dir}")
		core.scan_models(vvms_dir)
		log.info(f"VOICEVOX Core initialized: {len(core._style_to_vvm)} styles available")
		_voicevox_core = core
	except RuntimeError as e:
		log.warning(f"VOICEVOX Core cannot be used: {e}")
		_core_init_error = e
	except Exception as e:
		log.error(f"Failed to initialize VOICEVOX Core: {e}", exc_info=True)
		_core_init_error = e
	finally:
		_core_ready.set()


def initialize(indexCallback=None):
	global bgThread, bgQueue, player, onIndexReached, _core_ready, _core_init_error, _play_queue, playThread, _synthesis_executor

	_core_ready.clear()
	_core_init_error = None

	threading.Thread(target=_init_core_bg, daemon=True, name="VSU.CoreInit").start()

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
	global bgThread, bgQueue, player, onIndexReached, _voicevox_core, _play_queue, playThread, _synthesis_executor
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
	if _voicevox_core:
		try:
			_voicevox_core.cleanup()
		except Exception as e:
			log.error(f"Error cleaning up VOICEVOX Core: {e}", exc_info=True)
		_voicevox_core = None


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
	if _voicevox_core:
		mode = _vw.VOICEVOX_ACCELERATION_MODE_AUTO if val else _vw.VOICEVOX_ACCELERATION_MODE_CPU
		_voicevox_core.reinitialize_synthesizer(mode)


def _wait_for_core(timeout=180):
	"""コアの初期化完了を待つ。失敗時は例外を送出する。"""
	if not _core_ready.wait(timeout=timeout):
		raise RuntimeError("VOICEVOX Core did not initialize within timeout")
	if _core_init_error:
		raise RuntimeError(f"VOICEVOX Core failed to initialize: {_core_init_error}")


def get_availableVoices(useCache=True):
	global voices_cash
	if useCache and voices_cash:
		return voices_cash

	_wait_for_core()

	lst = _voicevox_core._all_metas if hasattr(_voicevox_core, '_all_metas') else _voicevox_core.get_metas_json()
	ret = OrderedDict()
	for speaker in lst:
		for style in speaker["styles"]:
			ret[str(style["id"])] = VoiceInfo(str(style["id"]), speaker["name"] + "(" + style["name"] + ")", "ja")
	voices_cash = ret
	return ret
