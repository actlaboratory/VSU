# -*- coding: utf-8 -*-
# Copyright (C) 2026 ACT Laboratory

import os
import threading
import urllib.request
import zipfile
import tarfile
import shutil
import stat
from pathlib import Path

import wx
import gui
from logHandler import log
from .dialogs import DownloadProgressDialog

CUDA_ZIP_URL = "https://github.com/VOICEVOX/voicevox_additional_libraries/releases/download/0.2.1/CUDA-windows-x64.zip"
ONNX_CUDA_URL = "https://github.com/VOICEVOX/onnxruntime-builder/releases/download/voicevox_onnxruntime-1.17.3/voicevox_onnxruntime-win-x64-cuda-1.17.3.tgz"
ZLIB_URL = "http://www.winimage.com/zLibDll/zlib123dllx64.zip"


def _get_onnx_lib_dir():
    addon_dir = Path(__file__).parent.parent.parent
    return addon_dir / "voicevox_core" / "onnxruntime" / "lib"


def _get_onnx_pending_dir():
    return _get_onnx_lib_dir().parent / "lib_pending"


def _rmtree(path):
    def on_error(func, p, exc_info):
        try:
            os.chmod(p, stat.S_IWRITE)
            func(p)
        except Exception:
            pass
    try:
        shutil.rmtree(path, onerror=on_error)
    except Exception:
        pass


def start_cuda_install():
    msg = (
        "CUDA加速ライブラリをダウンロードしてインストールします。\n\n"
        "ダウンロードサイズ: 約1.2GB（CUDAランタイム・onnxruntime・zlibwapi）\n\n"
        "インストール後にNVDAを再起動してください。\n"
        "続行しますか？"
    )
    if gui.messageBox(msg, "CUDA加速のインストール", wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION) != wx.YES:
        return

    dlg = DownloadProgressDialog(_("CUDA加速をインストール中"))
    dlg.Show()

    def do_install():
        temp_dir = Path(os.environ.get("TEMP", ".")) / "vsu_cuda_install"
        temp_dir.mkdir(parents=True, exist_ok=True)
        try:
            onnx_lib_dir = _get_onnx_pending_dir()
            _rmtree(onnx_lib_dir)
            onnx_lib_dir.mkdir(parents=True, exist_ok=True)

            # --- 1. CUDA ランタイム DLL ---
            cuda_zip = temp_dir / "CUDA-windows-x64.zip"

            def cuda_hook(count, block, total):
                if dlg.cancelled:
                    raise InterruptedError
                if total > 0:
                    pct = min(int(count * block * 50 / total), 50)
                    mb = count * block / 1048576
                    total_mb_val = total / 1048576
                    wx.CallAfter(dlg.set_progress, pct,
                                 f"CUDAランタイムをダウンロード中... {mb:.0f} / {total_mb_val:.0f} MB")

            wx.CallAfter(dlg.set_progress, 0, "CUDAランタイムをダウンロード中... (約1.05GB)")
            urllib.request.urlretrieve(CUDA_ZIP_URL, cuda_zip, cuda_hook)
            if dlg.cancelled:
                raise InterruptedError

            wx.CallAfter(dlg.set_progress, 50, "CUDAランタイムを展開中...")
            cuda_temp = temp_dir / "cuda_extracted"
            with zipfile.ZipFile(cuda_zip, 'r') as z:
                z.extractall(cuda_temp)
            cuda_zip.unlink(missing_ok=True)

            for dll in cuda_temp.glob("**/*.dll"):
                shutil.copy2(dll, onnx_lib_dir / dll.name)
                log.info(f"CUDA install: copied {dll.name}")
            _rmtree(cuda_temp)

            # --- 2. CUDA 版 voicevox_onnxruntime ---
            onnx_tgz = temp_dir / "voicevox_onnxruntime-cuda.tgz"

            def onnx_hook(count, block, total):
                if dlg.cancelled:
                    raise InterruptedError
                if total > 0:
                    pct = 55 + min(int(count * block * 35 / total), 35)
                    mb = count * block / 1048576
                    total_mb_val = total / 1048576
                    wx.CallAfter(dlg.set_progress, pct,
                                 f"CUDA版onnxruntimeをダウンロード中... {mb:.0f} / {total_mb_val:.0f} MB")

            wx.CallAfter(dlg.set_progress, 55, "CUDA版onnxruntimeをダウンロード中... (約65MB)")
            urllib.request.urlretrieve(ONNX_CUDA_URL, onnx_tgz, onnx_hook)
            if dlg.cancelled:
                raise InterruptedError

            wx.CallAfter(dlg.set_progress, 90, "CUDA版onnxruntimeを展開中...")
            onnx_temp = temp_dir / "onnx_extracted"
            with tarfile.open(onnx_tgz, 'r:gz') as t:
                t.extractall(onnx_temp, filter='data')
            onnx_tgz.unlink(missing_ok=True)

            for dll in onnx_temp.glob("**/*.dll"):
                shutil.copy2(dll, onnx_lib_dir / dll.name)
                log.info(f"CUDA onnxruntime install: copied {dll.name}")
            _rmtree(onnx_temp)

            # --- 3. zlibwapi.dll (cuDNN 8.x の依存ライブラリ) ---
            zlib_zip = temp_dir / "zlib123dllx64.zip"

            def zlib_hook(count, block, total):
                if dlg.cancelled:
                    raise InterruptedError

            wx.CallAfter(dlg.set_progress, 93, "zlibwapi.dllをダウンロード中...")
            urllib.request.urlretrieve(ZLIB_URL, zlib_zip, zlib_hook)
            if dlg.cancelled:
                raise InterruptedError

            wx.CallAfter(dlg.set_progress, 97, "zlibwapi.dllを展開中...")
            zlib_temp = temp_dir / "zlib_extracted"
            with zipfile.ZipFile(zlib_zip, 'r') as z:
                z.extractall(zlib_temp)
            zlib_zip.unlink(missing_ok=True)

            zlib_dll = next(zlib_temp.glob("**/zlibwapi.dll"), None)
            if zlib_dll:
                shutil.copy2(zlib_dll, onnx_lib_dir / "zlibwapi.dll")
                log.info("CUDA install: copied zlibwapi.dll")
            else:
                log.warning("zlibwapi.dll not found in downloaded zip")
            _rmtree(zlib_temp)

            wx.CallAfter(dlg.Destroy)
            wx.CallAfter(
                gui.messageBox,
                "CUDA加速ライブラリのインストールが完了しました。\nNVDAを再起動すると有効になります。",
                "インストール完了",
                wx.OK | wx.ICON_INFORMATION,
            )

        except InterruptedError:
            log.info("CUDA install cancelled by user")
            wx.CallAfter(dlg.Destroy)
        except Exception as e:
            log.error(f"CUDA install failed: {e}", exc_info=True)
            wx.CallAfter(dlg.Destroy)
            wx.CallAfter(
                gui.messageBox,
                f"インストール中にエラーが発生しました:\n{e}",
                "エラー",
                wx.OK | wx.ICON_ERROR,
            )
        finally:
            _rmtree(temp_dir)

    threading.Thread(target=do_install, daemon=True).start()
