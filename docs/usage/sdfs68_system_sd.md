# SDFS/68 システムSDカード方針

この文書は、SDFS/68 用のシステムSDカードを作るための初期方針をまとめる。

SDFS/68 は、ROM モニタの `BOOT` から起動する第2段システムである。ROM は固定LBAからstage1 loaderを読み、stage1がFAT root の `SDFS.BIN` を読み込む。

## 基本方針

- 初期方式は fixed boot area のstage1 loader起動とする。
- SDFS/68本体は root directory の通常ファイル `SDFS.BIN` とする。
- ROMはFATを読まず、stage1がFAT32 read-only最小実装で `SDFS.BIN` を読む。
- 初期 SDFS/68 は read-only とし、FAT write や SAVE は別Issueで扱う。
- 8.3 short filename を前提にする。LFN とサブディレクトリは後続段階で扱う。

## システムSDイメージ生成

初期ツール名は `tools/mk_sdfs_image.py` とする。

ツールは Mac / Windows / Linux で同じ Python コードを使い、FAT32 SDイメージファイルを生成する。実SDカードへの直接書き込みは行わない。

入力候補:

- stage1 loader binary
- `SDFS.BIN`
- S-Record ファイル (`.S`)
- Intel HEX ファイル (`.HEX`)
- バイナリファイル (`.BIN`)
- 将来の画像や固定データファイル

出力:

- FAT32 形式の SDイメージファイル。
- 固定LBA boot area にstage1 loaderを配置する。
- root directory に `SDFS.BIN` と指定ファイルを配置する。
- テスト用には小さい決定的イメージを生成できるようにする。

## 実SDカードへの書き込み

実SDカードへの書き込みは、初期ツールの責務に含めない。

Mac / Linux では `dd` や OS 標準のディスク操作でイメージを書き込む。Windows では既存のイメージ書き込みツールを使う。

直接デバイス書き込みをツールに含めない理由:

- 管理者権限が必要になる。
- デバイス指定ミスで別ディスクを破壊する危険がある。
- Mac / Windows / Linux でデバイス列挙と権限モデルが大きく違う。

## 初期ファイル配置

v1 の root directory は次を想定する。

| ファイル | 用途 |
| --- | --- |
| fixed boot area | stage1 loader。ROMが固定LBAから読む |
| `SDFS.BIN` | SDFS/68 本体。stage1がFAT rootから読む |
| `HELLO.S` | S-Record LOAD 確認用 |
| `HELLO.HEX` | Intel HEX LOAD 確認用 |
| `AUTOEXEC.S` | v2 以降の任意起動スクリプト候補 |

`AUTOEXEC.S` は v1 の必須ファイルではない。ROM 側 `BOOT` は `AUTOEXEC.S` を直接読まない。

## 将来拡張

SDFS/68 v2 以降では、既存 FAT32 カードへ必要ファイルをコピーする補助ツールを追加できる。

SDFS/68 v4 以降では、画像や固定バイナリデータをSD上に置き、ファイル全体をLOADせずに sector / offset 単位で読む direct read API を検討する。
