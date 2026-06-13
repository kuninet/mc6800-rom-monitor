# Issue #219 ローダ重複の削減とasm構成別解析基盤の整備

## 対象

- 親Issue: #216(バンクメモリボードとSDFS常駐場所変更検討)
- 関連: #217(検討計画の初版)
- 本書は #216 の「SDFS/68常駐部のサイズ削減余地」を具体化する調査メモであり、指摘表と解析手法、後続作業への引き継ぎを残す。

## 背景

#216 で整理したとおり、SDFS/68 は stage1 と本体を含めて現行の8KBワーク領域が窮屈になっている。常駐部のバイト数を削れれば、メモリマップ再設計の自由度が上がる。

そこで ROMモニタ(`main.asm`)と SDFSモジュール(`sdfs68.asm`)の重複を調べたところ、S-Record / Intel-HEX のテキストローダ一式がほぼ丸ごと二重実装されていることが分かった。

## 重要な手法上の注意 — ソース解析と構成別解析は別物

このコードベースは条件アセンブリ(`if MONITOR_FEATURE_*` など)を多用しており(`main.asm` だけで150箇所超)、ビルド構成ごとに実際にアセンブルされるコードが変わる。

| 観点 | ソース索引(構造地図) | アセンブルリスト(`.lst`) |
| --- | --- | --- |
| 見ているもの | 生ソースの和集合(全 `if` 分岐) | その構成で実際に出たコード(条件解決済み・実アドレス) |
| 条件アセンブリ | 評価しない | 解決済み |
| 「このバイナリに何が入るか」 | 判定不可 | アドレスで判定可 |
| 構成別の重複/デッドコード | 過大計上 | 正確 |

結論として、**構成依存の無駄削減判断は `.lst` を真実の土台にする**。呼び出し構造やクロス参照の俯瞰には別途ソース索引が有効だが、それ単独では「実際にビルドされるか」を答えられない。

## 指摘表

| # | 指摘 | 区分 | 根拠 | 対応方針 |
| --- | --- | --- | --- | --- |
| 1 | S-Record/Intel-HEX ローダが ROM と SDFS モジュールに二重実装 | 重複 | `.lst` 上、両バイナリに live で存在する対 **48組** | 削減方式を検討(下記) |
| 2 | ソース上の `X`↔`SDFS_X` 対 76組のうち 27組は ROM 側で条件除外され実体なし | 偽重複 | `MONITOR_FEATURE_FAT=0` 等。`PARSE_FILENAME_*` 一式がROMに不在 | 重複対象から除外(削減見積りに含めない) |
| 3 | `PIA_PRA` / `PIA_CRA` がどの構成でも未参照 | 未使用定数 | 全`.lst`のシンボルテーブルで `*`(unused) | Port A 未使用の裏付け。整理 or I2C流用検討(別軸)で参照 |
| 4 | `VEC_RESET` / `VEC_NMI` / `VEC_SWI` 等が未参照 | 未使用定数 | ベクタは `org` 直書きで設定されシンボル参照なし | ドキュメント化 or 整理(任意) |
| 5 | `.lst` の `*`(unused)コードラベルは「未到達」を意味しない | 注意 | フォールスルーラベル(`PARSE_DUMP_ARGS_READY` 等)や別バイナリから呼ばれるAPI入口(`SDFS_API_*`, `S1_JUMP_TABLE`)を含む | デッドルーチン判定は目視併用(機械判定は不可) |

## 真の重複48ルーチン(構成 `sbcio-sdfs`)

`tools/lst_analyze.py` で再現可能。S-Record/Intel-HEX のテキストローダを中心に、以下のファミリが ROM と SDFS の両方に live で存在する。

- S-Record: `READ_SREC_RECORD` / `READ_SREC_HEAD_OK` / `READ_SREC_TYPE_OK` / `READ_SREC_ADDR24` / `READ_SREC_DATA_LOOP` / `READ_SREC_STORE` / `READ_SREC_SKIP_STORE` / `READ_SREC_CHECKSUM` / `READ_SREC_EOF` / `READ_SREC_FAIL*`
- Intel-HEX: `READ_IHEX_RECORD` / `READ_IHEX_HEAD_OK` / `READ_IHEX_DATA*` / `READ_IHEX_SKIP_STORE` / `READ_IHEX_CHECKSUM` / `READ_IHEX_EOF` / `READ_IHEX_FAIL*`
- レコード振り分け: `READ_LOADER_RECORD*` / `READ_RECORD_HEAD*` / `READ_RECORD_TRAILER*`
- 行入力: `READ_LINE` / `READ_LINE_LOOP` / `READ_LINE_BACKSPACE` / `READ_LINE_DONE`
- HEX入力・変換: `READ_HEXBYTE_INPUT*` / `HEX_TO_NIBBLE*`
- 出力補助: `PRINT_HEX8` / `PRINT_NIBBLE*` / `PRINT_PROMPT`
- エラー表示: `SHOW_ERROR` / `SHOW_LOADER_ERROR*`
- チェックサム: `ADD_TO_LOADER_SUM`

代表的なアドレス対(ROM ↔ SDFS):`READ_SREC_RECORD` EA59 ↔ DB8A、`READ_LINE` E97E ↔ D652、`ADD_TO_LOADER_SUM` EC59 ↔ DD86。命令本体は接頭辞 `SDFS_` を除けば等価。

## 削減方式の選択肢

ROM($E000–$FFFF)は SDFS モジュール実行中も常にマップされている。したがって理論上、SDFS 側は自前コピーを捨てて ROM 側ローダを呼べる。

- **案1: ROM側ローダの公開API化(本命候補)**
  - ROM に小さなジャンプテーブル(stage1 の `S1_JUMP_TABLE` と同方式)を置き、ローダ入口を固定アドレスで公開する。
  - SDFS/68・stage1 はそのテーブル経由で呼び、自前の `SDFS_*` コピーを撤去する。
  - 効果: SDFSモジュールから数百バイトの回収が見込める(48ルーチン分)。#216 の常駐サイズ削減に直接効く。
  - 留意: ROMローダ入口アドレスが構成で動くため、固定エントリ(ジャンプテーブル)で安定化が必須。ローダが使うゼロページ/ワーク変数の配置共有も要確認。

- **案2: モジュール独立性を優先し二重実装を許容**
  - SDFS を ROM から独立した自己完結モジュールとして保つ。
  - 効果: メモリ回収なし。保守時に2コピーを同期するコストが残る(変更漏れリスク)。

## 案1の回収見積もりと実現可能性(追記)

構成 `sbcio-sdfs` の `.lst` 本文を行単位で集計(`tools/lst_analyze.py` の回収見積りセクションで再現可能)。

| 区分 | バイト | 割合 |
| --- | --- | --- |
| SDFSモジュール総コード | 3,605(0xE15) | 100% |
| **ROM再利用可能ローダ(回収対象)** | **759(0x2F7)** | 約21% |
| `PARSE_FILENAME_*`(SDFS固有・ROM不在=据置) | 247(0xF7) | 7% |
| その他SDFS本体ロジック | 2,599(0xA27) | 72% |

→ **SDFS常駐部から約759バイト回収できる見込み**(モジュールコードの約2割)。

### 実現可能性が高い理由 — ローダ用RAM変数が既に共有

ROMとSDFSで loader 系変数が同一アドレス(`hardware.inc` 共有 + 同 `MONITOR_RAM_BASE`)。例: `LOADER_MODE=C26A` / `LOADER_SUM=C26C` / `LOADER_ADDR=C26D` / `HEX_VALUE_HI=C263` / `LINE_BUF=C200` がいずれも ROM=SDFS で一致。

このため SDFS が ROM ローダを呼んでも**状態(変数)を作り直す必要がない**。本案の最大の難所がこの時点でクリアされている。

### APIサーフェスとジャンプテーブル

SDFS本体(非ローダ)から呼ばれる再利用入口は **9個**: `READ_LOADER_RECORD` / `READ_LINE` / `READ_HEXBYTE_INPUT` / `ADD_TO_LOADER_SUM` / `HEX_TO_NIBBLE` / `PRINT_HEX8` / `PRINT_PROMPT` / `SHOW_ERROR` / `SHOW_LOADER_ERROR`。

→ ROM側ジャンプテーブル **9本 × 3byte = 27バイト**追加でよい。ローダ内部の相互呼び出しはROM内で完結するためテーブル不要。

### 収支

- SDFS常駐部: **−759バイト**(`jsr SDFS_X` を `jsr <ROMテーブル入口>` に置換、サイズ不変)
- ROM: **+27バイト**(ジャンプテーブル)
- 正味 **約730バイト**を8KB常駐枠から解放

残る確認事項は「ローダのロード先書き込み(`LOADER_ADDR` 経由)がSDFSの想定と一致するか」程度。変数共有済みのため軽微とみられるが、実装PoCで確認する。

## #216 への影響

- 案1採用で SDFS常駐部から約730バイト(モジュールコードの約2割)を解放できる見込み。#216 の候補B/Cでの常駐サイズ評価に反映する。
- 削減後の正確なバイト数は、API化の実装後に `tools/lst_analyze.py` と `make` のサイズ確認で再計測する。

## 整備した解析基盤(保全)

- `tools/lst_analyze.py`: ASL の `.lst` シンボルテーブルをパースし、構成別に「未使用シンボル(`*`)」「ROM↔SDFS の真の重複対」「案1の回収見積りバイト数」を出力する。構成名を引数で指定(既定 `sbcio-sdfs`)。
- `tools/codegraph/`: ソース索引ツール(CodeGraph)の asm 拡張プラグインと適用手順。呼び出し構造・クロス参照の俯瞰用。条件アセンブリは評価しないため「構造地図」用途に限定する。

## 検証方法

- `python3 tools/lst_analyze.py sbcio-sdfs` で重複対と未使用シンボルを再生成する(`build/*.lst` が必要)。
- `make stage1 sdfs MONITOR_PROFILE=sbcio_vdg` 等でビルドし直すと最新の `.lst` が得られる。
- デッドルーチン候補は、`.lst` の `*` 印字を機械判定の入口にしつつ、フォールスルー/外部API入口を目視で除外する。
