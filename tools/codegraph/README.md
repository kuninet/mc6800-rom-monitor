# CodeGraph asm 拡張プラグイン

ソース索引ツール CodeGraph(`@colbymchenry/codegraph`)は tree-sitter ベースで、
標準では `.asm` を解析できない(シンボルが一切抽出されない)。本ディレクトリは、
このプロジェクトの MC6800 アセンブリを索引できるようにする **カスタム抽出器** と、
その適用手順を保全したもの。

呼び出し構造・クロス参照の俯瞰(「構造地図」)用途に使う。**条件アセンブリや
マクロは評価しない**ため、構成別の重複/デッドコード判定には使わない
(そちらは `tools/lst_analyze.py` の `.lst` ベース解析を使う)。

## 構成物

- `asm-extractor.js` — 行単位の正規表現でラベル/定数/呼出/参照を抽出する抽出器。
  抽出ルールはファイル冒頭のコメント参照。

## 適用手順(ローカル dist へのパッチ)

CodeGraph 本体は配布済みのコンパイル済み成果物で、拡張子→言語マップは
ハードコードのため、設定では拡張子を足せない。インストール先の `dist/` を
直接パッチする(本体アップグレードで消えるので、その都度再適用する)。

インストール先の例: `~/.codegraph/versions/<ver>/lib/dist/extraction/`

1. 本ファイルの `asm-extractor.js` を `extraction/` 直下にコピーする。

2. `extraction/grammars.js` の `EXTENSION_MAP` に追記する:
   ```js
   '.inc': 'assembly', // このプロジェクトの .inc はアセンブラ include(既定は 'php')
   '.asm': 'assembly',
   '.s': 'assembly',
   ```

3. `extraction/tree-sitter.js` の冒頭 require 群に追記する:
   ```js
   const asm_extractor_1 = require("./asm-extractor");
   ```

4. 同ファイルの `extractFromSource()` のディスパッチに分岐を追加する
   (`pascal`(.dfm)分岐の手前あたり):
   ```js
   else if (detectedLanguage === 'assembly') {
       const extractor = new asm_extractor_1.AsmExtractor(filePath, source);
       result = extractor.extract();
   }
   ```

5. フル再索引する(増分索引はソース無変更だと抽出器変更を拾わないため):
   ```sh
   codegraph init .        # もしくは codegraph index -f .
   ```

## 確認

```sh
codegraph callers PIA_PRB      # PIA_PRB を読み書きする asm ルーチン + emu(クロス言語)
codegraph callers SD_SPI_XFER  # 呼び出し元ルーチン
codegraph node   SD_PIA_INIT   # ソース + 呼出経路
```

## 既知の限界

- 条件アセンブリ・マクロ非評価(和集合を索引する)。構成別判断には不向き。
- 全ラベルを `function`/`label` として扱うため、分岐のみで到達する局所ラベルは
  「未呼出」に見える(デッドコード判定には使わない)。
- 末尾コロンのないラベル(古典 Motorola 表記)は未対応。本プロジェクトの
  `src/*.asm` は全てコロン付きのため実害なし。
