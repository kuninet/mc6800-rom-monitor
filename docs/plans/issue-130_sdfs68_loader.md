# Issue #130 SDFS/68 v1 HEX/S-recordロード

## 背景

#102 で SDFS/68 最小本体が起動し、stage1 boot services の header と jump table を確認できるようになった。#130 では、ROM常駐 `LF` の主用途である S-Record / Intel HEX ロードを SDFS/68 側へ移す。

## 方針

- SDFS/68 の最小シェルに `L filename` コマンドを追加する。
- ロード確認用に `Dhhhh` で1 byteを表示する最小dumpコマンドを追加する。
- filename は v1 では root directory の 8.3 short filename のみ扱う。
- `S1_LOAD_FILE_83` は使わない。これはロード先が `SDFS_LOAD_BASE` 固定で、起動後の SDFS/68 本体を自己上書きするため。
- ファイル検索は `S1_MOUNT` と `S1_FIND_83` を使う。
- ファイル内容の読み取りは、stage1 が設定した FAT work 変数を参照し、SDFS/68 側の最小 stream reader が `S1_READ_SECTOR` で sector を読みながら 1 byte ずつ loader parser へ渡す。
- S-Record / Intel HEX parser は ROM loader と同等の制限を引き継ぐ。

## 対応形式

- S-Record は `S0` / `S1` / `S2` / `S5` / `S8` / `S9` を扱う。
- S-Record の実データ書き込みは `S1` / `S2` のみ行う。
- `S2` は上位 1 byte が `0` の 24bit address のみ許容する。
- Intel HEX は record type `00` と `01` のみ扱う。
- Intel HEX の拡張リニアアドレス、拡張セグメントアドレスは v1 では扱わない。
- SDFS/68 v1 はロード先アドレスの保護を行わない。SDFS/68本体、stage1、SD/FAT work、stack、VDG VRAMなどを壊す入力は利用者責任で避ける。
- SDFS/68側のFAT streamは既存stage1/FAT work変数を参照する暫定実装であり、v1では `mk-sdfs` 生成イメージのrootファイルを対象にする。クラスタ番号が大きい汎用FAT32カードでの堅牢性は、将来のstage1 stream APIまたはFAT処理整理で扱う。

## 対象外

- stage1 boot services のAPI追加。
- `DIR`、`TYPE`、AUTOEXEC。
- 汎用FAT32カード上の任意クラスタ配置への完全対応。
- ロード先メモリ範囲の保護。
- FAT write、subdirectory、LFN。
- ROM側 `DIR` / `LF` 整理。これは #128 で扱う。

## 検証方針

- `mk-sdfs` 生成相当のSDイメージに `.S` / `.HEX` を置き、SDFS/68 の `L filename` でロードできることを確認する。
- ロード結果はテスト内で SDFS/68 のプロンプト文字列を書き換え、出力変化として確認する。
- 存在しないファイル、壊れたHEX、終端なしS-recordでハングせずプロンプトへ戻ることを確認する。
- `S1_LOAD_FILE_83` を起動後に使わないことを実装コメントと計画文書に残す。

## 後続

- #128 で SDFS/68 移行後のROM常駐FAT `DIR` / `LF` を整理する。
- 将来、stage1 APIに file stream service を追加する場合は、SDFS/68側のFAT stream重複を減らす。
