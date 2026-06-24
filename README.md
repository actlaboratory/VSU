# VSU: Voicevox Synthesizer Unit

NVDAの音声合成エンジンとしてVOICEVOXを利用できるようにするジョークアドオンです。
VOICEVOX Coreを内蔵しており、VOICEVOXを別途インストールする必要はありません。

## 動作要件

- NVDA 2026.1 以降（64bit版）
- Windows 10 / Windows 11（64bit）

## ユーザー向けドキュメント

[addon/doc/ja/readme.md](addon/doc/ja/readme.md) を参照してください。

## ビルド方法

Python 3.x と Git が必要です。

```
pip install -r requirements.txt
scons
```

ビルド成功後、`output/` フォルダに `.nvda-addon` ファイルが生成されます。

## ライセンス

本リポジトリのコードは [GNU General Public License v2.0 or later](https://www.gnu.org/licenses/old-licenses/gpl-2.0.html) の条件に基づき使用できます。

ビルド時に同梱されるサードパーティコンポーネントのライセンスについては [addon/doc/ja/readme.md](addon/doc/ja/readme.md) の著作権セクションを参照してください。
