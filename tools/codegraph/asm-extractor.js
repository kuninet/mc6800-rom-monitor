"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.AsmExtractor = void 0;
const tree_sitter_helpers_1 = require("./tree-sitter-helpers");
/**
 * 6800/6502/Z80 系レトロアセンブリ(.asm/.s/.inc)用のカスタム抽出器。
 *
 * 多様な手書きアセンブラ方言に合う tree-sitter 文法が無いため、行単位の
 * 正規表現で解析する。アセンブリのシンボル意味論は単純:
 *
 *   LABEL:                 → NodeKind `function`(入口)/ `label`(局所)
 *   NAME equ <expr>        → NodeKind `constant`(signature = 式)
 *   jsr / bsr TARGET       → `calls` エッジ
 *   jmp TARGET             → `references` エッジ(末尾ジャンプ/エラー経路)
 *   <データ命令> ... SYMBOL → オペランドのシンボルごとに `references` エッジ
 *   fcb/fdb SYMBOL         → `references` エッジ(データ表/ベクタ)
 *   NAME equ A-B           → NAME から A,B への `references`(定数依存)
 *   include "file"         → 取り込みファイル basename への `references`
 *
 * オペランドのシンボルは過剰に拾ってよい。解決器は実在ノードに一致する参照
 * だけを残し、残りを黙って捨てるため、余分なトークン($FFやレジスタ名)は
 * 無害。これにより `callers PIA_PRB` / `impact SD_PORTB_SHADOW` が機能し、
 * エミュレータ(Python)とファームウェア(asm)が同じレジスタ名を共有する
 * 関係でクロス言語参照も自動的に張られる。
 *
 * 条件分岐(beq/bne/bra/...)はルーチン内制御フローなので、コールグラフを
 * 汚さないよう意図的に無視する。
 */
const LABEL_RE = /^([A-Za-z_.][A-Za-z0-9_.$]*):/;
const EQU_RE = /^([A-Za-z_.][A-Za-z0-9_.$]*)\s+equ\s+(.*)$/i;
const SYMBOL_RE = /[A-Za-z_.][A-Za-z0-9_.$]*/g;
// フロー終端: 直後のラベルは新しいルーチンの入口とみなす。
const TERMINATOR_RE = /^\s*(rts|rti|jmp|bra)\b/i;
const CALL_OPS = new Set(['jsr', 'bsr']);
const BRANCH_OPS = new Set([
    'beq', 'bne', 'bra', 'bcc', 'bcs', 'bhi', 'bls', 'bge', 'blt', 'bgt', 'ble',
    'bmi', 'bpl', 'bvs', 'bvc', 'brn', 'lbra', 'lbeq', 'lbne',
]);
const DATA_OPS = new Set(['fcb', 'fdb', 'fcc', 'fqb', 'dc', 'db', 'dw']);
// シンボルに見えるがレジスタ/条件コードのトークン。未解決参照を減らすため除外。
const REGISTERS = new Set(['a', 'b', 'x', 'y', 's', 'u', 'd', 'cc', 'pc', 'sp']);
class AsmExtractor {
    filePath;
    source;
    nodes = [];
    edges = [];
    unresolvedReferences = [];
    errors = [];
    constructor(filePath, source) {
        this.filePath = filePath;
        this.source = source;
    }
    extract() {
        const startTime = Date.now();
        try {
            const fileNode = this.createFileNode();
            this.parse(fileNode.id);
        }
        catch (error) {
            this.errors.push({
                message: `ASM extraction error: ${error instanceof Error ? error.message : String(error)}`,
                severity: 'error',
                code: 'parse_error',
            });
        }
        return {
            nodes: this.nodes,
            edges: this.edges,
            unresolvedReferences: this.unresolvedReferences,
            errors: this.errors,
            durationMs: Date.now() - startTime,
        };
    }
    createFileNode() {
        const lines = this.source.split('\n');
        const id = (0, tree_sitter_helpers_1.generateNodeId)(this.filePath, 'file', this.filePath, 1);
        const fileNode = {
            id,
            kind: 'file',
            name: this.filePath.split('/').pop() || this.filePath,
            qualifiedName: this.filePath,
            filePath: this.filePath,
            language: 'assembly',
            startLine: 1,
            endLine: lines.length,
            startColumn: 0,
            endColumn: lines[lines.length - 1]?.length || 0,
            updatedAt: Date.now(),
        };
        this.nodes.push(fileNode);
        return fileNode;
    }
    /** 行末の `;` コメントを除去(asm のオペランドに `;` は出ない)。 */
    stripComment(line) {
        const idx = line.indexOf(';');
        return idx < 0 ? line : line.slice(0, idx);
    }
    addNode(name, kind, lineNum, line, signature) {
        const nodeId = (0, tree_sitter_helpers_1.generateNodeId)(this.filePath, kind, name, lineNum);
        const node = {
            id: nodeId,
            kind,
            name,
            qualifiedName: `${this.filePath}#${name}`,
            filePath: this.filePath,
            language: 'assembly',
            startLine: lineNum,
            endLine: lineNum,
            startColumn: 0,
            endColumn: line.length,
            updatedAt: Date.now(),
        };
        if (signature)
            node.signature = signature;
        this.nodes.push(node);
        return node;
    }
    addRef(fromNodeId, name, kind, lineNum) {
        this.unresolvedReferences.push({
            fromNodeId,
            referenceName: name,
            referenceKind: kind,
            line: lineNum,
            column: 0,
        });
    }
    /** オペランド式の中のシンボルらしいトークンごとに `references` を張る。 */
    emitOperandRefs(fromNodeId, operand, lineNum, skipFirst) {
        // 数値リテラルを落とし、$FF→"FF" のような桁文字が漏れないようにする。
        const cleaned = operand
            .replace(/\$[0-9A-Fa-f]+/g, ' ')
            .replace(/%[01]+/g, ' ')
            .replace(/'./g, ' ');
        let first = true;
        const seen = new Set();
        let m;
        SYMBOL_RE.lastIndex = 0;
        while ((m = SYMBOL_RE.exec(cleaned)) !== null) {
            const tok = m[0];
            if (skipFirst && first) {
                first = false;
                continue;
            }
            first = false;
            if (REGISTERS.has(tok.toLowerCase()))
                continue;
            if (seen.has(tok))
                continue;
            seen.add(tok);
            this.addRef(fromNodeId, tok, 'references', lineNum);
        }
    }
    parse(fileNodeId) {
        const lines = this.source.split('\n');
        let nearestLabel = null; // 直近のラベルノード(endLine 補正用)
        let currentEntry = fileNodeId; // 直近の「入口」ラベル — 参照/呼出の帰属先
        let prevCode = ''; // 直前の非空・非コメント行
        for (let i = 0; i < lines.length; i++) {
            const raw = lines[i];
            const lineNum = i + 1;
            const trimmedStart = raw.trimStart();
            if (trimmedStart.startsWith(';') || trimmedStart.startsWith('*'))
                continue;
            const line = this.stripComment(raw);
            if (line.trim() === '')
                continue;
            let rest = line;
            // --- ラベル定義(行頭・末尾コロン) ---
            const labelMatch = line.match(LABEL_RE);
            if (labelMatch) {
                const name = labelMatch[1];
                // 入口判定: 最初のラベル、またはフロー終端の直後。
                const isEntry = !nearestLabel || TERMINATOR_RE.test(prevCode);
                const kind = isEntry ? 'function' : 'label';
                if (nearestLabel)
                    nearestLabel.endLine = lineNum - 1;
                const node = this.addNode(name, kind, lineNum, line);
                nearestLabel = node;
                this.edges.push({ source: fileNodeId, target: node.id, kind: 'contains' });
                if (isEntry)
                    currentEntry = node.id;
                rest = line.slice(labelMatch[0].length);
            }
            else {
                // --- `NAME equ <expr>` 定数 ---
                const equMatch = line.match(EQU_RE);
                if (equMatch) {
                    const name = equMatch[1];
                    const expr = equMatch[2].trim();
                    const node = this.addNode(name, 'constant', lineNum, line, `equ ${expr}`);
                    this.edges.push({ source: fileNodeId, target: node.id, kind: 'contains' });
                    // 右辺シンボル → 定数依存グラフ。
                    this.emitOperandRefs(node.id, expr, lineNum, false);
                    prevCode = line;
                    continue;
                }
            }
            prevCode = line;
            const trimmed = rest.trim();
            if (trimmed === '')
                continue;
            // --- include ディレクティブ ---
            const incMatch = trimmed.match(/^include\s+["']([^"']+)["']/i);
            if (incMatch) {
                const base = incMatch[1].split('/').pop() || incMatch[1];
                this.addRef(fileNodeId, base, 'references', lineNum);
                continue;
            }
            // ニーモニック + オペランドに分割。
            const opMatch = trimmed.match(/^([A-Za-z_.][A-Za-z0-9_.$]*)\s*(.*)$/);
            if (!opMatch)
                continue;
            const mnem = opMatch[1].toLowerCase();
            const operand = opMatch[2];
            if (CALL_OPS.has(mnem)) {
                // jsr/bsr → 呼出先(最初のオペランドシンボル)への calls エッジ。
                const t = operand.match(SYMBOL_RE);
                if (t && t.length)
                    this.addRef(currentEntry, t[0], 'calls', lineNum);
            }
            else if (mnem === 'jmp') {
                const t = operand.match(SYMBOL_RE);
                if (t && t.length)
                    this.addRef(currentEntry, t[0], 'references', lineNum);
            }
            else if (BRANCH_OPS.has(mnem)) {
                // 局所制御フロー — 意図的に無視。
            }
            else {
                // データ/算術命令: オペランドの全シンボルをデータ参照とする。
                this.emitOperandRefs(currentEntry, operand, lineNum, false);
            }
        }
        if (nearestLabel)
            nearestLabel.endLine = lines.length;
    }
}
exports.AsmExtractor = AsmExtractor;
