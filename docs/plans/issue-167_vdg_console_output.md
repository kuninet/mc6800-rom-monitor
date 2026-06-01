# Issue #167 VDG console出力計画

## 背景

K68-VDG表示PoCでは `VDGTEST` により、K68-VDGの制御レジスタ `$8110` とVRAM `$A000-$BFFF` または `$C000-$DFFF` に固定文字列を書けることを確認済みである。

次の段階として、ROMモニタの通常出力をUARTだけでなくVDG画面にも複製する。入力はまだUARTのままとし、2nd ACIAキーボード統合やSDFS/68の画面操作完成は後続Issueで扱う。

## 採用方針

- `FEATURE_VDG=1` のROMだけにVDG console出力を入れる。
- UART出力は従来通り残し、実機デバッグの逃げ道にする。
- cold reset時にVDGを初期化し、画面をクリアしてカーソルをVRAM先頭に置く。
- `MON_OUTEEE` と `MIKBUG_OUTEEE_IMPL` からVDGへも同じ文字を出す。
- `MIKBUG_OUTEEE_IMPL` もVDGへ出すことで、`PDATA1` 経由の起動メッセージや、SDFS/68が呼ぶMIKBUG互換出力入口も画面へ出る。
- VDGカーソルは `MIKBUG_VAR_BASE-2` に置き、SD/FATやstage1/SDFS/68と共有しているwork領域の番地を動かさない。

## 最小仕様

- 通常文字は現在のVDGカーソル位置へ書き、カーソルを1文字進める。
- `CR` は次行先頭へ移動する。
- `LF` は無視する。UART側のCRLF変換やSDFS/68側の明示LFで二重改行しないため。
- `BS` / `DEL` は1文字戻して `$60` で消す。
- 画面末尾を越えた場合はいったんVRAM先頭へ戻る。

本格的なスクロール、カーソル表示、綺麗な折り返しは #168 で扱う。

## 対象外

- 2nd ACIAキーボード入力統合。
- UARTなしのスタンドアロン化。
- SDFS/68のVDG+keyboard操作完成。
- VDG画面の本格スクロール。
- カーソル表示。

## 検証方針

- `make bin`
- `MONITOR_PROFILE=sbcio_vdg make bin`
- `MONITOR_PROFILE=k6802_vdg make bin`
- `REQUIRE_BUILD_ROM=1 python3 tests/test_smoke.py`
- VDG有効profileでは、起動メッセージ、プロンプト、入力echoがVRAMへ入ることをsmoke testで確認する。
- `VDGTEST` が従来通り画面クリアと固定文字列表示を行うことを確認する。

実機では、VDG有効ROMで電源投入後に `MC6800 MONITOR` がVDG画面にも表示され、UARTから `H` / `MAP` / `VDGTEST` を実行して画面表示が追従することを確認する。
