# Issue #177 sbcio profile整理

## 背景

PR #176 のROM容量確認で、`sbcio` profileだけがROM常駐FAT `DIR` / `LF` を残しており、標準profileの中で空き容量が小さいことが分かった。
一方で、現在の本線はROMにFAT機能を増やさず、通常のSDファイル操作をSDFS/68側へ寄せる方針である。

そこで `sbcio` をROM常駐FAT互換profileとして残すのをやめ、標準profileの意味を次の形へ揃える。

| profile | SD | FAT | 位置づけ |
| --- | --- | --- | --- |
| `base` | なし | なし | SBC6800互換の最小ROM |
| `sbcio` | なし | なし | SBC-IO RAM拡張 + 2nd ACIAキーボード |
| `sbcio_vdg` | raw SD `BOOT` あり | なし | SBC-IO + VDG + SDFS/68本線 |
| `k6802_vdg` | raw SD `BOOT` あり | なし | K6802-SBC + VDG + SDFS/68本線 |

## 採用方針

- `MONITOR_PROFILE=sbcio` は `FEATURE_SD=0`、`FEATURE_FAT=0` にする。
- ROM常駐FAT `DIR` / `LF` の実装コードは今回削除しない。
- ROM常駐FATを確認したい場合は、標準profileではなく直接構成軸で `FEATURE_SD=1 FEATURE_FAT=1` を指定する。
- SDFS/68本線は引き続き `sbcio_vdg` / `k6802_vdg` の `BOOT` から起動する。
- `base` と `sbcio` はSDなしROMモニタとして説明する。

## 変更対象

- `Makefile` の `sbcio` preset。
- `tests/test_smoke.py` / `tests/test_sd_fixture.py` のfeature推定。
- `README.md`、usage文書、構成軸文書、関連計画文書。

## 検証方針

- `make bin`
- `REQUIRE_BUILD_ROM=1 python3 tests/test_smoke.py`
- `MONITOR_PROFILE=sbcio make bin`
- `MONITOR_PROFILE=sbcio REQUIRE_BUILD_ROM=1 python3 tests/test_smoke.py`
- `MONITOR_PROFILE=sbcio REQUIRE_BUILD_ROM=1 python3 tests/test_sd_fixture.py`
- `MONITOR_PROFILE=sbcio_vdg make bin`
- `MONITOR_PROFILE=sbcio_vdg REQUIRE_BUILD_ROM=1 python3 tests/test_smoke.py`
- `MONITOR_PROFILE=sbcio_vdg REQUIRE_BUILD_ROM=1 python3 tests/test_sd_fixture.py`
- `MONITOR_PROFILE=sbcio FEATURE_SD=1 FEATURE_FAT=1 make bin`
- `MONITOR_PROFILE=sbcio FEATURE_SD=1 FEATURE_FAT=1 REQUIRE_BUILD_ROM=1 python3 tests/test_sd_fixture.py`

## 後続メモ

`FEATURE_FAT` は直接指定互換として残るため、ROM常駐FATのテスト経路は完全には消さない。
ただし新しいDOS風ファイル操作はROMへ戻さず、SDFS/68側で育てる。
