# Issue #125 stage1 SDFS/68 header検査とentry jump

## 関連リンク

- Issue #125: https://github.com/kuninet/mc6800-rom-monitor/issues/125
- Issue #111: https://github.com/kuninet/mc6800-rom-monitor/issues/111
- Issue #123: https://github.com/kuninet/mc6800-rom-monitor/issues/123

## 方針

#121 で stage1 は root の8.3ファイルを1 sectorだけ `SDFS_LOAD_BASE` へ読めるようになった。#123 で3KB枠へ拡張したため、このIssueでは `SDFS.BIN` を第2段として起動する最小入口を追加する。

ROM側 #101 は固定LBAからstage1を読むだけに寄せるため、FAT rootの `SDFS.BIN` 検索、SDFS/68 header検査、entry jumpはstage1側の責務にする。

## 実装内容

- stage1 headerの既存reserved領域 `+10` - `+15` を次の用途に固定する。
  - `+10` - `+11`: stage1 boot entry address。
  - `+12` - `+13`: stage1 image size。
  - `+14` - `+15`: reserved。v1では `0`。
- `S1_BOOT_SDFS` を追加し、stage1 headerからROM側が参照できるようにする。
- `S1_BOOT_SDFS` は `S1_MOUNT`、root 8.3名 `SDFS    BIN` のロード、SDFS/68 header検査を順に行う。
- SDFS/68 headerは `SDFS68` signature、version `1`、header size `16`、load size、entry addressを検査する。
- 正常時はSDFS/68 entryへ `jmp` する。
- 失敗時はcarry setで呼び出し元へ戻る。

## v1制約

現時点の `S1_LOAD_FILE_83` は1 sector loaderなので、`SDFS.BIN` は1..512 bytesのみ対応する。512 byte超ロード、cluster chain対応、SDFS/68本体の実装は後続Issueで扱う。

entry addressは `SDFS_LOAD_BASE` から、SDFS/68 headerが宣言するload sizeの範囲内であることを確認する。v1では現行loaderに合わせてload sizeが512 byte以内であることも確認する。

## 検証方針

- stage1 headerのboot entryとimage sizeをbinaryから確認する。
- 正しい `SDFS.BIN` headerで、entryへ制御が渡ることをエミュレータで確認する。
- signature、version、header size、entry、sizeが不正な場合にcarry setで戻ることを確認する。
- 既存のstage1 SD read / mount / find / 1-sector loadテストを維持する。
