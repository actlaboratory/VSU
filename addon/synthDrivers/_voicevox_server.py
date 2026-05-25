# -*- coding: utf-8 -*-
# Copyright (C) 2026 ACT Laboratory
# Minimal VOICEVOX-compatible HTTP server using voicevox_core

import json
import threading
import time
from http.server import HTTPServer, ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse
from pathlib import Path
from logHandler import log

try:
    from ._voicevox_wrapper import (
        VoicevoxCore,
        VOICEVOX_ACCELERATION_MODE_AUTO,
        VOICEVOX_ACCELERATION_MODE_CPU,
        _check_cuda_runtime,
    )
except ImportError:
    # For testing outside NVDA
    from _voicevox_wrapper import (
        VoicevoxCore,
        VOICEVOX_ACCELERATION_MODE_AUTO,
        VOICEVOX_ACCELERATION_MODE_CPU,
        _check_cuda_runtime,
    )


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
        """Return list of available speakers from scanned voice models"""
        metas = self.voicevox_core._all_metas if hasattr(self.voicevox_core, '_all_metas') else self.voicevox_core.get_metas_json()
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
        try:
            text = query_params.get('text', [''])[0]
            speaker = int(query_params.get('speaker', ['3'])[0])

            if self.voicevox_core is None:
                self.send_response(500)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.end_headers()
                self.wfile.write(json.dumps({"error": "VOICEVOX Core not initialized"}, ensure_ascii=False).encode('utf-8'))
                return

            self.voicevox_core.ensure_model_loaded(speaker)
            audio_query = self.voicevox_core.create_audio_query(text, speaker)

            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(audio_query, ensure_ascii=False).encode('utf-8'))
        except Exception as e:
            log.error(f"audio_query error: {e}", exc_info=True)
            self.send_response(500)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}, ensure_ascii=False).encode('utf-8'))

    def handle_synthesis(self, query_params):
        """Synthesize speech from audio query"""
        try:
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            audio_query = json.loads(post_data.decode('utf-8'))

            speaker = int(query_params.get('speaker', ['3'])[0])

            if self.voicevox_core is None:
                self.send_response(500)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.end_headers()
                self.wfile.write(json.dumps({"error": "VOICEVOX Core not initialized"}, ensure_ascii=False).encode('utf-8'))
                return

            # accent_phrasesはaudio_query時点で生成済み。クライアントのJSONをそのまま使用。
            self.voicevox_core.ensure_model_loaded(speaker)
            wav_data = self.voicevox_core.synthesis(audio_query, speaker)

            self.send_response(200)
            self.send_header('Content-Type', 'audio/wav')
            self.send_header('Content-Length', str(len(wav_data)))
            self.end_headers()
            self.wfile.write(wav_data)

        except Exception as e:
            log.error(f"Synthesis error: {e}", exc_info=True)
            self.send_response(500)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}, ensure_ascii=False).encode('utf-8'))


class VoicevoxServer:
    """Minimal VOICEVOX-compatible HTTP server"""

    def __init__(self, core_dir, port=50021, use_gpu=False):
        """
        Initialize VOICEVOX server

        Args:
            core_dir: Path to voicevox_core directory
            port: HTTP port to listen on (default: 50021)
            use_gpu: GPU/DirectML acceleration (default: False = CPU)
        """
        self.core_dir = Path(core_dir)
        self.port = port
        self.use_gpu = use_gpu
        self.server = None
        self.server_thread = None
        self.voicevox_core = None

    def start(self):
        """Start the HTTP server"""
        try:
            # Initialize VOICEVOX Core
            acceleration_mode = VOICEVOX_ACCELERATION_MODE_AUTO if self.use_gpu else VOICEVOX_ACCELERATION_MODE_CPU
            log.info(f"Initializing VOICEVOX Core (mode={'GPU/DirectML' if self.use_gpu else 'CPU'})...")
            self.voicevox_core = VoicevoxCore(self.core_dir)
            self.voicevox_core.initialize(acceleration_mode=acceleration_mode)

            # VVMをロードせずにスキャンしてインデックスを構築（遅延ロード用）
            vvms_dir = self.core_dir / "models" / "vvms"
            if not vvms_dir.exists() or not any(vvms_dir.glob("*.vvm")):
                raise FileNotFoundError(f"No .vvm files found in: {vvms_dir}")
            self.voicevox_core.scan_models(vvms_dir)
            log.info(f"Voice model index built: {len(self.voicevox_core._style_to_vvm)} styles available")

            # Set core instance in handler
            VoicevoxHandler.voicevox_core = self.voicevox_core

            # Start HTTP server (ThreadingHTTPServer で並列リクエストを処理)
            self.server = ThreadingHTTPServer(('localhost', self.port), VoicevoxHandler)
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

    def set_gpu_mode(self, use_gpu):
        """GPU/DirectML モードを切り替える（サーバー稼働中に呼び出し可能）"""
        if self.use_gpu == use_gpu:
            return
        self.use_gpu = use_gpu
        if self.voicevox_core is None:
            return
        mode = VOICEVOX_ACCELERATION_MODE_AUTO if use_gpu else VOICEVOX_ACCELERATION_MODE_CPU
        log.info(f"Switching to {'GPU/DirectML' if use_gpu else 'CPU'} mode...")
        self.voicevox_core.reinitialize_synthesizer(mode)

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
