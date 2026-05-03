# Issue #54 実機PoCとSBC-IO PIAアドレス確定 計画

## 関連リンク

- Issue #54: https://github.com/kuninet/mc6800-rom-monitor/issues/54
- PR #59: https://github.com/kuninet/mc6800-rom-monitor/pull/59
- PR #60: https://github.com/kuninet/mc6800-rom-monitor/pull/60
- PR #61: https://github.com/kuninet/mc6800-rom-monitor/pull/61
- PR #62: https://github.com/kuninet/mc6800-rom-monitor/pull/62
- PR #63: https://github.com/kuninet/mc6800-rom-monitor/pull/63
- SBC-IO Rev02: https://sbc738827564.wordpress.com/2018/08/11/sbc-io-rev02/
- 使用予定 microSD SPI モジュール: https://www.amazon.co.jp/dp/B083DT3LQK/

## 方針

Issue #54 では、エミュレータで確認済みの SD/FAT read-only 実装を、SBC6800 + SBC-IO + MC6821 PIA + 市販 microSD SPI モジュールで実機確認する。

今回使う予定の Amazon KKHMF 系 microSD SPI モジュールは、同系統の商品説明から見る限り 3.3V レギュレータとレベル変換回路入りの Arduino 向け SPI モジュールとして扱える。ただし安価な互換モジュールは実装差があり得るため、実機投入前に VCC、カード側 3.3V、信号方向、ピン順を現物で確認する。

コード変更は、SBC-IO 実機で `PIA_BASE=$8050` が違うと判明した場合だけ最小限にする。まずは現行実装のまま ROM を焼き、既存モニタ動作、PIA アドレス、SPI 波形、SD 初期化、`DIR`、`LF` の順に切り分ける。

## 実装範囲

- `docs/testing/sbc_io_sd_bringup.md` に、実機確認手順、配線、ROM 書き込み、SD カード準備、失敗時の切り分けを追加する。
- `include/hardware.inc` の `PIA_BASE` は暫定 `$8050` のまま開始する。
- 実機確認で `PIA_BASE` が違う場合だけ、別コミットまたは同 PR の最小差分で変更し、文書に確定値を追記する。
- SAVE/write、subdirectory、LFN、AUTOEXEC、外部 MCU 化は対象外にする。

## 実機確認の順序

1. SD モジュール単体で、VCC 入力、カード側 3.3V、ピン順を確認する。
2. SD 未接続で ROM を起動し、既存プロンプト、`D`、既存 `L` が壊れていないことを確認する。
3. SBC-IO の PIA アドレスを確認し、`PIA_BASE=$8050` と一致するか確認する。
4. `DIR` 実行時に PIA Port B の CS/SCK/MOSI が動くことをロジアナまたはオシロで見る。
5. SDHC/FAT32/8.3/root のカードで `DIR` を実行し、root の `TEST.S` / `TEST.HEX` が表示されることを確認する。
6. `LF TEST.S`、`LF TEST.HEX` を実行し、ロード結果を `D0200`、`D0300` などで確認する。

## 確認ログとして残すもの

- 使用 ROM 種別と書き込みコマンド。
- `PIA_BASE` の確定値。
- SD モジュールのシルク上のピン順と実配線。
- VCC 入力、カード側 3.3V、MISO High レベルの実測値。
- `DIR` の表示結果。
- `LF TEST.S` / `LF TEST.HEX` の実行結果。
- 失敗した場合は、CS/SCK/MOSI/MISO 波形、SD カード種別、FAT32 形式、失敗箇所。

## 注意

市販 microSD SPI モジュールは、5V 入力対応と書かれていても、どの信号が双方向レベル変換されているかは品種で差がある。MOSI/SCK/CS は 5V から 3.3V へ変換される前提でよいが、MISO は SD カードから 3.3V のまま出ている可能性がある。MC6821 は TTL-compatible なので 3.3V High を読める見込みだが、読めない場合は最初に MISO レベルを疑う。

SD カードやモジュールを 5V 直結で壊さないことを優先する。カード側端子へ 5V が出ていないことを確認してから、SBC-IO と接続する。

## テスト方針

PR 前に次を実行する。

```powershell
make bin
$env:REQUIRE_BUILD_ROM='1'
python tests/test_smoke.py
python tests/test_sd_fixture.py
git diff --check
```

実機確認は、この PR で手順を整備した後に進める。実機結果が得られたら、`docs/testing/sbc_io_sd_bringup.md` または `docs/progress/` に結果を追記する。
