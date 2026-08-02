# Issue #295 SDFS/68 v3 BOOT3固定LBAローダ

親epic: #296 SDFS/68 v3 phase 2 実機起動・system運用epic

## 背景

#277 では `SDFS3SYS` 固定LBAローダをRAM harnessとして検証した。PH2ではこの経路をROMモニタの `BOOT3` コマンドにし、v2 SDFS/68を経由せずに v3 resident を直接RAMへロードできるようにする。

## 採用方針

- `BOOT` は既存の v2 stage1 起動経路として維持する。
- `BOOT3` は physical LBA `64` から `SDFS3SYS` を読み込む。
- `SDFS3SYS` の magic、header version、ABI major、flags、load address、header size、image size、checksum をROM側で検証する。
- resident payload は `SDFS3_LOAD_BASE` へ配置し、配置後に `SDFS3_FIND_API` でAPI headerを確認する。
- 正常終了時は `OK` を表示してROM monitorへ戻る。以後 `CMD DIR` などの `CMD` gatewayからresidentを呼び出す。
- 異常時は通常のmonitor errorとして `?` を返す。

## 対象構成

主対象は K6802-SBC + K68-VDG の次の構成とする。

```powershell
make rombin MONITOR_PROFILE=k6802_vdg ROM_KIND=W27C512 SDFS3_LOAD_BASE=0x5000 SDFS3_LOAD_LIMIT=0x7EFF BUILD_CONFIG_NAME=k6802-vdg-sdfs3-5000 PYTHON=python ASL_INCLUDE_ARG="build;include;src"
make sdfs3sys MONITOR_PROFILE=k6802_vdg SDFS3_LOAD_BASE=0x5000 SDFS3_LOAD_LIMIT=0x7EFF BUILD_CONFIG_NAME=k6802-vdg-sdfs3-5000 PYTHON=python ASL_INCLUDE_ARG="build;include;src"
```

`BOOT3` 自体は `FEATURE_SD=1` かつ `S1_SUPPORTED=1` のROMに入る。`SDFS3_LOAD_BASE` はROMとresidentで一致させる必要がある。

## 検証方針

- `BOOT3` が `SDFS3SYS` をロードし、直後に `CMD DIR` がFAT32 rootを読めることをエミュレータで確認する。
- bad magicの `SDFS3SYS` を `BOOT3` が拒否し、resident未ロード状態の `CMD DIR` も失敗することを確認する。
- 既存の #277 RAM harness テストと v3 `DIR` / `TYPE` / `LOAD` / `RUN` / `.COM` テストを維持する。

## 後続作業

- system SD作成ツールで `SDFS3SYS` をLBA `64` に配置する正式手順は別Issueで扱う。
- `BOOT3` の自動起動、slot A/B、active marker、FAT writeを伴うsystem updateは別Issueで扱う。
