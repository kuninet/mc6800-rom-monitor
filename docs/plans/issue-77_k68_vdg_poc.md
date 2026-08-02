# Issue #77 K68-VDG表示PoC

## 関連リンク

- Issue #77: https://github.com/kuninet/mc6800-rom-monitor/issues/77
- Issue #70: https://github.com/kuninet/mc6800-rom-monitor/issues/70
- K68-VDG: https://github.com/kuninet/K68-VDG

## 確認した事実

- K68-VDG READMEでは、VDG設定用レジスタは `$8110`、VRAMは `$A000-$BFFF` または `$C000-$DFFF` とされている。
- 現行 `sbcio` profileは、SD/FAT sector buffer、モニタワーク、MIKBUG互換ワーク、スタックを `$C000-$DFFF` に置く。
- Issue #70 以降の方針では、`$A000-$BFFF` を K68-VDG VRAM 候補として予約し、`RAMTEST` の対象外にしている。
- K6802-SBCでは、K68-VDGのVRAMを `$C000-$DFFF` に置き、`$A000-$BFFF` をSD/FATとモニタのワークRAMに使う構成も必要になる。

## 採用方針

- `base` / `sbcio` の既存互換を維持し、K68-VDG PoCは新規VDG有効profileでだけ有効にする。
- `sbcio_vdg` は `sbcio` と同じRAM/SD/FAT配置を継承し、K68-VDGのVRAMは `$A000-$BFFF` 固定にする。
- `k6802_vdg` はK6802-SBC向けに、SD/FATワークを `$A000-$BFFF`、K68-VDG VRAMを `$C000-$DFFF` にする。
- 初期PoCのコマンドは `VDGTEST` とし、画面クリアと固定文字列表示に限定する。
- `MAP` では `MAP SBCIO VDG`、`VRAM A000-BFFF`、`VDG 8110` を表示し、実行時検出ではなく profile 定義の想定配置を示す。
- `k6802_vdg` の `MAP` では `MAP K6802 VDG`、`WORK A000-BFFF`、`VRAM C000-DFFF`、`VDG 8110` を表示する。

後続の #167 ではROM容量を優先し、ROM常駐 `VDGTEST` は外した。固定表示確認は `diagnostics/VDGA000.S` / `VDGC000.S` をSDからロードして実行する。

## 検証方針

- `base` / `sbcio` では `VDGTEST` が `?` を返し、既存のヘルプ、MAP、SD/FAT、RAMTESTの挙動を維持する。
- `sbcio_vdg` では `VDGTEST` が `OK` を返し、エミュレータ上で `$A000` から固定文字列、後続にクリア値 `$60` が入ることを smoke test で確認する。
- `k6802_vdg` では `VDGTEST` が `OK` を返し、エミュレータ上で `$C000` から固定文字列、後続にクリア値 `$60` が入ることを smoke test で確認する。
- SD/FAT fixture testでは、VDG有効profileを `sbcio` 系 profile として扱い、SD/FATワークとVRAMが重ならないことを symbol と `MAP` 出力で確認する。
- RAMTESTでは、`sbcio_vdg` は `$C000-$DFFF` を許可して `$A000-$BFFF` をVRAMとして触らず、`k6802_vdg` は `$A000-$BFFF` を許可して `$C000-$DFFF` をVRAMとして触らないことを確認する。
- 実機依存の映像確認は `docs/testing/k68_vdg_bringup.md` の手順に残す。

## 対象外

- 本格的なコンソール画面化。
- 既存 `OUTCH` のVDG出力化。
- キーボード入力。
- スクロール処理。
- グラフィックAPI整備。
