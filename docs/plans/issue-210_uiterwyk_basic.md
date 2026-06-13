# Issue #210 Robert Uiterwyk 4K/8K BASICの浮動小数点候補調査

## 背景

Robert UiterwykのSWTPC系BASICは、MC6800向けの浮動小数点BASIC候補として重要である。
MicroBasic 1.3はローカルの `third_party/sbc6800_datapack/MICBAS13.ASM` に含まれているが、4K/8K版は別系統として機能が拡張されているため、SDFS/68へ載せる候補として調査する。

## 参照資料

- Robert Uiterwyk's BASIC: https://deramp.com/swtpc.com/BASIC_2/Uiterwyk.htm
- Robert Uiterwyk's Micro Basic: https://deramp.com/swtpc.com/NewsLetter1/MicroBasic.htm
- Micro-BASIC Version 1.3 PDF: https://deramp.com/swtpc.com/NewsLetter1/MicroBasic.pdf
- SWTPC 8K BASIC manual PDF: https://deramp.com/swtpc.com/BASIC_2/SWTPC_8K_BASIC.pdf

## 確認した事実

- DeRamp/SWTPC掲載資料には、Uiterwyk BASICの紹介ページ、Micro Basic 1.3の解説、Micro Basic 1.3のPDF、8K BASIC manual PDFへのリンクがある。
- Micro Basic 1.3は、1976年6月のSWTPC newsletterにソースが掲載されたTiny BASIC系で、整数演算のみ、変数はA-Zの26個、文字列変数は未対応である。
- Micro Basic 1.3のページには Source Code と 6800 S1 Load File へのリンクがある。
- Micro Basic 1.3は MIKBUG と MP-C interface cardを必要とする、と説明されている。
- Uiterwykは1976年時点で4Kの浮動小数点BASICに取り組んでいた。
- SWTPCは4K BASICを販売し、後に8K版も販売した。
- 4K BASICはBCD演算を使い、9桁精度、範囲は `10E99` と説明されている。
- BCD演算のため計算は遅いが、Altair 680B BASICの6桁精度より正確だったと説明されている。
- 8K版では文字列変数と三角関数が追加された。
- Uiterwyk BASICにはdisk版やmulti-user版も存在した。
- 1978年1月にUiterwykはソースコードの権利をMotorolaへ売却した、と説明されている。

## 未確認事項

- 4K/8K版のロードファイル本体、完全なソース、内部メモリ配置はまだ確認していない。
- 8K manual PDFの本文詳細は未精査であり、文字列機能、三角関数名、エラー動作は未確認である。
- 4K/8K版がMicro Basic 1.3と同じくMIKBUG/MP-C interface cardを前提にするかは未確認である。
- 明示的な再配布ライセンスは見つかっていない。
- したがって、現時点では外部資料として参照し、`third_party` への取り込みは保留する。

## SDFS/68適合性の見立て

Uiterwyk 4K/8K BASICは、浮動小数点BASIC候補として有望だが、現時点ではローカルで即実行できる候補ではない。

- 4K版はBCD浮動小数点があり、整数Tiny BASICより実用BASICに近い。
- 8K版は文字列変数と三角関数があり、スタンドアロン機としての利用価値は高い。
- ただし、現行リポジトリには4K/8K版の実体ファイルがなく、ロード範囲やI/O入口を確定できない。
- MIKBUG/MP-C依存が残っている場合、現行ROMのMIKBUG互換I/O入口で吸収できる可能性はある。
- SDFS/68から起動する場合は、電大版Tiny BASICや `MA680BAS.s` と同様、S-Recordとしてロードして制御を渡し切る方式が第一候補になる。
- BASIC起動後にSDFS/68へ戻る常駐復帰は前提にしない。

## third_party取り込み方針

現時点では、4K/8K版の `third_party` 取り込みは行わない。

理由:

- 明示的な再配布ライセンスが確認できていない。
- Uiterwykがソースコード権利をMotorolaへ売却したという記述がある。
- DeRamp/SWTPC掲載資料は調査・参照元として有用だが、リポジトリへ再配布するには根拠が不足している。

取り込む場合の条件:

- 入手元URL、取得日、ファイル名、原文の権利表示を記録する。
- ライセンスまたは再配布許諾の扱いを `third_party` 配下のREADMEへ明記する。
- まずはロードファイルだけでなく、マニュアルと起動手順をdocsへ整理する。

## MITS Altair 680 BASICとの比較

- MITS Altair 680 BASICはローカルに `MA680BAS.s` があり、SDFS/68からの実機確認に進みやすい。
- Uiterwyk 4K/8K BASICは、精度や8K版の文字列/三角関数という点で魅力がある。
- ただし、現時点では入手物の扱いとメモリ配置が未確定であるため、実機確認順は #209 MITS Altair 680 BASICを先にする。
- Uiterwyk 4K/8K BASICは、浮動小数点BASIC候補の第2本線として、権利確認と実体ファイル確認から始める。

## 推奨する後続作業

1. DeRamp掲載の4K/8K BASIC関連ファイルを洗い出す。
2. 各ファイルについて、ソース、S1 load file、manual、patchの区別を整理する。
3. ライセンス/再配布可否を確認し、`third_party` へ入れるか外部参照に留めるか決める。
4. ロードファイルが確認できた場合、ロード範囲、起動番地、I/O入口、MIKBUG/MP-C依存を調べる。
5. MITS Altair 680 BASIC実機確認後、Uiterwyk 4K/8K BASICを比較対象として試すか判断する。

## 判断

Uiterwyk 4K/8K BASICは、MC6800で小数点を扱えるBASIC候補として残す。
ただし、現時点ではローカル実体がある `MA680BAS.s` を先に実機確認し、Uiterwyk 4K/8K BASICは権利・入手性・メモリ配置確認を先行させる。

## 対象外

- 4K/8K BASICファイルのリポジトリ取り込み。
- BASIC本体のパッチ作成。
- SDFS/68ファイルI/O連携実装。
- FAT write実装。

