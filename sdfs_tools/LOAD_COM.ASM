        CPU     6800
; SDFS/68 v3 の LOAD コマンド。S-record か Intel HEX を $0000-$67FF に読み込む(#316)。
; 使い方: LOAD <ファイル>(本体は /BIN/XLDR.OVL)
XLDR_CMD        EQU     1
        INCLUDE "XLDR_STUB.INC"
        END     START
