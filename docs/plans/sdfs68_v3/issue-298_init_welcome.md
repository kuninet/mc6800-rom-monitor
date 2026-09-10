# Issue #298 SDFS/68 v3 resident起動時のINIT APIとWelcome表示

親epic: #296 SDFS/68 v3 phase 2 実機起動・system運用epic

## 背景

`BOOT3` は resident payloadを physical LBA `64` から読み検証しRAMへ配置し `SDFS3_FIND_API` でAPI headerを検出したあと、ROM側の `OK` を表示するだけだった。実機ではv3 residentが実際にロードされたのか、どのビルドが動いているのかが分からない。

ROMの責務は「読む・検証する・配置する・API探索」までとし、起動メッセージやそれ以降の初期化はresident側の責務とする方針を採る。この責務分離のための入口として、resident APIにINITエントリを新設した。

## 採用方針

- `issue-259_resident_api.md` の外部安定API表では、slot 9は `SDFS3_SYS_UPDATE`、slot 10-12は `SDFS3_WRITE_OPEN` / `WRITE_DATA` / `WRITE_CLOSE` として既に予約されている。この予約を潰さないため、INITはjump table末尾ではなくslot 13（offset 26）に置く。slot 9-12は `fdb SDFS3_NOT_IMPLEMENTED` で埋めて予約を温存する。`SDFS3_API_COUNT` / `SDFS3_API_MIN_COUNT` は9から14へ引き上げる。
- `SDFS3_FIND_API` 成功後、`CMD_BOOT3` はAPI headerが指すjump tableポインタ（header offset 12）経由でINITエントリ（offset 26 = slot 13 × 2）を `jsr 0,x` で直接呼び出す。INITは引数なしのため、`CMD_SDFS3_CALL` が使うpush/rtsトランポリンは不要とした。
- INITはロード完了後ちょうど1回、ロードした側（現状は `CMD_BOOT3` のみ）が呼ぶ責務とする。#277の固定LBA loader harnessや将来の別ロード経路がINITを呼ばない場合、residentは未初期化のままCMD経由で使える状態になりうるため、新しいロード経路を追加する際はこの契約を踏まえてINIT呼び出しの要否を検討すること。
- 既存API変更を伴わない後方互換のAPI追加のため、`SDFS3_API_MINOR` を0から1へ上げる。Welcome表示は `SDFS/68 V3 01.01` になる。ROM側 `SDFS3_FIND_API` はminorを検査しないため互換性への影響はない。
- INITはコンソールへ2行のWelcomeを出力する。1行目はAPIバージョン表示 `SDFS/68 V3 <major>.<minor>`（major/minorはビルド構成に依らない定数のため、ビルド識別にはならない）、2行目はresidentの配置とサイズによるビルド識別 `BASE=xxxx END=xxxx`（`SDFS3_LOAD_BASE` / `SDFS3_END-1` の値はビルド構成で変わる）。major/minorは `SDFS3_PRINT_HEX8` で2桁hex表記する（10進10以上は`0A`のようにhex表記になる）。成功時は常に `clc` + `rts` で返す。
- 表示文字列とINITロジックはresident側バイナリ（`resident_stub.asm`）にのみ置き、ROM側 (`main.asm`) には一切含めない。ROMは検出したjump table経由でINITを呼び出すだけである。
- K68-VDGのコンソールは32桁表示のため、Welcome各行は32文字以内に収めた。

## 対象構成

主対象は #295 と同じ K6802-SBC + K68-VDG の次の構成とする。

```powershell
make rombin MONITOR_PROFILE=k6802_vdg ROM_KIND=W27C512 SDFS3_LOAD_BASE=0x5000 SDFS3_LOAD_LIMIT=0x7EFF BUILD_CONFIG_NAME=k6802-vdg-sdfs3-5000 PYTHON=python ASL_INCLUDE_ARG="build;include;src"
make sdfs3 MONITOR_PROFILE=k6802_vdg SDFS3_LOAD_BASE=0x5000 SDFS3_LOAD_LIMIT=0x7EFF BUILD_CONFIG_NAME=k6802-vdg-sdfs3-5000 PYTHON=python ASL_INCLUDE_ARG="build;include;src"
make sdfs3sys MONITOR_PROFILE=k6802_vdg SDFS3_LOAD_BASE=0x5000 SDFS3_LOAD_LIMIT=0x7EFF BUILD_CONFIG_NAME=k6802-vdg-sdfs3-5000 PYTHON=python ASL_INCLUDE_ARG="build;include;src"
```

## 検証方針

エミュレータテストで次を確認する。

- `BOOT3` 実行後、Welcome 2行（`SDFS/68 V3 01.01` と `BASE=xxxx END=xxxx`）が `OK` より前に表示されること。
- `CMD DIR` などのresident呼び出しがINIT追加後も引き続き動作すること。
- jump table slot 9-12が `SDFS3_NOT_IMPLEMENTED` を指し続けていること（#259の予約枠を誰かが後から詰めてしまう退行を防ぐため）。
- Welcome文字列がresidentバイナリ（`SDFS3-*.BIN`）にのみ含まれ、ROMバイナリ（`mc6800-monitor-*.bin`）には含まれないこと。
- `SDFS3_LOAD_LIMIT` 超過エラー（`SDFS/68 v3 resident exceeds configured load area`）が出ないこと。INIT追加によるresidentサイズ増加が既存の load area に収まることを確認する。

対象外（この文書のスコープ外）:

- プロンプトをSDFS専用表示へ変更すること
- `BOOT3` の自動起動化
- `AUTOEXEC.COM` / `INIT.COM` / `HELLO.COM` の自動実行
- RTC初期化や環境初期化そのものの実装

## 後続作業

- `AUTOEXEC.COM` / `INIT.COM` の自動実行 (#304)
- RTC初期化・環境初期化
