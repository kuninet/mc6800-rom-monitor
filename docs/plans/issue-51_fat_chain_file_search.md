# Issue #51 FAT chain・file size・8.3検索 実装計画

## 関連リンク

- Issue #51: https://github.com/kuninet/mc6800-rom-monitor/issues/51
- Issue #50: https://github.com/kuninet/mc6800-rom-monitor/issues/50
- Issue #49: https://github.com/kuninet/mc6800-rom-monitor/issues/49
- PoC PR #46: https://github.com/kuninet/mc6800-rom-monitor/pull/46

## 方針

Issue #51では、FAT32 read-onlyの中核として、root directory cluster chain上の8.3 short filename検索、FAT entryによる次cluster取得、file sizeを上限にしたfile readを内部APIとして実装する。

公開モニタコマンドは追加しない。`DIR`、`LF filename`、S-Record/Intel HEX LOAD連携は #52 / #53 の対象として残す。

## 実装範囲

- `FAT32_FIND_83`
  - 入力: `X=11 byte 8.3名バッファ`
  - 前提: `FAT32_MOUNT` 済み
  - root directory cluster chainを読み、通常file entryを検索する
  - 一致した場合、開始clusterとfile sizeをRAM変数へ保存する
- `FAT32_READ_FILE`
  - 入力: `X=読み込み先RAM`
  - 前提: `FAT32_FIND_83` 成功済み
  - file cluster chainを辿り、file size分だけ読み込む
- `FAT32_NEXT_CLUSTER`
  - 現在clusterからFAT entryを読み、次clusterを取得する内部helper

## 対象外

- `DIR` / `LF filename` コマンド統合
- S-Record/Intel HEX parserへの接続
- subdirectory対応
- LFN entryの解釈
- 削除entry、volume label、directory属性entryの表示や利用
- write/SAVE対応

## 初期仕様

- 8.3名は大文字11 byte固定で比較する。
- LFN entry、volume label、subdirectoryはskipする。
- 削除entryはskipする。
- directory entry先頭が `$00` の場合は、そのdirectory chainの検索終了とする。
- FAT entryのEOC判定は `$0FFFFFF8` 以上を終端扱いにする。
- 初期fixtureでは `SecPerClus=1` を前提に検証する。複数sector/clusterは後続で必要になった時に拡張する。

## 確認方針

`tests/test_sd_fixture.py` にROM統合テストを追加する。

- `MULTI   BIN` を `FAT32_MOUNT` -> `FAT32_FIND_83` -> `FAT32_READ_FILE` で読み、2cluster分の既知prefixがRAM上に並ぶことを確認する。
- root directoryを複数clusterにしたfixtureを追加し、先頭clusterにない8.3 entryを `FAT32_FIND_83` が見つけられることを確認する。
- file size終端を確認するため、短い `TEST.S` の後続paddingを読み出し結果に含めないことを確認する。

## Issue #52/#53へ踏み込まないための確認

- monitor command tableは変更しない。
- `DIR` 表示は実装しない。
- `LF filename` は実装しない。
- S-Record/Intel HEX loaderへfile streamを渡さない。
