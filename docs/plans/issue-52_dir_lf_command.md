# Issue #52 DIR/LF filenameコマンド統合 実装計画

## 関連リンク

- Issue #52: https://github.com/kuninet/mc6800-rom-monitor/issues/52
- Issue #51: https://github.com/kuninet/mc6800-rom-monitor/issues/51
- PoC PR #46: https://github.com/kuninet/mc6800-rom-monitor/pull/46

## 方針

Issue #52では、FAT32 read-only基盤をモニタコマンドへ接続する。
実装対象は `DIR` によるroot directory表示と、`LF filename` によるFAT上ファイル検索入口までとする。

既存の `L` はシリアルLOADとして維持する。S-Record/Intel HEXの実ロード処理は #53 に分離し、今回の `LF` ではファイル内容をRAMへロードしない。

## 実装範囲

- `DIR`
  - `DIR` 完全一致で認識する。
  - `D` / `Dssss` / `Dssss-eeee` の既存dump動作を維持する。
  - `FAT32_MOUNT` 後、root directory cluster chainを読み、通常file entryだけを表示する。
  - 表示形式は `NAME.EXT A 0000001F` とする。
- `LF filename`
  - `LF TEST.S`、`LF   TEST.HEX   ` のような空白を許容する。
  - filenameをroot上の8.3 short filename 11 byteへ変換し、`FAT32_FIND_83` に渡す。
  - 成功時は `OK` を表示し、検索済みmetadataは既存FAT変数に保持する。
  - 失敗時は `?` を表示する。
- `H` と `docs/usage/monitor_commands.md` に `DIR` / `LF filename` を追加する。

## 対象外

- `LF` でのS-Record/Intel HEX実ロード
- file内容の自動解析
- subdirectory、LFN、wildcard対応
- SAVE/write対応
- `V` コマンド追加

## 確認方針

- `DIR` でfixture上の `TEST.S`、`TEST.HEX`、`MULTI.BIN` が表示されることを確認する。
- `LF TEST.S` と `LF   TEST.HEX   ` が `OK` を返すことを確認する。
- `LF NOFILE.S` が `?` を返すことを確認する。
- bare `L` は既存シリアルLOADとして維持されることを確認する。
- `V` は `?` のままであることを確認する。
- 既存dumpコマンド `D0100` が壊れていないことを確認する。
