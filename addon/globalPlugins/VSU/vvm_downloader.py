# -*- coding: utf-8 -*-
# Copyright (C) 2026 ACT Laboratory

import json
import os
import re
import threading
from urllib.request import urlopen, Request

import gui
import wx
from logHandler import log

from .constants import addonRootDir

VVM_VERSION_PREFIX = "0.16"
GITHUB_RELEASES_URL = "https://api.github.com/repos/VOICEVOX/voicevox_vvm/releases"
VVM_DIR = os.path.join(addonRootDir, "synthDrivers", "voicevox_core", "models", "vvms")


def start_download_vvms():
    """メニューから呼び出すエントリポイント。バックグラウンドでリリース情報を取得する。"""
    def _fetch():
        try:
            req = Request(GITHUB_RELEASES_URL, headers={"User-Agent": "VSU-vvm-downloader"})
            with urlopen(req, timeout=30) as f:
                releases = json.loads(f.read().decode("utf-8"))

            release = next(
                (r for r in releases if r.get("tag_name", "").startswith(VVM_VERSION_PREFIX)),
                None
            )
            if release is None:
                wx.CallAfter(
                    gui.message.MessageDialog.alert,
                    _("{prefix} 系の音声辞書ファイルが見つかりませんでした。").format(prefix=VVM_VERSION_PREFIX),
                    _("音声辞書ファイルのダウンロード")
                )
                return

            assets = [
                {"name": a["name"], "url": a["browser_download_url"], "size": a["size"]}
                for a in release["assets"]
                if re.match(r'^\d+\.vvm$', a["name"])
            ]

            os.makedirs(VVM_DIR, exist_ok=True)
            missing = [a for a in assets if not os.path.exists(os.path.join(VVM_DIR, a["name"]))]

            wx.CallAfter(_on_fetch_done, missing, release["tag_name"])

        except Exception as e:
            log.error(f"VVM fetch error: {e}", exc_info=True)
            wx.CallAfter(
                gui.message.MessageDialog.alert,
                _("リリース情報の取得に失敗しました:\n{}").format(str(e)),
                _("音声辞書ファイルのダウンロード")
            )

    t = threading.Thread(target=_fetch, daemon=True)
    t.start()


def _on_fetch_done(missing, tag_name):
    if not missing:
        gui.message.MessageDialog.alert(
            _("すべての音声辞書ファイルはすでにダウンロード済みです。"),
            _("音声辞書ファイルのダウンロード")
        )
        return

    total_mb = sum(a["size"] for a in missing) / (1024 * 1024)
    msg = _("音声辞書ファイルを {count} ファイル ({size:.1f} MB) ダウンロードします。よろしいですか？").format(
        count=len(missing), size=total_mb
    )
    if gui.message.MessageDialog.confirm(msg, _("音声辞書ファイルのダウンロード")) != gui.message.ReturnCode.OK:
        return

    errors = []

    def _do_download():
        for asset in missing:
            dest = os.path.join(VVM_DIR, asset["name"])
            try:
                req = Request(asset["url"], headers={"User-Agent": "VSU-vvm-downloader"})
                with urlopen(req, timeout=300) as resp, open(dest, "wb") as f:
                    while True:
                        chunk = resp.read(65536)
                        if not chunk:
                            break
                        f.write(chunk)
            except Exception as e:
                log.error(f"Failed to download {asset['name']}: {e}", exc_info=True)
                errors.append(asset["name"])
                if os.path.exists(dest):
                    try:
                        os.remove(dest)
                    except Exception:
                        pass

    progress = gui.IndeterminateProgressDialog(
        gui.mainFrame,
        _("音声辞書ファイルのダウンロード"),
        _("音声辞書ファイルをダウンロード中...")
    )
    try:
        gui.ExecAndPump(_do_download)
    finally:
        progress.done()
        del progress

    if errors:
        gui.message.MessageDialog.alert(
            _("以下の音声辞書ファイルのダウンロードに失敗しました:\n{}").format("\n".join(errors)),
            _("音声辞書ファイルのダウンロード")
        )
    else:
        gui.message.MessageDialog.alert(
            _("バージョン {ver} の音声辞書ファイルをすべてダウンロードしました。").format(ver=tag_name),
            _("音声辞書ファイルのダウンロード")
        )
