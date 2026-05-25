# -*- coding: utf-8 -*-
# Copyright (C) 2026 ACT Laboratory
# VOICEVOX Core ctypes wrapper for NVDA addon

import ctypes
import os
from ctypes import c_char_p, c_void_p, c_int32, c_uint16, c_uint32, c_bool, c_uint8, c_size_t, POINTER, Structure
from pathlib import Path

# Result codes
VOICEVOX_RESULT_OK = 0
VOICEVOX_RESULT_NOT_LOADED_OPENJTALK_DICT_ERROR = 1
VOICEVOX_RESULT_STYLE_NOT_FOUND_ERROR = 6
VOICEVOX_RESULT_MODEL_NOT_FOUND_ERROR = 7
VOICEVOX_RESULT_RUN_MODEL_ERROR = 8

# Acceleration modes
VOICEVOX_ACCELERATION_MODE_AUTO = 0
VOICEVOX_ACCELERATION_MODE_CPU = 1
VOICEVOX_ACCELERATION_MODE_GPU = 2

# Type aliases
VoicevoxResultCode = c_int32
VoicevoxStyleId = c_int32
VoicevoxAccelerationMode = c_int32

# Opaque structure types
class OpenJtalkRc(Structure):
    pass

class VoicevoxOnnxruntime(Structure):
    pass

class VoicevoxSynthesizer(Structure):
    pass

class VoicevoxVoiceModelFile(Structure):
    pass

# Options structures
class VoicevoxLoadOnnxruntimeOptions(Structure):
    _fields_ = [
        ("filename", c_char_p),
    ]

class VoicevoxSynthesizerOptions(Structure):
    _fields_ = [
        ("acceleration_mode", VoicevoxAccelerationMode),
        ("cpu_num_threads", c_uint16),
        ("gpu_device_id", c_uint32),
    ]

class VoicevoxTtsOptions(Structure):
    _fields_ = [
        ("enable_interrogative_upspeak", c_bool),
    ]

class VoicevoxSynthesisOptions(Structure):
    _fields_ = [
        ("enable_interrogative_upspeak", c_bool),
    ]


def _check_cuda_runtime(lib_dir):
    """CUDA ランタイムが利用可能かを安全に確認する（クラッシュしない）"""
    import ctypes
    from logHandler import log
    cuda_dlls = sorted(Path(lib_dir).glob("cudart64_*.dll"))
    if not cuda_dlls:
        return False
    try:
        cudart = ctypes.CDLL(str(cuda_dlls[0]))
        count = ctypes.c_int(0)
        err = cudart.cudaGetDeviceCount(ctypes.byref(count))
        if err == 0 and count.value > 0:
            log.info(f"CUDA runtime check: {count.value} device(s) available")
            return True
        else:
            log.info(f"CUDA runtime check: no usable device (err={err}, count={count.value})")
            return False
    except Exception as e:
        log.warning(f"CUDA runtime check failed: {e}")
        return False


def _apply_pending_dlls(lib_dir):
    """lib_pending/ に保留されているDLLをlib/ へ移動して適用する。DLLロード前に呼ぶこと。"""
    import shutil
    from logHandler import log
    pending_dir = lib_dir.parent / "lib_pending"
    if not pending_dir.exists():
        return
    log.info("Applying pending CUDA DLL updates from lib_pending/...")
    for dll in sorted(pending_dir.glob("*.dll")):
        dest = lib_dir / dll.name
        try:
            shutil.move(str(dll), str(dest))
            log.info(f"Applied pending DLL: {dll.name}")
        except Exception as e:
            log.error(f"Failed to apply pending DLL {dll.name}: {e}")
    try:
        pending_dir.rmdir()
    except Exception:
        pass


class VoicevoxCore:
    """VOICEVOX Core ctypes wrapper"""

    def __init__(self, core_dir):
        """
        Initialize VOICEVOX Core wrapper

        Args:
            core_dir: Path to voicevox_core directory containing DLLs
        """
        import threading
        from logHandler import log

        self.core_dir = Path(core_dir)
        self._model_load_lock = threading.Lock()

        # Load DLLs
        onnxruntime_dll = self.core_dir / "onnxruntime" / "lib" / "voicevox_onnxruntime.dll"
        core_dll = self.core_dir / "c_api" / "lib" / "voicevox_core.dll"

        log.info(f"VOICEVOX Core directory: {self.core_dir}")
        log.info(f"Looking for ONNX Runtime DLL: {onnxruntime_dll}")
        log.info(f"Looking for VOICEVOX Core DLL: {core_dll}")

        # 前回インストールのpending DLLを適用（DLLロード前に実施）
        _apply_pending_dlls(onnxruntime_dll.parent)

        if not onnxruntime_dll.exists():
            raise FileNotFoundError(f"ONNX Runtime DLL not found: {onnxruntime_dll}")
        if not core_dll.exists():
            raise FileNotFoundError(f"VOICEVOX Core DLL not found: {core_dll}")

        log.info("Files found, loading ONNX Runtime DLL...")
        try:
            lib_dir = onnxruntime_dll.parent
            self._dll_dir_cookie = os.add_dll_directory(str(lib_dir))
            cuda_present = any(lib_dir.glob("cudart64_*.dll"))
            if cuda_present:
                # CUDAが存在する場合、CUDA関連DLLをすべて依存順に明示的にプリロードする。
                # onnxruntimeがプロバイダーDLLを動的ロードする際に依存DLLが解決できず
                # クラッシュするのを防ぐ。
                # CUDA_LAUNCH_BLOCKING=1: カーネルを同期実行させ、非同期CUDAエラーを
                # クラッシュではなくORTのエラーコードとして返させる。
                os.environ.setdefault('CUDA_LAUNCH_BLOCKING', '1')
                log.info("CUDA_LAUNCH_BLOCKING=1 set for synchronous CUDA execution")
                self._cuda_preloaded_libs = []
                cuda_load_order = [
                    *sorted(lib_dir.glob("cudart64_*.dll")),
                    lib_dir / "zlibwapi.dll",
                    *sorted(lib_dir.glob("cufft64_*.dll")),
                    *sorted(lib_dir.glob("curand64_*.dll")),
                    *sorted(lib_dir.glob("cublasLt64_*.dll")),
                    *sorted(lib_dir.glob("cublas64_*.dll")),
                    *sorted(lib_dir.glob("cudnn_ops_infer64_*.dll")),
                    *sorted(lib_dir.glob("cudnn_cnn_infer64_*.dll")),
                    *sorted(lib_dir.glob("cudnn_adv_infer64_*.dll")),
                    *sorted(lib_dir.glob("cudnn64_*.dll")),
                    lib_dir / "voicevox_onnxruntime_providers_shared.dll",
                    lib_dir / "voicevox_onnxruntime_providers_cuda.dll",
                ]
                for dll_path in cuda_load_order:
                    if dll_path.exists():
                        try:
                            lib = ctypes.CDLL(str(dll_path))
                            self._cuda_preloaded_libs.append(lib)
                            log.info(f"Pre-loaded CUDA DLL: {dll_path.name}")
                        except Exception as e:
                            log.warning(f"Failed to pre-load CUDA DLL {dll_path.name}: {e}")
            else:
                directml_dll = lib_dir / "DirectML.dll"
                if directml_dll.exists():
                    self._directml_lib = ctypes.CDLL(str(directml_dll))
                    log.info(f"Pre-loaded bundled DirectML.dll from {directml_dll}")
            # Load ONNX Runtime
            self._onnxruntime_lib = ctypes.CDLL(str(onnxruntime_dll))
            log.info("ONNX Runtime DLL loaded successfully")
        except OSError as e:
            if e.winerror == 193:  # %1 is not a valid Win32 application
                import platform
                python_arch = platform.architecture()[0]
                error_msg = (
                    f"DLLのアーキテクチャが一致しません。"
                    f"VOICEVOX Coreは64bitのみをサポートしていますが、"
                    f"現在のPythonは{python_arch}です。"
                    f"64bit版のNVDAを使用するか、外部のVOICEVOXアプリケーションを起動してください。"
                )
                log.error(error_msg)
                raise RuntimeError(error_msg) from e
            else:
                log.error(f"Failed to load ONNX Runtime DLL: {e}", exc_info=True)
                raise
        except Exception as e:
            log.error(f"Failed to load ONNX Runtime DLL: {e}", exc_info=True)
            raise

        log.info("Loading VOICEVOX Core DLL...")
        try:
            # Load VOICEVOX Core
            self._lib = ctypes.CDLL(str(core_dll))
            log.info("VOICEVOX Core DLL loaded successfully")
        except Exception as e:
            log.error(f"Failed to load VOICEVOX Core DLL: {e}", exc_info=True)
            raise

        # Define function signatures
        log.info("Defining function signatures...")
        self._define_functions()

        # Initialize ONNX Runtime
        self.onnxruntime = None
        self.open_jtalk = None
        self.synthesizer = None
        self._loaded_model_paths = []
        log.info("VoicevoxCore wrapper initialized")

    def _define_functions(self):
        """Define ctypes function signatures"""
        lib = self._lib

        # voicevox_onnxruntime_load_once
        lib.voicevox_onnxruntime_load_once.argtypes = [VoicevoxLoadOnnxruntimeOptions, POINTER(POINTER(VoicevoxOnnxruntime))]
        lib.voicevox_onnxruntime_load_once.restype = VoicevoxResultCode

        # voicevox_open_jtalk_rc_new
        lib.voicevox_open_jtalk_rc_new.argtypes = [c_char_p, POINTER(POINTER(OpenJtalkRc))]
        lib.voicevox_open_jtalk_rc_new.restype = VoicevoxResultCode

        # voicevox_open_jtalk_rc_delete
        lib.voicevox_open_jtalk_rc_delete.argtypes = [POINTER(OpenJtalkRc)]
        lib.voicevox_open_jtalk_rc_delete.restype = None

        # voicevox_synthesizer_new
        lib.voicevox_synthesizer_new.argtypes = [
            POINTER(VoicevoxOnnxruntime),
            POINTER(OpenJtalkRc),
            VoicevoxSynthesizerOptions,
            POINTER(POINTER(VoicevoxSynthesizer))
        ]
        lib.voicevox_synthesizer_new.restype = VoicevoxResultCode

        # voicevox_synthesizer_delete
        lib.voicevox_synthesizer_delete.argtypes = [POINTER(VoicevoxSynthesizer)]
        lib.voicevox_synthesizer_delete.restype = None

        # voicevox_voice_model_file_open
        lib.voicevox_voice_model_file_open.argtypes = [c_char_p, POINTER(POINTER(VoicevoxVoiceModelFile))]
        lib.voicevox_voice_model_file_open.restype = VoicevoxResultCode

        # voicevox_voice_model_file_delete
        lib.voicevox_voice_model_file_delete.argtypes = [POINTER(VoicevoxVoiceModelFile)]
        lib.voicevox_voice_model_file_delete.restype = None

        # voicevox_synthesizer_load_voice_model
        lib.voicevox_synthesizer_load_voice_model.argtypes = [
            POINTER(VoicevoxSynthesizer),
            POINTER(VoicevoxVoiceModelFile)
        ]
        lib.voicevox_synthesizer_load_voice_model.restype = VoicevoxResultCode

        # voicevox_synthesizer_tts
        lib.voicevox_synthesizer_tts.argtypes = [
            POINTER(VoicevoxSynthesizer),
            c_char_p,
            VoicevoxStyleId,
            VoicevoxTtsOptions,
            POINTER(c_size_t),
            POINTER(POINTER(c_uint8))
        ]
        lib.voicevox_synthesizer_tts.restype = VoicevoxResultCode

        # voicevox_synthesizer_create_audio_query
        lib.voicevox_synthesizer_create_audio_query.argtypes = [
            POINTER(VoicevoxSynthesizer),
            c_char_p,
            VoicevoxStyleId,
            POINTER(c_void_p),
        ]
        lib.voicevox_synthesizer_create_audio_query.restype = VoicevoxResultCode

        # voicevox_synthesizer_synthesis
        lib.voicevox_synthesizer_synthesis.argtypes = [
            POINTER(VoicevoxSynthesizer),
            c_char_p,
            VoicevoxStyleId,
            VoicevoxSynthesisOptions,
            POINTER(c_size_t),
            POINTER(POINTER(c_uint8)),
        ]
        lib.voicevox_synthesizer_synthesis.restype = VoicevoxResultCode

        # voicevox_synthesizer_create_metas_json
        lib.voicevox_synthesizer_create_metas_json.argtypes = [POINTER(VoicevoxSynthesizer)]
        lib.voicevox_synthesizer_create_metas_json.restype = c_void_p

        # voicevox_voice_model_file_create_metas_json
        lib.voicevox_voice_model_file_create_metas_json.argtypes = [POINTER(VoicevoxVoiceModelFile)]
        lib.voicevox_voice_model_file_create_metas_json.restype = c_void_p

        # voicevox_synthesizer_is_loaded_voice_model
        lib.voicevox_synthesizer_is_loaded_voice_model.argtypes = [
            POINTER(VoicevoxSynthesizer),
            c_char_p,
        ]
        lib.voicevox_synthesizer_is_loaded_voice_model.restype = c_bool

        # voicevox_json_free
        lib.voicevox_json_free.argtypes = [c_void_p]
        lib.voicevox_json_free.restype = None

        # voicevox_wav_free
        lib.voicevox_wav_free.argtypes = [POINTER(c_uint8)]
        lib.voicevox_wav_free.restype = None

        # voicevox_error_result_to_message
        lib.voicevox_error_result_to_message.argtypes = [VoicevoxResultCode]
        lib.voicevox_error_result_to_message.restype = c_char_p

    def initialize(self, acceleration_mode=VOICEVOX_ACCELERATION_MODE_AUTO):
        """Initialize VOICEVOX Core"""
        # Load ONNX Runtime
        onnxruntime_dll = self.core_dir / "onnxruntime" / "lib" / "voicevox_onnxruntime.dll"
        onnxruntime = POINTER(VoicevoxOnnxruntime)()
        load_opts = VoicevoxLoadOnnxruntimeOptions(filename=str(onnxruntime_dll).encode('utf-8'))
        result = self._lib.voicevox_onnxruntime_load_once(
            load_opts,
            ctypes.byref(onnxruntime)
        )
        if result != VOICEVOX_RESULT_OK:
            raise RuntimeError(f"Failed to load ONNX Runtime: {self._get_error_message(result)}")
        self.onnxruntime = onnxruntime

        # Initialize Open JTalk
        dict_dir = self.core_dir / "dict" / "open_jtalk_dic_utf_8-1.11"
        open_jtalk = POINTER(OpenJtalkRc)()
        result = self._lib.voicevox_open_jtalk_rc_new(
            str(dict_dir).encode('utf-8'),
            ctypes.byref(open_jtalk)
        )
        if result != VOICEVOX_RESULT_OK:
            raise RuntimeError(f"Failed to initialize Open JTalk: {self._get_error_message(result)}")
        self.open_jtalk = open_jtalk

        # Create synthesizer
        options = VoicevoxSynthesizerOptions(
            acceleration_mode=acceleration_mode,
            cpu_num_threads=0,
            gpu_device_id=0,
        )
        synthesizer = POINTER(VoicevoxSynthesizer)()
        result = self._lib.voicevox_synthesizer_new(
            self.onnxruntime,
            self.open_jtalk,
            options,
            ctypes.byref(synthesizer)
        )
        if result != VOICEVOX_RESULT_OK:
            raise RuntimeError(f"Failed to create synthesizer: {self._get_error_message(result)}")
        self.synthesizer = synthesizer

    def scan_models(self, vvms_dir):
        """VVMファイルをスキャンしてstyle_id→vvmパスのインデックスを構築する。
        シンセサイザーへのロードは行わないため高速。"""
        import json
        from logHandler import log
        self._style_to_vvm = {}
        self._all_metas = []
        for vvm_path in sorted(Path(vvms_dir).glob("*.vvm")):
            try:
                metas = self._read_vvm_metas(vvm_path)
                for speaker in metas:
                    for style in speaker["styles"]:
                        self._style_to_vvm[int(style["id"])] = vvm_path
                self._all_metas.extend(metas)
                log.info(f"Scanned voice model: {vvm_path.name}")
            except Exception as e:
                log.error(f"Failed to scan {vvm_path.name}: {e}")

    def _read_vvm_metas(self, vvm_path):
        """VVMファイルを開いてメタ情報だけ読んで閉じる（シンセサイザーにはロードしない）"""
        import json
        model = POINTER(VoicevoxVoiceModelFile)()
        result = self._lib.voicevox_voice_model_file_open(
            str(vvm_path).encode('utf-8'), ctypes.byref(model))
        if result != VOICEVOX_RESULT_OK:
            raise RuntimeError(f"Failed to open voice model: {self._get_error_message(result)}")
        ptr = self._lib.voicevox_voice_model_file_create_metas_json(model)
        raw = ctypes.cast(ptr, c_char_p).value
        metas = json.loads(raw.decode('utf-8'))
        self._lib.voicevox_json_free(ptr)
        self._lib.voicevox_voice_model_file_delete(model)
        return metas

    def ensure_model_loaded(self, style_id):
        """style_idに対応するVVMがロードされていなければロードする"""
        from logHandler import log
        if not hasattr(self, '_style_to_vvm'):
            return
        with self._model_load_lock:
            vvm_path = self._style_to_vvm.get(int(style_id))
            if vvm_path is None:
                raise RuntimeError(f"No voice model found for style_id: {style_id}")
            if str(vvm_path) not in self._loaded_model_paths:
                log.info(f"Lazy-loading voice model for style_id={style_id}: {vvm_path.name}")
                self.load_model(vvm_path)

    def load_model(self, model_path):
        """Load a voice model file"""
        from logHandler import log
        model = POINTER(VoicevoxVoiceModelFile)()
        result = self._lib.voicevox_voice_model_file_open(
            str(model_path).encode('utf-8'),
            ctypes.byref(model)
        )
        if result != VOICEVOX_RESULT_OK:
            raise RuntimeError(f"Failed to open voice model: {self._get_error_message(result)}")

        result = self._lib.voicevox_synthesizer_load_voice_model(
            self.synthesizer,
            model
        )
        if result != VOICEVOX_RESULT_OK:
            self._lib.voicevox_voice_model_file_delete(model)
            raise RuntimeError(f"Failed to load voice model: {self._get_error_message(result)}")

        self._lib.voicevox_voice_model_file_delete(model)
        self._loaded_model_paths.append(str(model_path))
        log.info(f"Loaded voice model: {Path(model_path).name}")

    def reinitialize_synthesizer(self, acceleration_mode):
        """シンセサイザーを別のアクセラレーションモードで再初期化し、モデルを再ロードする"""
        from logHandler import log
        if self.synthesizer:
            self._lib.voicevox_synthesizer_delete(self.synthesizer)
            self.synthesizer = None

        options = VoicevoxSynthesizerOptions(
            acceleration_mode=acceleration_mode,
            cpu_num_threads=0,
            gpu_device_id=0,
        )
        synthesizer = POINTER(VoicevoxSynthesizer)()
        result = self._lib.voicevox_synthesizer_new(
            self.onnxruntime,
            self.open_jtalk,
            options,
            ctypes.byref(synthesizer)
        )
        if result != VOICEVOX_RESULT_OK:
            raise RuntimeError(f"Failed to create synthesizer: {self._get_error_message(result)}")
        self.synthesizer = synthesizer

        # 以前ロードされていたモデルを再ロード
        saved_paths = list(self._loaded_model_paths)
        self._loaded_model_paths = []
        for path in saved_paths:
            self.load_model(path)
        log.info(f"Synthesizer reinitialized with acceleration_mode={acceleration_mode}")

    def tts(self, text, style_id):
        """
        Convert text to speech

        Args:
            text: UTF-8 Japanese text
            style_id: Voice style ID

        Returns:
            bytes: WAV audio data
        """
        options = VoicevoxTtsOptions(enable_interrogative_upspeak=True)
        wav_length = c_size_t()
        wav_data = POINTER(c_uint8)()

        result = self._lib.voicevox_synthesizer_tts(
            self.synthesizer,
            text.encode('utf-8'),
            style_id,
            options,
            ctypes.byref(wav_length),
            ctypes.byref(wav_data)
        )

        if result != VOICEVOX_RESULT_OK:
            raise RuntimeError(f"TTS failed: {self._get_error_message(result)}")

        # Copy WAV data to Python bytes
        audio_bytes = bytes(ctypes.cast(wav_data, POINTER(c_uint8 * wav_length.value)).contents)

        # Free WAV data
        self._lib.voicevox_wav_free(wav_data)

        return audio_bytes

    def _get_error_message(self, result_code):
        """Get error message for result code"""
        msg = self._lib.voicevox_error_result_to_message(result_code)
        if msg:
            return msg.decode('utf-8')
        return f"Unknown error (code: {result_code})"

    def create_audio_query(self, text, style_id):
        """テキストからaudio query JSONを生成する"""
        import json
        ptr = c_void_p()
        result = self._lib.voicevox_synthesizer_create_audio_query(
            self.synthesizer,
            text.encode('utf-8'),
            style_id,
            ctypes.byref(ptr)
        )
        if result != VOICEVOX_RESULT_OK:
            raise RuntimeError(f"Failed to create audio query: {self._get_error_message(result)}")
        raw = ctypes.cast(ptr, c_char_p).value
        data = json.loads(raw.decode('utf-8'))
        self._lib.voicevox_json_free(ptr)
        return data

    def synthesis(self, audio_query_dict, style_id):
        """audio query JSON（dict）から音声合成する"""
        import json
        options = VoicevoxSynthesisOptions(enable_interrogative_upspeak=True)
        wav_length = c_size_t()
        wav_data = POINTER(c_uint8)()
        json_bytes = json.dumps(audio_query_dict, ensure_ascii=False).encode('utf-8')
        result = self._lib.voicevox_synthesizer_synthesis(
            self.synthesizer,
            json_bytes,
            style_id,
            options,
            ctypes.byref(wav_length),
            ctypes.byref(wav_data)
        )
        if result != VOICEVOX_RESULT_OK:
            raise RuntimeError(f"Synthesis failed: {self._get_error_message(result)}")
        audio_bytes = bytes(ctypes.cast(wav_data, POINTER(c_uint8 * wav_length.value)).contents)
        self._lib.voicevox_wav_free(wav_data)
        return audio_bytes

    def get_metas_json(self):
        """Get loaded voice model metadata as JSON string"""
        import json
        ptr = self._lib.voicevox_synthesizer_create_metas_json(self.synthesizer)
        if not ptr:
            raise RuntimeError("Failed to get metas: null returned")
        raw = ctypes.cast(ptr, c_char_p).value
        data = json.loads(raw.decode('utf-8'))
        self._lib.voicevox_json_free(ptr)
        return data

    def cleanup(self):
        """Clean up resources"""
        if self.synthesizer:
            self._lib.voicevox_synthesizer_delete(self.synthesizer)
            self.synthesizer = None
        if self.open_jtalk:
            self._lib.voicevox_open_jtalk_rc_delete(self.open_jtalk)
            self.open_jtalk = None
        # ONNX Runtime is not explicitly freed
