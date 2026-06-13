# Issue #216 バンクメモリボードとSDFS常駐場所変更検討

## 対象

- 親Issue: #216
- この計画文書の追加Issue: #217
- 対象領域: SDFS/68、stage1、SBC-IO系RAM拡張、K68-VDG系VRAM、将来のバンクメモリボード

## 背景

現行のSDFS/68は、ROMモニタの `BOOT` から fixed boot area のstage1を読み、stage1がFAT rootの `SDFS.BIN` をロードして起動する。
この構成では、ROMを救命具と低レベル入口に留め、FAT操作やDOS風コマンドをRAM上の第2段システムへ逃がせる。

一方で、現行のSBC-IO RAM拡張構成では、`$C000-$DFFF` の8KBワーク領域に次を同居させている。

| 領域 | 用途 |
| --- | --- |
| `$C000-$C1FF` | SD sector buffer |
| `$C200` 以降 | monitor/SDFS/FAT work |
| `$C400-$CFFF` | stage1 loader |
| `$D000-$DEFF` | `SDFS.BIN` ロード領域 |
| `$DF00-$DFFF` | stack想定 |

SDFS/68 V1.3時点で、8KBワーク領域はすでに余裕が小さい。
今後 `SAVE`、複数バッファ、FAT write、テキスト表示、ワイルドカード、トランジェントコマンド拡張、常駐APIを追加する場合、SDFS常駐場所を8KB固定で考えるのは危険である。

同時に、K68-VDG系のVRAMは `$A000-$BFFF` または `$C000-$DFFF` の8KBを占有する。
SDFS常駐領域、VRAM、ユーザーRAM、バンクメモリ窓を同時に成立させるには、基板側の単純さとソフト側のメモリ管理を分けて検討する必要がある。

## 現行サイズ確認

2026-06-13時点の最新ソースで `make stage1 sdfs MONITOR_PROFILE=sbcio_vdg` を実行した結果は次の通り。

| 項目 | 値 |
| --- | --- |
| `stage1-sbcio-vdg.bin` | 2514 bytes |
| `SDFS-sbcio-vdg.BIN` | 3614 bytes |
| `S1_BASE` | `$C400` |
| `S1_LIMIT` | `$CFFF` |
| `S1_END` | `$CDD2` |
| `SDFS_LOAD_BASE` | `$D000` |
| `SDFS_LOAD_LIMIT` | `$DEFF` |
| `SDFS_END` | `$DE1E` |

`SDFS_LOAD_LIMIT=$DEFF` に対して `SDFS_END=$DE1E` なので、SDFS本体の残りは226 bytes程度である。
`$C000-$DFFF` 全体では、SD sector buffer、work、stage1、SDFS、stackを含めて8KBに収めており、設計上の余裕は小さい。

ROM側も `make bin` で `mc6800-monitor.bin: 8075/8192 bytes` であり、ROMへFATや大きなDOS機能を戻す余裕はない。
そのため、ROMは薄く保ち、SDFS/68または別常駐層へ機能を逃がす方針を維持する。

## 検討方針

ハードウェアは8KB単位デコードを基本にする。
GAL/CPLDを使えば細かい制御は容易だが、長期入手性と自作しやすさを考えると、74HC138などで扱いやすい粒度に寄せる。

細かいI/Oデコードや可変窓を増やすより、次を優先する。

- `$0000` 近辺のゼロページと低位RAMを安定させる。
- SDFS/68自身が乗っている領域を実行中にバンク切替しない。
- VRAMは原則として固定配置にする。
- バンクメモリは、SDFSやアプリのデータバッファとして使う。
- ユーザープログラムが使える上限をSDFS/68側で明示する。

## 候補A: 現行延長の8KB SDFSワーク

```text
$0000-$7FFF  ユーザーRAM
$8000-$9FFF  I/O窓
$A000-$BFFF  VRAMまたはワークRAM
$C000-$DFFF  SDFS/stage1/work
$E000-$FFFF  ROM
```

現行の `ram64_c000_work` / `ram64_a000_work` に近い。
既存実装との距離が近く、検証しやすい。

欠点は、SDFS/68の成長余地がほぼないことである。
V1.3時点でSDFSロード領域の残りが226 bytes程度しかなく、今後のDOS機能追加には向かない。

この候補は、互換構成または現行SBC-IOの継続確認用として残す。
新規バンクメモリボードの本命にはしない。

## 候補B: `$6000-$7FFF` SDFS固定 + `$C000-$DFFF` バンク窓

```text
$0000-$5FFF  ユーザーRAM 24KB
$6000-$7FFF  SDFS/68 resident 8KB
$8000-$9FFF  I/O窓
$A000-$BFFF  VRAM固定
$C000-$DFFF  8KBバンクRAM窓
$E000-$FFFF  ROM
```

低位RAMのうち8KBをSDFS/68常駐用に固定する案。
`$C000-$DFFF` はSDFSが使うファイルバッファ、FATキャッシュ、ディレクトリキャッシュ、アプリ拡張RAMに使う。

良い点:

- VRAMとバンク窓を分離できる。
- SDFSが自分の実行領域をバンク切替しない。
- `$C000-$DFFF` を純粋なデータバッファとして扱える。
- 8KBブロック単位のデコードで実現しやすい。

懸念:

- SDFS常駐部8KBは現行サイズから見て長期的に厳しい。
- ユーザーRAM上限が `$5FFF` になり、既存の `$0000-$7FFF` 前提プログラムと衝突しやすい。
- stage1とSDFSの配置を大きく変更する必要がある。

この候補は、最小変更で「SDFS固定」と「バンクバッファ」を分ける試験案として扱う。
本格DOS化するなら、次の候補Cを優先する。

## 候補C: `$4000-$7FFF` SDFS固定 + `$C000-$DFFF` バンク窓

```text
$0000-$3FFF  ユーザーTPA 16KB
$4000-$7FFF  SDFS/68 resident 16KB
$8000-$9FFF  I/O窓
$A000-$BFFF  VRAM固定
$C000-$DFFF  8KBバンクRAM窓
$E000-$FFFF  ROM
```

SDFS/68常駐部に16KBを与える案。
ユーザーRAMは16KBへ減るが、DOS常駐部、stage1相当のboot services、FAT処理、コマンド処理、将来のwrite対応を置きやすい。

良い点:

- SDFS/68の成長余地が大きい。
- `$C000-$DFFF` バンク窓をデータ専用にしやすい。
- VRAMを `$A000-$BFFF` に固定できる。
- CP/M風に「SDFSがユーザー使用メモリ上限を返す」設計と相性がよい。

懸念:

- 低位の連続ユーザーRAMが16KBに減る。
- BASICや既存アプリのメモリ期待値を確認する必要がある。
- SDFS/68が常駐DOSとして強くなるため、ROMモニタとの責務境界を再確認する必要がある。

この候補を、バンクメモリボード前提の本命案とする。
ユーザーRAMを広く見せたい場合は、バンクRAMをアプリ用拡張領域として割り当てる。

## 候補D: `$A000` / `$C000` 両方をバンク化

```text
$0000-$7FFF  ユーザーRAM
$8000-$9FFF  I/O窓
$A000-$BFFF  BANK A またはVRAM
$C000-$DFFF  BANK C
$E000-$FFFF  ROM
```

柔軟性は高いが、VRAMやSDFSが切替対象に乗ると危険である。
VRAMが表示中に切り替わる、SDFS実行中に自身を消す、といった事故を防ぐには、ロックビットや運用規約が必要になる。

この候補は、基板初版では採用しない。
将来版で検討する場合も、片側はVRAM固定、もう片側だけバンク窓にする運用を優先する。

## バンクメモリボード案

初版は、8KB単位の単純デコードを前提にする。

```text
74HC138  A15-A13 から8KBブロックを選択
74HC74   バンクレジスタ
74HC157  SRAM上位アドレス切替
74HC00/32 CS/OE/WE調整
SRAM     128KB以上、可能なら512KB品も搭載可能にする
```

バンク窓は `$C000-$DFFF` を第一候補にする。
バンク番号は4bit以上を持たせ、128KB SRAMなら16本の8KBページ、512KB SRAMなら64本の8KBページとして扱える。

`$A000-$BFFF` はVRAM固定を第一候補にする。
SBC-IO/VDG構成差のため、ジャンパまたはビルド構成で `$A000` と `$C000` のVRAM配置を切り替えられる余地は残すが、SDFS常駐領域とVRAMが同じ可変バンクに乗る設計は避ける。

## CP/M風メモリ管理案

SDFS/68は、ユーザープログラムへ「使ってよいメモリ上限」を返すAPIを持つ。
CP/MのTPAに相当する考え方を入れ、SDFS常駐部、VRAM、バンク窓、スタックをユーザー領域から明示的に除外する。

初期API候補:

| API | 目的 |
| --- | --- |
| `SDFS_GET_MEMTOP` | ユーザーが使ってよい最終アドレスを返す |
| `SDFS_SET_MEMTOP` | SDFSまたはアプリが一時的にユーザー領域上限を下げる |
| `SDFS_GET_BANK` | 現在のバンク番号を返す |
| `SDFS_SET_BANK` | バンク窓のページを切り替える |
| `SDFS_BANK_READ` | バンクを指定して安全に読み出す補助入口 |
| `SDFS_BANK_WRITE` | バンクを指定して安全に書き込む補助入口 |

`.COM` トランジェントコマンドやS-Record loaderは、この上限を見てロード先を制限する。
現行SDFS/68はロード先保護をしないため、SDFS本体、stage1、VRAM、stackを壊せる。
常駐場所変更と同時に、ロード先保護の導入を検討する。

現行の `.COM` は `$0100-USER_RAM_END` を最大ロード範囲として扱う。
SDFS常駐場所変更で `USER_RAM_END` を `$5FFF` または `$3FFF` へ下げる場合、`.COM` 最大サイズも縮む。
TPA境界を導入するIssueでは、`.COM` ABI文書とテストの更新を同時に扱う。

また、stage1の `S1_LOAD_FILE_83` はロード先が `SDFS_LOAD_BASE` 固定である。
常駐中のSDFS/68からそのまま呼ぶと自己上書きになるため、常駐SDFSが使うファイル読み込みはstream APIまたはバンクバッファ向けAPIへ分ける。
常駐場所変更時は、stage1 boot専用APIとSDFS実行中APIの責務を明確にする。

## 推奨するIssue分割

親Issue #216 は、検討と方針整理の棚にする。
実装PRから親Issueを直接closeせず、子Issueから `Refs #216` を使う。

| 子Issue案 | 内容 | 完了条件 |
| --- | --- | --- |
| SDFS/68現行メモリ使用量の棚卸し | stage1、SDFS、work、stack、VRAMの実使用と余白をlistingから整理する | サイズ表と制約がdocsに残る |
| バンクメモリボード初版メモリマップ設計 | `$A000` VRAM固定、`$C000` 8KBバンク窓、SDFS常駐候補を設計する | 8KB単位のメモリマップ案と信号方針がdocs/designに残る |
| `MEMORY_CONFIG` にSDFS常駐16KB案を追加 | `$4000-$7FFF` SDFS resident、`$C000-$DFFF` bank/window想定の構成軸を追加する | Make構成軸とMAP表示案が整理される |
| SDFS/68ロード先とstage1配置の変更PoC | SDFSを `$4000-$7FFF` または `$6000-$7FFF` に移す試験を行う | `make stage1 sdfs` と該当テストが通る |
| SDFSメモリ上限API設計 | `SDFS_GET_MEMTOP` などの常駐APIと `.COM` / loader制限を設計する | ABI文書にAPI案と互換性が残る |
| バンクレジスタABI設計 | バンク番号、保存復帰、割り込み/復帰時の扱いを決める | SDFS側から安全にバンク窓を使う規約がdocsに残る |
| ロード先保護実装 | S-Record、Intel HEX、`.COM` のロード先をSDFS常駐部/VRAM/stackから保護する | 異常系テストで保護範囲へのロードを拒否する |
| `.COM` ABI更新 | `USER_RAM_END` 低下時の最大サイズ、引数領域、復帰条件を再定義する | ABI文書とSDFS build testが更新される |
| 実機・基板化前PoC | エミュレータまたは試作回路で `$C000` バンク窓を読み書きする | RAMTESTまたは専用診断でバンク切替が確認できる |

## 採用候補

現時点の本命は候補Cとする。

```text
$0000-$3FFF  ユーザーTPA
$4000-$7FFF  SDFS/68 resident
$8000-$9FFF  I/O窓
$A000-$BFFF  VRAM固定
$C000-$DFFF  8KBバンクRAM窓
$E000-$FFFF  ROM
```

理由:

- 現行8KBワーク領域はSDFS/68の成長に対して狭い。
- SDFS常駐部を16KBにすると、DOS化、write対応、API化の余地ができる。
- バンクRAMをSDFS自身ではなくデータバッファとして使える。
- VRAMを固定でき、表示中のバンク切替事故を避けやすい。
- 8KBブロック単位の単純デコードで説明できる。

候補Bは、ユーザーRAMを24KB残す妥協案として残す。
ただし、8KB SDFS常駐は長期的に再び詰まる可能性が高いため、基板初版の標準案にはしない。

## 検証方針

- `make bin` でROMサイズを確認する。
- `make stage1 sdfs MONITOR_PROFILE=sbcio_vdg` で現行構成のstage1/SDFSサイズを継続確認する。
- 新しい `MEMORY_CONFIG` を追加する場合は、`make bin stage1 sdfs` と `tests/test_stage1_build.py` / `tests/test_sdfs68_build.py` を更新する。
- `MAP` 表示で、ユーザーRAM、SDFS resident、VRAM、bank window、ROMの範囲が分かるようにする。
- 実機確認前に、エミュレータまたは診断S-Recordでバンク番号ごとに異なるパターンを書き込み、切替復帰を確認する。

## 対象外

- 初版でGAL/CPLD前提の細粒度MMUを作ること。
- `$A000` / `$C000` 両方を自由にバンク化すること。
- FAT writeやSAVEをこの親Issueだけで実装すること。
- ROMへFAT本体やDOS機能を戻すこと。
- 既存SBC6800互換の8KB RAM最小構成を壊すこと。
