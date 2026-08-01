# Issue #260 SDFS/68 v3 メモリマップとBank RAM利用方針

## 対象

- 親Issue: #254
- 前提Issue: #257、#258、#259
- 本Issue: #260
- 関連Issue: #216、#233、#238

## 背景

SDFS/68 v3では、ROMモニタをコマンド入口、SDFS/68をRAM residentのSD/FAT serviceとして扱う。
#257ではsystem imageを固定LBAから一括ロードする案、#258では二重slotによるsystem領域更新案、#259ではresident APIをstage1 APIから切り離す方針を整理した。

残る大きな判断は、resident本体、ユーザーTPA、VRAM、SD/FAT work、Bank RAM windowをどこへ置くかである。
既存の #233 / #238 では `$4000-$7FFF` をSDFS固定16KB領域にする `ram64_4000_work` が実装候補として入っている。
一方、過去の128KBバンクメモリボード案は、固定RAMを `$0000-$3FFF`、16KB bank windowを `$4000-$7FFF`、追加8KB RAMを `$A000` 側へ置く構成で検討されていた。
v3では、この2系統を同じ前提として扱わず、phase 1の機能互換と将来拡張のどちらを優先するかで比較する。

## 前提

- v3 phase 1は、v2のUI互換ではなく機能互換を目標にする。
- phase 1で必要な機能は、`DIR`、`TYPE`、`LOAD`、`RUN`、`.COM` 相当までとし、BASIC SAVE/LOAD、FAT write、system更新実機コマンドは後続とする。
- SDFS/68 v3 resident APIは、stage1 APIと外部ABI互換にしない。
- 4GB以上のSDHC上に、先頭予約領域と2GB程度のFAT32 partitionを置く方針を前提にする。
- Bank RAMは、resident APIのcapabilityとして検出できる任意拡張にする。

## 候補比較

横並びでは次のように評価する。

| 候補 | 固定resident | Bank window | ユーザーTPA | VRAM衝突 | Bank RAM必須性 | #233/#238との整合 | 初期判断 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 案A: 16KB固定resident + 8KB bank window | `$4000-$7FFF` | `$A000` または `$C000` 8KB候補 | `$0000-$3FFF` | `$A000/$C000` VRAMと8KB windowが排他 | 任意 | 高い | v3 phase 1の本線候補 |
| 案B: 16KB bank window + 固定8KB resident | `$A000` または `$C000` 8KB候補 | `$4000-$7FFF` 16KB | `$0000-$3FFF`中心 | 固定8KB residentとVRAMが排他 | 実質必要 | 低い | 旧128KBボード活用候補 |
| 案C: Bank RAMなし | `$4000-$7FFF` | なし | `$0000-$3FFF` | 構成依存 | 不要 | 高い | 最小PoC候補 |
| 案D: 64KB Bank RAM | 構成依存 | 8KBまたは16KB候補 | 構成依存 | 構成依存 | 任意拡張 | 中 | cache/staging PoC候補 |
| 案E: 128KB Bank RAM | 構成依存 | `$4000-$7FFF` 16KB候補 | `$0000-$3FFF`中心 | 追加8KB RAM/VRAM配置次第 | 任意拡張 | 低い | 将来拡張候補 |
| 案F: 8KB resident目標 + 16KB予約枠 | 実体は8KB目標、枠は `$4000-$7FFF` | 任意 | 実装サイズ次第で `$0000-$5FFF` などへ拡張余地 | 16KB枠を全消費しなければ緩和 | 不要 | 中から高 | phase 1のサイズ目標 |

### 案A: `$4000-$7FFF` 固定16KB resident + `$A000/$C000` 8KB bank window

```text
$0000-$3FFF  user TPA
$4000-$7FFF  SDFS v3 resident fixed area
$8000-$9FFF  I/O / board dependent
$A000-$BFFF  VRAM or 8KB bank window candidate
$C000-$DFFF  VRAM or 8KB bank window candidate
$E000-$FFFF  ROM
```

良い点:

- #233 / #238 の `ram64_4000_work` と最も近い。
- resident本体、API header、work、stackを固定RAM上に置ける。
- Bank RAMなしでもv3 phase 1の機能互換を進められる。
- ROM/BASIC側は、resident API headerとmemtopを比較的単純に扱える。

懸念:

- ユーザーTPAは `$0000-$3FFF` の16KBに下がる。
- 旧128KBバンクボードの `$4000-$7FFF` 16KB bank windowをそのまま活かせない。
- 8KB bank windowを `$A000` または `$C000` に置く場合、VRAM配置と衝突しやすい。
- 8KB windowはFAT cacheやSAVE stagingには使えるが、16KB単位のresident差し替えには向かない。

### 案B: `$0000-$3FFF` 固定RAM + `$4000-$7FFF` 16KB bank window + 固定8KB resident

```text
$0000-$3FFF  fixed RAM / user base / monitor work candidate
$4000-$7FFF  16KB bank window
$8000-$9FFF  I/O / board dependent
$A000-$BFFF  fixed 8KB resident or VRAM candidate
$C000-$DFFF  fixed 8KB resident or VRAM candidate
$E000-$FFFF  ROM
```

良い点:

- 旧128KBバンクボード案と整合しやすい。
- 16KB単位のbank windowを、FAT cache、directory cache、file buffer、transient実行、BASIC SAVE/LOAD stagingに使いやすい。
- 128KB SRAMなら、固定16KB + 16KB window x7 bankという過去案の考え方を活かせる。

懸念:

- resident固定部を8KBへ抑える必要があり、v3本体を小さく保つ設計難度が上がる。
- resident本体をbank側へ置くと、ROM/BASICから常に呼べるAPI headerやdispatch入口を固定RAMへ残す必要がある。
- VRAMを `$A000` または `$C000` に置く構成とresident固定8KBが衝突しやすい。
- bank切り替え中の割り込み、BASIC連携、API呼び出し規約が複雑になる。

### 案C: Bank RAMなし

```text
$0000-$3FFF  user TPA
$4000-$7FFF  SDFS v3 resident fixed area
$8000-$DFFF  I/O / VRAM / board dependent
$E000-$FFFF  ROM
```

良い点:

- 実装と実機確認が最も単純。
- v3 phase 1の機能互換をBank RAMなしで検証できる。
- Bank制御回路、window競合、cache coherencyを後回しにできる。

懸念:

- FAT write、BASIC SAVE、directory cache、large bufferを追加すると苦しくなる。
- SD sector bufferやpath bufferを固定resident領域から削る必要がある。
- 8KB/16KBを超えるSDFS拡張を支える逃げ場が少ない。

### 案D: 64KB Bank RAM

32KB SRAM x2などで、小さいbank付き構成を作る案。
固定領域とwindowの取り方は実装回路次第だが、v3では「bankがあればcache/stagingに使う」任意拡張として扱う。

良い点:

- 手持ち部品で作れる可能性がある。
- 2GB級FAT運用では、directory cacheやfile bufferが少し増えるだけでも体感が良くなる。
- 128KB設計の前段PoCとして使える。

懸念:

- 16KB windowならbank数が少なく、cache以外の用途にはすぐ使い切る。
- 8KB windowならbank数は増えるが、制御とソフト管理が細かくなる。
- v3本線の必須前提にすると、Bank RAMなし構成を切り捨てることになる。

### 案E: 128KB Bank RAM

旧128KBバンクボード案を活かす構成。
過去案では `$0000-$3FFF` 固定16KB、`$4000-$7FFF` 16KB bank window、`$A000` 側に追加8KB RAMを置く考え方だった。

良い点:

- 16KB bank windowはアドレスデコードとソフト管理の粒度が扱いやすい。
- FAT cache、directory cache、file buffer、SAVE staging、transient領域を分けやすい。
- 将来のFAT writeやBASIC SAVE/LOADでは最も余裕がある。

懸念:

- v3 phase 1の必須条件にするとハードルが上がりすぎる。
- `$4000-$7FFF` をbank windowにすると、#238の固定16KB resident案とは別構成になる。
- resident固定部とVRAMの配置を別途決めないと、BASIC互換やVDG構成と衝突する。

### 案F: 8KB resident目標 + 16KB予約枠

SDFS/68 v3 resident本体を8KB以内へ押し込むことを目標にする案。
ただし、メモリマップ上は最初から16KB枠を候補として確保し、8KBに収まった場合だけ余りをbuffer、user TPA拡大、または将来機能用に戻す。

良い点:

- PC-8001 SD-DOSのように、上位側のコマンド入口へ処理を寄せれば8KB級residentでも成立する可能性がある。
- v3はROMモニタ側にcommand dispatchを持つため、residentから独立シェル、行入力、汎用コマンド解釈を減らせる。
- 8KBに収まれば、ユーザー領域やBASIC連携への圧迫を減らせる。
- Bank RAMなし構成でも導入しやすい。

懸念:

- FAT read、path処理、`.COM`、S-Record/Intel HEX、error表示だけでもすぐ膨らむ可能性がある。
- BASIC SAVE/LOAD、FAT write、system updateを同じ8KBへ入れるのは厳しい。
- サイズ最優先にしすぎると、API境界やテストしやすさを犠牲にしやすい。

8KB residentは「必達条件」ではなく「phase 1のサイズ目標」とする。
メモリマップとしては16KB枠を予約し、実装結果が8KBへ収まるかを測る。
収まった場合は、#260後続のメモリマップIssueで `memtop` を上げる、bufferへ使う、または8KB固定resident構成を正式化する。

## 採用する初期判断

v3 phase 1では、案Aまたは案Cに近い「`$4000-$7FFF` 固定16KB resident枠」を本線にする。
ただし、実体のresident本体は案Fの8KB級へ抑えることをサイズ目標にする。
Bank RAMは必須にしない。
Bank RAMがある場合は、resident本体の置き場ではなく、FAT cache、directory cache、file buffer、SAVE/write staging、system update stagingに使う任意拡張として扱う。

理由:

- #256のROM command dispatchと #259のresident APIは、常に呼べる固定residentを前提にした方が小さく実装できる。
- v3 phase 1の機能互換は、Bank RAMなしでも検証できるべきである。
- Bank RAMを必須にすると、SDFS/68 v3の最初の導入がハードウェア設計に引きずられる。
- 8KB residentを目標にすることで、BASICやユーザーTPAへの圧迫を抑えられる。ただし8KBを超えた時点で設計を破綻させないため、16KB枠を予約しておく。
- 旧128KBバンクボード案は有用だが、`$4000-$7FFF` をbank windowにする構成はv3 phase 1の本線ではなく、拡張構成として比較を継続する方がよい。

## Bank RAMの位置づけ

Bank RAMは「あった方がよい」が「必須ではない」とする。

| 機能 | Bank RAMなし | Bank RAMあり |
| --- | --- | --- |
| v2機能互換 (`DIR` / `TYPE` / `LOAD` / `RUN` / `.COM`) | 目標対象 | cacheで高速化、buffer増加 |
| BASIC LOAD | 小さいbufferで実現候補 | stream/cacheで余裕 |
| BASIC SAVE / メモリ範囲SAVE | 実装は可能だが厳しい | staging bufferとして有用 |
| FAT write | 固定resident内で苦しい | FAT/cache/staging分離がしやすい |
| system update | PC側更新なら不要 | 実機更新時のstagingに有用 |
| 32bit cluster / 8GB以上 | 実装サイズ増が厳しい | cache用途として有用だが必須ではない |

resident APIでは、`GET_CAPS` のbank bitと、必要ならbank window情報を返す。
Bank RAM非搭載時は、同じAPIで縮退して動くことを目標にする。

## VRAM / BASIC互換への影響

VDG構成では、VRAM候補が `$A000-$BFFF` または `$C000-$DFFF` に入る。
そのため、8KB bank windowや固定8KB residentを同じ領域に置く案は、VDG構成ごとに排他になる。

v3 phase 1では、BASICやユーザープログラムが使える上限はresident APIの `memtop` で返す。
固定16KB resident案では、ユーザーTPAは `$0000-$3FFF` を基本とする。
これは既存の `$0000-$7FFF` TPAより狭いが、v3の最初の目標は機能互換であり、大きなTPA互換は要求しない。
BASIC SAVE/LOADでは、#261でBASICの使用領域、変数領域、SDFS resident領域、VRAMの衝突を別途整理する。

## #233 / #238への影響

#238で追加済みの `ram64_4000_work` は、v3 phase 1の固定16KB resident本線候補として活かす。
ただし、#238の時点ではv3 resident API、system image、system update、2GB級FAT目標、Bank RAM任意拡張までは整理されていなかった。
そのため、#238をそのまま最終仕様とはみなさない。

#233は「SDFS/68固定領域を16KB級へ拡張する」Issueとして、v3 phase 1の本線候補と整合する。
一方、旧128KBバンクボードの `$4000-$7FFF` 16KB bank window案は、#233/#238とは別の拡張構成として残す。
後続実装Issueでは、`ram64_4000_work` をv3固定resident PoCの土台にし、Bank RAM window対応はcapabilityつきの追加Issueへ分ける。

## 後続実装Issueへの分割案

1. `ram64_4000_work` をv3 resident固定配置のPoC構成として使うか確認し、必要なsymbol名を整理する。
2. resident API header公開位置、ROM work変数、`memtop` 値を #259 API仕様へ接続する。
3. Bank RAMなしで `CMD <tail>` resident stubを呼ぶPoCを作る。
4. Bank RAM capability bitとbank window情報の返却形式を定義する。
5. 8KB bank window (`$A000` / `$C000`) をcache/staging用途で使う実装Issueを分ける。
6. 旧128KBバンクボード互換の `$4000-$7FFF` 16KB window構成を、別MEMORY_CONFIG候補として再評価する。
7. VDG構成ごとのVRAMとbank windowの排他関係をMAP表示とテストに反映する。

## 対象外

- 新メモリ構成の実装。
- バンク制御回路の確定。
- Bank RAM用I/Oレジスタの最終決定。
- 実機PoC。
- BASIC SAVE/LOAD実装。
- FAT write実装。

## 検証方針

本Issueは設計文書の追加のみであり、バイナリやコマンド動作は変更しない。
PR前の `make test` は、ドキュメントのみの変更として省略できる。
差分確認では、v3設計文書と目次以外のファイルが混ざっていないこと、改行コードを変更していないことを確認する。

## 関連

- #254: SDFS/68 v3親Issue。
- #257: 固定LBA system image形式と1発ロード方式。
- #258: system領域更新方式。
- #259: resident API最小セット。
- #261: BASIC SAVE/LOAD連携方式。
- #216: バンクメモリボードとSDFS常駐場所変更。
- #233: SDFS/68固定領域16KB級拡張。
- #238: `ram64_4000_work` 追加。
- 旧128KBバンクメモリボード検討: https://kuninet.org/2018/08/22/sbc68%E7%B3%BB-128kb-%E3%83%90%E3%83%B3%E3%82%AF%E3%83%A1%E3%83%A2%E3%83%AA%E3%83%9C%E3%83%BC%E3%83%891/
