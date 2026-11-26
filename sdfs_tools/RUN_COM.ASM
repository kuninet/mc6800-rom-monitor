        CPU     6800
; SDFS/68 v3 の RUN コマンド。S-record を読み込んで S9/S8 の番地を起動する。
; 引数が 16 進 4 桁なら、その番地を起動する(#316)。
; 使い方: RUN <ファイル> / RUN <番地>(本体は /BIN/XLDR.OVL)
XLDR_CMD        EQU     2
        INCLUDE "XLDR_STUB.INC"
        END     START
