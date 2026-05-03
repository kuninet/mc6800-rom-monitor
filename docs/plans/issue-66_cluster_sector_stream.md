# Issue #66 cluster内複数sector stream read 計画

## 関連リンク

- Issue #66: https://github.com/kuninet/mc6800-rom-monitor/issues/66
- 親 Issue #54: https://github.com/kuninet/mc6800-rom-monitor/issues/54
- 先行 Issue #65: https://github.com/kuninet/mc6800-rom-monitor/issues/65
- PR #64: https://github.com/kuninet/mc6800-rom-monitor/pull/64

## 方針

Issue #65 で `cluster -> LBA` は `SecPerClus` 対応になり、実機でも `HELLO.S` のような512 byte以下のファイルを `LF` できることを確認した。

一方、現行 `FAT32_STREAM_GETC` は1 sectorを読み切ると常に `FAT32_NEXT_CLUSTER` へ進む。実カードの `SecPerClus=6` では、cluster内の2 sector目以降を読まずに次clusterへ進んでしまうため、`MICBAS13.S` や `MICBAS13.HEX` のような512 byte超ファイルを正しく読めない。

Issue #66 では、FAT file streamに `sector_in_cluster` 状態を追加し、同一cluster内のsectorを順に読んでからFAT chainへ進むようにする。`FAT32_READ_FILE` もテスト用内部APIとして使われているため、同じsector進行処理を使う。

## 実装内容

- `FAT_SECTOR_IN_CLUS` を追加し、`FAT32_STREAM_OPEN` と `FAT32_READ_FILE` 開始時に0へ初期化する。
- sector read時は `FAT_CLUSTER_TO_SD_LBA` の結果に `FAT_SECTOR_IN_CLUS` 分だけ加算して、cluster内の対象sectorを読む。
- 1 sector消費後、file sizeが残っていれば `FAT_SECTOR_IN_CLUS` を進める。
- `FAT_SECTOR_IN_CLUS < FAT_SEC_PER_CLUS` の間は同じclusterの次sectorを読む。
- `FAT_SECTOR_IN_CLUS == FAT_SEC_PER_CLUS` になったら0へ戻し、`FAT32_NEXT_CLUSTER` で次clusterへ進む。
- fixtureに、`SecPerClus>1` かつ512 byte境界を越えるS-Recordファイルを追加し、`LF` で実際にRAMへロードできることを確認する。
- 批判的レビューで、`SecPerClus>1` のcluster chain境界も明示的に踏むべきと指摘されたため、`SecPerClus=2` で3 sector以上のS-Recordファイルを読み、同一cluster内sector境界と次cluster遷移の両方を確認する。
- 追加テストで、S-RecordローダがBレジスタにデータ残数を保持したまま `LOADER_GETC` を呼ぶことが見えたため、FAT入力時もACIA入力と同じくBを保存する。これにより、sector境界処理でBが壊れてS-Record checksum段階へ誤進行する問題を避ける。

## 対象外

- SAVE/write。
- subdirectory、LFN、wildcard。
- AUTOEXEC。
- 外部MCU化。
- cluster番号の大容量カード全域対応。

## テスト方針

PR前に次を実行する。

```powershell
make bin
$env:REQUIRE_BUILD_ROM='1'
python tests/test_smoke.py
python tests/test_sd_fixture.py
python -m py_compile emu\sbc6800_emu.py tests\sd_fixtures.py tests\test_sd_fixture.py
git diff --check
```

実機では、`MICBAS13.S` または `MICBAS13.HEX` をrootに置いたカードで `LF` を実行し、`OK` とロード結果を確認する。
