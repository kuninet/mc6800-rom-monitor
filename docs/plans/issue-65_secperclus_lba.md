# Issue #65 SecPerClus対応のcluster先頭LBA計算 計画

## 関連リンク

- Issue #65: https://github.com/kuninet/mc6800-rom-monitor/issues/65
- 親 Issue #54: https://github.com/kuninet/mc6800-rom-monitor/issues/54
- PR #64: https://github.com/kuninet/mc6800-rom-monitor/pull/64

## 方針

実機では MISO プルアップ後に `DIR` が成功し、SD 初期化、FAT32 mount、root directory read までは確認できた。`LF HELLO.S` は失敗したが、直後の確認で `SD_ERROR=$00`、`FAT_ERROR=$00`、`FAT_SEC_PER_CLUS=$06`、`HELLO.S start cluster=5`、`file size=$54` が見えている。

現行実装は `cluster -> LBA` が `data_start + (cluster - 2)` で、`SecPerClus=1` 前提になっている。実カードでは `SecPerClus=6` のため、file cluster の先頭 LBA がずれる。Issue #65 では、まず 512 byte 以下の単一 sector ファイルを読めるように `FAT_CLUSTER_TO_SD_LBA` だけを `SecPerClus` 対応にする。

cluster 内の2 sector目以降を読む stream 状態管理は Issue #66 に残す。

## 実装内容

- `FAT_CLUSTER_TO_SD_LBA` を `data_start + (cluster - 2) * FAT_SEC_PER_CLUS` に変更する。
- 計算は既存制約に合わせ、cluster番号の下位8bitを使った加算ループにする。
- `tests/sd_fixtures.py` は既定 `SecPerClus=1` を維持しつつ、テスト用に `sectors_per_cluster` を指定できるようにする。
- `tests/test_sd_fixture.py` に `SecPerClus=6` fixtureで `LF TEST.S` 相当の小さいS-Recordファイルをロードできる確認を追加する。

## 対象外

- 512 byte を超えるファイルの `LF`。
- cluster 内の複数 sector stream read。
- `FAT32_READ_FILE` の複数 sector 正式対応。
- SAVE/write、subdirectory、LFN、AUTOEXEC、外部 MCU 化。

## テスト方針

PR 前に次を実行する。

```powershell
make bin
$env:REQUIRE_BUILD_ROM='1'
python tests/test_smoke.py
python tests/test_sd_fixture.py
python -m py_compile emu\sbc6800_emu.py tests\sd_fixtures.py tests\test_sd_fixture.py
git diff --check
```

実機では、`HELLO.S` を root に置いたカードで `LF HELLO.S` を実行し、`OK` と `D0100` のロード結果を確認する。

## 実機確認結果

PR #67 の実装ROMで、実カード上の `HELLO.S` を `LF HELLO.S` でロードできた。続けて `G0100` を実行し、`HELLO, WORLD` が表示され、`BRK 0106` でモニタへ戻るところまで確認できた。

確認時の要点:

- `F0100-01FF 00` でロード先を初期化。
- `LF HELLO.S` が `OK` を返した。
- `D0100` で `CE 01 07 BD E0 7E ... 48 45 4C 4C 4F 2C 20 57 4F 52 4C 44 ...` が入り、S-Recordの内容がRAMへ反映された。
- `G0100` で `HELLO, WORLD` を表示し、`BRK 0106 A=04 B=00 X=0117 SP=1F42 CC=D4` で停止した。

これにより、Issue #65 の範囲である `SecPerClus>1` カード上の512 byte以下ファイルLOADは実機で確認済みとする。512 byteを超える `MICBAS13.S` / `MICBAS13.HEX` のようなファイルは、予定どおり Issue #66 の cluster内複数sector stream read 対応で扱う。
