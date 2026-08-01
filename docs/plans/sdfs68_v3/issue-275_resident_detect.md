# Issue #275 SDFS/68 v3 ROM側resident header検出

## 背景

#271で `SDFS3API` headerを持つv3 resident stubを別成果物として生成できるようにした。
次の段階として、ROMモニタ側がRAM上のresident API headerを検査できる必要がある。

このIssueでは、ROMからresident APIを呼び出すところまでは進めず、header検出だけを実装する。
`CMD <tail>` gatewayと `SDFS3_CMD_DISPATCH` 呼び出しは #276 へ分ける。

## 採用方針

- ROM側に `SDFS3_FIND_API` を追加する。
- 初期検出位置は `SDFS_LOAD_BASE` とする。
- 検査項目は `SDFS3API` magic、`api_major=1`、`api_count>=7` に絞る。
- 成功時は `X=SDFS_LOAD_BASE`、carry clearで返す。
- 失敗時はcarry setで返す。
- 既存v2の `BOOT -> stage1 -> SDFS.BIN` 経路は変更しない。

## 検証方針

- `tests/test_sdfs68_v3_build.py` にROM側検出テストを追加する。
- `sbcio_4000` ROMをビルドし、RAM上の `SDFS_LOAD_BASE` へテストheaderを書き込む。
- 小さいRAMハーネスから `SDFS3_FIND_API` を `JSR` し、成功時に返る `X` と失敗時statusを確認する。
- 正常header、bad magic、bad major、api count不足を確認する。
- コード変更なので `make test` を実行する。

## 対象外

- `CMD <tail>` gateway実装。
- resident `CMD_DISPATCH` 呼び出し。
- 固定LBA `SDFS3SYS` loader実装。
- FAT/SD処理との接続。
- BASIC SAVE/LOAD実装。

## 関連

- #275: 対応Issue。
- #272: v3 phase 1 実装epic。
- #256: ROM command dispatch設計。
- #259: resident API最小セット。
- #260: メモリマップとBank RAM利用方針。
