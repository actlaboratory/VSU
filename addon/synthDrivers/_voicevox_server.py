# -*- coding: utf-8 -*-
# Copyright (C) 2026 ACT Laboratory
# Minimal VOICEVOX-compatible HTTP server using voicevox_core

import json
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse
from pathlib import Path
from logHandler import log

try:
    from ._voicevox_wrapper import VoicevoxCore, VOICEVOX_ACCELERATION_MODE_CPU
except ImportError:
    # For testing outside NVDA
    from _voicevox_wrapper import VoicevoxCore, VOICEVOX_ACCELERATION_MODE_CPU


class VoicevoxHandler(BaseHTTPRequestHandler):
    """HTTP request handler for VOICEVOX API"""

    # Class variable to hold the VoicevoxCore instance
    voicevox_core = None

    def log_message(self, format, *args):
        """Override to use NVDA logging"""
        log.debug(f"VOICEVOX Server: {format % args}")

    def do_GET(self):
        """Handle GET requests"""
        parsed_path = urlparse(self.path)

        if parsed_path.path == "/speakers":
            self.handle_speakers()
        else:
            self.send_error(404)

    def do_POST(self):
        """Handle POST requests"""
        parsed_path = urlparse(self.path)
        query_params = parse_qs(parsed_path.query)

        if parsed_path.path == "/audio_query":
            self.handle_audio_query(query_params)
        elif parsed_path.path == "/synthesis":
            self.handle_synthesis(query_params)
        else:
            self.send_error(404)

    def handle_speakers(self):
        """Return list of available speakers from loaded voice models"""
        metas = self.voicevox_core.get_metas_json()
        speakers = [
            {
                "name": m["name"],
                "speaker_uuid": m["speaker_uuid"],
                "styles": [{"name": s["name"], "id": s["id"]} for s in m["styles"]],
                "version": m.get("version", ""),
            }
            for m in metas
        ]
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(speakers, ensure_ascii=False).encode('utf-8'))

    def handle_audio_query(self, query_params):
        """Create audio query from text"""
        # For simplicity, we just create a minimal audio query
        # The actual synthesis will be done in the synthesis endpoint

        text = query_params.get('text', [''])[0]
        speaker = query_params.get('speaker', ['3'])[0]

        # Minimal audio query (matches VOICEVOX format but simplified)
        audio_query = {
            "accent_phrases": [],
            "speedScale": 1.0,
            "pitchScale": 0.0,
            "intonationScale": 1.0,
            "volumeScale": 1.0,
            "prePhonemeLength": 0.1,
            "postPhonemeLength": 0.1,
            "outputSamplingRate": 24000,
            "outputStereo": False,
            "kana": text  # Store original text for synthesis
        }

        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(audio_query, ensure_ascii=False).encode('utf-8'))

    def handle_synthesis(self, query_params):
        """Synthesize speech from audio query"""
        try:
            # Read audio query from request body
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            audio_query = json.loads(post_data.decode('utf-8'))

            speaker = int(query_params.get('speaker', ['3'])[0])
            text = audio_query.get('kana', '')

            if not text:
                self.send_error(400, "No text provided")
                return

            if self.voicevox_core is None:
                self.send_error(500, "VOICEVOX Core not initialized")
                return

            # audio queryを生成してパラメータを適用してから合成
            query = self.voicevox_core.create_audio_query(text, speaker)
            query["speedScale"] = audio_query.get('speedScale', 1.0)
            query["pitchScale"] = audio_query.get('pitchScale', 0.0)
            query["intonationScale"] = audio_query.get('intonationScale', 1.0)
            query["volumeScale"] = audio_query.get('volumeScale', 1.0)
            query["prePhonemeLength"] = audio_query.get('prePhonemeLength', 0.0)
            query["postPhonemeLength"] = audio_query.get('postPhonemeLength', 0.0)

            wav_data = self.voicevox_core.synthesis(query, speaker)

            self.send_response(200)
            self.send_header('Content-Type', 'audio/wav')
            self.send_header('Content-Length', str(len(wav_data)))
            self.end_headers()
            self.wfile.write(wav_data)

        except Exception as e:
            log.error(f"Synthesis error: {e}", exc_info=True)
            self.send_error(500, str(e))


class VoicevoxServer:
    """Minimal VOICEVOX-compatible HTTP server"""

    def __init__(self, core_dir, port=50021):
        """
        Initialize VOICEVOX server

        Args:
            core_dir: Path to voicevox_core directory
            port: HTTP port to listen on (default: 50021)
        """
        self.core_dir = Path(core_dir)
        self.port = port
        self.server = None
        self.server_thread = None
        self.voicevox_core = None

    def start(self):
        """Start the HTTP server"""
        try:
            # Initialize VOICEVOX Core
            log.info("Initializing VOICEVOX Core...")
            self.voicevox_core = VoicevoxCore(self.core_dir)
            self.voicevox_core.initialize()

            # models/vvms/ にある全VVMファイルを読み込む
            vvms_dir = self.core_dir / "models" / "vvms"
            vvm_files = sorted(vvms_dir.glob("*.vvm")) if vvms_dir.exists() else []
            if not vvm_files:
                raise FileNotFoundError(f"No .vvm files found in: {vvms_dir}")

            for model_path in vvm_files:
                log.info(f"Loading voice model: {model_path}")
                self.voicevox_core.load_model(model_path)

            # GPU推論の動作確認。失敗時はCPUモードで再初期化
            try:
                metas = self.voicevox_core.get_metas_json()
                test_style_id = metas[0]["styles"][0]["id"] if metas else 3
                self.voicevox_core.tts("テスト", test_style_id)
                log.info("GPU (AUTO) synthesis test passed")
            except RuntimeError as e:
                log.warning(f"GPU synthesis test failed: {e}. Falling back to CPU mode.")
                self.voicevox_core.reinitialize_synthesizer(VOICEVOX_ACCELERATION_MODE_CPU)
                log.info("Reinitialized with CPU mode")

            # Set core instance in handler
            VoicevoxHandler.voicevox_core = self.voicevox_core

            # Start HTTP server
            self.server = HTTPServer(('localhost', self.port), VoicevoxHandler)
            self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self.server_thread.start()

            log.info(f"VOICEVOX server started on port {self.port}")

            # Wait for server to be ready (with timeout)
            self._wait_for_server_ready(timeout=10.0)

        except Exception as e:
            log.error(f"Failed to start VOICEVOX server: {e}", exc_info=True)
            self.stop()
            raise

    def _wait_for_server_ready(self, timeout=10.0):
        """Wait for server to be ready to accept connections"""
        import socket
        start_time = time.time()
        retry_count = 0

        while time.time() - start_time < timeout:
            try:
                # Try to connect to the server
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                    sock.settimeout(1.0)
                    sock.connect(('localhost', self.port))
                log.info(f"VOICEVOX server is ready (took {retry_count} retries)")
                return True
            except (socket.error, ConnectionRefusedError):
                retry_count += 1
                time.sleep(0.1)  # Wait 100ms before retry

        raise TimeoutError(f"VOICEVOX server did not become ready within {timeout} seconds")

    def stop(self):
        """Stop the HTTP server"""
        if self.server:
            log.info("Stopping VOICEVOX server...")
            self.server.shutdown()
            self.server = None

        if self.voicevox_core:
            self.voicevox_core.cleanup()
            self.voicevox_core = None

        VoicevoxHandler.voicevox_core = None

    def is_running(self):
        """Check if server is running"""
        return self.server is not None and self.server_thread is not None and self.server_thread.is_alive()
