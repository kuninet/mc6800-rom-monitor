# Issue #175 ROM容量削減とデッドコード探索

## 背景

PR #174でVDG console出力、VDGTEST/KEYTESTのSD診断化、MコマンドのVDG出力修正まで入れた。
一方で、`sbcio_vdg` / `k6802_vdg` は8KB ROM上限に近く、今後のVDG/keyboard/BOOT共存のため、まず削減余地をlistingベースで確認した。

## 初回探索

`main` 更新後、次の2profileをビルドしてlistingを確認した。

```text
MONITOR_PROFILE=sbcio_vdg make bin
MONITOR_PROFILE=k6802_vdg make bin
```

`.bin` の表示サイズは固定ベクタ込みの範囲サイズなので、削減量の確認には向かない。
実際の削減は、`SD_INIT` や `SPURIOUS_IRQ` など後続ラベルの前倒し量で見る。

## 採用した削減

### VDGハイフン特例削除

K68-VDGでは、ASCII `$20-$3F` をVDG側 `$60-$7F` へ寄せる方針にした。
そのため、`'-'` だけを特別扱いして `$6D` を返す必要はない。

```text
'-' = $2D
$2D + $40 = $6D
```

`VDG_ASCII_TO_CHAR` は `$40` 未満を一律 `$40` 加算するだけにした。

### MAP文字列のprofile別条件アセンブル

`CMD_MAP` の処理本体はprofile別に条件アセンブルされていたが、MAP用文字列は他profile向けのものもROMへ入っていた。
これを参照側と同じ条件で囲み、現在のprofileで使う文字列だけをROMへ入れるようにした。

`sbcio_vdg` では、変更前の `SD_INIT` は `F1CC`、変更後は `F114` になった。
差分は `0xB8`、つまり184バイトぶん後続コードが前倒しになった。

## 見送った候補

| 候補 | 見込み | 見送り理由 |
| --- | ---: | --- |
| Intel HEX loader削除 | 約170B+α | ROM `L` の互換性低下がある。SREC専用に割り切る判断が必要 |
| RAMTESTのSD診断化 | 約294B+文字列 | ROM単体の復旧口として価値が高い |
| 逆アセンブラ縮小/SD診断化 | 約265B+文字列 | ROM最終形のマシン語デバッグ用途と衝突する |
| SD rawアクセス削減 | 約644B | `BOOT`方針そのものに影響する |

## 検証方針

MAP文字列条件化は全profileへ影響するため、`base`、`sbcio`、`sbcio_vdg`、`k6802_vdg` のsmoke testで確認する。
#177 以降の `sbcio` はSD/FATなしprofileであり、ROM常駐FATの確認は `FEATURE_SD=1 FEATURE_FAT=1` の直接指定互換構成で行う。
