# Issue #206 Microsoft BASIC-68 / TSC BASIC系のFLEX依存とSDFS/68移植可能性

## 背景

Microsoft BASIC-68、TSC Micro Basic Plus、TSC Extended BASICは、MC6800で小数点を扱える可能性があるBASIC候補として挙がった。
一方で、これらはFLEXやディスクOS文脈のBASICである可能性が高く、現行SDFS/68へ直接載せる候補か、将来のFLEX互換/別DOS候補へ回すべきかを分けて整理する。

## 参照資料

ローカル:

- `docs/testing/sbc6800_datapack.md`
- `docs/requirements/monitor_requirements.md`
- `docs/design/memory_map.md`
- `third_party/sbc6800_datapack/README.md`
- `third_party/sbc6800_datapack/MICBAS13.ASM`
- `third_party/sbc6800_datapack/MA680BAS.s`
- `third_party/sbc6800_datapack/MIKBUG.ASM`

外部:

- Microsoft BASIC: https://en.wikipedia.org/wiki/Microsoft_BASIC
- FLEX operating system: https://en.wikipedia.org/wiki/FLEX_%28operating_system%29
- Technical Systems Consultants: https://en.wikipedia.org/wiki/Technical_Systems_Consultants
- bitsavers Microsoft archive: https://bitsavers.org/pdf/microsoft/

## 確認した事実

### ローカル資産

- `third_party/sbc6800_datapack` は、MIKBUG固定入口の調査、既存プログラム互換確認、smoke test回帰データとして使われている。
- `MICBAS13.ASM` はMicroBasic 1.3で、MIKBUG ROMと関連128 byte RAMを前提にしている。
- `MA680BAS.s` は `ALTAIR BASIC for 6800` と始まり、末尾に `PORTED TO MIKBUG ON SBC6800` とある。
- `MIKBUG.ASM` は `OUTCH`、`INCH`、`PDATA1`、`CONTRL` などの入口を持つMIKBUG実装例である。
- 現行ROMモニタは、`OUTCH=$E075`、`INCH=$E078`、`PDATA1=$E07E`、`CONTRL=$E0E3`、`INEEE=$E1AC`、`OUTEEE=$E1D1` を互換対象として扱っている。

### Microsoft BASIC-68

- Microsoft BASICの資料では、BASIC-68がMotorola 6800向け、BASIC-69がMotorola 6809向けとして存在したとされている。
- BASIC-68 / BASIC-69はFLEX operating system上で提供されたと説明されている。
- Microsoft BASIC-68はBASIC-80の中核機能を引き継いだ系統とされる。
- Microsoft Software Catalogが参照元として挙げられているが、今回の調査ではBASIC-68の一次資料本文までは確認できていない。

### TSC BASIC系

- FLEXはTechnical Systems Consultantsが1976年にMotorola 6800向けに開発したディスクベースOSである。
- FLEXは256 byte sectorを使うディスクOSで、各sector内のlinkage byteでファイルやfree listをつなぐ構造と説明されている。
- FLEX向けには、標準BASIC、Extended BASIC、Extended BASICのtokenizing版であるPre-compiled BASICが提供されていたと説明されている。
- TSCはFLEX、mini-FLEX、FLEX09、UniFLEXのほか、複数のBASIC変種、FORTRAN、Pascal、C、assemblerなどを提供していた。

## 未確認事項

- Microsoft BASIC-68の実体ファイル、ロード形式、起動番地、I/O入口は未確認である。
- Microsoft BASIC-68の一次資料本文は未確認であり、現時点では二次情報に基づく候補である。
- TSC Micro Basic Plus、TSC Extended BASICという製品名と、FLEX資料上の標準BASIC、Extended BASIC、Pre-compiled BASICの対応関係は未確定である。
- TSC BASIC系の6800版実体ファイル、DOS call一覧、メモリ配置、ファイルI/O仕様は未確認である。
- 権利面、再配布可否、`third_party` 取り込み可否は未確認である。

## SDFS/68移植性

現行SDFS/68へ直接載せる候補としては優先度を下げる。

理由:

- BASIC-68 / TSC BASIC系はいずれもFLEXまたはディスクOS前提の可能性が高い。
- LOAD/SAVEやファイルI/OがDOS callへ依存している場合、SDFS/68のread-only loaderとは接続できない。
- FLEXは256 byte sectorの独自ディスク構造で、SDFS/68のFAT32 read-only方針とはファイルシステム層が異なる。
- DOS依存を剥がして単体BASICとして動かすには、I/O、ファイル、メモリ管理、起動環境を広く調べる必要がある。
- 現行リポジトリには即実行できるBASIC-68 / TSC BASIC実体がない。

一方で、将来候補としては価値がある。

- Microsoft BASIC-68が確認できれば、MC6800向けのMicrosoft系BASICとして浮動小数点BASIC候補になる。
- TSC BASIC系はFLEXとの相性が強いため、将来FLEX互換、FLEX移植、または別DOS棚で扱う候補になる。
- #166 副CPUディスク装置や将来のファイルサービスABIが進む場合、DOS依存BASICを受ける余地が増える。

## 現行候補との比較

- 電大版Tiny BASIC: ソースがあり、MIKBUG互換I/Oで動かしやすい。整数BASIC。
- MicroBasic 1.3: ローカルにソースがあり、既存SBC6800資産として比較しやすい。整数BASIC。
- MITS Altair 680 BASIC: ローカルにS-Recordがあり、浮動小数点BASIC候補として先に実機確認しやすい。
- Uiterwyk 4K/8K BASIC: 浮動小数点候補として魅力があるが、権利確認と実体ファイル確認が先。
- Microsoft BASIC-68 / TSC BASIC系: 機能面では魅力があるが、FLEX依存のため現行SDFS/68直載せ候補としては最後に回す。

## 推奨する後続作業

1. bitsaversやFLEX User Group資料から Microsoft BASIC-68 の一次資料を探す。
2. TSC BASIC系の製品名、標準BASIC、Extended BASIC、Pre-compiled BASICの対応を確認する。
3. 実体ファイルが見つかった場合、ロード形式、起動番地、DOS call、I/O入口を調べる。
4. SDFS/68へ載せるのではなく、FLEX互換/別DOS候補として棚を分けるか判断する。
5. 現行BASIC実機確認は、まず #207 電大版Tiny BASIC と #209 MITS Altair 680 BASICを優先する。

## 判断

Microsoft BASIC-68 / TSC BASIC系は、MC6800で小数点を扱えるBASIC候補として調査棚には残す。
ただし、現行SDFS/68上で短期に動かす候補ではない。
現時点では、FLEX依存と実体入手性の確認を先に行い、実装本線はローカル資産がある電大版Tiny BASIC、MicroBasic 1.3、MITS Altair 680 BASICを優先する。

## 対象外

- Microsoft BASIC-68 / TSC BASICファイルの取り込み。
- FLEX互換層の実装。
- SDFS/68のDOS call互換実装。
- FAT write実装。

