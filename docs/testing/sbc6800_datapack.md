# SBC6800 データパックの扱い

`third_party/sbc6800_datapack/` には、SBC6800 向けデータパック一式を保持する。

## 目的

- MIKBUG 固定入口番地の実データ調査
- 既存バイナリや S-record の互換動作確認
- エミュレータ smoke test の回帰データ

## 現在の主な利用ファイル

- `HELLO.S`
  - `PDATA1 ($E07E)` を使った最小の動作確認
- `MICBAS13.S`
  - `INEEE ($E1AC)` / `OUTEEE ($E1D1)` / `CONTRL ($E0E3)` を使った互換確認
- `MIKBUG.LST`
  - MIKBUG の固定入口番地確認

## 実装との関係

フェーズ6では、SBC6800 データパック付属の `HELLO` と `MICBAS13` がそのまま動くことを互換性の確認対象にした。

そのため、モニタ側では少なくとも次の番地を互換対象として扱う。

- `OUTCH = $E075`
- `INCH = $E078`
- `PDATA1 = $E07E`
- `CONTRL = $E0E3`
- `INEEE = $E1AC`
- `OUTEEE = $E1D1`

## テストとの関係

`tests/test_smoke.py` では、このディレクトリの `HELLO.S` と `MICBAS13.S` を読み込み、エミュレータ上で次を確認する。

- データパック形式の S-record をロードできる
- `HELLO, WORLD` が表示できる
- `MICBAS13` が起動して `READY` を表示できる

## 運用ルール

- データパックは一式を保持し、必要なファイルだけを後から足し引きしない
- 差し替えや更新を行う場合は、入手元と変更理由を Issue / PR に記録する
- third-party 資産として扱い、本プロジェクト本体のソースとは区別する
