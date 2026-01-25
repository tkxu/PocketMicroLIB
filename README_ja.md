# PocketMicroLIB

ポケットサイズの IoT デバイス向けの軽量 MicroPython ライブラリ集です。

PocketMicroLIB は、Raspberry Pi Pico などの組込みマイクロコントローラー上で  
実機運用できることを目的とした、実用的でハードウェア寄りのモジュール群です。

---

## 設計方針

- Python パッケージは使用しない（フラットな構成）
- MicroPython 向けに最適化
- 実機デプロイを優先した設計
- 必要な `.py` ファイルをそのまま MicroPython デバイスにコピーして使える

ファイル命名ルール：

- `micro_*.py` → 汎用インフラモジュール
- それ以外 → ハードウェア / サービス固有モジュール

---

モジュール概要
共通インフラモジュール

- `micro_logger.py`  
MicroPython 向けのシンプルなログ出力ユーティリティ

- `micro_modem.py`  
AT コマンドベースのセルラーモデム用汎用ベースクラス

- `micro_socket.py`  
モデム依存部分を抽象化したソケットレイヤー

- `micro_http_client.py`  
ソケットレイヤー上に構築した軽量 HTTP クライアント

- `micro_storage_manager.py`  
ファイル操作やログ管理などのストレージユーティリティ

- `micro_zip.py / micro_unzip.py`  
MicroPython で ZIP 圧縮・展開を行うための簡易ユーティリティ

ハードウェア / サービス固有モジュール

- `sdcard.py`  
SPI ベースの SD カードドライバ

- `soracom_harvest_files.py`  
SORACOM Harvest Files サービス用クライアント

- `ublox_sara_r.py`  
u-blox SARA-R410/R510 モデムの統合ドライバ


## インストール（Raspberry Pi Pico2）

PocketMicroLIB は Python パッケージではありません。
必要な .py ファイルをそのまま MicroPython デバイスにコピーして使用します。

例）mpremote を使ったコピー方法：

mpremote cp src/*.py :/

## ライセンス

このプロジェクトは MIT ライセンス で公開されています。
詳細は LICENSE ファイルをご覧ください。


## ディレクトリ構成

```text
PocketMicroLIB/
├─ README.md
├─ LICENSE.md
└─ src/
   ├─ micro_http_client.py       # MicroPython 向け軽量 HTTP クライアント
   ├─ micro_logger.py            # シンプルなログ出力ユーティリティ
   ├─ micro_modem.py             # 汎用モデムベースクラス
   ├─ micro_socket.py            # ソケット抽象化レイヤー
   ├─ micro_storage_manager.py   # ストレージ管理ユーティリティ
   ├─ micro_unzip.py             # MicroPython 用簡易 unzip ユーティリティ
   ├─ micro_zip.py               # MicroPython 用簡易 zip ユーティリティ
   ├─ sdcard.py                  # SD カードドライバ（SPI ベース）
   ├─ soracom_harvest_files.py   # SORACOM Harvest Files クライアント
   └─ ublox_sara_r.py            # u-blox SARA-R410/R510 モデム統合ドライバ
