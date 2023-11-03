# VSU: Voicevox Synthesizer Unit

## 概要

VSUは、NVDAの音声としてVoicevoxを利用できるようにするジョークアドオンです。
あくまでジョークアドオンという性質と完成度をご理解いただいたうえでご利用ください。

## システム要件

サポートされるNVDAの最低バージョンは、2021.1です。
Voicevoxについては、リリース時点で最新の0.14.8で動作確認しています。
Voicevoxには、CPU版とGPU版があります。VSUはどちらのバージョンでも利用可能ですが、レスポンス速度の都合上CPU版での利用は非常に困難です。
また、GPU版にはDirectML版とCUDA版があります。お持ちのGPUの聖堂を生かし切れていないと感じられる倍には、下記より別のバージョンをダウンロードしてお試しください。
https://github.com/VOICEVOX/voicevox_engine/releases/tag/0.14.6

## 起動方法

VSUを動作させるには、Voicevoxのディレクトリ内にある「run.exe」を「--enable_cancellable_synthesis」オプションをつけて起動した状態でNVDAを起動する必要があります。
多くのVoicevox連携アプリケーションとは異なり、Voicevoxのエディタを起動しているだけでは動作しませんので、ご注意ください。

## 設定

VSUをインストールすると、NVDAメニュー内にVSUの項目が追加されます。
現在は、自動バージョンアップチェックのON/OFFの切り替えと、手動でのバージョンアップチェックの実行が可能です。


## 連絡先

GitHubのアカウントを持っている方は、 [VSUのissuesページ](https://github.com/actlaboratory/VSU/issues) でissueを投稿していただけると、最も早く対応できます。

メールでのお問い合わせの場合は、 support@actlab.org 宛てに送信してください。

