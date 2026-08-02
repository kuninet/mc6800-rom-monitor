# Issue #123 stage1 3KB配置

## 関連リンク

- Issue #123: https://github.com/kuninet/mc6800-rom-monitor/issues/123
- Issue #111: https://github.com/kuninet/mc6800-rom-monitor/issues/111
- Issue #121: https://github.com/kuninet/mc6800-rom-monitor/issues/121

## 方針

#121 で `S1_LOAD_FILE_83` の1-sector loaderまで入った結果、stage1は約1951 bytesになった。2KB枠ではSDFS/68 header検査やentry jumpを追加する余裕が小さいため、stage1 v1の領域を3KBへ拡張する。

このIssueではメモリ配置だけを変更し、stage1の機能追加は行わない。

## 実装内容

- `sbcio_vdg`: stage1を `$C400-$CFFF`、SDFS/68ロード領域を `$D000-$DEFF` にする。
- `k6802_vdg`: stage1を `$A400-$AFFF`、SDFS/68ロード領域を `$B000-$BEFF` にする。
- `SDFS_LOAD_LIMIT` を生成configへ追加する。
- `$DF00-$DFFF` / `$BF00-$BFFF` は当面stack余白として扱う。
- stage1 build testの期待値を更新する。

## 対象外

- 512 byte超ロード。
- FAT chain対応。
- SDFS/68 header検査。
- SDFS/68 entry jump。
- ROM `BOOT` 実装。

## 検証方針

- stage1 binaryが新しい3KB枠内に収まることを確認する。
- `SDFS_LOAD_BASE` と `SDFS_LOAD_LIMIT` がprofile別の期待値になることを確認する。
- 既存のstage1 SD read / mount / find / 1-sector loadテストを維持する。
