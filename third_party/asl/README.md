# ASL toolchain for Windows CI

このディレクトリには、Windows 上で `mc6800-rom-monitor` をビルドするための ASL 配布物を置く。

## 配置方針

- `asw-*.zip`
  - GitHub Actions で展開して使う固定版の配布 ZIP
- `asw-*` 展開ディレクトリ
  - ローカル確認用
  - `.gitignore` で無視し、Git には含めない

## 現在の前提

- 配布物: `asw-1.42-Beta.zip`
- 入手元: `http://john.ccac.rwth-aachen.de:8000/ftp/as/precompiled/i386-unknown-win32/aswcurr.zip`
- 確認日: 2026-04-15

## ライセンス

展開物の `doc/COPYING` に GPL のライセンス文書が含まれている。ASL はこのプロジェクトのビルドツールとして同梱する。

- ライセンス文書: `third_party/asl/asw-*/doc/COPYING`

## CI での使い方

GitHub Actions では次の順で利用する。

1. `third_party/asl/asw-*.zip` を展開
2. `bin/asl.exe` で `build/mc6800-monitor.p` を生成
3. `bin/p2bin.exe` で `build/mc6800-monitor.bin` を生成
4. エミュレータ smoke テストを `REQUIRE_BUILD_ROM=1` で実行
