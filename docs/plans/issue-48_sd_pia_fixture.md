# Issue #48 SD/PIAエミュレータ・fixture整備計画

## 関連リンク

- Issue #48: https://github.com/kuninet/mc6800-rom-monitor/issues/48
- PoC PR #46: https://github.com/kuninet/mc6800-rom-monitor/pull/46

## 目的

Issue #48 は、後続の SD/FAT 実装に入る前のテスト基盤整備である。
ROMモニタのSDコマンド、SDアクセス用アセンブリ、実機SBC-IOの最終アドレス定義は追加しない。

今回の目的は、後続Issueで実装を検証できるように、次の土台を用意すること。

- Pythonで決定的に生成できるFAT32 fixture
- SDHC前提の最小SPI byte streamモデル
- MC6821 PIA Port Bのbit-bang SPI経由でSDモデルを読む経路
- fixtureとSD/PIAモデルをCIで検証するテスト

## 採用判断

- PIAの暫定アドレスはPoCと同じ `$8050-$8053` とする。
- Port BのSPI bit割当は `SCLK=$01`, `MOSI=$02`, `MISO=$04`, `CS=$08` とする。
- エミュレータに `--sd path` を追加する。未指定時はPIA/SDを接続せず、既存ACIA smoke testの挙動を変えない。
- SDモデルはread-only bootstrap/FAT検証に必要な `CMD0`, `CMD8`, `CMD55`, `ACMD41`, `CMD58`, `CMD17` に限定する。
- `CMD17` の引数はSDHC前提のLBA sectorとして扱い、R1、data token、512 byte payload、dummy CRCを返す。
- `.img` バイナリはコミットしない。fixtureはテスト実行時にPythonで生成する。

## fixture仕様

MBRありFAT32とsuperfloppy FAT32の2種類を生成する。
Windowsでそのまま実運用するための完全なカードイメージではなく、後続実装の検証値を固定するための最小構造とする。

- 512 byte/sector
- 1 sector/cluster
- FAT32
- Root cluster = 2
- FATは2面
- root directoryに `TEST.S`, `TEST.HEX`, `MULTI.BIN` を置く
- `MULTI.BIN` は `5 -> 6 -> EOC` の2 cluster chainにする

## PoC差分の扱い

PoC PR #46 から採用するもの。

- 暫定PIAアドレス
- Port BのSPI bit割当
- SDHC向けの最小SPIコマンド範囲

PoC PR #46 から採用しないもの。

- SD/FATアセンブリ実装
- ROMモニタのSDアクセスコマンド
- `include/hardware.inc` への実機PIA定義追加
- 生成済み `.img` や `.DS_Store` などの不要ファイル

## 対象外

- `src/sdcard.asm`
- `include/hardware.inc` のPIA定義
- ROM側のFAT directory traversal
- `DIR`, `LF`, `SAVE`, boot command連携
- 実機SBC-IOアドレスの最終決定

これらは #49 以降で扱う。

## 確認結果

このブランチでの確認結果。

- `make bin`: 成功
- `$env:REQUIRE_BUILD_ROM='1'; python tests/test_smoke.py`: 18件成功
- `python tests/test_sd_fixture.py`: 5件成功
- `python -m py_compile emu\sbc6800_emu.py tests\sd_fixtures.py tests\test_sd_fixture.py`: 成功
- `git diff --check`: 成功

