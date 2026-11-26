        CPU     6800
; SDFS/68 v3 の LOAD と RUN の本体(オーバーレイ)。/BIN/XLDR.OVL に置く(#316、仕様 3-2)。
; LOAD.COM・RUN.COM の入口が $6800(上端の一時区画)に読み込み、jmp で入る。
;   入口の規約: A = 1(LOAD)/ 2(RUN)、X = 引数の先頭、B = 引数の長さ
;   スタックの一番上は BIOS_EXEC が積んだ WBOOT のままなので、RTS で DOS に戻る
; S-record と Intel HEX を読み、$0000-$67FF(本体の手前まで)にだけ書く(決定 6)。
; 形式はファイルの最初のレコードの先頭の文字で決める(「S」なら S-record、「:」なら Intel HEX)。
; 拡張子は見ない。
; API は BIOS_GET_API で見つけ、slot 3〜6(READ_STREAM_OPEN/GETC/CLOSE、GET_ERROR)だけを使う。
; resident の内部も窓の番地も使わないので、プロファイルによらず 1 本で動く。

BIOS_GET_API    EQU     $E0EC
BIOS_EXEC       EQU     $E0EF
PDATA1          EQU     $E07E

XLDR_BASE       EQU     $6800
XLDR_TOP        EQU     $6C00   ; 本体と変数はこの手前に収める(CCP にかぶらない)
X_API_MAJOR     EQU     2
CHR_LF          EQU     $0A
CHR_CR          EQU     $0D
CHR_SPACE       EQU     $20
X_MODE_SREC     EQU     1
X_MODE_IHEX     EQU     2
X_CMD_RUN       EQU     2

 IF (XLDR_BASE&$00FF)<>0
        ERROR   "XLDR_BASE must be on a 256-byte boundary (the range check looks at the high byte)"
 ENDIF

        ORG     XLDR_BASE
XLDR_START:
        JMP     XLDR_MAIN
        FCC     "XLDR"          ; 入口が読み込んだあとに確かめる署名

; slot を呼ぶための jmp(番地は XLDR_MAIN が表から入れる)
X_OPEN:
        JMP     0
X_GETC:
        JMP     0
X_CLOSE:
        JMP     0
X_GETERR:
        JMP     0

; 失敗は「?」を出して RTS(WBOOT を通って DOS のプロンプトへ)
X_FAIL_CLOSE:
        JSR     X_CLOSE
X_FAIL:
        LDX     #X_TXT_ERR
        JMP     PDATA1          ; RTS で WBOOT へ

XLDR_MAIN:
        STAA    X_CMD
        STX     X_ARGP
        STAB    X_ARGL
        JSR     BIOS_GET_API
        BCS     X_FAIL
        LDAA    8,X
        CMPA    #X_API_MAJOR
        BNE     X_FAIL
        LDX     12,X            ; ジャンプテーブル
        STX     X_TBL
        LDX     6,X             ; slot 3 READ_STREAM_OPEN
        STX     X_OPEN+1
        LDX     X_TBL
        LDX     8,X             ; slot 4 READ_STREAM_GETC
        STX     X_GETC+1
        LDX     X_TBL
        LDX     10,X            ; slot 5 READ_STREAM_CLOSE
        STX     X_CLOSE+1
        LDX     X_TBL
        LDX     12,X            ; slot 6 GET_ERROR
        STX     X_GETERR+1
; RUN addr: 引数がちょうど 16 進 4 桁なら、その番地を起動する
        LDAA    X_CMD
        CMPA    #X_CMD_RUN
        BNE     X_LOAD_FILE
        LDX     X_ARGP
        LDAB    X_ARGL
        JSR     X_PARSE_HEX16
        BCS     X_LOAD_FILE
        LDX     X_HEXV
        BRA     X_EXEC
X_LOAD_FILE:
        CLR     X_LMODE
        CLR     X_ENTRY_SET
        LDX     X_ARGP
        LDAB    X_ARGL
        JSR     X_OPEN
        BCS     X_FAIL
X_LOAD_LOOP:
        JSR     X_READ_LOADER_RECORD
        BCS     X_FAIL_CLOSE
        CMPA    #1
        BNE     X_LOAD_LOOP
        JSR     X_CLOSE
        LDAA    X_CMD
        CMPA    #X_CMD_RUN
        BEQ     X_RUN_FILE
        LDX     #X_TXT_OK
        JMP     PDATA1          ; RTS で WBOOT へ
; RUN file: S-record の S9/S8 の番地を起動する(Intel HEX は起動の番地を持たないので「?」)
X_RUN_FILE:
        LDAA    X_LMODE
        CMPA    #X_MODE_SREC
        BNE     X_RUN_BAD
        TST     X_ENTRY_SET
        BEQ     X_RUN_BAD
        LDX     X_ENTRY
; RUN で起動するプログラムは A=0・X=0・B=0(仕様 3-2)。戻らない。
X_EXEC:
        STX     X_EXBLK
        LDX     #0
        STX     X_EXBLK+2
        CLRB
        LDX     #X_EXBLK
        JMP     BIOS_EXEC
X_RUN_BAD:
        JMP     X_FAIL

; X_NIB を X_ADDR に書いて X_ADDR を進める。$6800 以上(本体・CCP・核・窓・ROM)なら書かずに C=1
X_STORE:
        LDAA    X_ADDR
        CMPA    #XLDR_BASE/$100
        BHS     X_STORE_BAD
        LDAA    X_NIB
        LDX     X_ADDR
        STAA    0,X
        INX
        STX     X_ADDR
        CLC
        RTS
X_STORE_BAD:
        SEC
        RTS

X_PARSE_HEX16:
        STX     X_APTR
        STAB    X_ALEN
        CLR     X_HEXV
        CLR     X_HEXV+1
        CLR     X_DIGITS
X_PARSE_HEX16_SKIP:
        TST     X_ALEN
        BNE     X_PARSE_HEX16_SKIP_HAS
        JMP     X_PARSE_HEX16_FAIL
X_PARSE_HEX16_SKIP_HAS:
        LDX     X_APTR
        LDAA    0,X
        CMPA    #CHR_SPACE
        BNE     X_PARSE_HEX16_LOOP
        INX
        STX     X_APTR
        DEC     X_ALEN
        BRA     X_PARSE_HEX16_SKIP
X_PARSE_HEX16_LOOP:
        TST     X_ALEN
        BEQ     X_PARSE_HEX16_DONE
        LDX     X_APTR
        LDAA    0,X
        CMPA    #CHR_SPACE
        BEQ     X_PARSE_HEX16_TRAILING
        JSR     X_HEX_TO_NIBBLE
        BCS     X_PARSE_HEX16_FAIL
        LDAB    X_DIGITS
        CMPB    #4
        BHS     X_PARSE_HEX16_FAIL
        TSTB
        BEQ     X_PARSE_HEX16_HI_H
        CMPB    #1
        BEQ     X_PARSE_HEX16_HI_L
        CMPB    #2
        BEQ     X_PARSE_HEX16_LO_H
        ORAA    X_HEXV+1
        STAA    X_HEXV+1
        BRA     X_PARSE_HEX16_ADVANCE
X_PARSE_HEX16_HI_H:
        LSLA
        LSLA
        LSLA
        LSLA
        STAA    X_HEXV
        BRA     X_PARSE_HEX16_ADVANCE
X_PARSE_HEX16_HI_L:
        ORAA    X_HEXV
        STAA    X_HEXV
        BRA     X_PARSE_HEX16_ADVANCE
X_PARSE_HEX16_LO_H:
        LSLA
        LSLA
        LSLA
        LSLA
        STAA    X_HEXV+1
X_PARSE_HEX16_ADVANCE:
        LDX     X_APTR
        INX
        STX     X_APTR
        DEC     X_ALEN
        INC     X_DIGITS
        BRA     X_PARSE_HEX16_LOOP
X_PARSE_HEX16_TRAILING:
        LDX     X_APTR
        INX
        STX     X_APTR
        DEC     X_ALEN
X_PARSE_HEX16_TRAILING_LOOP:
        TST     X_ALEN
        BEQ     X_PARSE_HEX16_DONE
        LDX     X_APTR
        LDAA    0,X
        CMPA    #CHR_SPACE
        BNE     X_PARSE_HEX16_FAIL
        INX
        STX     X_APTR
        DEC     X_ALEN
        BRA     X_PARSE_HEX16_TRAILING_LOOP
X_PARSE_HEX16_DONE:
        LDAA    X_DIGITS
        CMPA    #4
        BNE     X_PARSE_HEX16_FAIL
        CLC
        RTS
X_PARSE_HEX16_FAIL:
        SEC
        RTS

X_READ_LOADER_RECORD:
        JSR     X_READ_RECORD_HEAD
        BCS     X_READ_LOADER_RECORD_FAIL
        LDAA    X_LMODE
        BNE     X_READ_LOADER_RECORD_MODE_SET
        LDAA    X_NIB
        CMPA    #'S'
        BEQ     X_READ_LOADER_RECORD_SET_SREC
        CMPA    #':'
        BEQ     X_READ_LOADER_RECORD_SET_IHEX
        SEC
        RTS
X_READ_LOADER_RECORD_SET_SREC:
        LDAA    #X_MODE_SREC
        STAA    X_LMODE
        BRA     X_READ_LOADER_RECORD_MODE_SET
X_READ_LOADER_RECORD_SET_IHEX:
        LDAA    #X_MODE_IHEX
        STAA    X_LMODE
X_READ_LOADER_RECORD_MODE_SET:
        LDAA    X_LMODE
        CMPA    #X_MODE_SREC
        BEQ     X_READ_SREC_RECORD
        CMPA    #X_MODE_IHEX
        BNE     X_READ_LOADER_RECORD_FAIL
        JMP     X_READ_IHEX_RECORD
X_READ_LOADER_RECORD_FAIL:
        SEC
        RTS

X_READ_RECORD_HEAD:
        JSR     X_GETC
        BCS     X_READ_RECORD_HEAD_FAIL
        CMPA    #CHR_LF
        BEQ     X_READ_RECORD_HEAD
        CMPA    #CHR_CR
        BEQ     X_READ_RECORD_HEAD
        CMPA    #CHR_SPACE
        BLO     X_READ_RECORD_HEAD
        STAA    X_NIB
        CLC
        RTS
X_READ_RECORD_HEAD_FAIL:
        SEC
        RTS

X_READ_RECORD_TRAILER:
        JSR     X_GETC
        BCS     X_READ_RECORD_TRAILER_EOF_OR_FAIL
        CMPA    #CHR_LF
        BEQ     X_READ_RECORD_TRAILER_OK
        CMPA    #CHR_CR
        BEQ     X_READ_RECORD_TRAILER_OK
X_READ_RECORD_TRAILER_FAIL:
        SEC
        RTS
X_READ_RECORD_TRAILER_EOF_OR_FAIL:
        JSR     X_GETERR
        TSTA
        BNE     X_READ_RECORD_TRAILER_FAIL
X_READ_RECORD_TRAILER_OK:
        CLC
        RTS

X_READ_HEXBYTE_INPUT:
        PSHB
        JSR     X_GETC
        BCS     X_READ_HEXBYTE_INPUT_FAIL
        JSR     X_HEX_TO_NIBBLE
        BCS     X_READ_HEXBYTE_INPUT_FAIL
        LSLA
        LSLA
        LSLA
        LSLA
        STAA    X_NIB
        JSR     X_GETC
        BCS     X_READ_HEXBYTE_INPUT_FAIL
        JSR     X_HEX_TO_NIBBLE
        BCS     X_READ_HEXBYTE_INPUT_FAIL
        ADDA    X_NIB
        PULB
        CLC
        RTS
X_READ_HEXBYTE_INPUT_FAIL:
        PULB
        SEC
        RTS

X_READ_SREC_RECORD:
        LDAA    X_NIB
        CMPA    #'S'
        BEQ     X_READ_SREC_HEAD_OK
        JMP     X_READ_SREC_FAIL
X_READ_SREC_HEAD_OK:
        JSR     X_GETC
        BCS     X_READ_SREC_FAIL_NEAR0
        STAA    X_TYPE
        CMPA    #'0'
        BEQ     X_READ_SREC_TYPE_OK
        CMPA    #'1'
        BEQ     X_READ_SREC_TYPE_OK
        CMPA    #'2'
        BEQ     X_READ_SREC_TYPE_OK
        CMPA    #'5'
        BEQ     X_READ_SREC_TYPE_OK
        CMPA    #'8'
        BEQ     X_READ_SREC_TYPE_OK
        CMPA    #'9'
        BEQ     X_READ_SREC_TYPE_OK
        JMP     X_READ_SREC_FAIL
X_READ_SREC_FAIL_NEAR0:
        JMP     X_READ_SREC_FAIL
X_READ_SREC_TYPE_OK:
        JSR     X_READ_HEXBYTE_INPUT
        BCS     X_READ_SREC_FAIL_NEAR1
        STAA    X_COUNT
        STAA    X_SUM
        LDAA    X_TYPE
        CMPA    #'2'
        BEQ     X_READ_SREC_ADDR24
        CMPA    #'8'
        BEQ     X_READ_SREC_ADDR24
        LDAA    X_COUNT
        CMPA    #3
        BLO     X_READ_SREC_FAIL_NEAR1
        JSR     X_READ_HEXBYTE_INPUT
        BCS     X_READ_SREC_FAIL_NEAR1
        STAA    X_ADDR
        JSR     X_ADD_TO_X_SUM
        JSR     X_READ_HEXBYTE_INPUT
        BCS     X_READ_SREC_FAIL_NEAR1
        STAA    X_ADDR+1
        JSR     X_ADD_TO_X_SUM
        LDAB    X_COUNT
        SUBB    #3
        BRA     X_READ_SREC_DATA_LOOP
X_READ_SREC_FAIL_NEAR1:
        JMP     X_READ_SREC_FAIL
X_READ_SREC_ADDR24:
        LDAA    X_COUNT
        CMPA    #4
        BLO     X_READ_SREC_FAIL_NEAR2
        JSR     X_READ_HEXBYTE_INPUT
        BCS     X_READ_SREC_FAIL_NEAR2
        STAA    X_NIB
        JSR     X_ADD_TO_X_SUM
        LDAA    X_NIB
        BNE     X_READ_SREC_FAIL_NEAR2
        JSR     X_READ_HEXBYTE_INPUT
        BCS     X_READ_SREC_FAIL_NEAR2
        STAA    X_ADDR
        JSR     X_ADD_TO_X_SUM
        JSR     X_READ_HEXBYTE_INPUT
        BCS     X_READ_SREC_FAIL_NEAR2
        STAA    X_ADDR+1
        JSR     X_ADD_TO_X_SUM
        LDAB    X_COUNT
        SUBB    #4
        BRA     X_READ_SREC_DATA_LOOP
X_READ_SREC_FAIL_NEAR2:
        JMP     X_READ_SREC_FAIL
X_READ_SREC_DATA_LOOP:
        TSTB
        BEQ     X_READ_SREC_CHECKSUM
        JSR     X_READ_HEXBYTE_INPUT
        BCS     X_READ_SREC_FAIL
        STAA    X_NIB
        JSR     X_ADD_TO_X_SUM
        LDAA    X_TYPE
        CMPA    #'1'
        BEQ     X_READ_SREC_STORE
        CMPA    #'2'
        BNE     X_READ_SREC_SKIP_STORE
X_READ_SREC_STORE:
        JSR     X_STORE
        BCS     X_READ_SREC_FAIL
X_READ_SREC_SKIP_STORE:
        DECB
        BRA     X_READ_SREC_DATA_LOOP
X_READ_SREC_CHECKSUM:
        JSR     X_READ_HEXBYTE_INPUT
        BCS     X_READ_SREC_FAIL
        JSR     X_ADD_TO_X_SUM
        CMPA    #$FF
        BNE     X_READ_SREC_FAIL
        JSR     X_READ_RECORD_TRAILER
        BCS     X_READ_SREC_FAIL
        LDAA    X_TYPE
        CMPA    #'8'
        BEQ     X_READ_SREC_EOF
        CMPA    #'9'
        BEQ     X_READ_SREC_EOF
        LDAA    #0
        CLC
        RTS
X_READ_SREC_EOF:
        LDAA    X_ADDR
        STAA    X_ENTRY
        LDAA    X_ADDR+1
        STAA    X_ENTRY+1
        LDAA    #1
        STAA    X_ENTRY_SET
        LDAA    #1
        CLC
        RTS
X_READ_SREC_FAIL:
        SEC
        RTS

X_READ_IHEX_RECORD:
        LDAA    X_NIB
        CMPA    #':'
        BEQ     X_READ_IHEX_HEAD_OK
        JMP     X_READ_IHEX_FAIL
X_READ_IHEX_HEAD_OK:
        JSR     X_READ_HEXBYTE_INPUT
        BCS     X_READ_IHEX_FAIL_NEAR1
        STAA    X_COUNT
        STAA    X_SUM
        JSR     X_READ_HEXBYTE_INPUT
        BCS     X_READ_IHEX_FAIL_NEAR1
        STAA    X_ADDR
        JSR     X_ADD_TO_X_SUM
        JSR     X_READ_HEXBYTE_INPUT
        BCS     X_READ_IHEX_FAIL_NEAR1
        STAA    X_ADDR+1
        JSR     X_ADD_TO_X_SUM
        JSR     X_READ_HEXBYTE_INPUT
        BCS     X_READ_IHEX_FAIL_NEAR1
        STAA    X_TYPE
        JSR     X_ADD_TO_X_SUM
        LDAA    X_TYPE
        CMPA    #$00
        BEQ     X_READ_IHEX_DATA
        CMPA    #$01
        BNE     X_READ_IHEX_FAIL
        LDAA    X_COUNT
        BNE     X_READ_IHEX_FAIL
        BRA     X_READ_IHEX_DATA
X_READ_IHEX_FAIL_NEAR1:
        JMP     X_READ_IHEX_FAIL
X_READ_IHEX_DATA:
        LDAB    X_COUNT
X_READ_IHEX_DATA_LOOP:
        TSTB
        BEQ     X_READ_IHEX_CHECKSUM
        JSR     X_READ_HEXBYTE_INPUT
        BCS     X_READ_IHEX_FAIL
        STAA    X_NIB
        JSR     X_ADD_TO_X_SUM
        LDAA    X_TYPE
        CMPA    #$00
        BNE     X_READ_IHEX_SKIP_STORE
        JSR     X_STORE
        BCS     X_READ_IHEX_FAIL
X_READ_IHEX_SKIP_STORE:
        DECB
        BRA     X_READ_IHEX_DATA_LOOP
X_READ_IHEX_CHECKSUM:
        JSR     X_READ_HEXBYTE_INPUT
        BCS     X_READ_IHEX_FAIL
        JSR     X_ADD_TO_X_SUM
        CMPA    #$00
        BNE     X_READ_IHEX_FAIL
        JSR     X_READ_RECORD_TRAILER
        BCS     X_READ_IHEX_FAIL
        LDAA    X_TYPE
        CMPA    #$01
        BEQ     X_READ_IHEX_EOF
        LDAA    #0
        CLC
        RTS
X_READ_IHEX_EOF:
        LDAA    #1
        CLC
        RTS
X_READ_IHEX_FAIL:
        SEC
        RTS

X_HEX_TO_NIBBLE:
        CMPA    #'0'
        BLO     X_HEX_TO_NIBBLE_FAIL
        CMPA    #'9'
        BHI     X_HEX_ALPHA
        SUBA    #'0'
        CLC
        RTS
X_HEX_ALPHA:
        CMPA    #'A'
        BLO     X_HEX_LOWER
        CMPA    #'F'
        BHI     X_HEX_LOWER
        SUBA    #'A'
        ADDA    #10
        CLC
        RTS
X_HEX_LOWER:
        CMPA    #'a'
        BLO     X_HEX_TO_NIBBLE_FAIL
        CMPA    #'f'
        BHI     X_HEX_TO_NIBBLE_FAIL
        SUBA    #'a'
        ADDA    #10
        CLC
        RTS
X_HEX_TO_NIBBLE_FAIL:
        SEC
        RTS

X_ADD_TO_X_SUM:
        ADDA    X_SUM
        STAA    X_SUM
        RTS


X_TXT_OK:
        FCC     "OK"
        FCB     CHR_CR,CHR_LF,4
X_TXT_ERR:
        FCC     "?"
        FCB     CHR_CR,CHR_LF,4

XLDR_END:
; 変数(初期値なし。ファイルには含めない)
X_CMD           EQU     XLDR_END
X_ARGP          EQU     XLDR_END+1
X_ARGL          EQU     XLDR_END+3
X_TBL           EQU     XLDR_END+4
X_EXBLK         EQU     XLDR_END+6      ; BIOS_EXEC に渡す {entry, argptr}
X_HEXV          EQU     XLDR_END+10
X_APTR          EQU     XLDR_END+12
X_ALEN          EQU     XLDR_END+14
X_DIGITS        EQU     XLDR_END+15
X_LMODE         EQU     XLDR_END+16
X_ENTRY_SET     EQU     XLDR_END+17
X_ENTRY         EQU     XLDR_END+18
X_TYPE          EQU     XLDR_END+20
X_COUNT         EQU     XLDR_END+21
X_SUM           EQU     XLDR_END+22
X_ADDR          EQU     XLDR_END+23
X_NIB           EQU     XLDR_END+25
XLDR_VARS_END   EQU     XLDR_END+26
 IF XLDR_VARS_END > XLDR_TOP
        ERROR   "XLDR.OVL overflows $6800-$6BFF"
 ENDIF
        END
