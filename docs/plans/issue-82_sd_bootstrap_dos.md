# Issue #82 SD bootstrap / M6800 DOS 構想整理

## 関連リンク

- Issue #82: https://github.com/kuninet/mc6800-rom-monitor/issues/82
- Issue #89: https://github.com/kuninet/mc6800-rom-monitor/issues/89
- Issue #81: https://github.com/kuninet/mc6800-rom-monitor/issues/81

## 方針

`BOOT` は root の `AUTOEXEC.S` を直接 LOAD するコマンドではなく、SD 上の第2段システムを起動する入口として扱う。第2段の初期候補は root directory の `SDFS.BIN` とし、`AUTOEXEC.S` は `SDFS.BIN` または将来の M6800 DOS 相当が起動後に任意で処理する起動スクリプト相当とする。

責務は次のように分ける。

| 要素 | 責務 |
| --- | --- |
| `BOOT` | SD 上の第2段システムを探して LOAD/RUN する入口 |
| 第1段bootstrap | reserved sector などから最小 loader を起動する将来候補 |
| `SDFS.BIN` | DIR/LF などの SD/FAT 操作と、必要に応じた `AUTOEXEC.S` 処理を持つ第2段 |
| `AUTOEXEC.S` | RTC、VDG、キーボード、BASIC 起動などを行う任意の起動スクリプト |

## 方式比較

| 方式 | 位置づけ | 採用条件 |
| --- | --- | --- |
| ROM 直 FAT から `SDFS.BIN` 起動 | 初期検討の現実路線 | ROM 容量に収まり、root directory から通常ファイルを読めること |
| FAT32 reserved sector bootstrap | ROM 削減案 | 専用 SD 作成手順、signature 検査、復旧手順を用意できること |
| 外部 MCU 経由 | 将来の性能改善案 | SD/FAT 処理を外部 firmware に逃がす価値が実装コストを上回ること |

## 採用保留条件

- ROM 容量が FAT read-only、VDG、キーボード、RTC 対応で逼迫するまでは、reserved sector bootstrap 実装を急がない。
- `AUTOEXEC.S` は ROM 側 `BOOT` や第1段bootstrapの責務に含めない。
- `CONFIG.SYS`、subdirectory、FAT write、SD イメージ作成ツールは #82 の設計整理では対象外にする。
- 実装に入る場合は、`BOOT` で `SDFS.BIN` を起動する Issue と、`SDFS.BIN` 側で `AUTOEXEC.S` を処理する Issue を分ける。

## 検証方針

#82 では設計整理を成果物とし、実装テストは後続 Issue に分ける。後続 PoC では、`SDFS.BIN` 未検出、signature 不一致、サイズ不正、FAT chain read error、`AUTOEXEC.S` なしの各ケースで安全に対話モードまたはシリアル `L` fallback へ戻れることを確認する。
