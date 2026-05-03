# SBC-IO + microSD SPI モジュール 実機確認手順

## 目的

SBC6800 + SBC-IO + MC6821 PIA に、市販 microSD SPI モジュールを接続し、ROM モニタの SD/FAT read-only 機能を実機で確認する。

確認対象は SDHC/FAT32/root directory/8.3 filename/read-only の `DIR` と `LF filename` までとする。SAVE/write、subdirectory、LFN、AUTOEXEC は対象外。

## 前提

- SBC6800 は既存 ROM モニタで起動し、ACIA 経由のコンソール操作ができる。
- ROM は `$E000-$FFFF` に配置する。
- RAM は少なくとも `$0000-$1FFF` が使える。
- SD sector buffer は現行実装どおり `$1C00-$1DFF` を使う。
- PIA アドレスは初期値として `PIA_BASE=$8050` を使う。実機 SBC-IO で異なる場合は Issue #54 で確定する。
- Port B の SPI bit 割当は次の通り。

| PIA Port B bit | 信号 | microSD モジュール |
| --- | --- | --- |
| `$01` | `SCLK` | `SCK` |
| `$02` | `MOSI` | `MOSI` |
| `$04` | `MISO` | `MISO` |
| `$08` | `CS` | `CS` |

## 使用予定 microSD モジュール

使用予定品は Amazon の KKHMF 系 microSD SPI モジュール。

- https://www.amazon.co.jp/dp/B083DT3LQK/

同系統の Arduino 向け microSD SPI モジュールは、3.3V レギュレータとレベル変換回路入りとして販売されている例が多い。ただし互換品の実装差があるため、現物確認を優先する。

## 1. モジュール単体確認

SBC-IO へ接続する前に、microSD モジュール単体で確認する。

1. SD カードを抜く。
2. モジュールのシルク印刷で `GND`、`VCC`、`MISO`、`MOSI`、`SCK`、`CS` の位置を確認する。
3. `GND` と `VCC` へ 5V を供給する。
4. カードソケット側の 3.3V 系が約 3.3V になっていることをテスターで確認する。
5. カード側端子へ 5V が直に出ていないことを確認する。

安価なモジュールでは、MOSI/SCK/CS だけを 3.3V へ落とし、MISO は 3.3V のまま出す構成もあり得る。MC6821 は TTL-compatible なので 3.3V High を読める見込みだが、不安定なら MISO の High レベルを実測する。

## 2. ROM ビルドと書き込み

まずエミュレータで既存テストを通す。

```powershell
make bin
$env:REQUIRE_BUILD_ROM='1'
python tests/test_smoke.py
python tests/test_sd_fixture.py
```

使用する ROM 種別に合わせて ROM イメージを作る。

```powershell
make rombin ROM_KIND=<使用ROM>
```

例:

```powershell
make rombin ROM_KIND=W27C512
make program ROM_KIND=W27C512
```

既存の個別ターゲットを使う場合:

```powershell
make program-w27c512
```

書き込み後は verify または readback を行い、ROM 内容が正しく書けていることを確認する。

## 3. SD 未接続で既存モニタを確認

SD モジュールを接続する前に、SBC6800 単体または SBC-IO 接続のみで既存モニタが動くことを確認する。

1. シリアル端末を `9600 8N1`、送信改行 `CR` にする。
2. SBC6800 を起動する。
3. プロンプトが出ることを確認する。
4. `D` や `D0100` などの既存 dump コマンドを確認する。
5. 既存のシリアル LOAD 用 `L` が壊れていないことを確認する。

ここで動かない場合は、SD ではなく ROM 書き込み、ROM 種別、既存 SBC6800 構成、ACIA 側を疑う。

## 4. PIA アドレス確認

SBC-IO Rev02 のデコード条件と実配線を確認し、PIA が見えるアドレスを決める。

- 初期候補: `$8050-$8053`
- `PIA_BASE=$8050`
- `PIA_PRA=$8050`
- `PIA_CRA=$8051`
- `PIA_PRB=$8052`
- `PIA_CRB=$8053`

現物のアドレスが違う場合は、`include/hardware.inc` の `PIA_BASE` だけを変更する。エミュレータの暫定アドレスと実機アドレスが違う場合は、文書に明記する。

可能なら、`DIR` 実行時に PIA Port B の `CS`、`SCK`、`MOSI` が動くことをロジアナまたはオシロで見る。

## 5. SD モジュール配線

SBC-IO と microSD モジュールを次のようにつなぐ。

| SBC-IO / PIA | microSD モジュール | 備考 |
| --- | --- | --- |
| GND | GND | 必ず共通にする |
| 5V | VCC | 予定モジュールは 5V 入力前提 |
| Port B bit0 `$01` | SCK | SPI clock |
| Port B bit1 `$02` | MOSI | PIA から SD |
| Port B bit2 `$04` | MISO | SD から PIA |
| Port B bit3 `$08` | CS | chip select |

SD カードを挿す前に、VCC と GND の短絡がないことを確認する。

## 6. SD カード準備

初期確認では、条件を絞ったカードを使う。

- SDHC カード。
- FAT32。
- 512 byte sector。
- root directory に 8.3 filename のファイルだけを置く。
- subdirectory、LFN、日本語ファイル名は使わない。

root に最低限次を置く。

```text
TEST.S
TEST.HEX
```

`TEST.S` は `$0200` 付近、`TEST.HEX` は `$0300` 付近など、既存 RAM 上で確認しやすいアドレスへ小さいデータをロードする内容にする。

## 7. 実機確認

まず `DIR` を実行する。

```text
] DIR
TEST.S A 000000xx
TEST.HEX A 000000xx
]
```

期待:

- ハングせずプロンプトへ戻る。
- root の `TEST.S` と `TEST.HEX` が表示される。
- LFN、volume label、subdirectory は表示されない。

次に `LF` を確認する。

```text
] LF TEST.S
OK
] D0200
```

```text
] LF TEST.HEX
OK
] D0300
```

期待:

- `OK` が表示される。
- `D0200`、`D0300` などでロード結果が見える。
- 必要なら `Gxxxx` で小さいテストプログラムを実行する。

## 8. 失敗時の切り分け

### 起動しない

- ROM 種別、ROM 書き込み、verify 結果を確認する。
- reset vector が `$FFFE-$FFFF` にあるか確認する。
- ACIA とシリアル端末設定を確認する。

### 既存コマンドは動くが `DIR` で即失敗する

- `PIA_BASE` が実機 SBC-IO と一致しているか確認する。
- PIA の `CRB` / Port B DDR 設定が効いているか確認する。
- `CS`、`SCK`、`MOSI` が動くか確認する。

### SPI 波形は出るが SD が応答しない

- microSD モジュールの VCC と 3.3V を確認する。
- `CS` の極性と配線を確認する。
- `MOSI`、`SCK`、`MISO` のピン順を確認する。
- MISO が 3.3V High まで上がっているか確認する。
- 別の SDHC/FAT32 カードで試す。
- `DIR` 直後に `D1E90-1EA5` を実行し、`SD_ERROR=$02`、`FAT_ERROR=$01` なら FAT 以前の SD 初期化失敗として扱う。
- `CMD0` の R1 応答が期待 `$01` にならない場合は、SPI の MISO サンプリングタイミングも疑う。ROM 側は SCLK High 後に MISO を読む実装で確認する。

### `DIR` は出るが `LF` が失敗する

- ファイル名が 8.3 uppercase として扱えるか確認する。
- `TEST.S` / `TEST.HEX` が root にあるか確認する。
- S-Record / Intel HEX の終端レコードと checksum を確認する。
- file size が期待通りか確認する。

## 9. 記録するログ

実機確認後、次を `docs/progress/` またはこの文書へ追記する。

- 確認日。
- 使用 ROM 種別。
- `PIA_BASE` 確定値。
- microSD モジュールのピン順。
- VCC 入力、カード側 3.3V、MISO High レベル。
- SD カード種別と FAT32 形式。
- `DIR` 表示結果。
- `LF TEST.S` / `LF TEST.HEX` 結果。
- 失敗した場合の波形と切り分け結果。

## 関連リンク

- Issue #54: https://github.com/kuninet/mc6800-rom-monitor/issues/54
- SBC-IO Rev02: https://sbc738827564.wordpress.com/2018/08/11/sbc-io-rev02/
- 使用予定 microSD SPI モジュール: https://www.amazon.co.jp/dp/B083DT3LQK/
- ChaN 氏 MMC/SDC SPI 解説: https://elm-chan.org/docs/mmc/mmc.html
