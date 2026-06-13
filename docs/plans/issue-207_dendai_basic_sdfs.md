# Issue #207 電大版Tiny BASICのSDFS/68起動とテキストLOAD適合性

## 背景

電大版Tiny BASICは `third_party/DENDAI_BASIC` にソースがあり、現行SBC6800/MIKBUG互換I/Oへ寄せた `D-BASIC-SBC6800.ASM` も含まれている。
SDFS/68配下でBASICを最初に動かす候補として、ロードしやすさ、低RAM衝突、BASICソースのテキストLOAD適合性を確認する。

## 確認した事実

- `D-BASIC-SBC6800.ASM` はBASICプログラム領域を `RAMSSS=$0980` から `RAMEEE=$1EFF` に置く。
- direct pageのワークは `ORG $1A` から始まり、`BUFFER`、式スタック、FOR/SUBスタック管理ポインタを低RAMへ置く。
- スタックは `STACK=$1F47`、`SUBSTK=$1F80` で、従来の8KB RAM上端付近を使う。
- 入出力は `INEEE=$E1AC` と `OUTEEE=$E1D1` を使うため、現行ROMモニタのMIKBUG互換文字I/O入口と相性がよい。
- `POLCAA` は `ACIACS=$8018` を直接読んでBREAK検出する。VDG+keyboard本線では、1st ACIA状態を読む設計のままでよいか確認が必要である。
- `LOAD` はBASICの行入力モードへ入り、`LOADM` が制御文字 `02` を待ってからテキスト行を取り込む構造である。
- `LIST` はプログラム行をテキストとして通常出力へ出し、最後に制御文字 `03` を出す。
- コマンド表には `LIST`、`LOAD`、`RUN`、`EX`、`AUTO`、`NEW` がある。ユーザーコマンドとしての `SAVE` は見当たらない。

根拠:

- `third_party/DENDAI_BASIC/D-BASIC-SBC6800.ASM`: `RAMSSS` / `RAMEEE` / `ACIACS` は行6-8。
- 同: direct pageワークと `STACK` / `SUBSTK` は行10-36。
- 同: `INEEE` / `OUTEEE` / `RESET` は行41-43。
- 同: `LOADM` / `GTLINE` / 行入力処理は行49-81。
- 同: `LOAD` は行134-136。
- 同: `START` 初期化と `RAMEND` 設定は行151-180。
- 同: `LIST` / `LISTX` は行1129-1173。
- 同: コマンド表は行1209-1222。
- 同: `INFFF` / `POLCAA` は行1289-1300。

## SDFS/68適合性

最初のSDFS/68起動候補としては有望である。

- SDFS/68の `.COM` は `$0100` 固定ロード、`RTS` 復帰前提であるため、BASIC本体のように制御を渡し切るプログラムにはそのまま合わない。
- 現行の `RUN path/file` はS-Record専用で、entry recordがある場合にジャンプできる。電大版BASICはS-Record化して `RUN DENBAS.S` のように起動する方針が自然である。
- `D-BASIC-SBC6800.ASM` は `ORG $100` で `JSR START` 後に `JMP CONTRL` するため、SDFS/68から起動した後はBASIC側へ制御を渡し切る扱いにする。
- SDFS/68へ戻る通常経路は前提にしない。BASICからROMへ戻る `EX` は `RESET=$E0D0` を呼ぶため、SDFS/68へ戻るのではなくROMモニタ再起動/再入口相当として扱う。
- `sbcio_vdg` / `k6802_vdg` では `USER_RAM_END=$7FFF` なので、BASICの `$0100-$1EFF` とスタック `$1F47` / `$1F80` はSDFS/68本体やstage1のwork RAMとは分離できる。

## BASICソースLOAD案

電大版BASICの `LOAD` はファイル名指定ではなく、コンソール入力からBASIC行を読む作りである。
そのため、最初の実装案はBASIC本体にFAT処理を入れず、SDFS/68側または小さい支援プログラムでテキストをコンソール入力相当に流し込む方式がよい。

候補:

1. ホスト側でBASICソースをS-Record化し、BASIC起動後に貼り付ける運用から始める。
2. SDFS/68へ `TYPE` 実装後、手動でBASICの `LOAD` と組み合わせる。ただし端末入力へ戻す機構は別に必要。
3. 後続Issueで「BASIC入力ストリーム」支援をSDFS/68に追加し、BASICの `INEEE` 呼び出しへSD上テキストを供給する。

現行SDFS/68の `LOAD` / `L` はS-RecordまたはIntel HEX用であり、BASICソースのプレーンテキストLOADではない。
したがって、BASICソースLOADは既存loaderに混ぜず、別Issueで「テキスト入力ストリーム」として設計する。

## SAVE案

電大版BASIC自身にはユーザーコマンドとしての `SAVE` が見当たらない。
保存は次のどちらかに分ける。

- 短期: `LIST` 出力をホスト側または将来のSDFS/68出力ストリームで捕まえ、テキストとして保存する。
- 中期: FAT write対応後に、SDFS/68側で新規ファイル作成・上書き・flush順序を設計し、`LIST` 出力をSDへ保存する。

FAT write本体は #83 の範囲であり、このIssueでは実装しない。

## 推奨する後続作業

1. 電大版BASICをS-Record化し、SDFS/68の `RUN` で起動できるか確認する。
2. `POLCAA` の `ACIACS=$8018` 直読みが現行ハードウェア構成で問題ないか確認する。
3. BASIC起動後、VDG+keyboard環境で `10 PRINT "HELLO"` / `RUN` / `LIST` / `LOAD` の手動確認を行う。
4. BASICソースLOAD支援は、SDFS/68の既存S-Record loaderではなく、別Issueのテキスト入力ストリームとして分割する。
5. SAVEは #83 と接続し、まずは `LIST` 出力保存を最小スコープにする。

## 対象外

- 電大版BASIC本体の移植パッチ実装。
- SDFS/68のテキスト入力ストリーム実装。
- FAT write実装。
- BASICからSDFS/68へ戻る常駐復帰ABI。

