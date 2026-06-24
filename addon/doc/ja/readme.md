# VSU: Voicevox Synthesizer Unit

## 概要

VSUは、NVDAの音声合成エンジンとしてVOICEVOXを利用できるようにするジョークアドオンです。
VOICEVOX Coreを内蔵しており、VOICEVOXを別途インストールする必要はありません。
ジョークアドオンという性質と品質についてご理解いただいたうえでご利用ください。

## システム要件

- NVDA 2026.1 以降（64bit版）
	- VoiceVoxを同梱する都合上、32bitのNVDA2025系以前では動作しません
- Windows 10 / Windows 11（64bit）
- DirectX 12 対応GPU（GPU加速を使用する場合。なくてもCPUで動作します）

## インストール

nvda-addonファイルをNVDAに読み込ませてインストールしてください。
VOICEVOX Coreははじめから同梱されており、別途インストール作業は不要です。

## GPU加速について

VSUはDirectML（DirectX 12ベース）によるGPU加速に対応しています。
デフォルトはCPUモードで動作します。NVDAの合成音声設定にある「GPU/DirectMLアクセラレーション」をONにすることで、DirectX 12対応GPUによる高速化が有効になります。
NVIDIAのRTXシリーズなどのGPUで効果が期待できますが、非対応環境で有効にすると極端に遅くなってしまうことに注意してください。

## 音声について

アドオンに同梱されているVVMファイル（音声辞書ファイル）によって利用できる話者が決まります。
標準では「ずんだもん」「四国めたん」など複数のキャラクターが含まれています。

音声をNVDAの設定画面（合成音声の設定）から選択できます。

### 音声辞書ファイルの追加

NVDAメニュー → VSU → 音声辞書ファイルをダウンロード から追加の音声辞書ファイルをダウンロードできます。
また、アドオンの `voicevox_core\models\vvms\` フォルダに `.vvm` ファイルを手動で置いても認識されます。

## 合成パラメータ

NVDAの合成音声設定から以下のパラメータを調整できます。

| パラメータ | 説明 | 規定値での動作 |
|---|---|---|
| 速さ | 読み上げ速度 | 50で等速、100で約2倍速 |
| ピッチ | 声の高さ | 50で変化なし |
| 抑揚 | イントネーションの強さ | 50で標準 |
| 音量 | 音量 | 50で標準 |

## NVDAメニューの項目

VSUをインストールすると、NVDAメニューに「VSU」の項目が追加されます。

- **起動時の更新チェックを無効にする / 有効にする**: 自動更新チェックのON/OFF
- **更新を確認**: 手動での更新確認
- **音声辞書ファイルをダウンロード**: 追加の音声辞書ファイルをダウンロード
- **CUDA加速をインストール**: NVIDIA GPU向けCUDA加速ライブラリをダウンロード・インストール

## CUDA加速について

標準ではDirectML（DirectX 12ベース）によるGPU加速を使用します。
NVIDIA製GPUをお持ちの場合、CUDAを使用することでさらに高速に動作する場合があります。

### CUDAインストール手順

1. NVDAメニュー → VSU → **CUDA加速をインストール** を選択します。
2. 確認ダイアログで「はい」を選択します。（ダウンロードサイズ: 約1.2GB）
3. 以下の3つのファイルが自動的にダウンロード・インストールされます。
   - CUDAランタイムDLL一式（cublas、cudnn等、約1.05GB）
   - CUDA版 voicevox_onnxruntime（約65MB）
   - zlibwapi.dll（cuDNN 8.xの依存ライブラリ）
4. ダウンロードと展開が完了したら、NVDAを再起動します。
5. 再起動後、GPU加速を有効にしている場合にはCUDAで動作するようになります。

### 注意事項

- CUDA加速にはNVIDIA製GPU（GeForce RTX シリーズ等）が必要です。
- インストールには安定したインターネット接続と約1.2GBの空き容量が必要です。
- インストール済みのCUDA加速を削除するには、アドオンを一度アンインストールして再インストールしてください（DirectMLモードに戻ります）。

## 英語の読み上げについて

VOICEVOXは英単語をアルファベット読みしてしまいます。
英単語をカタカナに変換してから読み上げるNVDAアドオン「ERE (EnglishReadingEnhancer)」と組み合わせて使用することを推奨します。

EREダウンロードページ: https://actlab.org/software/ERE

## 今後に向けて

- 例えば、ずんだ門なら文章の語尾を「なのだ」に置換する等、話者に応じた辞書を整備することが望まれます。
- 長い文字列をVoicevoxに送ると時間がかかってしまうので、内部で文章を分割して送っています。ただし、この分割ロジックについては最低限の実装のみになっているので、うまく分割されない場合があります。この点も含め、発声についても改善の余地が多分に残されています。

## バージョン履歴

- Ver 2.0.0(2026-06)
	- Voicevoxを同梱し、セットアップ手順を簡素化
	- 長い文章を句読点で分割、発話中に次の文字列を生成するなどして発声を高速化
	- NVDA2026.1以降での動作のみに制限
- Ver 1.0.0(2023-11)
	- 初期バージョン

## 連絡先

GitHubのアカウントをお持ちの方は、[VSUのissuesページ](https://github.com/actlaboratory/VSU/issues) よりissueを投稿いただくと迅速に対応できます。

メールでのお問い合わせ: support@actlab.org

## 著作権

本アドオンはGPLv2(or later)の条件に基づき使用することができます。
Copyright (c) 2023-2026 yamahubuki, AccessibleToolsLaboratory

Voicevox CoreはMITライセンスに基づき使用しています。
Copyright (c) 2021 Hiroshiba Kazuyuki

Voicevox onnxruntimはMITライセンスに基づき使用しています。
Copyright (c) 2021 VOICEVOX

DirectML.dllはNVIDIAの使用条件に基づき同梱しています。

音声モデルは、VOICEVOX 音声モデル 利用規約に基づき同梱しています。

OpenJTALKの辞書は、3-Clause BSD Licenseに基づき同梱しています。
Copyright (c) 2008-2018 Nagoya Institute of Technology
Department of Computer Science


Redistribution and use in source and binary forms, with or without modification, are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice, this list of conditions and the following disclaimer.

2. Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the following disclaimer in the documentation and/or other materials provided with the distribution.

3. Neither the name of the copyright holder nor the names of its contributors may be used to endorse or promote products derived from this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS “AS IS” AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

