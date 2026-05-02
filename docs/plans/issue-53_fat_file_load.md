# Issue #53 FAT上のS-Record/Intel HEX LOAD 実装計画

## 関連リンク

- Issue #53: https://github.com/kuninet/mc6800-rom-monitor/issues/53
- Issue #52: https://github.com/kuninet/mc6800-rom-monitor/issues/52
- Issue #51: https://github.com/kuninet/mc6800-rom-monitor/issues/51
- PoC PR #46: https://github.com/kuninet/mc6800-rom-monitor/pull/46

## 方針

Issue #53では、`LF filename` をFAT上の8.3ファイル検索だけで終わらせず、既存のS-Record/Intel HEXローダへ1 byteずつ流し込んでRAMへLOADする。

既存のparser、checksum、RAM書き込み処理は二重実装しない。入力元だけをACIAまたはFAT streamへ切り替え、bare `L` は従来どおりシリアルLOADとして維持する。

## 実装範囲

- `LOADER_INPUT` を追加し、loader内の入力取得を `LOADER_GETC` に集約する。
- `L` は `LOADER_INPUT=ACIA` として従来どおり端末入力から読む。
- `LF filename` は `FAT32_MOUNT`、`FAT32_FIND_83`、`FAT32_STREAM_OPEN` 後に `LOADER_INPUT=FAT` として既存loader loopを実行する。
- `FAT32_STREAM_OPEN` と `FAT32_STREAM_GETC` を追加し、file size分だけ1 byteずつ返す。
- FAT streamでfile EOFに到達した場合はcarry setで返し、loaderがACIA待ちへ落ちてハングしないようにする。
- `docs/usage/monitor_commands.md` の `LF filename` 説明を、検索入口から実LOADへ更新する。

## 対象外

- SAVE/write対応
- AUTOEXEC起動
- subdirectory、LFN、wildcard対応
- loader形式の拡張
- 実機SBC-IO確認
- 複数sector/clusterの正式対応

## 確認方針

- `LF TEST.S` でfixture上のS-Recordを読み、`$0200` に期待値が入ることを確認する。
- `LF TEST.HEX` でfixture上のIntel HEXを読み、`$0300` に期待値が入ることを確認する。
- `LF NOFILE.S` は `?` を返すことを確認する。
- `DIR`、`V`、bare `L` の既存動作が壊れていないことを確認する。
- 終端レコードがない壊れたファイルで、FAT stream EOF後にハングしないことを確認する。

## 注意

初期fixtureは `SecPerClus=1` のため、stream実装もこの前提で検証する。複数sector/clusterが必要になった場合は、FAT32のcluster内sector offset管理を追加する。
