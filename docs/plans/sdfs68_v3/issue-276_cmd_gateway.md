# Issue #276 SDFS/68 v3 ROM CMD gateway

## 背景

#275でROM側がRAM上の `SDFS3API` headerを検出できるようになり、#279でslot 7/8を含む最小API数の確認も `api_count>=9` へ更新した。
次の段階として、ROMモニタのコマンド入口からresident API slot 1 `SDFS3_CMD_DISPATCH` を呼び出せる必要がある。

このIssueでは `DIR` / `TYPE` / `LOAD` / `RUN` の実処理には入らず、ROM側の `CMD <tail>` gatewayとresident dispatch stub呼び出しだけを実装する。

## 採用方針

- `CMD <tail>` は `FEATURE_SD=1` かつ `S1_SUPPORTED=1` のROMで有効にする。
- 先頭 `C` は既存のbreak clearと競合するため、`CMD ` を先に判定し、不一致なら従来の `C` 処理へ落とす。
- `CMD` 単体と `CMDX` は曖昧な入力として `?` を返す。
- 呼び出し規約は #259 に合わせ、`A=0`、`B=tail length`、`X=tail pointer` とする。
- `CMD DIR` では `X=LINE_BUF+4`、`B=3` を渡す。
- jump tableは `fdb` のアドレス表として扱い、slot 1の2バイトを読んで実アドレスへ間接呼び出しする。
- MC6800では `X` 引数と `X` 間接呼び出しが衝突するため、stack上に戻り先とdispatch先を積む `RTS` trampolineで呼ぶ。
- dispatchがcarry setで戻った場合はROM側で `?` を表示して `]` へ戻る。

## 検証方針

- resident未ロードで `CMD DIR` が `?` を返してROMモニタへ戻ることを確認する。
- RAMへテスト用 `SDFS3API` header、jump table、slot 1 dispatch stubを置き、`CMD DIR` でstubが呼ばれることを確認する。
- stub側で受け取った `A`、`B`、`X` をメモリへ保存し、`A=0`、`B=3`、`X=LINE_BUF+4` を確認する。
- `H` のhelp表示に `CMD` が含まれることを既存smoke testで確認する。
- コード変更なので `make test` を実行する。

## 対象外

- `DIR` / `TYPE` / `LOAD` / `RUN` の実処理。
- 固定LBA `SDFS3SYS` loader実装。
- FAT/SD処理との接続。
- BASIC SAVE/LOAD実装。

## 関連

- #276: 対応Issue。
- #272: v3 phase 1 実装epic。
- #256: ROM command dispatch設計。
- #259: resident API最小セット。
- #275: ROM側resident header検出。
- #279: GET_MEMTOP / GET_CAPS API。
