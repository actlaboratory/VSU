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
from .dialogs import DownloadProgressDialog

VVM_VERSION_PREFIX = "0.16"
GITHUB_RELEASES_URL = "https://api.github.com/repos/VOICEVOX/voicevox_vvm/releases"
VVM_DIR = os.path.join(addonRootDir, "voicevox_core", "models", "vvms")


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
                    gui.messageBox,
                    _("{prefix} 系の音声辞書ファイルが見つかりませんでした。").format(prefix=VVM_VERSION_PREFIX),
                    _("音声辞書ファイルのダウンロード"),
                    wx.OK | wx.ICON_ERROR,
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
                gui.messageBox,
                _("リリース情報の取得に失敗しました:\n{}").format(str(e)),
                _("音声辞書ファイルのダウンロード"),
                wx.OK | wx.ICON_ERROR,
            )

    threading.Thread(target=_fetch, daemon=True).start()


def _on_fetch_done(missing, tag_name):
    if not missing:
        gui.messageBox(
            _("すべての音声辞書ファイルはすでにダウンロード済みです。"),
            _("音声辞書ファイルのダウンロード"),
            wx.OK | wx.ICON_INFORMATION,
        )
        return

    total_mb = sum(a["size"] for a in missing) / (1024 * 1024)
    msg = _("音声辞書ファイルを {count} ファイル ({size:.1f} MB) ダウンロードします。よろしいですか？").format(
        count=len(missing), size=total_mb
    )
    if gui.messageBox(msg, _("音声辞書ファイルのダウンロード"), wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION) != wx.YES:
        return

    total_bytes = sum(a["size"] for a in missing)
    dlg = DownloadProgressDialog(_("音声辞書ファイルのダウンロード"))
    dlg.Show()

    def _do_download():
        downloaded_bytes = 0
        errors = []

        for i, asset in enumerate(missing):
            if dlg.cancelled:
                break
            dest = os.path.join(VVM_DIR, asset["name"])
            try:
                req = Request(asset["url"], headers={"User-Agent": "VSU-vvm-downloader"})
                with urlopen(req, timeout=300) as resp, open(dest, "wb") as f:
                    file_downloaded = 0
                    while True:
                        if dlg.cancelled:
                            raise InterruptedError
                        chunk = resp.read(65536)
                        if not chunk:
                            break
                        f.write(chunk)
                        file_downloaded += len(chunk)
                        current_total = downloaded_bytes + file_downloaded
                        pct = min(int(current_total * 100 / total_bytes), 99) if total_bytes > 0 else 0
                        mb_done = current_total / 1048576
                        total_mb_val = total_bytes / 1048576
                        wx.CallAfter(
                            dlg.set_progress, pct,
                            f"({i + 1}/{len(missing)}) {asset['name']}: {mb_done:.1f} / {total_mb_val:.1f} MB"
                        )
                downloaded_bytes += file_downloaded
            except InterruptedError:
                if os.path.exists(dest):
                    try:
                        os.remove(dest)
                    except Exception:
                        pass
                wx.CallAfter(dlg.Destroy)
                return
            except Exception as e:
                log.error(f"Failed to download {asset['name']}: {e}", exc_info=True)
                errors.append(asset["name"])
                if os.path.exists(dest):
                    try:
                        os.remove(dest)
                    except Exception:
                        pass

        wx.CallAfter(dlg.Destroy)
        if errors:
            wx.CallAfter(
                gui.messageBox,
                _("以下の音声辞書ファイルのダウンロードに失敗しました:\n{}").format("\n".join(errors)),
                _("音声辞書ファイルのダウンロード"),
                wx.OK | wx.ICON_ERROR,
            )
        else:
            wx.CallAfter(
                gui.messageBox,
                _("バージョン {ver} の音声辞書ファイルをすべてダウンロードしました。\nNVDAを再起動すると新しい音声が使用できます。").format(ver=tag_name),
                _("音声辞書ファイルのダウンロード"),
                wx.OK | wx.ICON_INFORMATION,
            )

    threading.Thread(target=_do_download, daemon=True).start()
