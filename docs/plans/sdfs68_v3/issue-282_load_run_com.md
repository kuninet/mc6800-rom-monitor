# Issue #282 SDFS/68 v3 resident LOAD / RUN / .COM 接続

## 背景

#280 で `DIR` / `TYPE` を v3 resident の read-only FAT 処理へ接続した。
このIssueでは phase 1 の v2 互換範囲として、`CMD LOAD`、`CMD RUN`、明示 `.COM` 実行を resident 側へ接続する。

## 採用方針

- ROM 側の `CMD` gateway は変更しない。
- `LOAD` / `RUN` / `.COM` の判定後の実処理は resident 側へ置く。
- `LOAD` は v2 の S-Record / Intel HEX parser を `SDFS3_` 名前空間へ移植し、FAT stream から読ませる。
- `LOAD` 成功時は v2 互換として `OK` を出力してから ROM monitor へ戻る。
- `RUN addr` は v2 同様に指定アドレスへ `JMP` する。
- `RUN path` は `LOAD` 後、S-Record の entry record がある場合だけ entry へ `JMP` する。
- `.COM` は明示 `.COM` 入力のみ対象とし、raw binary を `$0100` へロードして `JSR $0100` 相当で呼ぶ。
- v3 の `.COM` は ROM `CMD` gateway から呼ばれるため、`.COM` 呼び出し前に stack を初期化しない。ROM 側の戻り先を保持したまま、`.COM` の `RTS` 復帰後に resident が carry clear で戻る。

## 対象外

- `FOO` から `FOO.COM` を補完探索する処理。
- FAT write。
- BASIC SAVE/LOAD adapter。
- system 更新。
- v2 SDFS/68 の削除。

## 検証方針

- 固定LBA loader harness で `SDFS3SYS` を RAM へ配置し、ROM prompt の `CMD` 経由で確認する。
- fixture SD 上の S-Record / Intel HEX を `CMD LOAD` でロードし、dump 結果で書き込み先を確認する。
- `CMD RUN addr` が指定アドレスへジャンプすることを SWI break で確認する。
- entry record 付き S-Record を `CMD RUN path` で実行できることを確認する。
- `.COM` が実行され、引数tailが `X` / `B` で渡ることを確認する。
- 不正 `.COM`、entry なし `RUN path`、サイズ超過 `.COM` が `?` でエラー復帰することを確認する。

## 関連

- #282: 対応Issue。
- #272: v3 phase 1 実装epic。
- #273: v3設計epic。
- #280: resident `DIR` / `TYPE` 接続。
- #281: resident `CMD_DISPATCH` parser。
