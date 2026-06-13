# Issue #209 MITS Altair 680 BASICの浮動小数点BASIC候補としての移植性

## 背景

`third_party/sbc6800_datapack/MA680BAS.s` は、SBC6800用MIKBUGで動作する MITS Altair 680 BASIC Version 1.1 Rev 3.2 とされている。
MC6800で小数点を扱えるBASIC候補として、SDFS/68からロード/起動できるか、現行メモリ配置と衝突しないか、SAVE/writeとどう接続するかを確認する。

## 確認した事実

- `MA680BAS.s` 冒頭は `ALTAIR BASIC for 6800`、`MITS-RAW.BIN` と記載されている。
- S-Recordは `$0000` から始まる。
- ファイル末尾付近には `TO PATCH BASIC TO SWTP WITH ACIA AT PORT1`、`JAN 11 1978 MICHAEL HOLLEY`、`REV4 SEPT 4,1978` とある。
- 同じ末尾に `PORTED TO MIKBUG ON SBC6800`、`BY @haserin09 on twitter`、`FEB 9 2021` とあり、SBC6800上のMIKBUG向け移植であることが示されている。
- patch recordは `$1F80` 付近に配置されている。
- `START ADDRESS $0000` と明記されている。
- `filelist.txt` では `MA680BAS.s` が「SBC6800用MIKBUGで動作するMITS Altair680 BASIC VER1.1 REV3.2」と説明されている。
- DeRampの Altair Basic for the 6800 ページでは、Altair 680 BASICのI/OはAltair 680B monitor ROM前提で、SWTPC 6800 + MP-S serial port向けpatchが提示されている。
- 同ページの実行例では、BASICをロードしてpatchを重ね、`$J 0000` で起動している。
- 実行例には `MEMORY SIZE?`、`TERMINAL WIDTH?`、`WANT SIN-COS-TAN-ATN?` があり、`MITS ALTAIR 680 BASIC VERSION 1.1 REV 3.2` と表示される。
- 実行例では `PRINT 4+3`、FOR/NEXT、`LIST`、`RUN` が動作している。

根拠:

- `third_party/sbc6800_datapack/MA680BAS.s`: 冒頭とS-Record開始は行1-5。
- 同: BASIC内文字列には `MITS ALTAIR 680 BASIC VERSION 1.1 REV 3.2` と読めるデータが含まれる。行430-436。
- 同: patch説明とSBC6800移植メモは行440-446。
- 同: patch recordとstart addressは行448-454。
- `third_party/sbc6800_datapack/filelist.txt`: `MA680BAS.s` の説明は行16。
- DeRamp `Altair Basic for the 6800`: I/O前提、patch、起動例、`MEMORY SIZE?` / `TERMINAL WIDTH?` / `WANT SIN-COS-TAN-ATN?` / version表示 / `LIST` / `RUN` の例が掲載されている。

参照URL:

- https://deramp.com/swtpc.com/Altair/Altair_Basic.htm
- https://en.wikipedia.org/wiki/Altair_BASIC

## SDFS/68適合性

SDFS/68からの実機確認候補として有力である。

- ローカル資産がS-Record形式なので、SDFS/68の `LOAD` / `RUN` 経路へ載せやすい。
- 起動番地は `$0000` であり、`RUN MA680BAS.S` のようにentry recordを含められれば制御を渡せる。
- `$0000` 起点で低RAMを広く使うため、BASIC起動後はSDFS/68へ戻る前提にしない。
- 現行のSDFS/68本体、stage1、SD/FAT workは `sbcio_vdg` では `$C000-$DFFF`、`k6802_vdg` では `$A000-$BFFF` 側にあるため、BASIC本体が低RAM中心なら同居余地はある。
- patchが `$1F80` 付近に入るため、MIKBUG互換ワークや旧来スタックと衝突しないかは実機/エミュレータで確認する必要がある。
- 起動時に `MEMORY SIZE?` を聞くため、SDFS/68やVDG VRAM、work RAMを含まない低RAM終端を答える運用が必要である。

## 浮動小数点BASICとしての評価

浮動小数点BASIC候補として、現時点では最優先で実機確認する価値がある。

- `WANT SIN-COS-TAN-ATN?` の実行例があり、少なくとも三角関数を選択可能な構成である。
- Altair BASIC系はMicrosoft BASIC系の流れであり、整数Tiny BASICより「ちゃんとしたBASIC」に近い。
- DeRampの実行例は `PRINT 4+3` までだが、起動時質問から数学関数テーブルを持つことが分かる。
- 小数点演算そのものはローカル実行で `PRINT 1.5+2.25` などを確認する必要がある。

## BASICソースLOAD/SAVE

`LIST` と `RUN` は実行例で確認できる。
一方で、SDFS/68のFAT writeは未実装なので、BASICの `SAVE` が使えたとしてもSD上FATファイルへ直接保存する経路はまだない。

当面の扱い:

- LOAD: BASIC本体起動後、BASICが持つLOAD相当機能があるかを確認する。なければテキスト入力ストリーム支援へ回す。
- SAVE: BASICの `LIST` 出力を保存する案と、BASIC内部形式を保存する案を分けて検討する。
- FAT write: #83で新規ファイル作成、上書き、flush、電源断耐性を扱う。

## 推奨する確認手順

1. `MA680BAS.s` をSDFS/68用system SDへ置く。
2. SDFS/68から `LOAD MA680BAS.S` でロードできるか確認する。
3. entry recordがない場合は、`RUN 0000` で起動する。
4. 起動時に `MEMORY SIZE?` へ低RAM終端を指定する。初期候補はSBC6800互換の範囲で安全側に寄せる。
5. `TERMINAL WIDTH?` はVDG 32桁の場合に32を試す。UART併用時は80も確認する。
6. `WANT SIN-COS-TAN-ATN?` は `Y` と `N` の両方で空き容量と動作を確認する。
7. `PRINT 1.5+2.25`、`PRINT SIN(1)`、`10 FOR N=1 TO 10`、`LIST`、`RUN` を確認する。
8. BASIC終了/脱出はSDFS/68復帰ではなく、ROMモニタへの復旧またはリセット扱いにする。

## リスク

- `$0000` 起点のため、direct pageと低RAMを広く占有する。
- patchが `$1F80` 付近を使うため、MIKBUG互換ワーク、旧来スタック、BASIC側メモリ上限指定の整理が必要である。
- `MEMORY SIZE?` の回答を誤ると、BASICプログラム領域やSDFS/68関連領域を破壊する可能性がある。
- Altair 680B monitor ROM前提のI/OとSBC6800 MIKBUG patchの関係を、現行ROMのMIKBUG互換入口で再確認する必要がある。
- ライセンス/再配布条件は `third_party/sbc6800_datapack` 既存資産の扱いを超えて新規取得する場合には別途確認する。

## 判断

MITS Altair 680 BASICは、MC6800で小数点を扱えるBASIC候補として最有力である。
ただし、SDFS/68上の「戻るコマンド」ではなく、SDFS/68からロードして制御を渡し切るアプリケーションとして扱う。
実装候補としては、電大版Tiny BASICでSDFS/68起動とテキストLOADの筋を確認した後、浮動小数点BASIC本命として実機確認へ進める。

## 対象外

- Altair 680 BASIC本体の逆アセンブルやパッチ作成。
- SDFS/68へ戻る復帰ABI。
- FAT write実装。
- BASICの内部形式SAVE対応。

