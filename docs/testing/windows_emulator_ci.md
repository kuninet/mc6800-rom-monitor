# Windows エミュレータと CI 手順

## 目的

Windows 上で次の 2 点を安定して確認する。

- SBC6800 簡易エミュレータが動作すること
- 最新ソースから生成した `mc6800-monitor.bin` が smoke test を通ること

この手順書は、ローカル確認と GitHub Actions の両方をまとめたもの。

## GitHub Actions で 2 本の結果が出る理由

PR の checks に次の 2 本が見えるのは、workflow が `push` と `pull_request` の両方で動くため。

- `Windows Emulator Smoke / smoke (push)`
- `Windows Emulator Smoke / smoke (pull_request)`

意味は次のとおり。

- `push`
  - ブランチに commit を push した時点の確認
- `pull_request`
  - PR として `main` に対して評価したときの確認

同じ workflow でも、トリガーが別なので 2 本表示される。

## CI の流れ

現在の [windows-emu.yml](/Users/kuninet/git/MC6800_monitor/.github/workflows/windows-emu.yml) は次の順で動く。

1. Python をセットアップ
2. `third_party/asl/asw-1.42-Beta.zip` を展開
3. `asl.exe` と `p2bin.exe` で `build/mc6800-monitor.bin` を生成
4. `REQUIRE_BUILD_ROM=1` を付けて `python tests/test_smoke.py` を実行

このため、CI では fixture ではなく、毎回最新ソースから生成した ROM を使う。

## ASL の配置

Windows 用の ASL 配布 ZIP は次に置く。

- [third_party/asl/asw-1.42-Beta.zip](/Users/kuninet/git/MC6800_monitor/third_party/asl/asw-1.42-Beta.zip)

展開済みディレクトリはローカル確認用として置いてよいが、Git 管理には入れない。

- 例: `third_party/asl/asw-1.42-Bata/`

補足:

- ライセンス文書は展開物の `doc/COPYING` に入っている
- 配布方針は [third_party/asl/README.md](/Users/kuninet/git/MC6800_monitor/third_party/asl/README.md) を参照

## ローカルでの確認方法

### 1. ASL を展開済みの場合

PowerShell でリポジトリ直下へ移動して実行する。

```powershell
Remove-Item -Recurse -Force build -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force build | Out-Null
$include = "$pwd\include;$pwd\src"
& '.\third_party\asl\asw-1.42-Bata\bin\asl.exe' -q -L -olist build\mc6800-monitor.lst -o build\mc6800-monitor.p -i $include src\main.asm
& '.\third_party\asl\asw-1.42-Bata\bin\p2bin.exe' build\mc6800-monitor.p build\mc6800-monitor.bin -q
```

正常なら `build/mc6800-monitor.bin` が生成される。

### 2. smoke test を実行する

CI と同じ条件で動かすには、`REQUIRE_BUILD_ROM=1` を付ける。

```powershell
$env:REQUIRE_BUILD_ROM='1'
python tests/test_smoke.py
```

期待値:

```text
==================================================
SBC6800 emulator smoke tests
==================================================
[PASS] test_boot_prompt
[PASS] test_dump_command
[PASS] test_modify_and_dump
[PASS] test_go_swi_return
[PASS] test_srec_load
[PASS] test_ihex_load
[PASS] test_error_display

Result: 7 passed, 0 failed
```

### 3. fixture を使う簡易確認

`build/mc6800-monitor.bin` を作らずに簡易確認だけしたい場合は、そのまま実行すると fixture にフォールバックする。

```powershell
python tests/test_smoke.py
```

ただし、これは「最新ソースのビルド確認」にはならない。日常確認や Python 側の調査用と割り切る。

## 個別にエミュレータを起動する

ROM を直接起動してプロンプトを見るだけなら次でよい。

```powershell
python emu\sbc6800_emu.py build\mc6800-monitor.bin --max-cycles 2000
```

入力スクリプトを与える場合:

```powershell
python emu\sbc6800_emu.py build\mc6800-monitor.bin --input tests\fixtures\sample_input.txt --max-cycles 5000000
```

## 既知の整理

- CI の本命は `build/mc6800-monitor.bin` を使う経路
- fixture フォールバックはローカル補助用
- workflow が `push` と `pull_request` の両方を監視しているため、checks は 2 本見える
