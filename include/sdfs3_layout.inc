; SDFS/68 v3 案 B の低位 RAM の配置(#310 の 4-1)。resident だけが include する。
; ROM はこの番地を持たない(SDFS3SYS ヘッダから読む。仕様 1-7)。sbcio_vdg・k6802_vdg で共通。
;
;   $0100-$6FFF  .COM が読み込める範囲(上限 SDFS3_COM_MAX = $6F00 バイト。#315)
;   $6800-$6BFF  上端の一時区画。LOAD・RUN の本体 XLDR.OVL が動く(#316)
;   $6C00-$6FFF  CCP(入口表 +0 cold / +3 warm / +6 予約 と、DOS のプロンプト)。
;                大きな .COM は CCP を潰してよい(戻りで ROM の WBOOT が読み直す)
;   $7000-$7FFF  核(SDFS3API ヘッダ、ジャンプテーブル、FAT32、ファイル API)
;
; CCP_BASE は 1KB 枠の先頭 $6C00(#316 で LOAD/RUN を外して戻した)。CCP が 1KB を超えたら下げる。
; 試験では、asl の -D SDFS3_CCP_BASE_TEST=<値> で下げたイメージを作れる(#316 のシナリオ 4。
; Makefile の SDFS3_ASL_DEFS で渡す)。XLDR_BASE は XLDR.OVL が動く上端の一時区画。

 ifdef SDFS3_CCP_BASE_TEST
SDFS3_CCP_BASE   equ SDFS3_CCP_BASE_TEST
 else
SDFS3_CCP_BASE   equ $6C00
 endif
SDFS3_CORE_BASE  equ $7000
SDFS3_XLDR_BASE  equ $6800
SDFS3_MEMTOP     equ SDFS3_CORE_BASE-1
SDFS3_COM_BASE   equ $0100
SDFS3_COM_MAX    equ SDFS3_CORE_BASE-SDFS3_COM_BASE

 if (SDFS3_CCP_BASE&$00FF) <> 0
        error   "SDFS3_CCP_BASE must be on a 256-byte boundary"
 endif
 if SDFS3_CCP_BASE < SDFS3_RAM_FLOOR
        error   "SDFS3_CCP_BASE is below SDFS3_RAM_FLOOR"
 endif
 if USER_RAM_END < $7FFF
        error   "SDFS/68 v3 needs USER_RAM_END=$7FFF (sbcio_vdg or k6802_vdg); 4000 work profiles are v2 only"
 endif
