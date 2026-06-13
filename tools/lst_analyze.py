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


if __name__ == "__main__":
    cfg = sys.argv[1] if len(sys.argv) > 1 else "sbcio-sdfs"
    ours = our_symbols()
    rom = report(ROOT / f"build/mc6800-monitor-{cfg}.lst", f"ROMモニタ [{cfg}]", ours)
    sdfs = report(ROOT / f"build/SDFS-{cfg}.lst", f"SDFSモジュール [{cfg}]", ours)
    report(ROOT / f"build/stage1-{cfg}.lst", f"stage1 [{cfg}]", ours)
    if rom and sdfs:
        dup_report(rom, sdfs, ours)
