; LOAD.COM・RUN.COM の共通の入口(#316、仕様 3-2)。include する前に XLDR_CMD(1 = LOAD、2 = RUN)を決める。
; 本体 XLDR.OVL を /BIN から(なければルートから)$6800 に読み、A = XLDR_CMD、X・B = 引数のままで
; 本体へ jmp する。本体の RTS は BIOS_EXEC が積んだ WBOOT に戻る。
; 本体は核の LOAD_PATH(flags = 0)で読む。上限は GET_MEMTOP なので、本体の末尾が memtop を
; 越えるときは読み込みの前に失敗する。読み込みの途中の失敗は、核が WBOOT へ飛んで「?」を出す。
; 本体が見つからない・合わないときは「?」を出して RTS(DOS のプロンプトへ戻る)。

BIOS_GET_API    EQU     $E0EC
PDATA1          EQU     $E07E
XLDR_BASE       EQU     $6800
X_API_MAJOR     EQU     2

        ORG     $0100
START   STX     ARGP
        STAB    ARGL
        JSR     BIOS_GET_API
        BCS     FAIL
        LDAA    8,X
        CMPA    #X_API_MAJOR
        BNE     FAIL
        LDX     12,X            ; ジャンプテーブル
        STX     TBL
        LDX     14,X            ; slot 7 GET_MEMTOP
        STX     CALL+1
        JSR     CALL
        STX     BLK+5           ; limit = memtop
        LDX     TBL
        LDX     4,X             ; slot 2 LOAD_PATH
        STX     CALL+1
        LDX     #BLK
        JSR     CALL            ; /BIN/XLDR.OVL
        BCC     LOADED
        LDX     #PATH+5         ; なければルートの XLDR.OVL
        STX     BLK
        LDAA    #PATH_LEN-5
        STAA    BLK+2
        LDX     #BLK
        JSR     CALL
        BCS     FAIL
LOADED  LDX     XLDR_BASE+3     ; 署名 "XLDR"
        CPX     #$584C
        BNE     FAIL
        LDX     XLDR_BASE+5
        CPX     #$4452
        BNE     FAIL
        LDAA    #XLDR_CMD
        LDX     ARGP
        LDAB    ARGL
        JMP     XLDR_BASE
FAIL    LDX     #MSG_ERR
        JMP     PDATA1          ; RTS で WBOOT へ

CALL    JMP     0
; LOAD_PATH のブロック {path, path_len, load, limit, flags, argptr, arg_len}
BLK     FDB     PATH
        FCB     PATH_LEN
        FDB     XLDR_BASE
        FDB     0
        FCB     0
        FDB     0
        FCB     0
PATH    FCC     "/BIN/XLDR.OVL"
PATH_LEN EQU    *-PATH
MSG_ERR FCC     "?"
        FCB     $0D,$0A,4
TBL     FDB     0
ARGP    FDB     0
ARGL    FCB     0
