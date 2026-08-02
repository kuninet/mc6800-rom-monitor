# Issue #277 SDFS/68 v3 固定LBA loader harness

## 背景

#278で `SDFS3SYS` header付きsystem imageを生成できるようになった。
次の段階では、固定LBAから `SDFS3SYS` を読み、headerを検査してresident payloadを `SDFS_LOAD_BASE` へ配置し、ROM側の `SDFS3_FIND_API` で検出できることを確認する必要がある。

## 採用方針

- v2の `BOOT -> stage1 -> SDFS.BIN` 経路は変更しない。
- #277では恒久ROMコマンドを追加せず、エミュレータテスト用のRAM loader harnessで固定LBAロードを検証する。
- 固定LBAは暫定で `64` を使う。v2のstage1固定LBA `16` とは分け、将来のv3 system領域設計で最終決定する。
- loader harnessはROM内の `SD_INIT`、`SD_READ_SECTOR`、`SDFS3_FIND_API` を呼び出す。
- 初期stubの `SDFS3SYS` は1 sector内に収まるため、harnessは1 sector imageとして検証する。16KB級residentの複数sector loaderは後続で扱う。

## ROMへ入れない判断

`sbcio_4000` profileのROMは #278 時点で `8075/8192 bytes` まで使用しており、残りは117 bytes程度である。
`SDFS3SYS` のmagic、version、load address、size、checksum、payload copy、resident検出までを恒久ROMコマンドとして追加するには不足する。

そのため、このIssueでは「固定LBA system imageを読んでresident化できるか」を先に検証し、恒久的な `BOOT3` または `BOOT` 拡張はROMサイズ削減、16KB ROM、bank loaderのいずれかの判断後に分ける。

## 検証内容

`tests/test_sdfs68_v3_build.py` に次を追加する。

- `make sdfs3sys MONITOR_PROFILE=sbcio_4000` で生成した `SDFS3SYS` をLBA 64へ配置する。
- RAM loader harnessをmonitorの `M` コマンドで `$0300` へ置き、`G0300` で実行する。
- 正常系ではpayload全体が `SDFS_LOAD_BASE` へ配置され、`SDFS3_FIND_API` が成功することを確認する。
- bad magic、bad version、bad load address、bad size、bad checksum、resident API header不正、SD read failureを拒否する。

## 対象外

- 恒久ROMコマンド `BOOT3` の追加。
- `BOOT` の既定動作変更。
- 複数sector `SDFS3SYS` のロード。
- system slot A/B、active marker、FAT write。

## 関連

- #277: 対応Issue。
- #272: v3 phase 1 実装epic。
- #257: 固定LBA system image形式と1発ロード方式。
- #275: ROM側resident header検出。
- #278: SDFS3SYS system image生成。
