# Issue #300 SDFS/68 v3 system slot A/Bとactive marker形式

## 対象

- 親Issue: #254
- Epic: #296
- 前提Issue: #257、#258、#295
- 本Issue: #300
- 後続Issue: #301、#302、#303

## 背景

#295 で ROM モニタの `BOOT3` は physical LBA 64 の単一 `SDFS3SYS` を読み、header 検査と16bit checksum 検査を通してから `SDFS3_LOAD_BASE` へ配置している。
この単一slot方式は初期の実機確認には十分だが、system 更新に失敗した場合に旧 image へ戻る手段がない。

#258 では復旧方式として二重slot + active marker を本線候補にした。
本Issueは、その候補を後続の ROM loader (#301) と PC側更新ツール (#302) が参照できるバイト単位の仕様へ確定させる。
実装は本Issueの対象外である。

## 決定事項の要約

- system予約領域を physical LBA `16` から `2047` に置き、その中に slot A、slot B、active marker を固定配置する。
- slot 先頭は `SDFS3SYS` image の先頭そのものとし、slot wrapper header は導入しない。
- slot 世代番号は `SDFS3SYS` header の reserved 領域を割り当てて表現する。
- active marker は `SDFS3SYS` header と同じ checksum / size 欄配置を持つ1 sectorとする。
- ROM loader は active marker だけを信頼せず、marker 不正時は slot 側 generation と checksum で起動slotを選ぶ。
- active marker を持たない既存の単一LBA image は、fallback 規則により slot A として起動できる。

## physical LBA レイアウト

SDカード先頭からの physical LBA で固定配置する。sector size は 512 bytes とする。

| physical LBA | sectors | 用途 |
| ---: | ---: | --- |
| `0` | 1 | MBR |
| `1` - `15` | 15 | 予約。使用しない |
| `16` - `47` | 32 | v2互換 `stage1` 固定領域 (`DEFAULT_STAGE1_LBA=16`) |
| `48` | 1 | v3 system active marker |
| `49` - `63` | 15 | 予約。将来のmarker拡張候補 |
| `64` - `95` | 32 | system slot A |
| `96` - `127` | 32 | system slot B |
| `128` - `2047` | 1920 | 予約。将来のsystem領域拡張候補 |
| `2048` - | - | FAT32 partition |

- slot A の開始 LBA `64` は #295 の `SDFS3SYS_FIXED_LBA` と同一である。既存 image と ROM 実装を変更せずに slot A として扱える。
- slot あたり上限は 32 sectors = 16384 bytes とし、`tools/mk_sdfs3sys.py` の `MAX_IMAGE_SIZE` と一致させる。
- v2 `stage1` 領域を残すのは、v3 が不調な場合の比較経路として #257 の判断を維持するためである。v3専用カードで `stage1` を置かない場合も、LBA `16` - `47` はFATへ割り当てない。
- FAT32 partition 開始 LBA は `2048` を既定とする。`tools/fat32_image.py` の `DEFAULT_PARTITION_START_LBA=32` はv2既定であり、v3 system image では使わない。

## SDFS3SYS header の拡張

slot の先頭は `SDFS3SYS` image の先頭とし、slot wrapper header は置かない。

理由は次のとおりである。

- wrapper を置くと slot 先頭と `SDFS3SYS` 先頭がずれ、#295 の `BOOT3` と `tools/mk_sdfs3sys.py` の前提を両方変更することになる。
- slot が必要とする追加情報は世代番号だけであり、header の reserved 領域で足りる。
- 単一LBA image と slot image をバイト単位で同一に保てるため、既存の実機確認手順とfixtureを流用できる。

#257 の header のうち reserved `$1C` - `$1F` を次のように割り当てる。

| Offset | Size | 項目 | 内容 |
| ---: | ---: | --- | --- |
| `$1C` | 2 | `slot_generation` | slot 世代番号。big endian。`0` は世代未設定を表す |
| `$1E` | 2 | `reserved` | 将来拡張用。`0` 固定 |

- `header_version` は `1` のまま維持する。`slot_generation` は reserved からの割り当てであり、既存 image は `0` として解釈される。
- `slot_generation` は `$1C` にあるため、既存の16bit加算 checksum の計算範囲に含まれる。世代を書き換えたら checksum を再計算する。
- 値域は `1` - `$FFFF` とし、更新のたびに +1 する。`$FFFF` の次は `0` を飛ばして `1` へ戻る。
- `0` は「世代未設定」であり、世代比較の対象外とする。

## active marker sector 形式

physical LBA `48` の1 sectorに置く。marker が使うのは先頭32 bytesで、残り480 bytesは `0` 埋めとする。

| Offset | Size | 項目 | 内容 |
| ---: | ---: | --- | --- |
| `$00` | 8 | `magic` | `SDFS3MRK` |
| `$08` | 1 | `marker_version` | marker形式のversion。初期値は `1` |
| `$09` | 1 | `active_slot` | `0` = slot A、`1` = slot B。他の値は不正 |
| `$0A` | 1 | `slot_count` | slot 数。初期値は `2` |
| `$0B` | 1 | `flags` | bit0 = 16bit checksum 有効。他bitは `0` |
| `$0C` | 2 | `marker_generation` | marker 世代番号。big endian。`1` から開始する |
| `$0E` | 2 | `slot_max_sectors` | slot あたり上限 sector 数。初期値は `32` |
| `$10` | 2 | `slot_a_lba` | slot A 開始 physical LBA の下位16bit。初期値は `64` |
| `$12` | 2 | `slot_b_lba` | slot B 開始 physical LBA の下位16bit。初期値は `96` |
| `$14` | 4 | `reserved` | 将来拡張用。`0` 固定 |
| `$18` | 2 | `checksum` | checksum欄を `0` として計算した sector 全体512 bytesの16bit加算 |
| `$1A` | 2 | `marker_size` | marker 部の byte 数。初期値は `32` |
| `$1C` | 4 | `reserved` | 将来拡張用。`0` 固定 |

- 16bit値は `SDFS3SYS` header と同じく上位byte、下位byteの順に置く。
- `checksum` を `$18`、size 欄を `$1A` に置くのは `SDFS3SYS` header と同一である。ROM loader は既存の checksum ルーチンと size 検査の形をそのまま使える。
- checksum は sector 全体512 bytesの単純16bit加算とする。`SDFS3SYS` の checksum は image 全体、marker の checksum は sector 全体であり、どちらも checksum 欄2 bytesを `0` として計算する。
- `slot_a_lba` と `slot_b_lba` は下位16bitのみを持つ。本仕様の配置では上位16bitは `0` であり、ROM loader は自身の固定値と一致するかの確認にだけ使う。
- ROM loader は `slot_a_lba` / `slot_b_lba` / `slot_max_sectors` を「読み替えるための値」ではなく「marker が同じレイアウトを前提にしているかの検証情報」として扱う。ROM 側の固定値と不一致なら marker 不正とする。レイアウト変更を marker だけで行えるようにはしない。

## 検査条件

### marker 有効条件

次をすべて満たすとき marker は有効である。

- sector read が成功する。
- `magic` が `SDFS3MRK` である。
- `marker_version` が `1` である。
- `marker_size` が `32` 以上、かつ `512` 以下である。
- `flags` bit0 が `1` である。
- `checksum` が sector 全体の計算値と一致する。
- `active_slot` が `0` または `1` である。
- `slot_count` が `2` である。
- `slot_max_sectors` が ROM の固定値 `32` と一致する。
- `slot_a_lba` が `64`、`slot_b_lba` が `96` と一致する。

### slot 有効条件

次をすべて満たすとき slot は起動可能である。#295 の `BOOT3` header 検査に、size 範囲と image 全体 checksum の条件を明示的に加えたものである。

- slot 先頭 sector の read が成功する。
- `magic` が `SDFS3SYS` である。
- `header_version` が `1` である。
- `abi_major` が ROM の対応値と一致する。
- `flags` bit0 が `1` である。
- `load_address` が ROM の `SDFS3_LOAD_BASE` と一致する。
- `header_size` が `$0020` である。
- `image_size` が `header_size + 1` 以上、`16384` 以下である。
- `image_size` が示す byte 数をすべて読んだうえで、16bit加算 checksum が `checksum` と一致する。

`image_size` から必要 sector 数は `ceil(image_size / 512)` であり、slot 上限 32 sectors を超えない。
`image_size` の上限 `16384` を満たせば sector 数条件は自動的に満たされる。

### 重なり検出条件

PC側ツールと生成物検証は、次のいずれかに該当する image を不正として扱う。

- slot A の範囲 `[64, 96)` と slot B の範囲 `[96, 128)` が重なる。
- marker LBA `48` が slot 範囲または `stage1` 領域 `[16, 48)` に含まれる。
- FAT32 partition 開始 LBA が `128` 未満である。
- FAT32 partition の範囲が marker、slot A、slot B、`stage1` 領域のいずれかと重なる。
- `image_size` が `16384` を超える、または slot 範囲外へはみ出す。
- MBR の LBA `0` を上書きする。

## 起動slot選択の優先順位

ROM loader は次の順で起動slotを決める。marker だけには依存しない。

1. marker が有効で、`active_slot` が指す slot も有効なら、その slot をロードする。
2. marker が無効、または `active_slot` が指す slot が無効な場合は、slot A と slot B の両方を検査する。
   - 両方が有効で、両方の `slot_generation` が `0` でなく、値が異なる場合は、`slot_generation` が大きい方を選ぶ。
   - 世代の巻き戻りは判定しない。`$FFFF` と `1` が並んだ場合は `$FFFF` を新しいとみなす。この状態は PC側更新ツールが作らないようにする。
   - 片方だけ有効なら、その有効な slot を選ぶ。
   - 両方有効だが世代比較ができない場合は、slot A、slot B の順で先に有効だった方を選ぶ。
3. どちらの slot も無効なら、resident をロードせずに `?` を表示して ROM モニタの `] ` プロンプトへ戻る。

`SD_INIT` または sector read の失敗は slot 無効として扱う。
検査に通るまで resident 有効フラグを立てない方針は #257 のまま維持し、途中まで RAM へ読んだ状態で resident を有効扱いしない。

## 更新時の generation 規約

PC側更新ツール (#302) と将来の実機側更新は次を守る。

- 新しい image を非active slot へ書くとき、`slot_generation` を「現在の両slotの `slot_generation` の最大値 + 1」にする。`$FFFF` の次は `1` とする。
- `slot_generation` を決めてから `SDFS3SYS` checksum を計算する。
- slot 書き込み後に読み戻し、slot 有効条件をすべて確認する。
- 確認に通った場合だけ marker を書き換える。`active_slot` を新slotへ、`marker_generation` を +1 する。
- marker 書き込み後に読み戻し、marker 有効条件を確認する。
- いずれかで失敗した場合は marker を書き換えず、旧active slotを維持する。

この順序により、slot 書き込み中の中断では marker が旧slotを指したままとなり、marker 書き込み中の中断では marker 不正として slot 側 generation による選択へ落ちる。

## 既存の単一LBA imageとの互換

#295 と #299 が作る「LBA 64 に `SDFS3SYS` 1つ、marker なし」の image は、本仕様のもとで次のように扱われる。

- LBA 48 は `0` 埋めまたは未書き込みであり、`magic` 不一致で marker 無効となる。
- 選択規則2へ進み、slot A が有効、slot B が無効となる。
- slot A がロードされる。

したがって既存の開発用 image は互換を切らずにそのまま起動できる。
`slot_generation` は `0` のままでよく、二重slot化した時点で PC側ツールが `1` 以降を振る。
本仕様は既存 image 形式を変更しないため、#301 の ROM loader を入れた後も、単一slot imageでの実機確認手順は維持する。

## ROM側実装への影響見積り

#301 での実装量を見積もる目的でのみ記す。確定値ではない。

- marker sector の read と magic / version / checksum / active_slot 検査が増える。`SDFS3SYS` header と checksum 欄配置を揃えたため、既存の `BOOT3_SUM_CURRENT` 相当を再利用できる。
- slot 開始 LBA が2つになるため、`BOOT3_SET_LBA` を slot 指定つきへ拡張する必要がある。
- 選択規則2の世代比較は16bit比較1回で足りる。
- ROM 容量が不足する場合に削る優先順位は、世代比較、marker の `slot_*` 検証情報の照合、marker の `slot_count` 検査の順とする。これらを削っても選択規則3の slot A、slot B 順の fallback は残す。

## 対象外

- ROM loader の実装。#301 で扱う。
- PC側更新ツールの実装。#302 で扱う。
- 実機側 raw sector write と `INSTALL` / `SYSWRITE`。#303 以降で扱う。
- FAT write。
- LBA `128` - `2047` の予約領域の具体的な用途。

## 検証方針

本Issueは設計文書の追加のみであり、バイナリやコマンド動作は変更しない。
PR前の `make test` は、ドキュメントのみの変更として省略できる。
差分確認では、v3設計文書と目次以外のファイルが混ざっていないこと、改行コードを変更していないことを確認する。

## 関連

- #254: SDFS/68 v3親Issue。
- #296: phase 2 実機起動・system運用epic。
- #257: 固定LBA system image形式と1発ロード方式。
- #258: system領域更新方式。
- #295: BOOT3 固定LBA loader。
- #299: system SD生成ツールのBOOT3用イメージ正式化。
- #301: BOOT3のslot A/B対応拡張。
- #302: PC側の非active slot更新。
