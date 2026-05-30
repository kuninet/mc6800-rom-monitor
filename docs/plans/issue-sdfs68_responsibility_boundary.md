# Issue #136 SDFS/68 責務境界整理

## 背景

SDFS/68 v1 では、ROM `BOOT` から固定LBA stage1を読み、stage1がFAT rootの `SDFS.BIN` を起動し、SDFS/68側で `L filename` によるS-Record / Intel HEXロードまでできるようになった。

一方で、SDFS/68に機能を足していくと、ROMモニタの延長なのか、第2段DOSなのかが曖昧になりやすい。v2へ進む前に、操作性と責務の境界を固定する。

## 採用方針

- ROMモニタは、電源投入直後の救命具、デバッガ、復旧口として扱う。
- ROMモニタの本線は、メモリダンプ、メモリ変更、指定アドレス実行、ブレークポイント、再開、逆アセンブルなどの低レベル操作とする。
- stage1は、SD/FATを読むboot servicesであり、ユーザー操作面には出さない。
- SDFS/68は、通常運用のための小さい第2段DOSとして扱う。
- SDFS/68内で `M`、`B`、`C`、`R`、`U` などのROMモニタ機能を再実装しない。
- SDFS/68でのプログラム起動は `RUN` を本線にする。
- 低レベルデバッグ、メモリ変更、逆アセンブルは `EXIT` でROMモニタへ戻って行う。
- ROM常駐FAT `DIR` / `LF` は `sbcio` profileの互換機能として扱い、SDFS/68本線へ新しいファイル操作を移す。
- `BOOT` はSDFS/68を起動する入口であり、ROMにDOS機能を増やす入口ではない。

## 操作モデル

通常運用は次の流れを本線にする。

```text
] BOOT
SDFS/68
SDFS> DIR
SDFS> RUN HELLO.S
```

デバッグ時はSDFS/68からROMモニタへ戻る。

```text
SDFS> LOAD TEST.S
SDFS> EXIT
] U0200
] M0200
] BOOT
SDFS>
```

`EXIT` はSDFS/68からROMモニタへ戻る明示的な出口であり、SDFS/68をモニタ機能で肥大化させる代わりに使う。

## 対象外

- SDFS/68内へのROMモニタ機能の移植。
- 本格的な実行ファイル形式。
- `FOO` 入力で `FOO.COM` を探すトランジェントコマンド。
- ユーザープログラムからSDFS/68へ戻るABI。
- FAT write、subdirectory、LFN、direct read API。

## 後続

- #137 でSDFS/68 v2全体の基本操作ロードマップを管理する。
- #138 以降で `DIR`、`TYPE`、`RUN`、`LOAD`、`EXIT` を子Issueとして実装する。
