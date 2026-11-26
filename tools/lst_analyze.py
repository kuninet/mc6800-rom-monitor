#!/usr/bin/env python3
"""構成正確な無駄削減解析 — ASL のアセンブルリスト(.lst)ベース。

ソース索引(構造地図)は生ソースの和集合しか見ない(条件アセンブリ/マクロを
評価しない)。一方 ASL の .lst 末尾シンボルテーブルは「その構成で実際に
アセンブルされた結果」を持ち、未使用シンボルを `*` で印字する。これを
構成正確な無駄削減判断の土台にする。

flag: 'C' = コード(ラベル) / '-' = 値(equ 等)

使い方:
    python3 tools/lst_analyze.py [構成名]   # 既定 sbcio-sdfs
"""
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CELL = re.compile(r"^\s*(\*?)\s*([A-Za-z_.][A-Za-z0-9_.$]*)\s*:\s+(.+?)\s+([C-])\s*$")


def our_symbols():
    """ソース索引DB(あれば)から自前 asm シンボル名集合を得る(組込み除去用)。

    DBが無い場合は空集合を返し、全シンボルを対象にする。"""
    db = ROOT / ".codegraph" / "codegraph.db"
    if not db.exists():
        return set()
    con = sqlite3.connect(db)
    try:
        rows = con.execute(
            "SELECT DISTINCT name FROM nodes WHERE language='assembly' "
            "AND file_path NOT LIKE 'third_party/%'"
        ).fetchall()
    except sqlite3.Error:
        return set()
    finally:
        con.close()
    return {r[0] for r in rows}


def parse_symbol_table(lst_path):
    """{name: (value, flag, unused_bool)} を返す。"""
    p = Path(lst_path)
    if not p.exists():
        return {}
    text = p.read_text(errors="replace").splitlines()
    start = next((i for i, l in enumerate(text) if "Symbol Table" in l), None)
    if start is None:
        return {}
    syms = {}
    for line in text[start + 1:]:
        for cell in line.split("|"):
            m = CELL.match(cell)
            if not m:
                continue
            star, name, value, flag = m.groups()
            syms[name] = (value.strip(), flag, star == "*")
    return syms


def in_scope(name, ours):
    """自前シンボル集合が空(DBなし)なら全対象、あれば交差で組込みを除去。"""
    return (not ours) or (name in ours)


def report(lst_path, label, ours):
    syms = parse_symbol_table(lst_path)
    if not syms:
        print(f"\n{'='*70}\n■ {label}  ({Path(lst_path).name})  — リストなし(スキップ)")
        return {}
    mine = {n: v for n, v in syms.items() if in_scope(n, ours)}
    dead_code = sorted(n for n, (_, f, u) in mine.items() if u and f == "C")
    dead_const = sorted(n for n, (_, f, u) in mine.items() if u and f == "-")
    print(f"\n{'='*70}\n■ {label}  ({Path(lst_path).name})")
    print(f"  対象シンボル {len(mine)} 個 / 全 {len(syms)} 個")
    print(f"\n  ▼ 未使用コード(※フォールスルー/外部API入口を含む。要目視) {len(dead_code)} 件")
    for n in dead_code:
        print(f"      {n}  @{mine[n][0]}")
    print(f"\n  ▼ 未使用定数(デッド equ 候補) {len(dead_const)} 件")
    for n in dead_const:
        print(f"      {n} = {mine[n][0]}")
    return syms


def dup_report(rom, sdfs, ours):
    """main↔SDFS_ 対が、各バイナリで実際に live(コード・使用中)か。"""
    print(f"\n{'='*70}\n■ 重複対の構成正確チェック(ROM vs SDFSモジュール)")
    universe = set(rom) | set(sdfs) | ours
    pairs = sorted(n for n in universe
                   if not n.startswith("SDFS_") and f"SDFS_{n}" in universe)
    both_live = []
    for base in pairs:
        r = rom.get(base)
        s = sdfs.get(f"SDFS_{base}")
        r_live = r and r[1] == "C" and not r[2]
        s_live = s and s[1] == "C" and not s[2]
        if r_live and s_live:
            both_live.append(base)
    print(f"  ソース上の対: {len(pairs)} 組")
    print(f"  両バイナリに live(=実コード・使用中)で存在する真の重複: {len(both_live)} 組")
    for b in both_live:
        print(f"      {b}  (ROM @{rom[b][0]})  ↔  SDFS_{b}  (SDFS @{sdfs['SDFS_'+b][0]})")


BODY = re.compile(r"^\s*\d+/[0-9A-Fa-f]+\s*:\s*(.*)$")
LABELDEF = re.compile(r"^([A-Za-z_.][A-Za-z0-9_.$]*):")


def reclaim_report(cfg, rom):
    """案1(ROMローダAPI化)でSDFSモジュールから回収できるバイト数を、
    リスト本文の実出力バイトを行単位で集計して見積もる。

    各行を直近のラベルに帰属させ、`SDFS_X` の X が ROM に live コードとして
    存在すれば「ROM再利用可能=回収対象」とする。ただしROMに存在しない
    `SDFS_PARSE_FILENAME_*` はSDFS固有として据置に分類する。"""
    rom_live = {n for n, v in rom.items() if v[1] == "C" and not v[2]}
    p = ROOT / f"build/SDFS-{cfg}.lst"
    if not p.exists():
        print(f"\n{'='*70}\n■ 回収見積り — SDFSリストなし(スキップ)")
        return
    lines = p.read_text(errors="replace").splitlines()
    end = next((i for i, l in enumerate(lines) if "Symbol Table" in l), len(lines))
    cur = None
    reuse = filename = other = total = 0
    for l in lines[:end]:
        m = BODY.match(l)
        if not m:
            continue
        toks = m.group(1).split()
        nb = 0
        for tk in toks:
            if re.fullmatch(r"[0-9A-F]{2}", tk):
                nb += 1
            else:
                break
        ld = LABELDEF.match(" ".join(toks[nb:]))
        if ld:
            cur = ld.group(1)
        total += nb
        if cur and cur.startswith("SDFS_"):
            base = cur[5:]
            if base.startswith("PARSE_FILENAME"):
                filename += nb
            elif base in rom_live:
                reuse += nb
            else:
                other += nb
        else:
            other += nb
    print(f"\n{'='*70}\n■ 案1 回収見積り(SDFSモジュール [{cfg}])")
    print(f"  総出力バイト: {total} (0x{total:X})")
    print(f"  ├ ROM再利用可能ローダ(回収対象): {reuse} bytes (0x{reuse:X})")
    print(f"  ├ PARSE_FILENAME(SDFS固有・据置): {filename} bytes (0x{filename:X})")
    print(f"  └ その他SDFS本体: {other} bytes (0x{other:X})")
    print(f"  ==> 回収見込み 約 {reuse} bytes")


# ---- 核→CCP 参照検査(#311) -------------------------------------------------
LST_LINE = re.compile(r"^\s*(?:\(\d+\))?\s*(\d+)/\s*([0-9A-Fa-f]+)\s*:\s?(.*)$")
IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_.$]*")
HEXPAIR = re.compile(r"^\s*[0-9A-F]{2}(?=\s|$)")


def _split_bytes_source(rest):
    """リスト行の「: 」以降を (バイト数, ソース文字列) に分ける。"""
    nbytes = 0
    while True:
        m = HEXPAIR.match(rest)
        if not m:
            break
        nbytes += 1
        rest = rest[m.end():]
    return nbytes, rest.strip()


DATA_DIRECTIVES = ("fcb", "fdb", "fcc", "rmb", "db", "dw")


def check_core_ccp_refs(lst_path):
    """案 B の並び(#313)で、核の範囲 [SDFS3_CORE_START, SDFS3_END) の命令・データが、
    CCP の範囲 [SDFS3_CCP_START, SDFS3_CCP_END) のラベルを参照していないか調べる。

    返り値: (違反リスト, 情報dict)。違反は (行番号, アドレス, ソース, 参照先名)。
    核の先頭にある SDFS3API ヘッダとジャンプテーブルも検査に入る(slot が CCP を指すと違反)。
    情報dictには範囲と、CCP の最後の命令(データ行を除く。空き領域への落ち込み検査用)を入れる。"""
    syms = parse_symbol_table(lst_path)
    for need in ("SDFS3_CCP_START", "SDFS3_CCP_END", "SDFS3_CORE_START", "SDFS3_END"):
        if need not in syms:
            raise ValueError(f"missing symbol in listing: {need}")
    ccp = int(syms["SDFS3_CCP_START"][0], 16)
    ccp_end = int(syms["SDFS3_CCP_END"][0], 16)
    core = int(syms["SDFS3_CORE_START"][0], 16)
    end = int(syms["SDFS3_END"][0], 16)
    if not (ccp < ccp_end <= core < end):
        raise ValueError(f"unexpected layout: CCP ${ccp:04X}-${ccp_end:04X} core ${core:04X}-${end:04X}")
    ccp_labels = {}
    for name, (value, flag, _unused) in syms.items():
        if flag != "C":
            continue
        try:
            addr = int(value, 16)
        except ValueError:
            continue
        if ccp <= addr < ccp_end:
            ccp_labels[name] = addr
    violations = []
    last_ccp_insn = None
    scanned = 0
    for lineno, line in enumerate(Path(lst_path).read_text(errors="replace").splitlines(), 1):
        if "Symbol Table" in line:
            break
        m = LST_LINE.match(line)
        if not m:
            continue
        addr = int(m.group(2), 16)
        nbytes, src = _split_bytes_source(m.group(3))
        if nbytes == 0:
            continue
        code = src.split(";", 1)[0]
        code = re.sub(r'"[^"]*"', '""', code)
        code = re.sub(r"'.'", "''", code)
        code = re.sub(r"^[A-Za-z_][A-Za-z0-9_.$]*:", "", code.strip()).strip()
        if ccp <= addr < ccp_end:
            if code and code.split()[0].lower() not in DATA_DIRECTIVES:
                last_ccp_insn = code
            continue
        if not (core <= addr < end):
            continue
        scanned += 1
        for name in IDENT.findall(code):
            if name in ccp_labels:
                violations.append((lineno, addr, src, name))
    info = {
        "ccp": ccp,
        "ccp_end": ccp_end,
        "core": core,
        "end": end,
        "scanned": scanned,
        "last_ccp_insn": last_ccp_insn,
    }
    return violations, info


# ---- CCP から SD の書き込みを呼ばない検査(#303) -----------------------------
SD_WRITE_NAMES = (
    "BIOS_SD_SELECT", "BIOS_SD_DESELECT", "BIOS_SD_SEND_CMD", "BIOS_SD_XFER",
    "BIOS_SD_WAIT_R1", "BIOS_SD_WRITE", "SDFS3_SD_WRITE",
)


def _is_sd_write_name(name):
    return name in SD_WRITE_NAMES or name.startswith("SDFS3_SDW_")


def check_ccp_sd_write_refs(lst_path):
    """CCP の範囲 [SDFS3_CCP_START, SDFS3_CCP_END) の命令・データが、SD の書き込み
    (核の SDFS3_SD_WRITE とその内部ラベル SDFS3_SDW_*)と ROM の SD 低レベル入口
    (BIOS_SD_SELECT〜WAIT_R1、予約の BIOS_SD_WRITE)を参照していないか調べる。

    返り値: (違反リスト, CCP を走査した行数)。違反は (行番号, アドレス, ソース, 参照先名)。"""
    syms = parse_symbol_table(lst_path)
    for need in ("SDFS3_CCP_START", "SDFS3_CCP_END"):
        if need not in syms:
            raise ValueError(f"missing symbol in listing: {need}")
    ccp = int(syms["SDFS3_CCP_START"][0], 16)
    ccp_end = int(syms["SDFS3_CCP_END"][0], 16)
    violations = []
    scanned = 0
    for lineno, line in enumerate(Path(lst_path).read_text(errors="replace").splitlines(), 1):
        if "Symbol Table" in line:
            break
        m = LST_LINE.match(line)
        if not m:
            continue
        addr = int(m.group(2), 16)
        nbytes, src = _split_bytes_source(m.group(3))
        if nbytes == 0 or not (ccp <= addr < ccp_end):
            continue
        code = src.split(";", 1)[0]
        code = re.sub(r'"[^"]*"', '""', code)
        code = re.sub(r"'.'", "''", code)
        code = re.sub(r"^[A-Za-z_][A-Za-z0-9_.$]*:", "", code.strip()).strip()
        scanned += 1
        for name in IDENT.findall(code):
            if _is_sd_write_name(name):
                violations.append((lineno, addr, src, name))
    return violations, scanned


def check_core_ccp_main(lst_path):
    violations, info = check_core_ccp_refs(lst_path)
    print(f"CCP ${info['ccp']:04X}-${info['ccp_end'] - 1:04X} / 核 ${info['core']:04X}-${info['end'] - 1:04X}"
          f" (核を {info['scanned']} 行走査)")
    last = (info["last_ccp_insn"] or "").split()
    if not last or last[0].lower() not in ("rts", "rti", "jmp", "bra"):
        print(f"違反: CCP の最後の命令が {info['last_ccp_insn']!r} で、空き領域へ落ち込む可能性")
        return 1
    for lineno, addr, src, name in violations:
        print(f"違反: {lineno}行 ${addr:04X} `{src}` が CCP の {name} を参照")
    print(f"核→CCP 参照: {len(violations)} 件")
    return 1 if violations else 0


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--check-core-ccp":
        sys.exit(check_core_ccp_main(sys.argv[2]))
    cfg = sys.argv[1] if len(sys.argv) > 1 else "sbcio-sdfs"
    ours = our_symbols()
    rom = report(ROOT / f"build/mc6800-monitor-{cfg}.lst", f"ROMモニタ [{cfg}]", ours)
    sdfs = report(ROOT / f"build/SDFS-{cfg}.lst", f"SDFSモジュール [{cfg}]", ours)
    report(ROOT / f"build/stage1-{cfg}.lst", f"stage1 [{cfg}]", ours)
    if rom and sdfs:
        dup_report(rom, sdfs, ours)
        reclaim_report(cfg, rom)
