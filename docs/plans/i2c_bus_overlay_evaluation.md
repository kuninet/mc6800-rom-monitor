# PIA I2C オーバーレイ配置検討メモ

## 関連リンク

- Issue #70 次期モニタ拡張ロードマップ: https://github.com/kuninet/mc6800-rom-monitor/issues/70
- ロードマップ #6 PIA Port A I2C RTC: [issue-70_next_monitor_roadmap.md](issue-70_next_monitor_roadmap.md)
- SD/FAT 要件書: [../requirements/2026-04-25_sdcard_spi_fat_requirements.md](../requirements/2026-04-25_sdcard_spi_fat_requirements.md)
- SBC-IO Rev02: https://sbc738827564.wordpress.com/2018/08/11/sbc-io-rev02/
- I2C 仕様 (NXP UM10204): https://www.nxp.com/docs/en/user-guide/UM10204.pdf

## 目的

SBC-IO の MC6821 PIA を介してビットバンギングで I2C バスを増設し、RTC、EEPROM、小型 OLED/LCD などの I2C デバイスをモニタから扱えるようにする土台を整理する。

具体的には次の 2 案を比較し、後続 Issue 化の単位を確定させる。

- **Port A 専用案**: PIA Port A の任意 2 ビットを SDA/SCL に割当てる。SD ビットバンギング SPI と物理的に分離する。
- **Port B 共有案**: SD で使っていない Port B bit 6/7 を SDA/SCL に流用する。`src/sdcard.asm` の `SD_PORTB_SHADOW` と DDR を共有する。

本メモは技術検証と推奨判断を残すものであり、I2C ドライバ本体や個別デバイスドライバの実装は別 Issue で扱う。

## 採用判断

- **Port A 専用案を本命とする**。Issue #70 ロードマップ #6 の既定線と整合する。
- Port B 共有案は、SBC-IO Rev02 の拡張ヘッダで Port A が物理的に引き出されていない場合の代替として残す。
- I2C 速度は初期 PoC で約 10kHz を狙う。MC6800 1MHz の bit-bang で 100kHz 標準モード相当に届かせるかは PoC 後に判断する。
- SCL は当面出力固定とし、クロックストレッチ対応は後段に分離する。
- 5V PIA と 3.3V I2C デバイスの境界には双方向レベルシフタ (例 BSS138) を入れる。プルアップは 4.7kΩ 程度を共通化する。

## 現状の Port B / Port A 使用状況

PIA レジスタ (`include/hardware.inc:18-24`):

- `PIA_PRA = $8050`
- `PIA_CRA = $8051`
- `PIA_PRB = $8052`
- `PIA_CRB = $8053`
- `PIA_DDR_SELECT = $04`

Port B 割当:

| bit | 信号 | 方向 | 状態 |
| --- | --- | --- | --- |
| 0 | SCLK | OUT | SD SPI 使用 |
| 1 | MOSI | OUT | SD SPI 使用 |
| 2 | MISO | IN | SD SPI 使用 |
| 3 | CS | OUT | SD SPI 使用 |
| 4 | CARD_DETECT 予約 | IN | 未実装 (要件書で予約) |
| 5 | WP 予約 | IN | 未実装 (要件書で予約) |
| 6 | — | — | 完全未使用 |
| 7 | — | — | 完全未使用 |

Port A: 全 8 bit が完全未使用。

SD 実装の前提 (`src/sdcard.asm:262-271`, `src/sdcard.asm:290-328`):

- `SD_PIA_INIT` で DDRB を `SPI_OUTPUT_MASK = $0B` に固定し、CRB の DDR_SELECT を立てっぱなし運用。以降の `staa PIA_PRB` はすべてデータレジスタへ向かう。
- `SD_SPI_XFER` は 1 bit ごとに `ldaa SD_PORTB_SHADOW → 操作 → staa PIA_PRB` を繰り返す。bit 6/7 もシャドウ値で毎ビット書き戻される。

## Port A 専用案 vs Port B 共有案 比較

| 観点 | Port B 共有 (bit 6=SDA, bit 7=SCL) | Port A 専用 (推奨) |
| --- | --- | --- |
| 電気的 open-drain (DDR トグル + 外部プルアップ) | 必要 | 必要 |
| 3.3V/5V レベル変換 | 必要 (3.3V 系 RTC/OLED が多い) | 必要 |
| DDR レジスタ共有 | あり: SDA Hi-Z 化に CRB→`$00`→PRB に DDR 値→CRB→`$04` 復帰の 3 ステップ。SD の DDR `$0B` 前提と重複 | なし: DDRA 独立 |
| `SD_PORTB_SHADOW` 干渉 | あり: SD 1 bit 毎に bit 6/7 を書き戻すため、シャドウへ I2C 状態同期が必須 | なし |
| 再入安全性 (将来の割込駆動 SD) | DDR=`$0B` 前提が崩れるリスク | 完全独立 |
| Card Detect/WP 予約 (bit 4/5) | bit 6/7 のみ使えば温存可 | 影響なし |
| 物理配線 | PB6/PB7 が拡張ヘッダにあるか要確認 | PA0–7 は引き出される可能性が高い |
| ROM 容量 | DDR トグルヘルパ + シャドウ sync 命令を sdcard.asm 経路に注入 | 独立 init で完結、SD コード変更ゼロ |
| 実装複雑度 | 高 | 低〜中 |
| 将来拡張余地 | Port A 全 8 bit 温存 (キー読み・LED 等に) | Port A の余り 6 bit 残る |
| エミュレータ改修 | I2C スレーブ + bit 6/7 ↔ SD 経路の相互干渉テスト | I2C スレーブを Port A に直結 (経路直交) |
| 複数 I2C スレーブ同居 (RTC+EEPROM+OLED) | 影響なし (I2C は 7bit アドレスでバス上多重化) | 同左 |

## Port A 専用案の概要

- 候補ビット割当: `I2C_SDA = $01` (PA0)、`I2C_SCL = $02` (PA1)。残り PA2–PA7 は将来用に温存。
- 初期化: `clr PIA_CRA` → `clr PIA_PRA` (DDR=全入力=Hi-Z) → `ldaa #PIA_DDR_SELECT, staa PIA_CRA`。
- SDA/SCL の Low 駆動は CRA を `$00` ↔ `$04` でトグルし、DDRA の対応ビットを 0/1 で切替。Hi-Z 復帰は外部プルアップでの '1' に任せる。
- `src/sdcard.asm` には変更を加えない。
- 想定追加ファイル: `src/i2c.asm` (新規)、`include/hardware.inc` への I2C 関連定数追加。
- エミュレータ側は Port A に I2C スレーブダミーを接続する形で拡張する。SD 経路と直交するため SD 既存テストへの回帰リスクが小さい。

## Port B 共有案の概要

- 候補ビット割当: `I2C_SDA = $40` (PB6)、`I2C_SCL = $80` (PB7)。bit 4/5 の Card Detect/WP 予約は温存する。
- DDR 退避ヘルパ (CRB クリア → PRB へ DDR 値 → CRB へ `$04` 復帰) を新設し、I2C 操作の前後で DDRB を `$0B` ↔ `$0B|$40` などにトグルする。
- `SD_PORTB_SHADOW` を共通シャドウへ格上げ (例: `PIA_PRB_SHADOW`)。SD 側はこれまで通り bit 0/1/3 のみ操作 (既存 `anda #$FF-...` マスクは bit 6/7 を破壊しない)、I2C 側は bit 6/7 のみ操作する分担にする。
- 再入規約として「I2C 関数中に SD 関数を呼ばない」を明記する。割り込み駆動 SD は将来想定外として扱う。
- `src/sdcard.asm` への侵襲が発生するため、Port A 専用案より既存テストへの回帰リスクが大きい。

## 複数 I2C デバイス同居の論点

- **アドレス衝突**: DS3231 RTC は `0x68`、24C32 EEPROM は `0x50`〜`0x57` (A0/A1/A2 で可変)、SSD1306 OLED は `0x3C` または `0x3D`。標準的にはぶつからないが、DS3231 モジュールに 24C32 が同梱されたタイプは EEPROM が `0x57` 固定の場合があり、汎用 24C32 のジャンパと干渉しないようアドレス選択を物理的に管理する必要がある。
- **電源/プルアップ**: 全デバイスが 3.3V 共通であれば 1 組のプルアップ (4.7kΩ) で足りる。SBC-IO の PIA 側は 5V のため、I2C バス側を 3.3V に揃え、PIA との境界に BSS138 双方向レベルシフタを 1 段挟む構成を基本とする。
- **クロック**: SSD1306 は 100kHz〜400kHz 動作。MC6800 1MHz の bit-bang で 100kHz を超えるのは命令数的に厳しいため、初期 PoC は数 kHz〜10kHz を狙う。OLED 全画面更新 (約 1KB) は時間がかかるが、AUTOEXEC からの初期化や 1 行ステータス表示用途なら許容範囲。
- **OLED の負荷**: SSD1306 は I2C 書込が支配的で、RTC/EEPROM とアクセス頻度が大きく違う。bit-bang での主用途にするのは性能的に厳しいため、初期は RTC/EEPROM を本命、OLED は表示量を絞った PoC として扱う。
- **クロックストレッチ**: DS3231 と SSD1306 は基本使わない。初期実装では SCL を出力固定で十分。Stretch を本格対応するのは後段に分離する。

## PIA 補助ライン (CA1/CA2/CB1/CB2) の活用候補

PIA はデータポート 8bit に加えて、ポートごとに 2 本ずつ補助制御ライン (CA1/CA2、CB1/CB2) を持つ。SD ビットバンギング SPI では `SD_PIA_INIT` が `clr PIA_CRB` → `staa #PIA_DDR_SELECT, PIA_CRB` の 2 段だけしか CRB を触らず、CRA はそもそも触れていない。CRA/CRB の上位ビットは全て 0 のままなので、**CA1/CA2/CB1/CB2 の 4 本は SD 動作中もアイドル状態で空いている**。これを I2C オーバーレイ周辺の補助信号に流用できる。

各ラインの性格:

| ライン | 入出力 | モード | 用途の方向性 |
| --- | --- | --- | --- |
| CA1, CB1 | 入力専用 | エッジ検出 (CRA/CRB bit 1 で立上り/立下り選択) + IRQ フラグ + IRQ 許可 (bit 0) | 外部割込入力 |
| CA2, CB2 | 入出力切替 | 入力モード (CA1/CB1 と同様の IRQ 入力) / ハンドシェイク出力 (PRA 読み・PRB 書きに連動した自動パルス) / マニュアル出力 (CRA/CRB bit 3 を直接出力) | IRQ 入力または +1 GPIO |

### 本プロジェクトで楽しめそうな使い道

1. **RTC アラーム / 1Hz tick の IRQ 化 (本命)**: DS3231 の `INT/SQW` ピンを CA1 または CB1 に接続する。DS3231 はアラーム 1/2 で「指定時刻一致時に INT を Low にする」動作と、1Hz 矩形波出力モードを持つ。これを PIA 経由で MC6800 IRQ に流すと、ポーリングなしに「指定時刻にハンドラへ飛ぶ」「1Hz で時計表示を更新する」が実現できる。AUTOEXEC からセットしたアラームで定刻処理を起こす、`AT hh:mm` 風コマンドの土台、CTC 風の周期 tick — bit-bang I2C と組み合わせると応用が広がる。
2. **SD Card Detect / WP の IRQ 入力化**: 現在 PB4/PB5 に予約しているカード検出 / 書込禁止信号を CA1 / CB1 へ移すと、挿抜変化を IRQ で検出できる。ポーリングが消え、Port B 上位ビットも空く。
3. **CA2/CB2 マニュアル出力で +2 GPIO**: LED、SD 電源 enable、ブザーなど。注意: CA2/CB2 のマニュアル出力切替は CRA/CRB の上位ビット書き換えが必要で、bit-bang I2C SCL のような高頻度トグル用途には PRA/DDRA トグルより遅い。GPIO 用途に絞るのが妥当。
4. **将来の 2nd ACIA キーボード I/F MCU との同期 strobe**: ハンドシェイク出力モードで PRA 読み / PRB 書きに連動したパルスを自動生成できる。ただし SD で PRB を書く頻度が高いので、SD 期間中は CB2 ハンドシェイクを使えない (誤発火する)。CA2 側 (PRA 連動) なら SD と独立。

### RTC IRQ 経路 (案)

- 配線: DS3231 `INT/SQW` (オープンドレイン出力) → 4.7kΩ プルアップ (3.3V) → BSS138 で 5V へ → PIA `CA1` (Port A 案の場合)。Port A を I2C SDA/SCL に使うなら CB1 でもよい。
- 初期化: `CRA bit 1` でエッジ方向選択 (DS3231 INT は Low active なので立下りエッジ)、`CRA bit 0=1` で IRQ 許可。フラグは PRA 読み出しでクリアされる仕様。
- ハンドラ: モニタ既存の IRQ ベクタ (`VEC_IRQ = $FFF8`) 経由で割込ハンドラへ。ハンドラ内で I2C 経由 DS3231 の Status レジスタを読みアラーム要因をクリアする (これは本格 I2C 駆動が必要なので、実装はドライバ完成後)。
- 副次効果: モニタ全体に「IRQ 駆動の周期 tick」基盤が入る。PTM 案 (issue-70 #5) と機能が重なるため、RTC アラーム経由 tick で済むなら PTM の優先度は下げられる。

### 既存 SD コードへの影響

- CRA は SD 初期化で触っていないため、CA1/CA2 の IRQ 設定は SD と完全独立に行える。
- CRB は SD 初期化で `$04` (DDR_SELECT のみ) を書いているが、上位ビット (CB1 IRQ 関連 / CB2 制御) を立てると `staa PIA_CRB` 命令を SD 側で再実行しない限り維持される。`SD_PIA_INIT` を一度通せば後続 SD 動作は CRB を触らないので、CRB 上位ビットを足しても SD 既存テストへの影響はない見込み。Port B 共有 I2C 案を採る場合のみ DDR トグルで CRB を頻繁に触るため、CB1/CB2 設定の保持に注意が必要。

## 後続 Issue 化候補

| 候補 | 内容 | 優先 |
| --- | --- | --- |
| A | SBC-IO Rev02 拡張ヘッダの PA[7:0] / PB[6:7] / CA1 / CA2 / CB1 / CB2 引き出し確認 (実機 schematic レビュー) | 高 (両案の前提) |
| B | I2C bit-bang ドライバ PoC (Port A、SCL 固定、~10kHz、START/STOP/書込/読出/ACK/NACK) | 高 |
| C | DS3231 RTC ドライバ + AUTOEXEC からの時刻表示 | 中 |
| C2 | DS3231 `INT/SQW` を CA1 (または CB1) に接続して RTC アラーム / 1Hz tick を IRQ 化 | 中 (C の後段) |
| D | 24C32 EEPROM ドライバ (CONFIG.SYS 代替の起動パラメータ保存先候補) | 中 |
| E | SSD1306 OLED 表示 PoC (1 行ステータス表示から) | 低 |
| G | SD Card Detect / WP を CA1 / CB1 へ移す案 (Port B bit 4/5 開放) | 低 |
| F (代替) | Port B 共有案による I2C bit-bang PoC (Port A が引き出されていない場合のみ) | 条件付 |

依存順は A → B → C → C2 → (D, E, G) を基本とする。F は A の結果次第で B に置き換わる。

## 未確定事項

- SBC-IO Rev02 拡張ヘッダにおける PA[7:0] および PB[6:7] の物理引き出し有無。
- 双方向レベルシフタ IC の選定 (BSS138 ベースの 4ch モジュールで 3 本以上を一括変換するか、個別の MOSFET 構成にするか)。
- I2C 目標クロック (10kHz 起点で十分か、OLED 用途で 100kHz を狙うか)。
- I2C プルアップ抵抗の最終値 (4.7kΩ を起点に、線長と容量で 2.2kΩ〜10kΩ レンジで調整)。
- `tests/` 配下に I2C smoke を追加する場合の fixture 形式 (Python 側で I2C スレーブダミーを書く構成)。
- `include/hardware.inc` の I2C 定数命名 (`I2C_SDA` / `I2C_SCL` を Port A 案と Port B 案で共通名にするか分けるか)。
- DS3231 `INT/SQW` の接続先を CA1 と CB1 のどちらにするか (Port A を I2C に使う前提なら CB1 が自然だが、IRQ 入力としての電気的・タイミング差は実用上ほぼ無いので配線都合で決めてよい)。
- RTC IRQ ハンドラ内で I2C アクセスを行う設計の安全性確認 (再入規約、ハンドラ滞在時間、SD bit-bang 中に IRQ が来た場合の取り扱い)。

## 対象外

このメモではドキュメント化のみを行う。以下は別 Issue で扱う。

- `src/i2c.asm` の実装。
- `include/hardware.inc` への I2C 関連定数追加。
- `src/sdcard.asm` の改修 (Port B 共有案を採る場合のシャドウ拡張など)。
- エミュレータへの I2C スレーブモデル追加。
- 個別 I2C デバイス (RTC/EEPROM/OLED) のドライバ実装。
- AUTOEXEC からの RTC 統合および時刻表示コマンド。
- 後続 Issue の GitHub 登録 (本メモでは候補列挙のみ)。
