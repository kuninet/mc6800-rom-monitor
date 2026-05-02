# Issue #49 SDHC sector read実装計画

## 関連リンク

- Issue #49: https://github.com/kuninet/mc6800-rom-monitor/issues/49
- Issue #48: https://github.com/kuninet/mc6800-rom-monitor/issues/48
- PoC PR #46: https://github.com/kuninet/mc6800-rom-monitor/pull/46

## 方針

Issue #49では、FAT32、`DIR`、`LF`、S-Record/Intel HEX LOAD連携には入らない。
ROM側へ内部APIとしてSDHC初期化と`CMD17`による512 byte sector readだけを追加する。

公開モニタコマンドは追加しない。後続 #50 以降でFAT32処理を実装するときの下回りとして扱う。

## 実装範囲

- PIAアドレスはエミュレータ暫定値として `$8050-$8053` を定義する。
- Port BのSPI bit割当は #48 と同じ `SCLK=$01`, `MOSI=$02`, `MISO=$04`, `CS=$08` とする。
- `src/sdcard.asm` を追加し、`SD_INIT`、`SD_READ_SECTOR`、`SD_SPI_XFER` を実装する。
- `SD_LBA0..3` はSDHCのLBA sector番号をbig-endianで保持する。
- `SD_READ_SECTOR` は `X=書き込み先RAM`、`SD_LBA0..3=LBA` を入力とし、成功時C=0、失敗時C=1を返す。
- 既定のsector buffer候補は `$1C00-$1DFF` とする。

## 対象外

- ROMモニタの公開コマンド追加
- FAT32 BPB/MBR解析
- root directory走査
- `DIR` / `LF filename`
- SAVE/write対応
- 実機SBC-IOアドレスの最終決定
- PoC由来の大規模差分や生成済み `.img`

## 確認方針

`tests/test_sd_fixture.py` にROM統合テストを追加する。

- FAT32 fixtureを一時ファイルとして生成し、エミュレータへ `--sd` で接続する。
- listingから `SD_INIT`、`SD_READ_SECTOR`、`SD_LBA0..3`、`SD_SECTOR_BUF` のアドレスを取得する。
- モニタの `M` コマンドでRAMへ小さなテストハーネスを注入する。
- ハーネスは `SD_INIT`、LBA設定、`SD_READ_SECTOR`、`SWI` を実行する。
- `D` コマンドでsector buffer先頭をdumpし、fixtureの既知バイト列と一致することを確認する。

## 実装時の確認結果

- `SD_INIT`、`SD_READ_SECTOR`、`SD_SPI_XFER` は公開コマンドではなく内部APIとして追加した。
- `DIR`、`LF`、S-Record/Intel HEX LOAD処理、FAT32解析には手を入れていない。
- ROM統合テストでは、MBRありFAT32 fixture上の `MULTI.BIN` 第1クラスタLBAを読み、`SD_SECTOR_BUF` 先頭が既知バイト列 `MULTI-CLUSTER-1` になることを確認する。
- `SD_SECTOR_BUF=$1C00` は今回の既定候補であり、SBC-IO RAM拡張や `$C000` buffer案は後続Issueで扱う。
