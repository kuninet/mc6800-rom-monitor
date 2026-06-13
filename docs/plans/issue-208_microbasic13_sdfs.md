# Issue #208 SWTPC MicroBasic 1.3のSDFS/68適合性

## 背景

`third_party/sbc6800_datapack/MICBAS13.ASM` は Robert H. Uiterwyk による MicroBasic 1.3 で、SBC6800データパックに含まれる既存BASIC資産である。
電大版Tiny BASICの代替候補として、SDFS/68からロード/起動する価値、BASICソースLOAD/SAVE支援の必要性、低RAM衝突を確認する。

## 確認した事実

- ソース冒頭に、Motorola MIKBUG ROM と関連128 byte RAMを前提にし、前提が違う場合は `SP` と `XSTACK` を移す必要があると書かれている。
- direct pageは `ORG $20` から始まり、`INDEX1`、`SAVESP`、`NEXTBA`、`SOURCE`、`BASLIN`、`XSTACK`、`MEMEND` などを置く。
- `XSTACK` の初期値は `$1F7F`、`MEMEND` は `$0FFF` である。
- 行入力バッファは `ORG $00B0` の `BUFFER RMB $50` である。
- 本体は `ORG $0100` から始まり、`PROGM JMP START` を置く。
- コマンド表には `RUN`、`LIST`、`NEW`、`PAT`、`GOSUB`、`GOTO`、`SIZE`、`PRINT`、`INPUT`、`DIM`、`FOR`、`NEXT` などがある。
- コマンド表上に `LOAD` と `SAVE` は見当たらない。
- 入出力は `OUTEEE=$E1D1` と `INEEE=$E1AC` を使う。
- `BREAK` は `PIAD=$8004` を読むため、現行ハードウェアで意味があるか確認が必要である。
- `LIST` は内部形式のプログラム行をテキストへ戻して出力する。
- `READY` / `NEWLIN` / `RUN` はスタックや `XSTACK` を `$1F45` / `$1F7F` に戻す。
- `PAT` は `CONTRL=$E0E3` へ戻るため、MIKBUG/モニタ側へ逃げるためのパッチ入口として使われている。

根拠:

- `third_party/sbc6800_datapack/MICBAS13.ASM`: MIKBUG前提とSP/XSTACK注意は行6-11。
- 同: direct pageワーク、`XSTACK`、`MEMEND` は行13-49。
- 同: 入力バッファと本体 `ORG $0100` は行51-58。
- 同: コマンド表は行61-123。
- 同: 行入力とプロンプト処理は行146-185。
- 同: `OUTEEE` / `INEEE` / `PIAD` は行187-204。
- 同: `LIST` / `OUTLIN` は行284-321。
- 同: `READY` / `RUN` / `CLIST` / `PATCH` は行759-859。

## SDFS/68適合性

MicroBasic 1.3はSDFS/68からロードして試す価値はあるが、最初の本線候補としては電大版Tiny BASICより一段重い。

- `ORG $0100` で始まるため、SDFS/68のS-Record `RUN` から起動しやすい。
- 一方で、`MEMEND=$0FFF` と `XSTACK=$1F7F` の前提が固定的で、BASICの作業領域は低RAM内に閉じる。
- SDFS/68本体やstage1は現行の `sbcio_vdg` / `k6802_vdg` ではwork RAM側にいるため、大きな衝突は避けられる見込みである。
- `PAT` が `CONTRL=$E0E3` へ戻るため、SDFS/68へ戻るのではなくROMモニタへ戻る系統として扱う。
- `PIAD=$8004` を読むBREAK処理は、SBC6800データパック前提のままなので、現行SBC-IO/VDG/keyboard構成では無効化または再解釈が必要になる可能性がある。

## BASICソースLOAD/SAVE適合性

MicroBasic 1.3は、BASICソースLOAD/SAVEの直接候補としては弱い。

- `LIST` はあるため、プログラムをテキストとして出力する経路はある。
- `LOAD` コマンドが見当たらないため、SD上テキストをBASIC行として取り込むには、行入力へ流し込む外部支援が必要である。
- `SAVE` コマンドも見当たらないため、保存は `LIST` 出力を捕まえる方式に限定される。
- BASIC内部形式を直接保存する案は、MicroBasic固有の行圧縮/キーワード表に依存するため、電大版Tiny BASICより先に選ぶ理由は薄い。

## 浮動小数点の見立て

この `MICBAS13.ASM` からは、浮動小数点BASICとして扱える根拠は見つからない。
演算処理は16bit整数中心に見えるため、浮動小数点候補としては #209 MITS Altair 680 BASIC、#210 Robert Uiterwyk 4K/8K BASICを優先する。

## 推奨する後続作業

1. S-Record化済みの `MICBAS13.HEX` / `MICBAS13.S` 相当をSDFS/68から `LOAD` / `RUN` できるか確認する。
2. 起動後に `PRINT 1+2`、`10 PRINT 1`、`RUN`、`LIST` を確認する。
3. `PAT` がROMモニタへ戻る挙動を確認し、SDFS/68へ戻らない前提を明記する。
4. `PIAD=$8004` 依存を現行ボードで無効化すべきか判断する。
5. BASICソースLOAD/SAVE支援はMicroBasic固有ではなく、電大版Tiny BASICと共通の「テキスト入力/出力ストリーム」課題として扱う。

## 判断

MicroBasic 1.3は既存SBC6800資産として比較対象に残す。
ただし、最初にBASICソースLOADまで進める候補は、`LOAD` コマンドを持つ電大版Tiny BASICを優先する。
MicroBasic 1.3は、整数BASIC候補の比較軸と、SDFS/68から既存SBC6800 BASIC資産を起動する確認用として扱う。

## 対象外

- MicroBasic 1.3本体のパッチ実装。
- `LOAD` / `SAVE` コマンド追加。
- FAT write実装。
- SDFS/68へ戻る常駐復帰ABI。

