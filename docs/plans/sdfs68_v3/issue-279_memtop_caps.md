# Issue #279 SDFS/68 v3 GET_MEMTOP / GET_CAPS API

## 背景

#271でv3 resident stubの `SDFS3API` headerとslot 0-6のjump tableを追加した。
#259/#261では、ROMやBASIC adapterがresident常駐後の安全なRAM上限とcapabilityを問い合わせられることが必要と判断している。

このIssueでは、後続のROM gatewayやBASIC adapterが参照できるように、`GET_MEMTOP` と `GET_CAPS` をresident APIとして実体化する。

## 採用方針

- API slotは #259 の設計どおり、slot 7を `SDFS3_GET_MEMTOP`、slot 8を `SDFS3_GET_CAPS` にする。
- `SDFS3_API_COUNT` は `9` に更新する。
- ROM側の `SDFS3_FIND_API` も、slot 7/8を安全に使えるように `api_count>=9` を受け入れ条件にする。
- `SDFS3_GET_MEMTOP` は初期実装として `X=USER_RAM_END`、carry clearで返す。
- `SDFS3_GET_CAPS` は初期実装として `A=0`、`B=0`、`X=SDFS3_API_HEADER`、carry clearで返す。
- header flagsは当面 `0` のままにする。
- Bank RAM、FAT write、BASIC補助はcapability上も未対応として明示する。

## 検証方針

- `tests/test_sdfs68_v3_build.py` で `sbcio_4000` と `k6802_4000` のv3 residentを確認する。
- headerの `api_count=9` とjump table slot 7/8のsymbol対応を確認する。
- ROM側検出テストで `api_count=7` と `api_count=8` を拒否することを確認する。
- `GET_MEMTOP` が `USER_RAM_END` を返す命令列であることを確認する。
- `GET_CAPS` がcapabilityなし、かつheader addressを返す命令列であることを確認する。
- コード変更なので `make test` を実行する。

## 対象外

- Bank RAM実制御。
- FAT write capability有効化。
- BASIC SAVE/LOAD adapter実装。
- ROM `CMD <tail>` gateway実装。
- `GET_CAPS` のbit定義拡張。

## 関連

- #279: 対応Issue。
- #272: v3 phase 1 実装epic。
- #259: resident API最小セット。
- #260: メモリマップとBank RAM利用方針。
- #261: BASIC SAVE/LOAD連携方式。
