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

## ディレクトリ構成

```text
PocketMicroLIB/
├─ README.md
├─ LICENSE
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
   ├─ state.py                   # シンプルな状態管理ユーティリティ
   └─ ublox_sara_r.py            # u-blox F9P GNSS + SARA-R モデム統合ドライバ
