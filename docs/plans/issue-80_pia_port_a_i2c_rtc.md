# Issue #80 PIA Port A I2C RTC PoC 設計

## 目的

SBC-IO の MC6821 PIA を使い、Port A で I2C を bit-bang する PoC を成立させるための設計メモである。主対象は DS3231 RTC モジュールで、まずは「低速・単機能・読み出し中心」の最小構成で成立性を確認する。

この設計は製品化前提ではなく、配線・電気的条件・PIA 制御方式・既存 SD 実装との関係を早めに切り分けるための検証計画に寄せる。

## 関連リンク

- Issue #80: https://github.com/kuninet/mc6800-rom-monitor/issues/80
- Issue #70: https://github.com/kuninet/mc6800-rom-monitor/issues/70
- Issue #54: https://github.com/kuninet/mc6800-rom-monitor/issues/54
- Port A / Port B I2C 配置検討: [i2c_bus_overlay_evaluation.md](i2c_bus_overlay_evaluation.md)
- 次期モニタ拡張ロードマップ: [issue-70_next_monitor_roadmap.md](issue-70_next_monitor_roadmap.md)
- SD/FAT 要件: [../requirements/2026-04-25_sdcard_spi_fat_requirements.md](../requirements/2026-04-25_sdcard_spi_fat_requirements.md)
- SBC-IO + microSD 実機確認手順: [../testing/sbc_io_sd_bringup.md](../testing/sbc_io_sd_bringup.md)
- I2C 仕様 (NXP UM10204): https://www.nxp.com/docs/en/user-guide/UM10204.pdf

## 採用判断

- 主案は **PIA Port A を I2C 専用に使う**。
- Port B は既存どおり **SD SPI 用に維持** する。
- 代替案として、Port B の未使用ビットを I2C に転用する案と、SD/RTC 専用 I/O 基板を追加する案を比較対象として残す。
- I2C はまず **master only**、**7bit address**、**START/STOP**、**1 byte write/read**、**ACK/NACK** のみを実装対象にする。
- **clock stretching は非対応** とする。これは SCL を常に push-pull 出力する意味ではなく、SCL High 期間に相手側が Low 保持しているかを待たないという意味で扱う。
- 最初の PoC は **標準モード未満の低速** で動かす。速度よりも、配線・レベル変換・PIA の open-drain 相当制御が正しいかを優先する。

## 現行ハード前提

現行実装では `include/hardware.inc` で PIA を次のように扱っている。

| 項目 | 値 | 用途 |
| --- | --- | --- |
| `PIA_BASE` | `$8050` | MC6821 PIA 暫定ベースアドレス |
| `PIA_PRA` | `$8050` | Port A data / DDRA |
| `PIA_CRA` | `$8051` | Port A control |
| `PIA_PRB` | `$8052` | Port B data / DDRB |
| `PIA_CRB` | `$8053` | Port B control |
| `PIA_DDR_SELECT` | `$04` | control register bit 2。0 で data register、1 で DDR を選択 |

Port B は SD SPI で使用済みである。

| Port B bit | 信号 | 方向 | 状態 |
| --- | --- | --- | --- |
| bit 0 `$01` | `SCLK` | 出力 | SD SPI clock |
| bit 1 `$02` | `MOSI` | 出力 | PIA から SD |
| bit 2 `$04` | `MISO` | 入力 | SD から PIA |
| bit 3 `$08` | `CS` | 出力 | SD chip select |
| bit 4 `$10` | Card Detect 候補 | 入力 | 要件上の予約 |
| bit 5 `$20` | Write Protect 候補 | 入力 | 要件上の予約 |
| bit 6 `$40` | 未使用 | 未定 | Port B 共有案の候補 |
| bit 7 `$80` | 未使用 | 未定 | Port B 共有案の候補 |

Issue #80 では、既存 SD SPI の Port B 実装に手を入れず、未使用の Port A を I2C 専用に使う。

## 前提と対象

- 対象 RTC は **DS3231**。
- テストに使うのは **Amazon などで流通しているモジュール型 DS3231** を想定する。
- DS3231 モジュールには、個体によって **AT24C02 / 24C32 などの 24Cxx EEPROM**、**プルアップ抵抗**、**充電回路** が載る場合がある。
- DS3231 の RTC 7bit アドレスは **`0x68`** である。実際にバスへ送る address byte は write が `0xD0`、read が `0xD1` になる。
- 付属 EEPROM がある場合は **`0x50`-`0x57`** の範囲で見えることがあるため、RTC だけを見たい PoC でもモジュール構成差を前提にする。

## 電気・配線上の注意

### open-drain 相当の作り方

PIA の出力を I2C のプッシュプル出力として使わない。SDA/SCL は次のように扱う。

- Low にしたいときは PIA を **出力 0** にする。
- High にしたいときは PIA を **入力** にして、外部プルアップへ任せる。

この方式で、I2C の open-drain 相当をソフトウェアで再現する。

### プルアップ

- SDA/SCL には外部プルアップを置く。
- PoC ではまず **4.7kΩ を基準** にする。
- 3.3V 側の I2C バスに対しては、その電圧へ引き上がる前提で設計する。
- モジュール上のプルアップと外付けプルアップが並列になる場合があるため、外付け抵抗は無条件に足さず、実効抵抗と立ち上がり波形を確認してから決める。

### 5V/3.3V レベル

SBC-IO 側の PIA は 5V 系で動く。DS3231 自体は幅広い電源電圧で動く品種だが、市販モジュールはプルアップ先、EEPROM、バックアップ電池回路、周辺部品の実装が一定ではない。SD や将来の I2C デバイスとの同居も考えるため、PoC では I2C バス側を 3.3V に寄せ、PIA と I2C バスの間には **BSS138 等の双方向レベルシフタ** を基本案として置く。

この構成を前提にすると、

- PIA 側の High は 5V ロジック
- I2C バス側は 3.3V ロジック
- SDA/SCL は双方向変換

を満たせる。

### モジュール依存の注意

DS3231 モジュールは部品構成が一定ではないため、以下を確認対象に含める。

- 既に 4.7kΩ 程度のプルアップが載っているか
- AT24C02 / 24C32 などの 24Cxx EEPROM が同居しているか
- 充電回路付きのバックアップ電池端子か。CR2032 のような非充電電池を使う場合は、充電回路が有効なままになっていないか確認する
- SCL/SDA の耐圧やレベルシフタ有無
- VCC を 5V に入れた場合、SDA/SCL のプルアップ先が 5V になるか 3.3V になるか

PoC では「モジュール単体でつながる」ことを過信せず、**実機モジュールの実装差を前提に測定する**。

今回確認した DS3231 モジュール回路図では、`SDA`、`SCL`、`SQW`、`32K` が抵抗アレイで `VCC` へプルアップされている。また `AT24C02` 相当の EEPROM が同じ I2C バスに載り、バックアップ電池端子へ `VCC` から抵抗とダイオードを通す充電回路候補がある。

このタイプのモジュールを使う場合、I2C バス電圧はモジュールの `VCC` で決まる。`VCC=5V` で使うと `SDA` / `SCL` / `SQW` / `32K` も 5V にプルアップされるため、3.3V I2C デバイスや3.3V入力へ直結しない。PoC で I2C バス側を 3.3V に揃える場合は、モジュール側 `VCC` も 3.3V にするか、モジュール上のプルアップとレベル変換の関係を実測してから接続する。

`SQW` と `32K` は Issue #80 の初期 PoC では未使用とし、未接続でよい。将来 PIA の補助入力や別入力へ接続する場合は、その入力耐圧とモジュール `VCC` を確認してから扱う。

バックアップ電池は、充電式の LIR2032 等を前提にしたモジュールがある。CR2032 のような非充電電池を使う場合は、充電回路を無効化するか、電池を接続しない状態で PoC を始める。

## Port A 主案

### 使い方

Port A の 2bit を I2C に割り当てる。

| PIA Port A bit | 信号 | 用途 |
| --- | --- | --- |
| `PA0` / `$01` | `SDA` | I2C data |
| `PA1` / `$02` | `SCL` | I2C clock |
| `PA2`-`PA7` | 予約 | 後続の GPIO / デバイス選択 / デバッグ用候補 |

Port A を専用化することで、SD SPI の Port B 実装に影響を与えずに I2C を評価できる。

### PIA 制御方針

MC6821 PIA では、control register bit 2 で data register と DDR のどちらを Port register address へ出すかを切り替える。I2C の High は Hi-Z で表現するため、PoC では DDRA の対応 bit を切り替えて SDA/SCL を制御する。

基本状態は次の通りにする。

| I2C線 | Lowにする操作 | Highにする操作 |
| --- | --- | --- |
| SDA | PRA data bit は 0 のまま、DDRA bit 0 を 1 にする | DDRA bit 0 を 0 にして入力化する |
| SCL | PRA data bit は 0 のまま、DDRA bit 1 を 1 にする | DDRA bit 1 を 0 にして入力化する |

PRA data bit は常に 0 を保持する。誤って data bit へ 1 を書いた状態で出力にすると push-pull 的に High を駆動するため、I2C バス上の他デバイスと衝突し得る。

既存の [i2c_bus_overlay_evaluation.md](i2c_bus_overlay_evaluation.md) で「SCL は当面出力固定」とした方針は、clock stretching を読まずに master 側タイミングだけで SCL を進めるという意味に限定する。電気的には SCL High も SDA と同じく Hi-Z と外部プルアップで作り、PIA から High を直接駆動しない。

### 設計上の利点

- SD 実装と I2C 実装の責務を分離しやすい。
- `SD_PORTB_SHADOW` のような既存 Port B シャドウ管理を壊さない。
- 7bit I2C の複数デバイス増設にも、Port A 側で整理しやすい。
- RTC アクセスが SD 転送と競合しにくい。

### 設計上の注意

- Port A を使うと、既存 SBC-IO の I/O 余地は減る。
- I2C の bit-bang 中は、DDRA/Port A の切り替えを明確にしないと SDA の High/Low が不安定になる。
- `PA0`/`PA1` の切替を雑に扱うと、START/STOP のエッジや ACK サンプル位置が崩れる。

## Port B 共有案

Port B の未使用ビットを I2C に流用する案も比較対象として残す。これは SD SPI と I2C を同じ PIA 上でまとめる方向だが、今回は主案にしない。

懸念は次のとおり。

- 既存 SD SPI の `SD_PORTB_SHADOW` と DDR 切替が I2C と衝突しやすい。
- SD 転送中に I2C 用の DDR を触ると、Port B のビット 0/1/3 に影響を与えやすい。
- 将来の SD 操作と RTC 操作の同時利用時に、ソフトウェア設計が複雑になる。

Port B 共有案は「配線が最小で済む」一方で、「既存 SD 実装の安定性を壊しやすい」ため、PoC の初手には不向きと見る。

## 専用 I/O 基板案

SBC-IO の PIA 共有をやめ、SD/RTC 専用 I/O 基板を別に作る案もある。これは最も整理されるが、現時点では優先しない。

評価点は以下。

- PIA の役割を SD と I2C で分離できる
- レベルシフタ、プルアップ、RTC、SD を基板上でまとめやすい
- 将来の拡張はしやすい

一方で、基板追加は PoC の速度を落としやすく、まず確認したい「Port A で bit-bang I2C が成立するか」という論点からは遠い。したがって、専用基板案は代替として残しつつ、PoC の主案にはしない。

## PoC 最小仕様

PoC では次を最小機能とする。

1. I2C master として SDA/SCL を制御できる
2. START / STOP を発行できる
3. 7bit address の write/read ができる
4. 1 byte write ができる
5. 1 byte read ができる
6. ACK / NACK を扱える
7. clock stretching は未対応
8. 速度は低速固定でよい

PoC で扱う DS3231 操作は、まずは以下に絞る。

- レジスタの読み出し
- 時刻・日付の読み出し
- 必要なら制御レジスタの 1 byte 書き込み

EEPROM や OLED は PoC の本筋ではない。モジュール上に載っていても、初回の確認対象は RTC 本体に限定する。

想定する最小トランザクションは次の順序である。

1. `START`
2. DS3231 の write address byte `0xD0` を送信し ACK を確認する
3. 読みたい DS3231 レジスタ番号を 1 byte 書く
4. `REPEATED START`
5. DS3231 の read address byte `0xD1` を送信し ACK を確認する
6. 1 byte 読む
7. 最終 byte として NACK を返す
8. `STOP`

## ソフトウェア方針

- I2C 実装は新規ファイルに分離する。
- 既存 SD 実装からは独立した API にする。
- `include/hardware.inc` には I2C 用の定数を追加する前提で整理する。
- 失敗時のリトライは最小限に留め、まずは「ACK が返るか」「read が成立するか」を観測できるようにする。
- Issue #80 の設計資料ではコード追加までは行わない。実装は後続 Issue / PR で扱う。

PoC 段階では、機能追加よりも、以下の観測しやすさを優先する。

- SDA/SCL の遷移が論理的に正しいか
- ACK/NACK を正しくサンプルできているか
- DS3231 の 7bit address `0x68` に到達できるか
- モジュールのプルアップやレベル差で波形が崩れていないか

## 検証方針

### 机上確認

- DS3231 モジュールの回路図または商品写真で、24Cxx EEPROM やプルアップの有無を確認する。
- BSS138 系レベルシフタ基板の配線を確認する。
- Port A の DDRA 切替と open-drain 相当制御の状態遷移を整理する。

### 実機 PoC

最小の実機確認は次の順に行う。

1. SDA/SCL の静的レベル確認
2. START/STOP の波形確認
3. DS3231 の write address byte `0xD0` への ACK 確認
4. DS3231 レジスタ 1 byte read 確認
5. 必要なら 1 byte write 確認
6. 時刻レジスタ一式の連続読み出し確認

### 期待する合格条件

- DS3231 が ACK を返す
- 時刻レジスタが安定して読める
- 低速 PoC で再現性がある
- SD SPI 実装に副作用を与えない

## 比較表

| 案 | 内容 | 評価 |
| --- | --- | --- |
| Port A 主案 | PIA Port A を I2C 専用化する | 採用 |
| Port B 共有案 | Port B 未使用ビットを I2C に流用する | 代替案 |
| 専用 I/O 基板案 | SD/RTC 専用基板を追加する | 代替案 |

Port A 主案は、既存 SD 実装を壊しにくく、PoC の論点を I2C に閉じ込めやすい。Port B 共有案は配線面で魅力があるが、既存 SPI と制御がぶつかる。専用 I/O 基板案は整理しやすいが、PoC の着手が重い。

## 未確定事項

- DS3231 モジュールの実機構成差
- 3.3V 側プルアップ値の最適化
- レベルシフタ基板の実装形態
- SBC-IO Rev02 の拡張ヘッダで `PA0` / `PA1` をどう取り出すか
- Port A の具体的な制御 API 名称
- 時刻表示をどのコマンド体系に載せるか
- 1 byte read 以外の DS3231 操作をどこまで PoC に含めるか

## 対象外

- 本格的な日付時刻 API。
- FAT timestamp 連携。
- `AUTOEXEC.S` からの RTC 初期化。
- DS3231 のアラーム、`INT/SQW`、IRQ 連携。
- AT24C02 / 24C32 などの 24Cxx EEPROM、SSD1306 OLED、その他 I2C デバイスのドライバ。
- I2C clock stretching 対応。
- I2C bus scan コマンド。

## 後続作業

この設計資料を前提に、次の実装・検証へ進める。

1. `include/hardware.inc` に I2C 用定数を追加する
2. `src/i2c.asm` を作る
3. DS3231 の最小 read PoC を実装する
4. 実機で ACK と時刻読み出しを確認する
5. Port B 共有案と専用基板案は、PoC 結果を見て再評価する
