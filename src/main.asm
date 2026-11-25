        cpu     6800

        include "../include/hardware.inc"
        include "../include/mikbug.inc"

        org     MIKBUG_OUTCH

OUTCH:
        jmp     OUTEEE

INCH:
        jmp     INEEE

        org     MIKBUG_PDATA1

PDATA1:
        ldaa    0,x
        cmpa    #$04
        beq     PDATA1_DONE
        jsr     OUTCH
        inx
        bra     PDATA1
PDATA1_DONE:
        rts

        org     MIKBUG_CONTRL

CONTRL:
        jmp     MONITOR_ENTRY

 if MONITOR_FEATURE_SD
; 案 B の BIOS 入口表(#310 の 1-6)。番地は hardware.inc の BIOS_* と一致させる。
BIOS_JMP macro   addr,target
 if * <> addr
        error   "BIOS entry table is misaligned"
 endif
        jmp     target
        endm

        org     BIOS_WBOOT

        BIOS_JMP BIOS_WBOOT,BIOS_WBOOT_IMPL
        BIOS_JMP BIOS_INFO,BIOS_INFO_IMPL
        BIOS_JMP BIOS_GET_API,BIOS_GET_API_IMPL
        BIOS_JMP BIOS_EXEC,BIOS_EXEC_IMPL
        BIOS_JMP BIOS_READ_LINE,BIOS_READ_LINE_IMPL
        BIOS_JMP BIOS_MONITOR,BIOS_MONITOR_IMPL
        BIOS_JMP BIOS_SD_INIT,SD_INIT
        BIOS_JMP BIOS_SD_READ,SD_READ_SECTOR
        BIOS_JMP BIOS_SD_SELECT,SD_SELECT
        BIOS_JMP BIOS_SD_DESELECT,SD_DESELECT
        BIOS_JMP BIOS_SD_SEND_CMD,SD_SEND_CMD
        BIOS_JMP BIOS_SD_XFER,SD_SPI_XFER
        BIOS_JMP BIOS_SD_WAIT_R1,SD_WAIT_R1
        BIOS_JMP BIOS_SD_WRITE,BIOS_UNIMPL
        BIOS_JMP BIOS_RSV14,BIOS_UNIMPL
        BIOS_JMP BIOS_RSV15,BIOS_UNIMPL
 if * <> BIOS_TABLE_END
        error   "BIOS entry table size mismatch"
 endif

BIOS_INFO_IMPL:
        ldaa    #BIOS_VERSION
        ldab    #BIOS_ENTRY_COUNT
        rts

; X -> {entry(2), argptr(2)}、B = 引数長。ブロックはスタックを切り替える前に読む
; (呼び手のブロックが新しいスタックの位置と重なっても壊さないため)。
; entry に着いた時点で SP = BIOS_PROG_STACK-2、スタックの一番上は BIOS_WBOOT。
BIOS_EXEC_IMPL:
        ldaa    1,x
        psha
        ldaa    0,x
        psha
        ldx     2,x
        pula
        staa    BIOS_PROG_STACK-3
        pula
        staa    BIOS_PROG_STACK-2
        lds     #BIOS_PROG_STACK-4
        ldaa    #BIOS_WBOOT/$0100
        staa    BIOS_PROG_STACK-1
        ldaa    #BIOS_WBOOT&$00FF
        staa    BIOS_PROG_STACK
        clra
        rts

BIOS_READ_LINE_IMPL:
        jsr     READ_LINE
        ldx     #LINE_BUF
        ldab    LINE_LEN
        rts

; $E20D はモニタの門(MON_GATE)へ飛ぶ。
BIOS_MONITOR_IMPL:
        lds     #STACK_TOP
        jmp     MONITOR_REENTRY

BIOS_UNIMPL:
        sec
        rts

; RAM の 16bit 加算和。入力 X = 開始番地、BB_WORK = 終端(最後のバイトの次の番地)。
; 出力 A:B = [X, 終端) の和、X = 終端。1 バイト 20 サイクル。
; 開始 <= 終端であること(逆だとアドレス空間を一周し、$8000 台の I/O も読む)。
; 区画の値を渡すときは、先に BB_CHECK_VALID を通す。
BIOS_RAM_SUM:
        clra
        clrb
        cpx     BB_WORK
        beq     BIOS_RAM_SUM_DONE
BIOS_RAM_SUM_LOOP:
        addb    0,x
        adca    #0
        inx
        cpx     BB_WORK
        bne     BIOS_RAM_SUM_LOOP
BIOS_RAM_SUM_DONE:
        rts
BIOS_GAP_END:
 if BIOS_GAP_END > MIKBUG_INEEE
        error   "BIOS code overflows the MIKBUG gap"
 endif
 endif

        org     MIKBUG_INEEE

INEEE:
        jmp     MIKBUG_INEEE_IMPL

        org     MIKBUG_OUTEEE

OUTEEE:
        jmp     MIKBUG_OUTEEE_IMPL

        org     MONITOR_BASE

MONITOR_ENTRY:
        lds     #STACK_TOP
        jsr     ACIA_INIT
 if MONITOR_FEATURE_KEYBOARD
        ldaa    #MONITOR_FEATURE_KEYBOARD
        beq     MONITOR_ENTRY_NO_KEYBOARD
        jsr     ACIA2_INIT
MONITOR_ENTRY_NO_KEYBOARD:
 endif
MONITOR_REENTRY_AT:
 if MONITOR_FEATURE_SD
 if MONITOR_REENTRY_AT <> MONITOR_REENTRY
        error   "MONITOR_REENTRY_AT must be MONITOR_BASE+$0D"
 endif
        jmp     MON_GATE                ; 番地は変えない(v2 の EXIT が決め打ちで飛ぶ)
 else
        jmp     MAIN_LOOP
 endif

RESET:
        lds     #STACK_TOP
        clr     DUMP_ADDR
        clr     DUMP_ADDR+1
        clr     BP_ACTIVE
        clr     BRK_ACTIVE
        jsr     ACIA_INIT
 if MONITOR_FEATURE_KEYBOARD
        ldaa    #MONITOR_FEATURE_KEYBOARD
        beq     RESET_NO_KEYBOARD
        jsr     ACIA2_INIT
RESET_NO_KEYBOARD:
 endif
 if MONITOR_FEATURE_VDG
        clr     ACIA_TX_WAIT
        jsr     VDG_INIT
 endif
        ldx     #TXT_WELCOME
        jsr     PDATA1
        ldaa    #CHR_CR
        jsr     MON_OUTEEE

MAIN_LOOP:
        jsr     PRINT_PROMPT
        jsr     READ_LINE
        ldab    LINE_LEN
        beq     MAIN_LOOP

        ldaa    LINE_BUF
        cmpa    #'D'
        bne     CHK_CMD_MOD
 if MONITOR_FEATURE_VDG
        jsr     IS_CMD_DS
        bcs     MAIN_DISPATCH_NOT_DS
        jmp     CMD_DUMP_SHORT
MAIN_DISPATCH_NOT_DS:
 endif
 if MONITOR_FEATURE_FAT
        jsr     IS_CMD_DIR
        bcs     MAIN_DISPATCH_DUMP
        jmp     CMD_DIR
MAIN_DISPATCH_DUMP:
 endif
 if MONITOR_FEATURE_SD
 if S1_SUPPORTED
        jsr     IS_CMD_DOS
        bcs     MAIN_DISPATCH_NOT_DOS
        jmp     BIOS_WBOOT_IMPL
MAIN_DISPATCH_NOT_DOS:
 endif
 endif
        jmp     CMD_DUMP
CHK_CMD_MOD:
        cmpa    #'M'
        bne     CHK_CMD_GO
        jsr     IS_CMD_MAP
        bcs     MAIN_DISPATCH_MOD
        jmp     CMD_MAP
MAIN_DISPATCH_MOD:
        jmp     CMD_MOD
CHK_CMD_GO:
        cmpa    #'G'
        bne     CHK_CMD_LOAD
        jmp     CMD_GO
CHK_CMD_LOAD:
        cmpa    #'L'
        bne     CHK_CMD_BREAK
        jmp     CMD_LOAD
CHK_CMD_BREAK:
        cmpa    #'B'
        bne     CHK_CMD_RESUME
 if MONITOR_FEATURE_SD
 if S1_SUPPORTED
        jsr     IS_CMD_BOOT
        bcc     MAIN_DISPATCH_BOOT
        jsr     IS_CMD_BOOT3
        bcs     MAIN_DISPATCH_BREAK
        jmp     CMD_BOOT3
MAIN_DISPATCH_BOOT:
        jmp     CMD_BOOT
MAIN_DISPATCH_BREAK:
 endif
 endif
        jmp     CMD_BREAK_SET
CHK_CMD_RESUME:
        cmpa    #'R'
        bne     CHK_CMD_CLEAR
        jsr     IS_CMD_RAMTEST
        bcs     MAIN_DISPATCH_RESUME
        jmp     CMD_RAMTEST
MAIN_DISPATCH_RESUME:
        jmp     CMD_RESUME
CHK_CMD_CLEAR:
        cmpa    #'C'
        bne     CHK_CMD_UNASM
        jmp     CMD_BREAK_CLEAR
CHK_CMD_UNASM:
        cmpa    #'U'
        bne     CHK_CMD_HELP
 if MONITOR_FEATURE_VDG
        jsr     IS_CMD_UW
        bcs     MAIN_DISPATCH_UNASM
        jmp     CMD_UART_WAIT
MAIN_DISPATCH_UNASM:
 endif
        jmp     CMD_UNASM
CHK_CMD_HELP:
        cmpa    #'H'
        bne     CHK_CMD_FILL
        jmp     CMD_HELP
CHK_CMD_FILL:
        cmpa    #'F'
        bne     CHK_CMD_AFTER_FILL
        jmp     CMD_FILL
CHK_CMD_AFTER_FILL:
        jmp     MAIN_LOOP_ERROR

MAIN_LOOP_ERROR:
        jsr     SHOW_ERROR
        jmp     MAIN_LOOP

 if MONITOR_FEATURE_FAT
IS_CMD_DIR:
        ldab    LINE_LEN
        cmpb    #3
        bne     IS_CMD_DIR_FAIL
        ldaa    LINE_BUF+1
        cmpa    #'I'
        bne     IS_CMD_DIR_FAIL
        ldaa    LINE_BUF+2
        cmpa    #'R'
        bne     IS_CMD_DIR_FAIL
        clc
        rts
IS_CMD_DIR_FAIL:
        sec
        rts
 endif

 if MONITOR_FEATURE_VDG
IS_CMD_DS:
        ldab    LINE_LEN
        cmpb    #2
        blo     IS_CMD_DS_FAIL
        ldaa    LINE_BUF+1
        cmpa    #'S'
        bne     IS_CMD_DS_FAIL
        clc
        rts
IS_CMD_DS_FAIL:
        sec
        rts

IS_CMD_UW:
        ldab    LINE_LEN
        cmpb    #2
        blo     IS_CMD_UW_FAIL
        ldaa    LINE_BUF+1
        cmpa    #'W'
        bne     IS_CMD_UW_FAIL
        clc
        rts
IS_CMD_UW_FAIL:
        sec
        rts
 endif

IS_CMD_MAP:
        ldab    LINE_LEN
        cmpb    #3
        bne     IS_CMD_MAP_FAIL
        ldaa    LINE_BUF+1
        cmpa    #'A'
        bne     IS_CMD_MAP_FAIL
        ldaa    LINE_BUF+2
        cmpa    #'P'
        bne     IS_CMD_MAP_FAIL
        clc
        rts
IS_CMD_MAP_FAIL:
        sec
        rts

IS_CMD_RAMTEST:
        ldab    LINE_LEN
        cmpb    #17
        bne     IS_CMD_RAMTEST_FAIL
        ldx     #LINE_BUF
        ldaa    0,x
        cmpa    #'R'
        bne     IS_CMD_RAMTEST_FAIL
        ldaa    1,x
        cmpa    #'A'
        bne     IS_CMD_RAMTEST_FAIL
        ldaa    2,x
        cmpa    #'M'
        bne     IS_CMD_RAMTEST_FAIL
        ldaa    3,x
        cmpa    #'T'
        bne     IS_CMD_RAMTEST_FAIL
        ldaa    4,x
        cmpa    #'E'
        bne     IS_CMD_RAMTEST_FAIL
        ldaa    5,x
        cmpa    #'S'
        bne     IS_CMD_RAMTEST_FAIL
        ldaa    6,x
        cmpa    #'T'
        bne     IS_CMD_RAMTEST_FAIL
        ldaa    7,x
        cmpa    #CHR_SPACE
        bne     IS_CMD_RAMTEST_FAIL
        clc
        rts
IS_CMD_RAMTEST_FAIL:
        sec
        rts

 if MONITOR_FEATURE_SD
 if S1_SUPPORTED
IS_CMD_BOOT:
        ldab    LINE_LEN
        cmpb    #4
        bne     IS_CMD_BOOT_FAIL
        ldaa    LINE_BUF+1
        cmpa    #'O'
        bne     IS_CMD_BOOT_FAIL
        ldaa    LINE_BUF+2
        cmpa    #'O'
        bne     IS_CMD_BOOT_FAIL
        ldaa    LINE_BUF+3
        cmpa    #'T'
        bne     IS_CMD_BOOT_FAIL
        clc
        rts
IS_CMD_BOOT_FAIL:
        sec
        rts

IS_CMD_BOOT3:
        ldab    LINE_LEN
        cmpb    #5
        bne     IS_CMD_BOOT3_FAIL
        ldaa    LINE_BUF+1
        cmpa    #'O'
        bne     IS_CMD_BOOT3_FAIL
        ldaa    LINE_BUF+2
        cmpa    #'O'
        bne     IS_CMD_BOOT3_FAIL
        ldaa    LINE_BUF+3
        cmpa    #'T'
        bne     IS_CMD_BOOT3_FAIL
        ldaa    LINE_BUF+4
        cmpa    #'3'
        bne     IS_CMD_BOOT3_FAIL
        clc
        rts
IS_CMD_BOOT3_FAIL:
        sec
        rts

IS_CMD_DOS:
        ldab    LINE_LEN
        cmpb    #3
        bne     IS_CMD_DOS_FAIL
        ldaa    LINE_BUF+1
        cmpa    #'O'
        bne     IS_CMD_DOS_FAIL
        ldaa    LINE_BUF+2
        cmpa    #'S'
        bne     IS_CMD_DOS_FAIL
        clc
        rts
IS_CMD_DOS_FAIL:
        sec
        rts
 endif
 endif

CMD_DUMP:
        ldab    LINE_LEN
        cmpb    #1
        beq     CMD_DUMP_NOARG
        jsr     PARSE_DUMP_ARGS
        bcc     CMD_DUMP_SHOW
        jmp     MAIN_LOOP_ERROR
CMD_DUMP_NOARG:
        ldx     DUMP_ADDR
        stx     DUMP_END
        jsr     SET_DUMP_END_64
CMD_DUMP_SHOW:
        ldab    #16
        stab    ARG2_LEN
        jsr     DUMP_RANGE
        jmp     MAIN_LOOP

 if MONITOR_FEATURE_VDG
CMD_DUMP_SHORT:
        ldab    LINE_LEN
        cmpb    #2
        beq     CMD_DUMP_SHORT_NOARG
        jsr     PARSE_DUMP_SHORT_ARGS
        bcc     CMD_DUMP_SHORT_SHOW
        jmp     MAIN_LOOP_ERROR
CMD_DUMP_SHORT_NOARG:
        ldx     DUMP_ADDR
        stx     DUMP_END
        jsr     SET_DUMP_END_64
CMD_DUMP_SHORT_SHOW:
        ldab    #8
        stab    ARG2_LEN
        jsr     DUMP_RANGE
        jmp     MAIN_LOOP
 endif

DUMP_RANGE:
        ldx     DUMP_ADDR
        jsr     CMP_X_DUMP_END
        bls     DUMP_RANGE_LINE
        rts
DUMP_RANGE_LINE:
        ldx     DUMP_ADDR
        stx     LINE_PTR
        clr     DUMP_COUNT
DUMP_COUNT_LOOP:
        ldx     DUMP_ADDR
        jsr     CMP_X_DUMP_END
        bhi     DUMP_COUNT_DONE
        ldab    DUMP_COUNT
        cmpb    ARG2_LEN
        bhs     DUMP_COUNT_DONE
        inc     DUMP_COUNT
        ldx     DUMP_ADDR
        inx
        stx     DUMP_ADDR
        ldaa    DUMP_ADDR
        oraa    DUMP_ADDR+1
        beq     DUMP_COUNT_DONE
        bra     DUMP_COUNT_LOOP
DUMP_COUNT_DONE:
        ldx     LINE_PTR
        jsr     PRINT_HEX16
        jsr     PRINT_SPACE

        ldab    DUMP_COUNT
CMD_DUMP_HEX_LOOP:
        tstb
        beq     CMD_DUMP_HEX_DONE
        ldaa    0,x
        jsr     PRINT_HEX8
        jsr     PRINT_SPACE
        inx
        decb
        bra     CMD_DUMP_HEX_LOOP
CMD_DUMP_HEX_DONE:

        ldab    ARG2_LEN
        cmpb    #16
        bne     CMD_DUMP_ASCII_DONE
        jsr     PRINT_SPACE

        ldx     LINE_PTR
        ldab    DUMP_COUNT
CMD_DUMP_ASCII_LOOP:
        tstb
        beq     CMD_DUMP_ASCII_DONE
        ldaa    0,x
        cmpa    #$20
        blo     CMD_DUMP_ASCII_DOT
        cmpa    #$7E
        bhi     CMD_DUMP_ASCII_DOT
        bra     CMD_DUMP_ASCII_PUTC
CMD_DUMP_ASCII_DOT:
        ldaa    #'.'
CMD_DUMP_ASCII_PUTC:
        jsr     MON_OUTEEE
        inx
        decb
        bra     CMD_DUMP_ASCII_LOOP
CMD_DUMP_ASCII_DONE:

        jsr     PRINT_CRLF
        ldaa    DUMP_ADDR
        oraa    DUMP_ADDR+1
        beq     DUMP_RANGE_DONE
        ldx     DUMP_ADDR
        jsr     CMP_X_DUMP_END
        bhi     DUMP_RANGE_DONE
        jmp     DUMP_RANGE_LINE
DUMP_RANGE_DONE:
        rts

PARSE_DUMP_ARGS:
        ldx     #LINE_BUF+1
        stx     ARG_PTR
        ldab    LINE_LEN
        decb
        stab    ARG_LEN
PARSE_DUMP_ARGS_READY:
        clr     ARG2_LEN
PARSE_DUMP_SCAN:
        tstb
        beq     PARSE_DUMP_NO_RANGE
        ldaa    0,x
        cmpa    #'-'
        beq     PARSE_DUMP_RANGE
        inx
        inc     ARG2_LEN
        decb
        bra     PARSE_DUMP_SCAN

PARSE_DUMP_NO_RANGE:
        ldx     ARG_PTR
        ldab    ARG_LEN
        jsr     PARSE_HEX
        bcs     PARSE_DUMP_FAIL
        ldx     HEX_VALUE_HI
        stx     DUMP_ADDR
        stx     DUMP_END
        jsr     SET_DUMP_END_64
        clc
        rts

SET_DUMP_END_64:
        ldab    #63
SET_DUMP_END_64_LOOP:
        ldx     DUMP_END
        inx
        beq     SET_DUMP_END_64_WRAP
        stx     DUMP_END
        decb
        bne     SET_DUMP_END_64_LOOP
        rts
SET_DUMP_END_64_WRAP:
        ldx     #$FFFF
        stx     DUMP_END
        rts

PARSE_DUMP_RANGE:
        tst     ARG2_LEN
        beq     PARSE_DUMP_FAIL
        dex
        inx
        inx
        stx     ARG2_PTR
        decb
        beq     PARSE_DUMP_FAIL
        stab    ARG_LEN

        ldx     ARG_PTR
        ldab    ARG2_LEN
        jsr     PARSE_HEX
        bcs     PARSE_DUMP_FAIL
        ldx     HEX_VALUE_HI
        stx     DUMP_ADDR

        ldx     ARG2_PTR
        ldab    ARG_LEN
        jsr     PARSE_HEX
        bcs     PARSE_DUMP_FAIL
        ldx     HEX_VALUE_HI
        stx     DUMP_END

        ldx     DUMP_ADDR
        jsr     CMP_X_DUMP_END
        bhi     PARSE_DUMP_FAIL
        clc
        rts

PARSE_DUMP_FAIL:
        sec
        rts

 if MONITOR_FEATURE_VDG
PARSE_DUMP_SHORT_ARGS:
        ldx     #LINE_BUF+2
        stx     ARG_PTR
        ldab    LINE_LEN
        decb
        decb
        stab    ARG_LEN
        jmp     PARSE_DUMP_ARGS_READY
 endif

PARSE_FILL_ARGS:
        stx     ARG_PTR
        clr     ARG_LEN
PARSE_FILL_START_SCAN:
        tstb
        bne     PARSE_FILL_START_HAS_CHAR
        jmp     PARSE_FILL_FAIL
PARSE_FILL_START_HAS_CHAR:
        ldaa    0,x
        cmpa    #'-'
        beq     PARSE_FILL_START_DONE
        cmpa    #CHR_SPACE
        bne     PARSE_FILL_START_CHAR_OK
        jmp     PARSE_FILL_FAIL
PARSE_FILL_START_CHAR_OK:
        inc     ARG_LEN
        inx
        decb
        bra     PARSE_FILL_START_SCAN
PARSE_FILL_START_DONE:
        tst     ARG_LEN
        bne     PARSE_FILL_START_LEN_OK
        jmp     PARSE_FILL_FAIL
PARSE_FILL_START_LEN_OK:
        inx
        decb
        bne     PARSE_FILL_HAS_END
        jmp     PARSE_FILL_FAIL
PARSE_FILL_HAS_END:
        stx     ARG2_PTR
        clr     ARG2_LEN
PARSE_FILL_END_SCAN:
        tstb
        bne     PARSE_FILL_END_HAS_CHAR
        jmp     PARSE_FILL_FAIL
PARSE_FILL_END_HAS_CHAR:
        ldaa    0,x
        cmpa    #CHR_SPACE
        beq     PARSE_FILL_END_DONE
        inc     ARG2_LEN
        inx
        decb
        bra     PARSE_FILL_END_SCAN
PARSE_FILL_END_DONE:
        tst     ARG2_LEN
        bne     PARSE_FILL_END_LEN_OK
        jmp     PARSE_FILL_FAIL
PARSE_FILL_END_LEN_OK:
PARSE_FILL_VALUE_SKIP:
        tstb
        bne     PARSE_FILL_VALUE_HAS_CHAR
        jmp     PARSE_FILL_FAIL
PARSE_FILL_VALUE_HAS_CHAR:
        ldaa    0,x
        cmpa    #CHR_SPACE
        bne     PARSE_FILL_VALUE_FOUND
        inx
        decb
        bra     PARSE_FILL_VALUE_SKIP
PARSE_FILL_VALUE_FOUND:
        stx     LOADER_PARSE_PTR
        stab    LOADER_COUNT
        cmpb    #3
        bhs     PARSE_FILL_FAIL

        ldx     ARG_PTR
        ldab    ARG_LEN
        jsr     PARSE_HEX
        bcs     PARSE_FILL_FAIL
        ldx     HEX_VALUE_HI
        stx     MOD_ADDR

        ldx     ARG2_PTR
        ldab    ARG2_LEN
        jsr     PARSE_HEX
        bcs     PARSE_FILL_FAIL
        ldx     HEX_VALUE_HI
        stx     DUMP_END

        ldx     MOD_ADDR
        jsr     CMP_X_DUMP_END
        bhi     PARSE_FILL_FAIL

        ldx     LOADER_PARSE_PTR
        ldab    LOADER_COUNT
        jsr     PARSE_HEX
        bcs     PARSE_FILL_FAIL
        ldaa    HEX_VALUE_HI
        bne     PARSE_FILL_FAIL
        ldaa    HEX_VALUE_LO
        staa    FILL_VALUE
        clc
        rts
PARSE_FILL_FAIL:
        sec
        rts

 if MONITOR_FEATURE_FAT
PARSE_FILENAME_83:
        stx     ARG_PTR
        stab    ARG_LEN
        jsr     CLEAR_FIND_NAME
PARSE_FILENAME_SKIP_HEAD:
        tst     ARG_LEN
        bne     PARSE_FILENAME_SKIP_HAS
        jmp     PARSE_FILENAME_FAIL
PARSE_FILENAME_SKIP_HAS:
        ldx     ARG_PTR
        ldaa    0,x
        cmpa    #CHR_SPACE
        bne     PARSE_FILENAME_NAME_START
        inx
        stx     ARG_PTR
        dec     ARG_LEN
        bra     PARSE_FILENAME_SKIP_HEAD

PARSE_FILENAME_NAME_START:
        ldx     #FAT_FIND_NAME0
        stx     FAT_ENTRY_PTR
        clr     ARG2_LEN
PARSE_FILENAME_NAME_LOOP:
        tst     ARG_LEN
        beq     PARSE_FILENAME_NAME_DONE
        ldx     ARG_PTR
        ldaa    0,x
        cmpa    #CHR_SPACE
        bne     PARSE_FILENAME_NAME_NOT_SPACE
        jmp     PARSE_FILENAME_TRAILING
PARSE_FILENAME_NAME_NOT_SPACE:
        cmpa    #'.'
        bne     PARSE_FILENAME_NAME_NOT_DOT
        jmp     PARSE_FILENAME_EXT_START
PARSE_FILENAME_NAME_NOT_DOT:
        ldab    ARG2_LEN
        cmpb    #8
        blo     PARSE_FILENAME_NAME_ROOM
        jmp     PARSE_FILENAME_FAIL
PARSE_FILENAME_NAME_ROOM:
        jsr     TO_UPPER
        ldx     FAT_ENTRY_PTR
        staa    0,x
        inx
        stx     FAT_ENTRY_PTR
        inc     ARG2_LEN
        ldx     ARG_PTR
        inx
        stx     ARG_PTR
        dec     ARG_LEN
        bra     PARSE_FILENAME_NAME_LOOP

PARSE_FILENAME_NAME_DONE:
        tst     ARG2_LEN
        bne     PARSE_FILENAME_NAME_OK
        jmp     PARSE_FILENAME_FAIL
PARSE_FILENAME_NAME_OK:
        clc
        rts

PARSE_FILENAME_EXT_START:
        tst     ARG2_LEN
        bne     PARSE_FILENAME_EXT_NAME_OK
        jmp     PARSE_FILENAME_FAIL
PARSE_FILENAME_EXT_NAME_OK:
        ldx     ARG_PTR
        inx
        stx     ARG_PTR
        dec     ARG_LEN
        ldx     #FAT_FIND_NAME8
        stx     FAT_ENTRY_PTR
        clr     ARG2_LEN
PARSE_FILENAME_EXT_LOOP:
        tst     ARG_LEN
        bne     PARSE_FILENAME_EXT_HAS_LEN
        jmp     PARSE_FILENAME_OK
PARSE_FILENAME_EXT_HAS_LEN:
        ldx     ARG_PTR
        ldaa    0,x
        cmpa    #CHR_SPACE
        bne     PARSE_FILENAME_EXT_NOT_SPACE
        jmp     PARSE_FILENAME_TRAILING
PARSE_FILENAME_EXT_NOT_SPACE:
        cmpa    #'.'
        bne     PARSE_FILENAME_EXT_CHAR_OK
        jmp     PARSE_FILENAME_FAIL
PARSE_FILENAME_EXT_CHAR_OK:
        ldab    ARG2_LEN
        cmpb    #3
        blo     PARSE_FILENAME_EXT_ROOM
        jmp     PARSE_FILENAME_FAIL
PARSE_FILENAME_EXT_ROOM:
        jsr     TO_UPPER
        ldx     FAT_ENTRY_PTR
        staa    0,x
        inx
        stx     FAT_ENTRY_PTR
        inc     ARG2_LEN
        ldx     ARG_PTR
        inx
        stx     ARG_PTR
        dec     ARG_LEN
        bra     PARSE_FILENAME_EXT_LOOP

PARSE_FILENAME_TRAILING:
        ldx     ARG_PTR
        inx
        stx     ARG_PTR
        dec     ARG_LEN
PARSE_FILENAME_TRAILING_LOOP:
        tst     ARG_LEN
        beq     PARSE_FILENAME_OK
        ldx     ARG_PTR
        ldaa    0,x
        cmpa    #CHR_SPACE
        beq     PARSE_FILENAME_TRAILING_SPACE_OK
        jmp     PARSE_FILENAME_FAIL
PARSE_FILENAME_TRAILING_SPACE_OK:
        inx
        stx     ARG_PTR
        dec     ARG_LEN
        bra     PARSE_FILENAME_TRAILING_LOOP

PARSE_FILENAME_OK:
        clc
        rts
PARSE_FILENAME_FAIL:
        sec
        rts

CLEAR_FIND_NAME:
        ldx     #FAT_FIND_NAME0
        ldab    #11
CLEAR_FIND_NAME_LOOP:
        ldaa    #CHR_SPACE
        staa    0,x
        inx
        decb
        bne     CLEAR_FIND_NAME_LOOP
        rts

TO_UPPER:
        cmpa    #'a'
        blo     TO_UPPER_DONE
        cmpa    #'z'
        bhi     TO_UPPER_DONE
        suba    #$20
TO_UPPER_DONE:
        rts

CMD_DIR_PRINT_ENTRY:
        ldx     FAT_ENTRY_PTR
        ldab    #8
CMD_DIR_PRINT_BASE_LOOP:
        ldaa    0,x
        cmpa    #CHR_SPACE
        beq     CMD_DIR_PRINT_BASE_SKIP
        jsr     MON_OUTEEE
CMD_DIR_PRINT_BASE_SKIP:
        inx
        decb
        bne     CMD_DIR_PRINT_BASE_LOOP
        jsr     CMD_DIR_EXT_HAS_CHAR
        bcs     CMD_DIR_PRINT_ATTR
        ldaa    #'.'
        jsr     MON_OUTEEE
        ldx     FAT_ENTRY_PTR
        ldab    #8
CMD_DIR_PRINT_EXT_POS:
        inx
        decb
        bne     CMD_DIR_PRINT_EXT_POS
        ldab    #3
CMD_DIR_PRINT_EXT_LOOP:
        ldaa    0,x
        cmpa    #CHR_SPACE
        beq     CMD_DIR_PRINT_EXT_SKIP
        jsr     MON_OUTEEE
CMD_DIR_PRINT_EXT_SKIP:
        inx
        decb
        bne     CMD_DIR_PRINT_EXT_LOOP
CMD_DIR_PRINT_ATTR:
        jsr     PRINT_SPACE
        ldaa    #'A'
        jsr     MON_OUTEEE
        jsr     PRINT_SPACE
        ldx     FAT_ENTRY_PTR
        ldaa    31,x
        jsr     PRINT_HEX8
        ldx     FAT_ENTRY_PTR
        ldaa    30,x
        jsr     PRINT_HEX8
        ldx     FAT_ENTRY_PTR
        ldaa    29,x
        jsr     PRINT_HEX8
        ldx     FAT_ENTRY_PTR
        ldaa    28,x
        jsr     PRINT_HEX8
        jsr     PRINT_CRLF
        rts

CMD_DIR_EXT_HAS_CHAR:
        ldx     FAT_ENTRY_PTR
        ldab    #8
CMD_DIR_EXT_POS:
        inx
        decb
        bne     CMD_DIR_EXT_POS
        ldab    #3
CMD_DIR_EXT_SCAN:
        ldaa    0,x
        cmpa    #CHR_SPACE
        bne     CMD_DIR_EXT_YES
        inx
        decb
        bne     CMD_DIR_EXT_SCAN
        sec
        rts
CMD_DIR_EXT_YES:
        clc
        rts
 endif

CMP_X_DUMP_END:
        stx     HEX_VALUE_HI
        ldaa    HEX_VALUE_HI
        cmpa    DUMP_END
        bne     CMP_X_DUMP_END_DONE
        ldaa    HEX_VALUE_LO
        cmpa    DUMP_END+1
CMP_X_DUMP_END_DONE:
        rts

CMD_MOD:
        ldab    LINE_LEN
        cmpb    #1
        beq     CMD_MOD_START_ERR
        ldx     #LINE_BUF+1
        decb
        jsr     PARSE_HEX
        bcc     CMD_MOD_ADDR_OK
CMD_MOD_START_ERR:
        jmp     MAIN_LOOP_ERROR
CMD_MOD_ADDR_OK:
        ldx     HEX_VALUE_HI
        stx     MOD_ADDR

CMD_MOD_LOOP:
        ldx     MOD_ADDR
        jsr     PRINT_HEX16
        ldaa    #':'
        jsr     MON_OUTEEE
        jsr     PRINT_SPACE

        ldx     MOD_ADDR
        ldaa    0,x
        jsr     PRINT_HEX8
        jsr     PRINT_SPACE
        ldaa    #'-'
        jsr     MON_OUTEEE
        jsr     PRINT_SPACE

        jsr     READ_LINE

        ldab    LINE_LEN
        beq     CMD_MOD_NEXT
        cmpb    #3
        bhs     CMD_MOD_ERROR

        ldaa    LINE_BUF
        cmpa    #'.'
        beq     CMD_MOD_END

        ldx     #LINE_BUF
        jsr     PARSE_HEX
        bcs     CMD_MOD_ERROR
        ldaa    HEX_VALUE_LO
        ldx     MOD_ADDR
        staa    0,x

CMD_MOD_NEXT:
        ldx     MOD_ADDR
        inx
        stx     MOD_ADDR
        bra     CMD_MOD_LOOP

CMD_MOD_END:
        jmp     MAIN_LOOP

CMD_MOD_ERROR:
        jsr     SHOW_ERROR
        bra     CMD_MOD_LOOP

CMD_GO:
        ldab    LINE_LEN
        cmpb    #1
        beq     CMD_GO_ERR
        ldx     #LINE_BUF+1
        decb
        jsr     PARSE_HEX
        bcc     CMD_GO_ADDR_OK
CMD_GO_ERR:
        jmp     MAIN_LOOP_ERROR
CMD_GO_ADDR_OK:
 if MONITOR_FEATURE_SD
; プログラムはモニタと別のスタック(W+$1F7F から)で動かし、RTS でモニタの門へ戻す(決定 4・16)。
        ldaa    #MON_GATE/$0100
        staa    BIOS_PROG_STACK-1
        ldaa    #MON_GATE&$00FF
        staa    BIOS_PROG_STACK
        lds     #BIOS_PROG_STACK-2
 endif
        ldx     HEX_VALUE_HI
        jmp     0,x

CMD_BREAK_SET:
        ldab    LINE_LEN
        cmpb    #1
        beq     CMD_BREAK_QUERY
        ldx     #LINE_BUF+1
        decb
        jsr     PARSE_HEX
        bcs     CMD_BREAK_SET_ERR
        ldx     HEX_VALUE_HI
        stx     BP_ADDR
        ldaa    BP_ADDR
        cmpa    #$20
        bhs     CMD_BREAK_SET_ERR
        tst     BP_ACTIVE
        beq     CMD_BREAK_SET_WRITE
        jsr     RESTORE_BREAKPOINT
CMD_BREAK_SET_WRITE:
        ldx     BP_ADDR
        ldaa    0,x
        staa    BP_ORIG
        ldaa    #$3F
        staa    0,x
        ldaa    #1
        staa    BP_ACTIVE
        jmp     MAIN_LOOP
CMD_BREAK_SET_ERR:
        jmp     MAIN_LOOP_ERROR

CMD_BREAK_QUERY:
        ldx     #TXT_BP
        jsr     PDATA1
        tst     BP_ACTIVE
        bne     CMD_BREAK_QUERY_ACTIVE
        ldx     #TXT_NONE
        jsr     PDATA1
        jsr     PRINT_CRLF
        jmp     MAIN_LOOP
CMD_BREAK_QUERY_ACTIVE:
        ldx     BP_ADDR
        jsr     PRINT_HEX16
        jsr     PRINT_CRLF
        jmp     MAIN_LOOP

CMD_BREAK_CLEAR:
        ldab    LINE_LEN
        cmpb    #1
        beq     CMD_BREAK_CLEAR_ANY
        ldx     #LINE_BUF+1
        decb
        jsr     PARSE_HEX
        bcs     CMD_BREAK_CLEAR_ERR
        tst     BP_ACTIVE
        beq     CMD_BREAK_CLEAR_ERR
        ldaa    HEX_VALUE_HI
        cmpa    BP_ADDR
        bne     CMD_BREAK_CLEAR_ERR
        ldaa    HEX_VALUE_LO
        cmpa    BP_ADDR+1
        bne     CMD_BREAK_CLEAR_ERR
        jsr     RESTORE_BREAKPOINT
        jmp     MAIN_LOOP
CMD_BREAK_CLEAR_ANY:
        tst     BP_ACTIVE
        beq     CMD_BREAK_CLEAR_DONE
        jsr     RESTORE_BREAKPOINT
CMD_BREAK_CLEAR_DONE:
        jmp     MAIN_LOOP
CMD_BREAK_CLEAR_ERR:
        jmp     MAIN_LOOP_ERROR

CMD_RESUME:
        ldab    LINE_LEN
        cmpb    #1
        bne     CMD_RESUME_ERR
        tst     BRK_ACTIVE
        beq     CMD_RESUME_ERR
        clr     BRK_ACTIVE
        ldx     BRK_FRAME
        ldaa    BRK_SAVE_CC
        staa    0,x
        ldaa    BRK_SAVE_B
        staa    1,x
        ldaa    BRK_SAVE_A
        staa    2,x
        ldaa    BRK_SAVE_X
        staa    3,x
        ldaa    BRK_SAVE_X+1
        staa    4,x
        ldaa    BRK_SAVE_PC
        staa    5,x
        ldaa    BRK_SAVE_PC+1
        staa    6,x
        txs
        rti
CMD_RESUME_ERR:
        jmp     MAIN_LOOP_ERROR

RESTORE_BREAKPOINT:
        ldx     BP_ADDR
        ldaa    BP_ORIG
        staa    0,x
        clr     BP_ACTIVE
        rts

 if MONITOR_FEATURE_VDG
CMD_UART_WAIT:
        ldab    LINE_LEN
        cmpb    #2
        beq     CMD_UART_WAIT_SHOW
        cmpb    #5
        beq     CMD_UART_WAIT_ON
        cmpb    #6
        beq     CMD_UART_WAIT_OFF
        jmp     MAIN_LOOP_ERROR
CMD_UART_WAIT_ON:
        ldaa    LINE_BUF+2
        cmpa    #CHR_SPACE
        bne     CMD_UART_WAIT_ERR
        ldaa    LINE_BUF+3
        cmpa    #'O'
        bne     CMD_UART_WAIT_ERR
        ldaa    LINE_BUF+4
        cmpa    #'N'
        bne     CMD_UART_WAIT_ERR
        ldaa    #1
        staa    ACIA_TX_WAIT
        bra     CMD_UART_WAIT_SHOW
CMD_UART_WAIT_OFF:
        ldaa    LINE_BUF+2
        cmpa    #CHR_SPACE
        bne     CMD_UART_WAIT_ERR
        ldaa    LINE_BUF+3
        cmpa    #'O'
        bne     CMD_UART_WAIT_ERR
        ldaa    LINE_BUF+4
        cmpa    #'F'
        bne     CMD_UART_WAIT_ERR
        ldaa    LINE_BUF+5
        cmpa    #'F'
        bne     CMD_UART_WAIT_ERR
        clr     ACIA_TX_WAIT
        bra     CMD_UART_WAIT_SHOW
CMD_UART_WAIT_ERR:
        jmp     MAIN_LOOP_ERROR
CMD_UART_WAIT_SHOW:
        ldx     #TXT_UW
        jsr     PDATA1
        tst     ACIA_TX_WAIT
        beq     CMD_UART_WAIT_SHOW_OFF
        ldx     #TXT_ON
        bra     CMD_UART_WAIT_SHOW_DONE
CMD_UART_WAIT_SHOW_OFF:
        ldx     #TXT_OFF
CMD_UART_WAIT_SHOW_DONE:
        jsr     PDATA1
        jsr     PRINT_CRLF
        jmp     MAIN_LOOP
 endif

CMD_UNASM:
        ldab    LINE_LEN
        cmpb    #1
        beq     CMD_UNASM_ERR
        ldx     #LINE_BUF+1
        decb
        jsr     PARSE_HEX
        bcs     CMD_UNASM_ERR
        ldx     HEX_VALUE_HI
        stx     DISASM_ADDR
        ldaa    #8
        staa    DISASM_COUNT
CMD_UNASM_LOOP:
        tst     DISASM_COUNT
        beq     CMD_UNASM_DONE
        jsr     DISASM_ONE
        dec     DISASM_COUNT
        bra     CMD_UNASM_LOOP
CMD_UNASM_DONE:
        jmp     MAIN_LOOP
CMD_UNASM_ERR:
        jmp     MAIN_LOOP_ERROR

CMD_HELP:
        ldab    LINE_LEN
        cmpb    #1
        bne     CMD_HELP_ERR
        ldx     #TXT_HELP
        jsr     PDATA1
        ldaa    #CHR_CR
        jsr     MON_OUTEEE
        jmp     MAIN_LOOP
CMD_HELP_ERR:
        jmp     MAIN_LOOP_ERROR

CMD_MAP:
 if MONITOR_PROFILE_K6802_VDG
        ldx     #TXT_MAP_K6802_VDG
 else
 if MONITOR_PROFILE_K6802_4000
        ldx     #TXT_MAP_K6802_4000
 else
 if MONITOR_PROFILE_SBCIO_4000
        ldx     #TXT_MAP_SBCIO_4000
 else
 if MONITOR_PROFILE_SBCIO
 if MONITOR_FEATURE_VDG
        ldx     #TXT_MAP_SBCIO_VDG
 else
        ldx     #TXT_MAP_SBCIO
 endif
 else
        ldx     #TXT_MAP_BASE
 endif
 endif
 endif
 endif
        jsr     MAP_PRINT_LINE

 if BUILD_MEMORY_CONFIG_BASE8K
        ldx     #TXT_MAP_BASE_RAM
        jsr     MAP_PRINT_LINE
        ldx     #TXT_MAP_BASE_USER
        jsr     MAP_PRINT_LINE
        ldx     #TXT_MAP_BASE_WORK
        jsr     MAP_PRINT_LINE
 if MONITOR_FEATURE_SD
        ldx     #TXT_MAP_BASE_SD
        jsr     MAP_PRINT_LINE
 endif
        ldx     #TXT_MAP_BASE_MON
        jsr     MAP_PRINT_LINE
        ldx     #TXT_MAP_BASE_MIK
        jsr     MAP_PRINT_LINE
        ldx     #TXT_MAP_BASE_STK
        jsr     MAP_PRINT_LINE
 endif

 if BUILD_MEMORY_CONFIG_RAM64_C000_WORK
        ldx     #TXT_MAP_SBCIO_RAM
        jsr     MAP_PRINT_LINE
        ldx     #TXT_MAP_SBCIO_USER
        jsr     MAP_PRINT_LINE
        ldx     #TXT_MAP_SBCIO_WORK
        jsr     MAP_PRINT_LINE
 if MONITOR_FEATURE_SD
        ldx     #TXT_MAP_SBCIO_SD
        jsr     MAP_PRINT_LINE
 endif
        ldx     #TXT_MAP_SBCIO_MON
        jsr     MAP_PRINT_LINE
        ldx     #TXT_MAP_SBCIO_MIK
        jsr     MAP_PRINT_LINE
        ldx     #TXT_MAP_SBCIO_STK
        jsr     MAP_PRINT_LINE
 endif

 if BUILD_MEMORY_CONFIG_RAM64_A000_WORK
        ldx     #TXT_MAP_SBCIO_RAM
        jsr     MAP_PRINT_LINE
        ldx     #TXT_MAP_SBCIO_USER
        jsr     MAP_PRINT_LINE
        ldx     #TXT_MAP_K6802_WORK
        jsr     MAP_PRINT_LINE
 if MONITOR_FEATURE_SD
        ldx     #TXT_MAP_K6802_SD
        jsr     MAP_PRINT_LINE
 endif
        ldx     #TXT_MAP_K6802_MON
        jsr     MAP_PRINT_LINE
        ldx     #TXT_MAP_K6802_MIK
        jsr     MAP_PRINT_LINE
        ldx     #TXT_MAP_K6802_STK
        jsr     MAP_PRINT_LINE
 endif

 if BUILD_MEMORY_CONFIG_RAM64_4000_WORK
        ldx     #TXT_MAP_RAM64_4000_RAM
        jsr     MAP_PRINT_LINE
        ldx     #TXT_MAP_RAM64_4000_USER
        jsr     MAP_PRINT_LINE
        ldx     #TXT_MAP_RAM64_4000_WORK
        jsr     MAP_PRINT_LINE
 if MONITOR_FEATURE_SD
         ldx     #TXT_MAP_RAM64_4000_SD
         jsr     MAP_PRINT_LINE
 endif
        ldx     #TXT_MAP_RAM64_4000_MON
        jsr     MAP_PRINT_LINE
        ldx     #TXT_MAP_RAM64_4000_MIK
        jsr     MAP_PRINT_LINE
        ldx     #TXT_MAP_RAM64_4000_STK
        jsr     MAP_PRINT_LINE
 endif

 if MONITOR_FEATURE_VDG
 if BUILD_VDG_VRAM_C000
        ldx     #TXT_MAP_K6802_VRAM
        jsr     MAP_PRINT_LINE
 else
        ldx     #TXT_MAP_VDG_VRAM
        jsr     MAP_PRINT_LINE
 endif
        ldx     #TXT_MAP_VDG_CTL
        jsr     MAP_PRINT_LINE
 endif
 if MONITOR_FEATURE_KEYBOARD
        ldx     #TXT_MAP_KEYBOARD
        jsr     MAP_PRINT_LINE
 endif
        ldx     #TXT_MAP_ROM
        jsr     MAP_PRINT_LINE
        jmp     MAIN_LOOP

MAP_PRINT_LINE:
        jsr     PDATA1
        jsr     PRINT_CRLF
        rts

CMD_RAMTEST:
        jsr     PARSE_RAMTEST_ARGS
        bcs     CMD_RAMTEST_ERR
        jsr     RAMTEST_VALIDATE_RANGE
        bcs     CMD_RAMTEST_ERR
        ldx     #TXT_RAMTEST_PREFIX
        jsr     PDATA1
        ldx     DUMP_ADDR
        jsr     PRINT_HEX16
        ldaa    #'-'
        jsr     MON_OUTEEE
        ldx     DUMP_END
        jsr     PRINT_HEX16
        jsr     PRINT_CRLF
        ldx     DUMP_END
        stx     RAMTEST_END_SAFE
        tsx
        dex
        stx     RAMTEST_SP_SAFE
        lds     #RAMTEST_STACK_TOP
        jsr     RAMTEST_RANGE
        lds     RAMTEST_SP_SAFE
CMD_RAMTEST_RESULT:
        bcs     CMD_RAMTEST_FAIL
        ldx     #TXT_OK
        jsr     MAP_PRINT_LINE
        jmp     MAIN_LOOP
CMD_RAMTEST_FAIL:
        stx     HEX_VALUE_HI
        ldx     #TXT_RAMTEST_NG
        jsr     PDATA1
        ldx     HEX_VALUE_HI
        jsr     PRINT_HEX16
        jsr     PRINT_CRLF
        jmp     MAIN_LOOP
CMD_RAMTEST_ERR:
        jmp     MAIN_LOOP_ERROR

PARSE_RAMTEST_ARGS:
        ldaa    LINE_BUF+12
        cmpa    #'-'
        bne     PARSE_RAMTEST_FAIL
        ldx     #LINE_BUF+8
        ldab    #4
        jsr     PARSE_HEX
        bcs     PARSE_RAMTEST_FAIL
        ldx     HEX_VALUE_HI
        stx     DUMP_ADDR
        ldx     #LINE_BUF+13
        ldab    #4
        jsr     PARSE_HEX
        bcs     PARSE_RAMTEST_FAIL
        ldx     HEX_VALUE_HI
        stx     DUMP_END
        ldx     DUMP_ADDR
        jsr     CMP_X_DUMP_END
        bhi     PARSE_RAMTEST_FAIL
        clc
        rts
PARSE_RAMTEST_FAIL:
        sec
        rts

RAMTEST_VALIDATE_RANGE:
        ldaa    #RAMTEST1_ENABLED
        beq     RAMTEST_VALIDATE_REGION2
        ldx     #RAMTEST1_START
        stx     RAMTEST_END_SAFE
        ldx     DUMP_ADDR
        jsr     CMP_X_RAMTEST_SAFE
        blo     RAMTEST_VALIDATE_REGION2
        ldx     #RAMTEST1_END
        stx     RAMTEST_END_SAFE
        ldx     DUMP_END
        jsr     CMP_X_RAMTEST_SAFE
        bls     RAMTEST_VALIDATE_OK
RAMTEST_VALIDATE_REGION2:
        ldaa    #RAMTEST2_ENABLED
        beq     RAMTEST_VALIDATE_REGION3
        ldx     #RAMTEST2_START
        stx     RAMTEST_END_SAFE
        ldx     DUMP_ADDR
        jsr     CMP_X_RAMTEST_SAFE
        blo     RAMTEST_VALIDATE_REGION3
        ldx     #RAMTEST2_END
        stx     RAMTEST_END_SAFE
        ldx     DUMP_END
        jsr     CMP_X_RAMTEST_SAFE
        bls     RAMTEST_VALIDATE_OK
RAMTEST_VALIDATE_REGION3:
        ldaa    #RAMTEST3_ENABLED
        beq     RAMTEST_VALIDATE_FAIL
        ldx     #RAMTEST3_START
        stx     RAMTEST_END_SAFE
        ldx     DUMP_ADDR
        jsr     CMP_X_RAMTEST_SAFE
        blo     RAMTEST_VALIDATE_FAIL
        ldx     #RAMTEST3_END
        stx     RAMTEST_END_SAFE
        ldx     DUMP_END
        jsr     CMP_X_RAMTEST_SAFE
        bls     RAMTEST_VALIDATE_OK
RAMTEST_VALIDATE_FAIL:
        sec
        rts
RAMTEST_VALIDATE_OK:
        clc
        rts

RAMTEST_RANGE:
        ldx     DUMP_ADDR
RAMTEST_RANGE_LOOP:
        jsr     RAMTEST_ONE_BYTE
        bcs     RAMTEST_RANGE_FAIL
        cpx     RAMTEST_END_SAFE
        beq     RAMTEST_RANGE_OK
        inx
        bra     RAMTEST_RANGE_LOOP

RAMTEST_ONE_BYTE:
        ldaa    0,x
        psha
        ldaa    #$55
        staa    0,x
        cmpa    0,x
        bne     RAMTEST_FAIL
        ldaa    #$AA
        staa    0,x
        cmpa    0,x
        bne     RAMTEST_FAIL
        pula
        staa    0,x
        clc
        rts
RAMTEST_FAIL:
        pula
        staa    0,x
        sec
        rts
RAMTEST_RANGE_OK:
        clc
        rts
RAMTEST_RANGE_FAIL:
        sec
        rts

CMP_X_RAMTEST_SAFE:
        stx     RAMTEST_CMP_SAFE
        ldaa    RAMTEST_CMP_SAFE
        cmpa    RAMTEST_END_SAFE
        bne     CMP_X_RAMTEST_SAFE_DONE
        ldaa    RAMTEST_CMP_SAFE+1
        cmpa    RAMTEST_END_SAFE+1
CMP_X_RAMTEST_SAFE_DONE:
        rts

CMD_FILL:
        ldab    LINE_LEN
        cmpb    #1
        beq     CMD_FILL_ERR
        ldx     #LINE_BUF+1
        decb
        jsr     PARSE_FILL_ARGS
        bcs     CMD_FILL_ERR
CMD_FILL_LOOP:
        ldx     MOD_ADDR
        ldaa    FILL_VALUE
        staa    0,x
        jsr     CMP_X_DUMP_END
        beq     CMD_FILL_DONE
        inx
        stx     MOD_ADDR
        bra     CMD_FILL_LOOP
CMD_FILL_DONE:
        jmp     MAIN_LOOP
CMD_FILL_ERR:
        jmp     MAIN_LOOP_ERROR

 if MONITOR_FEATURE_VDG
VDG_INIT:
        ldaa    #VDG_MODE
        staa    VDG_CTL
        jsr     VDG_CLEAR
        ldx     #VDG_VRAM_START
        stx     VDG_CURSOR
        ldaa    #$60
        staa    VDG_CURSOR_CHAR
        clr     VDG_LAST_CR
        jsr     VDG_DRAW_CURSOR
        rts

VDG_CLEAR:
        ldx     #VDG_VRAM_START
VDG_CLEAR_LOOP:
        ldaa    #$60
        staa    0,x
        cpx     #VDG_TEXT_END
        beq     VDG_CLEAR_DONE
        inx
        bra     VDG_CLEAR_LOOP
VDG_CLEAR_DONE:
        rts

VDG_PUTC:
        cmpa    #CHR_LF
        beq     VDG_PUTC_ENTER
        cmpa    #CHR_CR
        beq     VDG_PUTC_ENTER
        cmpa    #CHR_BS
        beq     VDG_PUTC_ENTER
        cmpa    #CHR_SPACE
        bhs     VDG_PUTC_ENTER
        rts
VDG_PUTC_ENTER:
        psha
        pshb
        stx     VDG_SAVE_X
        tab
        jsr     VDG_UNDRAW_CURSOR
        tba
        cmpa    #CHR_LF
        beq     VDG_PUTC_LF
        cmpa    #CHR_CR
        beq     VDG_PUTC_CR
        cmpa    #CHR_BS
        beq     VDG_PUTC_BS
        cmpa    #CHR_DEL
        beq     VDG_PUTC_BS
        clr     VDG_LAST_CR
        jsr     VDG_ASCII_TO_CHAR
        ldx     VDG_CURSOR
        staa    0,x
        inx
        stx     VDG_CURSOR
        jsr     VDG_CHECK_CURSOR
        bra     VDG_PUTC_DONE
VDG_PUTC_LF:
        tst     VDG_LAST_CR
        beq     VDG_PUTC_LF_NEWLINE
        clr     VDG_LAST_CR
        bra     VDG_PUTC_DONE
VDG_PUTC_LF_NEWLINE:
        jsr     VDG_NEWLINE
        bra     VDG_PUTC_DONE
VDG_PUTC_CR:
        tst     VDG_LAST_CR
        bne     VDG_PUTC_DONE
        jsr     VDG_NEWLINE
        ldaa    #1
        staa    VDG_LAST_CR
        bra     VDG_PUTC_DONE
VDG_PUTC_BS:
        clr     VDG_LAST_CR
        ldx     VDG_CURSOR
        cpx     #VDG_VRAM_START
        beq     VDG_PUTC_DONE
        dex
        stx     VDG_CURSOR
        ldaa    #$60
        staa    0,x
VDG_PUTC_DONE:
        jsr     VDG_DRAW_CURSOR
        ldx     VDG_SAVE_X
        pulb
        pula
        rts

VDG_NEWLINE:
        ldx     VDG_CURSOR
VDG_NEWLINE_LOOP:
        inx
        stx     VDG_CURSOR
        ldaa    VDG_CURSOR+1
        anda    #$1F
        bne     VDG_NEWLINE_LOOP
        jsr     VDG_CHECK_CURSOR
        rts

VDG_CHECK_CURSOR:
        ldx     VDG_CURSOR
        cpx     #VDG_TEXT_END+1
        bne     VDG_CHECK_CURSOR_DONE
        jsr     VDG_SCROLL
VDG_CHECK_CURSOR_DONE:
        rts

VDG_SCROLL:
        ldx     #VDG_VRAM_START
VDG_SCROLL_COPY:
        ldaa    $20,x
        staa    0,x
        cpx     #VDG_TEXT_END-$20
        beq     VDG_SCROLL_CLEAR
        inx
        bra     VDG_SCROLL_COPY
VDG_SCROLL_CLEAR:
        ldx     #VDG_TEXT_END-$1F
VDG_SCROLL_CLEAR_LOOP:
        ldaa    #$60
        staa    0,x
        cpx     #VDG_TEXT_END
        beq     VDG_SCROLL_DONE
        inx
        bra     VDG_SCROLL_CLEAR_LOOP
VDG_SCROLL_DONE:
        ldx     #VDG_TEXT_END-$1F
        stx     VDG_CURSOR
        rts

VDG_UNDRAW_CURSOR:
        ldx     VDG_CURSOR
        ldaa    VDG_CURSOR_CHAR
        staa    0,x
        rts

VDG_DRAW_CURSOR:
        ldx     VDG_CURSOR
        ldaa    0,x
        staa    VDG_CURSOR_CHAR
        ldaa    #$20
        staa    0,x
        rts

VDG_ASCII_TO_CHAR:
        cmpa    #$40
        bhs     VDG_ASCII_TO_CHAR_DONE
        adda    #$40
VDG_ASCII_TO_CHAR_DONE:
        rts
 endif

CMD_LOAD:
        ldab    LINE_LEN
        cmpb    #1
        bne     CMD_LOAD_EXTENDED

        ldaa    #'L'
        jsr     MON_OUTEEE
        ldaa    #CHR_CR
        jsr     MON_OUTEEE

        clr     LOADER_MODE
        clr     LOADER_STAGE
        clr     LOADER_INPUT

CMD_LOAD_LOOP:
        jsr     READ_LOADER_RECORD
        bcs     CMD_LOAD_ERROR
        cmpa    #1
        beq     CMD_LOAD_OK
        bra     CMD_LOAD_LOOP

CMD_LOAD_OK:
        ldaa    #'O'
        jsr     MON_OUTEEE
        ldaa    #'K'
        jsr     MON_OUTEEE
        ldaa    #CHR_CR
        jsr     MON_OUTEEE
        jmp     MAIN_LOOP

CMD_LOAD_ERROR:
        jsr     SHOW_LOADER_ERROR
        jmp     MAIN_LOOP

CMD_LOAD_BADARG:
        jmp     MAIN_LOOP_ERROR

CMD_LOAD_EXTENDED:
 if MONITOR_FEATURE_FAT
        ldaa    LINE_BUF+1
        cmpa    #'F'
        beq     CMD_LF
        cmpa    #'f'
        beq     CMD_LF
 endif
        jmp     CMD_LOAD_BADARG

 if MONITOR_FEATURE_FAT
CMD_LF:
        ldab    LINE_LEN
        subb    #2
        ldx     #LINE_BUF+2
        jsr     PARSE_FILENAME_83
        bcs     CMD_LF_ERROR
        jsr     FAT32_MOUNT
        bcs     CMD_LF_ERROR
        ldx     #FAT_FIND_NAME0
        jsr     FAT32_FIND_83
        bcs     CMD_LF_ERROR
        jsr     FAT32_STREAM_OPEN
        bcs     CMD_LF_ERROR
        clr     LOADER_MODE
        clr     LOADER_STAGE
        ldaa    #LOAD_INPUT_FAT
        staa    LOADER_INPUT
        bra     CMD_LOAD_LOOP
CMD_LF_ERROR:
        jmp     MAIN_LOOP_ERROR
 endif

 if MONITOR_FEATURE_SD
 if S1_SUPPORTED
S1_BOOT_SECTORS equ (S1_LIMIT-S1_BASE+1)/$0200
S1_BOOT_MAX_HI  equ (S1_LIMIT-S1_BASE+1)/$0100
S1_BOOT_MAX_LO  equ 0

CMD_BOOT:
        clr     BB_MAGIC
        jsr     SD_INIT
        bcs     CMD_BOOT_ERROR
        jsr     BOOT_SET_LBA16
        ldx     #S1_BASE
        stx     FAT_READ_PTR
        ldaa    #S1_BOOT_SECTORS
        staa    FAT_TMP
CMD_BOOT_READ_LOOP:
        ldx     FAT_READ_PTR
        jsr     SD_READ_SECTOR
        bcs     CMD_BOOT_ERROR
        dec     FAT_TMP
        beq     CMD_BOOT_CHECK
        ldaa    FAT_READ_PTR
        adda    #$02
        staa    FAT_READ_PTR
        jsr     BOOT_INC_SD_LBA
        bra     CMD_BOOT_READ_LOOP
CMD_BOOT_CHECK:
        jsr     BOOT_CHECK_STAGE1
        bcs     CMD_BOOT_ERROR
        ldx     S1_BASE+10
        jmp     0,x
CMD_BOOT_ERROR:
        jmp     MAIN_LOOP_ERROR

BOOT_SET_LBA16:
        clr     SD_LBA0
        clr     SD_LBA1
        clr     SD_LBA2
        ldaa    #$10
        staa    SD_LBA3
        rts

BOOT_INC_SD_LBA:
        inc     SD_LBA3
        bne     BOOT_INC_SD_LBA_DONE
        inc     SD_LBA2
        bne     BOOT_INC_SD_LBA_DONE
        inc     SD_LBA1
        bne     BOOT_INC_SD_LBA_DONE
        inc     SD_LBA0
BOOT_INC_SD_LBA_DONE:
        rts

BOOT_CHECK_STAGE1:
        ldx     #S1_BASE
        ldaa    0,x
        cmpa    #'S'
        bne     BOOT_STAGE1_SIG_FAIL
        ldaa    1,x
        cmpa    #'1'
        bne     BOOT_STAGE1_SIG_FAIL
        ldaa    2,x
        cmpa    #'A'
        bne     BOOT_STAGE1_SIG_FAIL
        ldaa    3,x
        cmpa    #'P'
        bne     BOOT_STAGE1_SIG_FAIL
        ldaa    4,x
        cmpa    #'I'
        bne     BOOT_STAGE1_SIG_FAIL
        ldaa    5,x
        cmpa    #'6'
        bne     BOOT_STAGE1_SIG_FAIL
        ldaa    6,x
        cmpa    #'8'
        bne     BOOT_STAGE1_SIG_FAIL
        ldaa    7,x
        cmpa    #1
        bne     BOOT_STAGE1_SIG_FAIL

        ldaa    12,x
        oraa    13,x
        beq     BOOT_STAGE1_SIZE_FAIL
        ldaa    12,x
        cmpa    #S1_BOOT_MAX_HI
        bhi     BOOT_STAGE1_SIZE_FAIL
        blo     BOOT_STAGE1_CHECK_ENTRY
        ldaa    13,x
        cmpa    #S1_BOOT_MAX_LO
        bhi     BOOT_STAGE1_SIZE_FAIL

BOOT_STAGE1_CHECK_ENTRY:
        ldaa    10,x
        suba    #S1_BASE/$0100
        bcs     BOOT_STAGE1_SIZE_FAIL
        staa    FAT_TMP
        cmpa    #S1_BOOT_MAX_HI
        bhs     BOOT_STAGE1_SIZE_FAIL
        ldaa    FAT_TMP
        cmpa    12,x
        bhi     BOOT_STAGE1_SIZE_FAIL
        blo     BOOT_STAGE1_OK
        ldaa    11,x
        cmpa    13,x
        bhs     BOOT_STAGE1_SIZE_FAIL
BOOT_STAGE1_OK:
        clc
        rts
BOOT_STAGE1_SIG_FAIL:
        ldaa    #FAT_ERR_SIG
        jmp     BOOT_FAIL_A
BOOT_STAGE1_SIZE_FAIL:
        ldaa    #FAT_ERR_SIZE
        jmp     BOOT_FAIL_A
BOOT_FAIL_A:
        staa    FAT_ERROR
        sec
        rts

SDFS3SYS_FIXED_LBA equ 64
SDFS3SYS_HEADER_SIZE equ $20
SDFS3SYS_MAX_HI equ $40
SDFS3SYS_MAX_LO equ $00
SDFS3SYS_MIN_LO equ SDFS3SYS_HEADER_SIZE+1

BOOT3_HEADER_SUM   equ FAT_VOLUME_LBA0     ; cold だけが使う(FAT_* は BOOT3 のあと CCP が mount し直す)

; 範囲指定の読み込みと和の照合の作業欄(BIOS 区画の BB_WORK。#314)。FAT_* は使わない。
BB_RR_OFF          equ BB_WORK             ; ファイル上のオフセット(次に写すバイト)
BB_RR_END          equ BB_WORK+2           ; ファイル上のオフセットの終端(最後の次)
BB_RR_DST          equ BB_WORK+4           ; 次に書く RAM の番地
BB_RR_TMP          equ BB_WORK+6           ; 作業用(セクタバッファ内の番地など)
BB_STATE_TMP       equ BB_WORK+7           ; BB_CHECK_SUMS が組み立てる STATE
BB_STATE_CCP       equ $01
BB_STATE_CORE      equ $02
 if (SD_SECTOR_BUF&$01FF)<>0
        error   "SD_SECTOR_BUF must be 512-byte aligned (BB_READ_RANGE)"
 endif

; BOOT3(cold)。SDFS3SYS を 1 回読みで検証してヘッダの load へ置き、BIOS 区画を書いて
; CCP の +0 へ入る。ヘッダの 32B は SD のバッファで、ペイロードはコピーした RAM で和を取り、
; 足してヘッダ +$18 と照合する。ROM は resident のスロットを呼ばない。
; 失敗したら区画を無効にして「?」でモニタへ戻る(和が合わないときは RAM の resident の
; 区画だけが新旧混ざるが、区画を無効にするので使われない)。
CMD_BOOT3:
        clr     BB_MAGIC
        jsr     SD_INIT
        bcs     CMD_BOOT3_ERROR
        ldx     #SDFS3SYS_FIXED_LBA
        stx     BB_SLOT_LBA
        jsr     BB_READ_HEADER
        bcs     CMD_BOOT3_ERROR
        jsr     BOOT3_CHECK_HEADER
        bcs     CMD_BOOT3_ERROR
        ldx     #SDFS3SYS_HEADER_SIZE
        stx     BB_RR_OFF
        ldx     SD_SECTOR_BUF+14
        stx     BB_RR_END
        ldx     BB_IMG_BASE
        stx     BB_RR_DST
        jsr     BB_READ_RANGE
        bcs     CMD_BOOT3_ERROR
        jsr     BB_STORE
        bcs     CMD_BOOT3_ERROR
        ldab    BB_SUM_CCP+1           ; ヘッダ + CCP + 核 = ヘッダ +$18
        ldaa    BB_SUM_CCP
        addb    BB_SUM_CORE+1
        adca    BB_SUM_CORE
        addb    BOOT3_HEADER_SUM+1
        adca    BOOT3_HEADER_SUM
        cmpb    BB_IMG_SUM+1
        bne     CMD_BOOT3_FAIL_SUM
        cmpa    BB_IMG_SUM
        bne     CMD_BOOT3_FAIL_SUM
        lds     #STACK_TOP
        ldx     BB_CCP_VEC
        jmp     0,x
CMD_BOOT3_FAIL_SUM:
        jsr     BOOT3_FAIL_SUM
CMD_BOOT3_ERROR:
        clr     BB_MAGIC
        jmp     MAIN_LOOP_ERROR

BOOT3_CHECK_HEADER:
        ldx     #SD_SECTOR_BUF
        ldaa    0,x
        cmpa    #'S'
        bne     BOOT3_HEADER_FAIL_SIG
        ldaa    1,x
        cmpa    #'D'
        bne     BOOT3_HEADER_FAIL_SIG
        ldaa    2,x
        cmpa    #'F'
        bne     BOOT3_HEADER_FAIL_SIG
        ldaa    3,x
        cmpa    #'S'
        bne     BOOT3_HEADER_FAIL_SIG
        ldaa    4,x
        cmpa    #'3'
        bne     BOOT3_HEADER_FAIL_SIG
        ldaa    5,x
        cmpa    #'S'
        bne     BOOT3_HEADER_FAIL_SIG
        ldaa    6,x
        cmpa    #'Y'
        bne     BOOT3_HEADER_FAIL_SIG
        ldaa    7,x
        cmpa    #'S'
        bne     BOOT3_HEADER_FAIL_SIG
        ldaa    8,x
        cmpa    #1
        bne     BOOT3_HEADER_FAIL_SIG
        ldaa    9,x
        cmpa    #SDFS3_API_MAJOR
        bne     BOOT3_HEADER_FAIL_SIG
        ldaa    11,x
        cmpa    #1
        bne     BOOT3_HEADER_FAIL_SIG
        ldaa    26,x
        bne     BOOT3_HEADER_FAIL_SIZE
        ldaa    27,x
        cmpa    #SDFS3SYS_HEADER_SIZE
        bne     BOOT3_HEADER_FAIL_SIZE
        ldaa    14,x
        cmpa    #SDFS3SYS_MAX_HI
        bhi     BOOT3_HEADER_FAIL_SIZE
        blo     BOOT3_CHECK_MIN
        ldaa    15,x
        cmpa    #SDFS3SYS_MAX_LO
        bhi     BOOT3_HEADER_FAIL_SIZE
BOOT3_CHECK_MIN:
        ldaa    14,x
        bne     BOOT3_CHECK_RANGE
        ldaa    15,x
        cmpa    #SDFS3SYS_MIN_LO
        blo     BOOT3_HEADER_FAIL_SIZE
        bra     BOOT3_CHECK_RANGE
BOOT3_HEADER_FAIL_SIG:
        jmp     BOOT3_FAIL_SIG
BOOT3_HEADER_FAIL_SIZE:
        jmp     BOOT3_FAIL_SIZE
; 大きさを確かめたあとで、load が置いてよい範囲に収まるかを見る(仕様 1-5)。
; SDFS3_RAM_FLOOR <= load、load + (size - ヘッダ) <= USER_RAM_END+1(桁あふれなし)。
; 通ったら load・CCP 入口表・核の先頭を区画に控える(コピーでヘッダが上書きされるため)。
BOOT3_CHECK_RANGE:
        ldaa    13,x
        suba    #SDFS3_RAM_FLOOR&$00FF
        ldaa    12,x
        sbca    #SDFS3_RAM_FLOOR/$0100
        bcs     BOOT3_HEADER_FAIL_SIZE
        ldab    13,x
        addb    15,x
        ldaa    12,x
        adca    14,x
        bcs     BOOT3_HEADER_FAIL_SIZE
        subb    #SDFS3SYS_HEADER_SIZE
        sbca    #0
        cmpa    #(USER_RAM_END+1)/$0100
        bhi     BOOT3_HEADER_FAIL_SIZE
        blo     BOOT3_RANGE_OK
        cmpb    #(USER_RAM_END+1)&$00FF
        bhi     BOOT3_HEADER_FAIL_SIZE
BOOT3_RANGE_OK:
        subb    #1                     ; IMG_LAST = load + payload - 1(payload >= 1)
        sbca    #0
        staa    BB_IMG_LAST
        stab    BB_IMG_LAST+1
        ldaa    12,x
        ldab    13,x
        staa    BB_IMG_BASE
        stab    BB_IMG_BASE+1
        addb    17,x
        adca    16,x
        staa    BB_CCP_VEC
        stab    BB_CCP_VEC+1
        ldaa    12,x
        ldab    13,x
        addb    19,x
        adca    18,x
        staa    BB_CORE_BASE
        stab    BB_CORE_BASE+1
; ヘッダ +$18 を区画に控え、+$18 を 0 にしたヘッダ 32B の和を取る。
        ldaa    24,x
        staa    BB_IMG_SUM
        ldaa    25,x
        staa    BB_IMG_SUM+1
        clr     24,x
        clr     25,x
        ldx     #SD_SECTOR_BUF+SDFS3SYS_HEADER_SIZE
        stx     BB_WORK
        ldx     #SD_SECTOR_BUF
        jsr     BIOS_RAM_SUM
        staa    BOOT3_HEADER_SUM
        stab    BOOT3_HEADER_SUM+1
        clc
        rts

BOOT3_FAIL_SIG:
        ldaa    #FAT_ERR_SIG
        bra     BOOT3_FAIL_A
BOOT3_FAIL_SIZE:
        ldaa    #FAT_ERR_SIZE
        bra     BOOT3_FAIL_A
BOOT3_FAIL_SUM:
        ldaa    #FAT_ERR_CHECKSUM
BOOT3_FAIL_A:
        staa    FAT_ERROR
        sec
        rts

; slot の先頭セクタ(SDFS3SYS ヘッダ)を SD_SECTOR_BUF に読む。LBA = BB_SLOT_LBA。C=1 で失敗。
BB_READ_HEADER:
        clr     BB_RR_OFF
        jsr     BB_RR_LBA
        bra     BB_RR_LOAD

; ファイル上の [OFF, END) を DST から RAM へ写す(BB_WORK の OFF・END・DST)。C=1 で SD の失敗。
; 呼ぶ前に BB_READ_HEADER で slot の先頭セクタを読んであること。必要なセクタだけを読み、
; バッファにあるセクタ(SD_LBA と同じ)は読み直さない。SD_SECTOR_BUF と SD_* だけを使う。
BB_READ_RANGE:
        jsr     BB_RR_AT_END
        beq     BB_RR_DONE
        jsr     BB_RR_ENSURE
        bcs     BB_RR_RTS
BB_RR_BYTE:
        ldaa    BB_RR_OFF              ; バッファ内の番地 = SD_SECTOR_BUF + (OFF & $01FF)
        anda    #$01
        adda    #SD_SECTOR_BUF/$0100
        staa    BB_RR_TMP
        ldaa    BB_RR_OFF+1
        staa    BB_RR_TMP+1
        ldx     BB_RR_TMP
        ldaa    0,x
        ldx     BB_RR_DST
        staa    0,x
        inx
        stx     BB_RR_DST
        ldx     BB_RR_OFF
        inx
        stx     BB_RR_OFF
        ldaa    BB_RR_OFF+1
        bne     BB_RR_NEXT
        ldaa    BB_RR_OFF
        bita    #$01
        beq     BB_READ_RANGE          ; 512 境界: 次のセクタへ
BB_RR_NEXT:
        jsr     BB_RR_AT_END
        bne     BB_RR_BYTE
BB_RR_DONE:
        clc
BB_RR_RTS:
        rts

; Z=1 なら OFF = END。
BB_RR_AT_END:
        ldaa    BB_RR_OFF
        cmpa    BB_RR_END
        bne     BB_RR_AT_END_RTS
        ldaa    BB_RR_OFF+1
        cmpa    BB_RR_END+1
BB_RR_AT_END_RTS:
        rts

; OFF のセクタをバッファに用意する。今のバッファのセクタ(SD_LBA)と同じなら読まない。
BB_RR_ENSURE:
        jsr     BB_RR_LBA
        tst     SD_LBA0
        bne     BB_RR_LOAD
        tst     SD_LBA1
        bne     BB_RR_LOAD
        cmpa    SD_LBA2
        bne     BB_RR_LOAD
        cmpb    SD_LBA3
        bne     BB_RR_LOAD
        clc
        rts
BB_RR_LOAD:
        clr     SD_LBA0
        clr     SD_LBA1
        staa    SD_LBA2
        stab    SD_LBA3
        ldx     #SD_SECTOR_BUF
        jmp     SD_READ_SECTOR

; A:B = BB_SLOT_LBA + OFF/512(cold と warm で同じ部品を使う)。
BB_RR_LBA:
        ldab    BB_RR_OFF
        lsrb
        clra
        addb    BB_SLOT_LBA+1
        adca    BB_SLOT_LBA
        rts

; A:B = X - IMG_BASE + ヘッダ(RAM の番地からファイル上のオフセットへ)。BB_RR_TMP を使う。
BB_FILE_OFF:
        stx     BB_RR_TMP
        ldab    BB_RR_TMP+1
        ldaa    BB_RR_TMP
        subb    BB_IMG_BASE+1
        sbca    BB_IMG_BASE
        addb    #SDFS3SYS_HEADER_SIZE
        adca    #0
        rts

SDFS3_API_MAJOR    equ 2

; 核の先頭(BB_CORE_BASE)の SDFS3API ヘッダを確かめる。C=0 で X = 核の先頭。
; 区画の自己検査を通したあとで呼ぶ。署名と major の 9 バイトがイメージの中にあることを
; 先に確かめ、壊れたヘッダで $8000 台の I/O を読まないようにする。
BB_CHECK_API:
        ldab    BB_IMG_LAST+1
        subb    BB_CORE_BASE+1
        ldaa    BB_IMG_LAST
        sbca    BB_CORE_BASE
        bne     BB_CHECK_API_ROOM
        cmpb    #8
        blo     BB_CHECK_API_FAIL
BB_CHECK_API_ROOM:
        ldx     BB_CORE_BASE
        ldaa    0,x
        cmpa    #'S'
        bne     BB_CHECK_API_FAIL
        ldaa    1,x
        cmpa    #'D'
        bne     BB_CHECK_API_FAIL
        ldaa    2,x
        cmpa    #'F'
        bne     BB_CHECK_API_FAIL
        ldaa    3,x
        cmpa    #'S'
        bne     BB_CHECK_API_FAIL
        ldaa    4,x
        cmpa    #'3'
        bne     BB_CHECK_API_FAIL
        ldaa    5,x
        cmpa    #'A'
        bne     BB_CHECK_API_FAIL
        ldaa    6,x
        cmpa    #'P'
        bne     BB_CHECK_API_FAIL
        ldaa    7,x
        cmpa    #'I'
        bne     BB_CHECK_API_FAIL
        ldaa    8,x
        cmpa    #SDFS3_API_MAJOR
        bne     BB_CHECK_API_FAIL
        clc
        rts
BB_CHECK_API_FAIL:
        sec
        rts

; BIOS 区画を仕上げる(BOOT3 の成功時)。C=0 で成功、C=1 で失敗(区画は呼び手が無効にする)。
; 入る前に IMG_BASE・CCP_VEC・CORE_BASE・IMG_LAST・IMG_SUM・SLOT_LBA は書いてある。
; 和はいったん 0 で CHECK を付けて自己検査し、範囲が正しいと分かってから取る。
BB_STORE:
        ldx     #0
        stx     BB_SUM_CCP
        stx     BB_SUM_CORE
        clr     BB_STATE
        ldaa    #BB_MAGIC_HI
        staa    BB_MAGIC
        ldaa    #BB_MAGIC_LO
        staa    BB_MAGIC+1
        jsr     BB_SET_CHECK
        jsr     BB_CHECK_VALID
        bcs     BB_STORE_DONE
        jsr     BB_CHECK_API
        bcs     BB_STORE_DONE
        jsr     BB_RAM_SUM_CCP
        staa    BB_SUM_CCP
        stab    BB_SUM_CCP+1
        jsr     BB_RAM_SUM_CORE
        staa    BB_SUM_CORE
        stab    BB_SUM_CORE+1
        jsr     BB_SET_CHECK
        clc
BB_STORE_DONE:
        rts

BB_SET_CHECK:
        jsr     BB_SUM8
        nega
        staa    BB_CHECK
        rts

; A を STATE に書いて CHECK を付け直す。戻ったとき Z は STATE が 0 かどうか。
BB_SET_STATE:
        staa    BB_STATE
        jsr     BB_SET_CHECK
        tst     BB_STATE
        rts

; RAM 上の CCP [IMG_BASE, CORE_BASE) と核 [CORE_BASE, IMG_LAST] の和を A:B に返す。
; 区画の自己検査を通したあとで呼ぶ。BB_WORK を使う。
BB_RAM_SUM_CCP:
        ldx     BB_CORE_BASE
        stx     BB_WORK
        ldx     BB_IMG_BASE
        jmp     BIOS_RAM_SUM
BB_RAM_SUM_CORE:
        ldx     BB_IMG_LAST
        inx
        stx     BB_WORK
        ldx     BB_CORE_BASE
        jmp     BIOS_RAM_SUM

; RAM の CCP と核の和を区画と照合し、壊れた区画のビット(BB_STATE_CCP・BB_STATE_CORE)を
; A に返す。区画の自己検査を通したあとで呼ぶ。BB_WORK だけを使い、区画の欄には書かない。
BB_CHECK_SUMS:
        clr     BB_STATE_TMP
        jsr     BB_RAM_SUM_CCP
        cmpa    BB_SUM_CCP
        bne     BB_CHECK_SUMS_CCP_BAD
        cmpb    BB_SUM_CCP+1
        beq     BB_CHECK_SUMS_CORE
BB_CHECK_SUMS_CCP_BAD:
        inc     BB_STATE_TMP
BB_CHECK_SUMS_CORE:
        jsr     BB_RAM_SUM_CORE
        cmpa    BB_SUM_CORE
        bne     BB_CHECK_SUMS_CORE_BAD
        cmpb    BB_SUM_CORE+1
        beq     BB_CHECK_SUMS_DONE
BB_CHECK_SUMS_CORE_BAD:
        ldaa    BB_STATE_TMP
        oraa    #BB_STATE_CORE
        staa    BB_STATE_TMP
BB_CHECK_SUMS_DONE:
        ldaa    BB_STATE_TMP
        rts

; 区画の +$00..+$12 の 8bit 和を A に返す。X を壊す。
BB_SUM8:
        ldx     #BIOS_BLOCK
        clra
BB_SUM8_LOOP:
        adda    0,x
        inx
        cpx     #BB_CHECK
        bne     BB_SUM8_LOOP
        rts

; 区画の自己検査。C=0 有効、C=1 未ロード。区画にもほかの RAM にも書かない。A・X を壊す。
; SDFS3_RAM_FLOOR <= IMG_BASE < CORE_BASE <= IMG_LAST <= USER_RAM_END、
; IMG_BASE <= CCP_VEC < CORE_BASE(仕様 1-3)。16bit の大小は suba/sbca の借りで見る。
; 「a < b」は b-1 から a を引くかわりに、a から b を引いて借りが出ること(bcc で弾く)で見る。
BB_CHECK_VALID:
        ldaa    BB_MAGIC
        cmpa    #BB_MAGIC_HI
        bne     BB_INVALID
        ldaa    BB_MAGIC+1
        cmpa    #BB_MAGIC_LO
        bne     BB_INVALID
        jsr     BB_SUM8
        adda    BB_CHECK
        bne     BB_INVALID
        ldaa    BB_IMG_BASE+1          ; SDFS3_RAM_FLOOR <= IMG_BASE
        suba    #SDFS3_RAM_FLOOR&$00FF
        ldaa    BB_IMG_BASE
        sbca    #SDFS3_RAM_FLOOR/$0100
        bcs     BB_INVALID
        ldaa    BB_IMG_BASE+1          ; IMG_BASE < CORE_BASE
        suba    BB_CORE_BASE+1
        ldaa    BB_IMG_BASE
        sbca    BB_CORE_BASE
        bcc     BB_INVALID
        ldaa    BB_IMG_LAST+1          ; CORE_BASE <= IMG_LAST
        suba    BB_CORE_BASE+1
        ldaa    BB_IMG_LAST
        sbca    BB_CORE_BASE
        bcs     BB_INVALID
        ldaa    #USER_RAM_END&$00FF    ; IMG_LAST <= USER_RAM_END
        suba    BB_IMG_LAST+1
        ldaa    #USER_RAM_END/$0100
        sbca    BB_IMG_LAST
        bcs     BB_INVALID
        ldaa    BB_CCP_VEC+1           ; IMG_BASE <= CCP_VEC
        suba    BB_IMG_BASE+1
        ldaa    BB_CCP_VEC
        sbca    BB_IMG_BASE
        bcs     BB_INVALID
        ldaa    BB_CCP_VEC+1           ; CCP_VEC < CORE_BASE
        suba    BB_CORE_BASE+1
        ldaa    BB_CCP_VEC
        sbca    BB_CORE_BASE
        bcc     BB_INVALID
        clc
        rts
BB_INVALID:
        sec
        rts

; BIOS_WBOOT とモニタの DOS(DOS へ warm で入る門)。区画の自己検査に通ったら和を照合して
; STATE に記録し、壊れた区画(CCP だけ/核だけ/両方)だけを SD から静かに読み直して
; CCP の +3 へ入る(Welcome は出さない。決定 13)。
; 自己検査に通らなければ区画に書かずに「?」でモニタへ。読み直しに失敗したら(SD が抜けた、
; カードが替わった、読み直しても和が合わない)区画を無効にして「?」でモニタへ。
BIOS_WBOOT_IMPL:
        lds     #STACK_TOP
        jsr     BB_CHECK_VALID
        bcs     BIOS_WBOOT_REJECT
        jsr     BB_CHECK_SUMS
        jsr     BB_SET_STATE
        beq     BIOS_WBOOT_ENTER
        jsr     BB_RELOAD
        bcs     BIOS_WBOOT_FAIL
        jsr     BB_CHECK_SUMS
        jsr     BB_SET_STATE
        bne     BIOS_WBOOT_FAIL
BIOS_WBOOT_ENTER:
        ldx     BB_CCP_VEC
        jmp     3,x
BIOS_WBOOT_FAIL:
        clr     BB_MAGIC
BIOS_WBOOT_REJECT:
        jmp     MAIN_LOOP_ERROR

; STATE のビットの区画だけを SD から読み直す。C=1 で失敗。
; slot の先頭セクタを読み、ヘッダ +$18 が BB_IMG_SUM と違えば(カードが替わった)、RAM に
; 書く前にやめる。区画の値は自己検査を通してあること。
BB_RELOAD:
        jsr     SD_INIT
        bcs     BB_RELOAD_RTS
        jsr     BB_READ_HEADER
        bcs     BB_RELOAD_RTS
        ldaa    SD_SECTOR_BUF+24
        cmpa    BB_IMG_SUM
        bne     BB_RELOAD_FAIL
        ldaa    SD_SECTOR_BUF+25
        cmpa    BB_IMG_SUM+1
        bne     BB_RELOAD_FAIL
        ldaa    BB_STATE
        bita    #BB_STATE_CCP
        beq     BB_RELOAD_CORE
        ldx     #SDFS3SYS_HEADER_SIZE  ; CCP: ファイル上 [ヘッダ, CORE_BASE の位置) を IMG_BASE へ
        stx     BB_RR_OFF
        ldx     BB_IMG_BASE
        stx     BB_RR_DST
        ldx     BB_CORE_BASE
        jsr     BB_FILE_OFF
        staa    BB_RR_END
        stab    BB_RR_END+1
        jsr     BB_READ_RANGE
        bcs     BB_RELOAD_RTS
BB_RELOAD_CORE:
        ldaa    BB_STATE
        bita    #BB_STATE_CORE
        beq     BB_RELOAD_OK
        ldx     BB_IMG_LAST            ; 核: ファイル上 [CORE_BASE の位置, IMG_LAST の次) を CORE_BASE へ
        inx
        jsr     BB_FILE_OFF
        staa    BB_RR_END
        stab    BB_RR_END+1
        ldx     BB_CORE_BASE
        stx     BB_RR_DST
        jsr     BB_FILE_OFF
        staa    BB_RR_OFF
        stab    BB_RR_OFF+1
        jsr     BB_READ_RANGE
        bcs     BB_RELOAD_RTS
BB_RELOAD_OK:
        clc
BB_RELOAD_RTS:
        rts
BB_RELOAD_FAIL:
        sec
        rts

; モニタ行きの検査(決定 1)。区画が有効なら和を照合して STATE に記録し、壊れていれば注意を
; 1 行(*SDFS3 CCP / *SDFS3 CORE / *SDFS3 CCP CORE)出す。読み直さない。
; 区画が無効(v2 モード・未ロード)なら何もしない。BB_WORK とレジスタだけを使う。
MON_CHECK:
        jsr     BB_CHECK_VALID
        bcs     MON_CHECK_DONE
        jsr     BB_CHECK_SUMS
        jsr     BB_SET_STATE
        beq     MON_CHECK_DONE
        ldx     #TXT_BB_WARN
        jsr     PDATA1
        ldaa    BB_STATE
        bita    #BB_STATE_CCP
        beq     MON_CHECK_CORE
        ldx     #TXT_BB_CCP
        jsr     PDATA1
MON_CHECK_CORE:
        ldaa    BB_STATE
        bita    #BB_STATE_CORE
        beq     MON_CHECK_EOL
        ldx     #TXT_BB_CORE
        jsr     PDATA1
MON_CHECK_EOL:
        jsr     PRINT_CRLF
MON_CHECK_DONE:
        rts

; モニタの門。$E20D(CONTRL・v2 の EXIT・BIOS_MONITOR)、SWI の BRK 表示のあと、G で
; 起動したプログラムの RTS がここへ来る。モニタのスタックに戻してから検査する。
MON_GATE:
        lds     #STACK_TOP
        jsr     MON_CHECK
        jmp     MAIN_LOOP

TXT_BB_WARN:
        fcc     "*SDFS3"
        fcb     $04
TXT_BB_CCP:
        fcc     " CCP"
        fcb     $04
TXT_BB_CORE:
        fcc     " CORE"
        fcb     $04

; X = SDFS3API ヘッダ(区画の CORE_BASE)、C=0。区画が無効なら C=1。和は見ない。B は保つ。
BIOS_GET_API_IMPL:
        jsr     BB_CHECK_VALID
        bcs     BIOS_GET_API_DONE
        ldx     BB_CORE_BASE
        clc
BIOS_GET_API_DONE:
        rts
 endif
 endif
 if MONITOR_FEATURE_FAT
CMD_DIR:
        ldab    LINE_LEN
        cmpb    #3
        beq     CMD_DIR_START
        jmp     MAIN_LOOP_ERROR
CMD_DIR_START:
        jsr     FAT32_MOUNT
        bcc     CMD_DIR_MOUNT_OK
        jmp     MAIN_LOOP_ERROR
CMD_DIR_MOUNT_OK:
        jsr     FAT_COPY_ROOT_TO_CUR
CMD_DIR_CLUSTER:
        jsr     FAT_CLUSTER_TO_SD_LBA
        ldx     #SD_SECTOR_BUF
        jsr     SD_READ_SECTOR
        bcc     CMD_DIR_SCAN_PREP
        jmp     MAIN_LOOP_ERROR
CMD_DIR_SCAN_PREP:
        ldx     #SD_SECTOR_BUF
        stx     FAT_ENTRY_PTR
        ldaa    #16
        staa    FAT_DIR_COUNT
CMD_DIR_ENTRY_LOOP:
        ldx     FAT_ENTRY_PTR
        ldaa    0,x
        beq     CMD_DIR_DONE
        cmpa    #$E5
        beq     CMD_DIR_SKIP_ENTRY
        ldaa    11,x
        anda    #$0F
        cmpa    #$0F
        beq     CMD_DIR_SKIP_ENTRY
        ldaa    11,x
        bita    #$18
        bne     CMD_DIR_SKIP_ENTRY
        jsr     CMD_DIR_PRINT_ENTRY
CMD_DIR_SKIP_ENTRY:
        jsr     FAT_ADVANCE_ENTRY_PTR
        dec     FAT_DIR_COUNT
        bne     CMD_DIR_ENTRY_LOOP
        jsr     FAT32_NEXT_CLUSTER
        bcs     CMD_DIR_DONE
        jsr     FAT_COPY_NEXT_TO_CUR
        bra     CMD_DIR_CLUSTER
CMD_DIR_DONE:
        jmp     MAIN_LOOP
 endif

PRINT_PROMPT:
        ldaa    #CHR_PROMPT
        jsr     MON_OUTEEE
        ldaa    #CHR_SPACE
        jsr     MON_OUTEEE
        rts

READ_LINE:
        ldx     #LINE_BUF
        stx     LINE_PTR
        clr     LINE_LEN

READ_LINE_LOOP:
        jsr     CONSOLE_GETC
        cmpa    #CHR_LF
        beq     READ_LINE_LOOP
        cmpa    #CHR_CR
        beq     READ_LINE_DONE
        cmpa    #CHR_BS
        beq     READ_LINE_BACKSPACE
        cmpa    #CHR_DEL
        beq     READ_LINE_BACKSPACE
        cmpa    #CHR_SPACE
        blo     READ_LINE_LOOP

        ldab    LINE_LEN
        cmpb    #LINE_BUF_SIZE
        bhs     READ_LINE_LOOP

        ldx     LINE_PTR
        staa    0,x
        inx
        stx     LINE_PTR
        inc     LINE_LEN
        jsr     MON_OUTEEE
        bra     READ_LINE_LOOP

READ_LINE_BACKSPACE:
        tst     LINE_LEN
        beq     READ_LINE_LOOP

        ldx     LINE_PTR
        dex
        stx     LINE_PTR
        dec     LINE_LEN

        ldaa    #CHR_BS
        jsr     MON_OUTEEE
        ldaa    #CHR_SPACE
        jsr     MON_OUTEEE
        ldaa    #CHR_BS
        jsr     MON_OUTEEE
        bra     READ_LINE_LOOP

READ_LINE_DONE:
        ldaa    #CHR_CR
        jsr     MON_OUTEEE
        rts

READ_LOADER_RECORD:
        jsr     READ_RECORD_HEAD
        bcs     READ_LOADER_RECORD_FAIL
        ldaa    LOADER_MODE
        bne     READ_LOADER_RECORD_MODE_SET
        ldaa    HEX_NIBBLE
        cmpa    #'S'
        beq     READ_LOADER_RECORD_SET_SREC
        cmpa    #':'
        beq     READ_LOADER_RECORD_SET_IHEX
        sec
        rts
READ_LOADER_RECORD_SET_SREC:
        ldaa    #LOAD_MODE_SREC
        staa    LOADER_MODE
        bra     READ_LOADER_RECORD_MODE_SET
READ_LOADER_RECORD_SET_IHEX:
        ldaa    #LOAD_MODE_IHEX
        staa    LOADER_MODE
READ_LOADER_RECORD_MODE_SET:
        ldaa    LOADER_MODE
        cmpa    #LOAD_MODE_SREC
        beq     READ_SREC_RECORD
        cmpa    #LOAD_MODE_IHEX
        bne     READ_LOADER_RECORD_FAIL
        jmp     READ_IHEX_RECORD
READ_LOADER_RECORD_FAIL:
        sec
        rts

READ_RECORD_HEAD:
        jsr     LOADER_GETC
        bcs     READ_RECORD_HEAD_FAIL
        cmpa    #CHR_LF
        beq     READ_RECORD_HEAD
        cmpa    #CHR_CR
        beq     READ_RECORD_HEAD
        cmpa    #CHR_SPACE
        blo     READ_RECORD_HEAD
        staa    HEX_NIBBLE
        clc
        rts
READ_RECORD_HEAD_FAIL:
        sec
        rts

READ_RECORD_TRAILER:
        jsr     LOADER_GETC
        bcs     READ_RECORD_TRAILER_FAIL
        cmpa    #CHR_LF
        beq     READ_RECORD_TRAILER_OK
        cmpa    #CHR_CR
        beq     READ_RECORD_TRAILER_OK
READ_RECORD_TRAILER_FAIL:
        sec
        rts
READ_RECORD_TRAILER_OK:
        clc
        rts

READ_HEXBYTE_INPUT:
        pshb
        jsr     LOADER_GETC
        bcs     READ_HEXBYTE_INPUT_FAIL
        jsr     HEX_TO_NIBBLE
        bcs     READ_HEXBYTE_INPUT_FAIL
        lsla
        lsla
        lsla
        lsla
        tab
        jsr     LOADER_GETC
        bcs     READ_HEXBYTE_INPUT_FAIL
        jsr     HEX_TO_NIBBLE
        bcs     READ_HEXBYTE_INPUT_FAIL
        aba
        pulb
        clc
        rts
READ_HEXBYTE_INPUT_FAIL:
        pulb
        sec
        rts

READ_SREC_RECORD:
        ldaa    HEX_NIBBLE
        cmpa    #'S'
        beq     READ_SREC_HEAD_OK
        jmp     READ_SREC_FAIL
READ_SREC_HEAD_OK:
        ldaa    #1
        staa    LOADER_STAGE
        jsr     LOADER_GETC
        bcs     READ_SREC_FAIL_NEAR0
        staa    LOADER_TYPE
        cmpa    #'0'
        beq     READ_SREC_TYPE_OK
        cmpa    #'1'
        beq     READ_SREC_TYPE_OK
        cmpa    #'2'
        beq     READ_SREC_TYPE_OK
        cmpa    #'5'
        beq     READ_SREC_TYPE_OK
        cmpa    #'8'
        beq     READ_SREC_TYPE_OK
        cmpa    #'9'
        beq     READ_SREC_TYPE_OK
        jmp     READ_SREC_FAIL
READ_SREC_FAIL_NEAR0:
        jmp     READ_SREC_FAIL
READ_SREC_TYPE_OK:
        ldaa    #2
        staa    LOADER_STAGE
        jsr     READ_HEXBYTE_INPUT
        bcs     READ_SREC_FAIL_NEAR1
        staa    LOADER_COUNT
        staa    LOADER_SUM
        ldaa    LOADER_TYPE
        cmpa    #'2'
        beq     READ_SREC_ADDR24
        cmpa    #'8'
        beq     READ_SREC_ADDR24
        ldaa    LOADER_COUNT
        cmpa    #3
        blo     READ_SREC_FAIL_NEAR1
        ldaa    #3
        staa    LOADER_STAGE
        jsr     READ_HEXBYTE_INPUT
        bcs     READ_SREC_FAIL_NEAR1
        staa    LOADER_ADDR
        jsr     ADD_TO_LOADER_SUM
        jsr     READ_HEXBYTE_INPUT
        bcs     READ_SREC_FAIL_NEAR1
        staa    LOADER_ADDR+1
        jsr     ADD_TO_LOADER_SUM
        ldab    LOADER_COUNT
        subb    #3
        bra     READ_SREC_DATA_LOOP
READ_SREC_FAIL_NEAR1:
        jmp     READ_SREC_FAIL
READ_SREC_ADDR24:
        ldaa    LOADER_COUNT
        cmpa    #4
        blo     READ_SREC_FAIL_NEAR2
        ldaa    #3
        staa    LOADER_STAGE
        jsr     READ_HEXBYTE_INPUT
        bcs     READ_SREC_FAIL_NEAR2
        staa    HEX_NIBBLE
        jsr     ADD_TO_LOADER_SUM
        ldaa    HEX_NIBBLE
        bne     READ_SREC_FAIL_NEAR2
        jsr     READ_HEXBYTE_INPUT
        bcs     READ_SREC_FAIL_NEAR2
        staa    LOADER_ADDR
        jsr     ADD_TO_LOADER_SUM
        jsr     READ_HEXBYTE_INPUT
        bcs     READ_SREC_FAIL_NEAR2
        staa    LOADER_ADDR+1
        jsr     ADD_TO_LOADER_SUM
        ldab    LOADER_COUNT
        subb    #4
        bra     READ_SREC_DATA_LOOP
READ_SREC_FAIL_NEAR2:
        jmp     READ_SREC_FAIL
READ_SREC_DATA_LOOP:
        ldaa    #4
        staa    LOADER_STAGE
        tstb
        beq     READ_SREC_CHECKSUM
        jsr     READ_HEXBYTE_INPUT
        bcs     READ_SREC_FAIL
        staa    HEX_NIBBLE
        jsr     ADD_TO_LOADER_SUM
        ldaa    LOADER_TYPE
        cmpa    #'1'
        beq     READ_SREC_STORE
        cmpa    #'2'
        bne     READ_SREC_SKIP_STORE
READ_SREC_STORE:
        ldaa    HEX_NIBBLE
        pshb
        ldx     LOADER_ADDR
        staa    0,x
        inx
        stx     LOADER_ADDR
        pulb
READ_SREC_SKIP_STORE:
        decb
        bra     READ_SREC_DATA_LOOP
READ_SREC_CHECKSUM:
        ldaa    #5
        staa    LOADER_STAGE
        jsr     READ_HEXBYTE_INPUT
        bcs     READ_SREC_FAIL
        jsr     ADD_TO_LOADER_SUM
        cmpa    #$FF
        bne     READ_SREC_FAIL
        jsr     READ_RECORD_TRAILER
        bcs     READ_SREC_FAIL
        ldaa    LOADER_TYPE
        cmpa    #'8'
        beq     READ_SREC_EOF
        cmpa    #'9'
        beq     READ_SREC_EOF
        ldaa    #0
        clc
        rts
READ_SREC_EOF:
        ldaa    #1
        clc
        rts
READ_SREC_FAIL:
        sec
        rts

READ_IHEX_RECORD:
        ldaa    HEX_NIBBLE
        cmpa    #':'
        beq     READ_IHEX_HEAD_OK
        jmp     READ_IHEX_FAIL
READ_IHEX_HEAD_OK:
        ldaa    #1
        staa    LOADER_STAGE
        ldaa    #2
        staa    LOADER_STAGE
        jsr     READ_HEXBYTE_INPUT
        bcs     READ_IHEX_FAIL_NEAR1
        staa    LOADER_COUNT
        staa    LOADER_SUM
        ldaa    #3
        staa    LOADER_STAGE
        jsr     READ_HEXBYTE_INPUT
        bcs     READ_IHEX_FAIL_NEAR1
        staa    LOADER_ADDR
        jsr     ADD_TO_LOADER_SUM
        jsr     READ_HEXBYTE_INPUT
        bcs     READ_IHEX_FAIL_NEAR1
        staa    LOADER_ADDR+1
        jsr     ADD_TO_LOADER_SUM
        jsr     READ_HEXBYTE_INPUT
        bcs     READ_IHEX_FAIL_NEAR1
        staa    LOADER_TYPE
        jsr     ADD_TO_LOADER_SUM
        ldaa    LOADER_TYPE
        cmpa    #$00
        beq     READ_IHEX_DATA
        cmpa    #$01
        bne     READ_IHEX_FAIL
        ldaa    LOADER_COUNT
        bne     READ_IHEX_FAIL
        bra     READ_IHEX_DATA
READ_IHEX_FAIL_NEAR1:
        jmp     READ_IHEX_FAIL
READ_IHEX_DATA:
        ldaa    #4
        staa    LOADER_STAGE
        ldab    LOADER_COUNT
READ_IHEX_DATA_LOOP:
        tstb
        beq     READ_IHEX_CHECKSUM
        jsr     READ_HEXBYTE_INPUT
        bcs     READ_IHEX_FAIL
        staa    HEX_NIBBLE
        jsr     ADD_TO_LOADER_SUM
        ldaa    LOADER_TYPE
        cmpa    #$00
        bne     READ_IHEX_SKIP_STORE
        ldaa    HEX_NIBBLE
        pshb
        ldx     LOADER_ADDR
        staa    0,x
        inx
        stx     LOADER_ADDR
        pulb
READ_IHEX_SKIP_STORE:
        decb
        bra     READ_IHEX_DATA_LOOP
READ_IHEX_CHECKSUM:
        ldaa    #5
        staa    LOADER_STAGE
        jsr     READ_HEXBYTE_INPUT
        bcs     READ_IHEX_FAIL
        jsr     ADD_TO_LOADER_SUM
        cmpa    #$00
        bne     READ_IHEX_FAIL
        jsr     READ_RECORD_TRAILER
        bcs     READ_IHEX_FAIL
        ldaa    LOADER_TYPE
        cmpa    #$01
        beq     READ_IHEX_EOF
        ldaa    #0
        clc
        rts
READ_IHEX_EOF:
        ldaa    #1
        clc
        rts
READ_IHEX_FAIL:
        sec
        rts

SHOW_ERROR:
        ldaa    #CHR_QUESTION
        jsr     MON_OUTEEE
        ldaa    #CHR_CR
        jsr     MON_OUTEEE
        rts

SHOW_LOADER_ERROR:
        ldaa    #CHR_QUESTION
        jsr     MON_OUTEEE
        ldaa    LOADER_MODE
        beq     SHOW_LOADER_ERROR_DONE
        cmpa    #LOAD_MODE_SREC
        bne     SHOW_LOADER_ERROR_IHEX
        ldaa    #'S'
        jsr     MON_OUTEEE
        bra     SHOW_LOADER_ERROR_STAGE
SHOW_LOADER_ERROR_IHEX:
        ldaa    #'I'
        jsr     MON_OUTEEE
SHOW_LOADER_ERROR_STAGE:
        ldaa    LOADER_STAGE
        adda    #'0'
        jsr     MON_OUTEEE
SHOW_LOADER_ERROR_DONE:
        ldaa    #CHR_CR
        jsr     MON_OUTEEE
        rts

PRINT_SPACE:
        ldaa    #CHR_SPACE
        jsr     MON_OUTEEE
        rts

PRINT_CRLF:
        ldaa    #CHR_CR
        jsr     MON_OUTEEE
        rts

ADD_TO_LOADER_SUM:
        adda    LOADER_SUM
        staa    LOADER_SUM
        rts

LOADER_GETC:
 if MONITOR_FEATURE_FAT
        ldaa    LOADER_INPUT
        cmpa    #LOAD_INPUT_FAT
        beq     LOADER_GETC_FAT
 endif
        jsr     ACIA_GETC
        clc
        rts
 if MONITOR_FEATURE_FAT
LOADER_GETC_FAT:
        pshb
        jsr     FAT32_STREAM_GETC
        bcc     LOADER_GETC_FAT_OK
        pulb
        sec
        rts
LOADER_GETC_FAT_OK:
        pulb
        clc
        rts
 endif

PRINT_HEX8:
        psha
        lsra
        lsra
        lsra
        lsra
        bsr     PRINT_NIBBLE
        pula
        bsr     PRINT_NIBBLE
        rts

PRINT_NIBBLE:
        anda    #$0F
        cmpa    #10
        bhs     PRINT_NIBBLE_AF
        adda    #'0'
        bra     PRINT_NIBBLE_OUT
PRINT_NIBBLE_AF:
        adda    #'A'-10
PRINT_NIBBLE_OUT:
        jsr     MON_OUTEEE
        rts

PRINT_HEX16:
        stx     HEX_VALUE_HI
        ldaa    HEX_VALUE_HI
        bsr     PRINT_HEX8
        ldaa    HEX_VALUE_LO
        bsr     PRINT_HEX8
        ldx     HEX_VALUE_HI
        rts

PARSE_HEX:
        tstb
        beq     PARSE_HEX_FAIL
        cmpb    #5
        bhs     PARSE_HEX_FAIL

        clr     HEX_VALUE_HI
        clr     HEX_VALUE_LO

PARSE_HEX_LOOP:
        ldaa    0,x
        jsr     HEX_TO_NIBBLE
        bcs     PARSE_HEX_FAIL
        staa    HEX_NIBBLE

        asl     HEX_VALUE_LO
        rol     HEX_VALUE_HI
        asl     HEX_VALUE_LO
        rol     HEX_VALUE_HI
        asl     HEX_VALUE_LO
        rol     HEX_VALUE_HI
        asl     HEX_VALUE_LO
        rol     HEX_VALUE_HI

        ldaa    HEX_VALUE_LO
        adda    HEX_NIBBLE
        staa    HEX_VALUE_LO
        bcc     PARSE_HEX_NEXT
        inc     HEX_VALUE_HI

PARSE_HEX_NEXT:
        inx
        decb
        bne     PARSE_HEX_LOOP
        clc
        rts

PARSE_HEX_FAIL:
        sec
        rts

SWI_HANDLER:
        tsx
        stx     BRK_FRAME
        ldaa    0,x
        staa    BRK_SAVE_CC
        ldaa    1,x
        staa    BRK_SAVE_B
        ldaa    2,x
        staa    BRK_SAVE_A
        ldaa    3,x
        staa    BRK_SAVE_X
        ldaa    4,x
        staa    BRK_SAVE_X+1
        ldaa    5,x
        staa    BRK_SAVE_PC
        ldaa    6,x
        staa    BRK_SAVE_PC+1
        lds     #STACK_TOP

        ldaa    BRK_SAVE_PC
        staa    BRK_ADDR
        ldaa    BRK_SAVE_PC+1
        staa    BRK_ADDR+1
        ldx     BRK_ADDR
        dex
        stx     BRK_ADDR

        ldaa    BRK_ADDR
        staa    BRK_SAVE_PC
        ldaa    BRK_ADDR+1
        staa    BRK_SAVE_PC+1

        ldx     BRK_FRAME
        inx
        inx
        inx
        inx
        inx
        inx
        stx     BRK_USER_SP

        tst     BP_ACTIVE
        beq     SWI_HANDLER_PRINT
        ldaa    BRK_ADDR
        cmpa    BP_ADDR
        bne     SWI_HANDLER_PRINT
        ldaa    BRK_ADDR+1
        cmpa    BP_ADDR+1
        bne     SWI_HANDLER_PRINT
        jsr     RESTORE_BREAKPOINT

SWI_HANDLER_PRINT:
        ldaa    #1
        staa    BRK_ACTIVE
        jsr     PRINT_CRLF
        ldx     #TXT_BRK
        jsr     PDATA1
        ldx     BRK_ADDR
        jsr     PRINT_HEX16
        jsr     PRINT_SPACE
        ldx     #TXT_A
        jsr     PDATA1
        ldaa    BRK_SAVE_A
        jsr     PRINT_HEX8
        jsr     PRINT_SPACE
        ldx     #TXT_B
        jsr     PDATA1
        ldaa    BRK_SAVE_B
        jsr     PRINT_HEX8
        jsr     PRINT_SPACE
        ldx     #TXT_X
        jsr     PDATA1
        ldaa    BRK_SAVE_X
        staa    HEX_VALUE_HI
        ldaa    BRK_SAVE_X+1
        staa    HEX_VALUE_LO
        ldx     HEX_VALUE_HI
        jsr     PRINT_HEX16
        jsr     PRINT_SPACE
        ldx     #TXT_SP
        jsr     PDATA1
        ldx     BRK_USER_SP
        jsr     PRINT_HEX16
        jsr     PRINT_SPACE
        ldx     #TXT_CC
        jsr     PDATA1
        ldaa    BRK_SAVE_CC
        jsr     PRINT_HEX8
        jsr     PRINT_CRLF
 if MONITOR_FEATURE_SD
        jmp     MON_GATE                ; 退避したあとで検査する(決定 1)
 else
        jmp     MAIN_LOOP
 endif

DISASM_ONE:
        ldx     DISASM_ADDR
        jsr     PRINT_HEX16
        jsr     PRINT_SPACE
        ldaa    0,x
        staa    HEX_NIBBLE
        jsr     PRINT_HEX8
        jsr     PRINT_SPACE
        ldaa    HEX_NIBBLE
        cmpa    #$86
        beq     DISASM_LDAA_IMM
        cmpa    #$C6
        beq     DISASM_LDAB_IMM
        cmpa    #$CE
        beq     DISASM_LDX_IMM
        cmpa    #$8E
        beq     DISASM_LDS_IMM
        cmpa    #$B7
        beq     DISASM_STAA_EXT
        cmpa    #$F7
        beq     DISASM_STAB_EXT
        cmpa    #$BD
        beq     DISASM_JSR_EXT
        cmpa    #$7E
        beq     DISASM_JMP_EXT
        cmpa    #$20
        beq     DISASM_BRA_REL
        cmpa    #$26
        beq     DISASM_BNE_REL
        cmpa    #$27
        beq     DISASM_BEQ_REL
        cmpa    #$39
        beq     DISASM_RTS
        cmpa    #$3F
        beq     DISASM_SWI
        cmpa    #$01
        beq     DISASM_NOP
        ldx     #TXT_DB
        jsr     PDATA1
        ldaa    HEX_NIBBLE
        jsr     PRINT_HEX8
        ldab    #1
        jmp     DISASM_ADVANCE

DISASM_LDAA_IMM:
        ldx     #TXT_LDAA_IMM
        bra     DISASM_IMM8
DISASM_LDAB_IMM:
        ldx     #TXT_LDAB_IMM
        bra     DISASM_IMM8
DISASM_LDX_IMM:
        ldx     #TXT_LDX_IMM
        bra     DISASM_IMM16
DISASM_LDS_IMM:
        ldx     #TXT_LDS_IMM
        bra     DISASM_IMM16
DISASM_STAA_EXT:
        ldx     #TXT_STAA_EXT
        bra     DISASM_EXT16
DISASM_STAB_EXT:
        ldx     #TXT_STAB_EXT
        bra     DISASM_EXT16
DISASM_JSR_EXT:
        ldx     #TXT_JSR_EXT
        bra     DISASM_EXT16
DISASM_JMP_EXT:
        ldx     #TXT_JMP_EXT
        bra     DISASM_EXT16
DISASM_BRA_REL:
        ldx     #TXT_BRA_REL
        bra     DISASM_IMM8
DISASM_BNE_REL:
        ldx     #TXT_BNE_REL
        bra     DISASM_IMM8
DISASM_BEQ_REL:
        ldx     #TXT_BEQ_REL
        bra     DISASM_IMM8
DISASM_RTS:
        ldx     #TXT_RTS
        jsr     PDATA1
        ldab    #1
        jmp     DISASM_ADVANCE
DISASM_SWI:
        ldx     #TXT_SWI
        jsr     PDATA1
        ldab    #1
        jmp     DISASM_ADVANCE
DISASM_NOP:
        ldx     #TXT_NOP
        jsr     PDATA1
        ldab    #1
        jmp     DISASM_ADVANCE

DISASM_IMM8:
        jsr     PDATA1
        ldx     DISASM_ADDR
        ldaa    1,x
        jsr     PRINT_HEX8
        ldab    #2
        jmp     DISASM_ADVANCE

DISASM_IMM16:
        jsr     PDATA1
        ldx     DISASM_ADDR
        ldaa    1,x
        staa    HEX_VALUE_HI
        ldaa    2,x
        staa    HEX_VALUE_LO
        ldx     HEX_VALUE_HI
        jsr     PRINT_HEX16
        ldab    #3
        jmp     DISASM_ADVANCE

DISASM_EXT16:
        jsr     PDATA1
        ldx     DISASM_ADDR
        ldaa    1,x
        staa    HEX_VALUE_HI
        ldaa    2,x
        staa    HEX_VALUE_LO
        ldx     HEX_VALUE_HI
        jsr     PRINT_HEX16
        ldab    #3

DISASM_ADVANCE:
        jsr     PRINT_CRLF
        ldx     DISASM_ADDR
DISASM_ADVANCE_LOOP:
        inx
        decb
        bne     DISASM_ADVANCE_LOOP
        stx     DISASM_ADDR
        rts

TXT_BRK:        fcc     "BRK "
                fcb     $04
TXT_WELCOME:    fcc     "MC6800 MONITOR"
                fcb     $04
TXT_HELP:
 if MONITOR_FEATURE_FAT
 if MONITOR_FEATURE_VDG
                fcc     "D DS DIR M MAP RAMTEST G L LF BOOT BOOT3 DOS B C R U UW H F"
 else
                fcc     "D DIR M MAP RAMTEST G L LF BOOT BOOT3 DOS B C R U H F"
 endif
 else
 if MONITOR_FEATURE_SD
 if S1_SUPPORTED
 if MONITOR_FEATURE_VDG
                fcc     "D DS M MAP RAMTEST G L BOOT BOOT3 DOS B C R U UW H F"
 else
                fcc     "D M MAP RAMTEST G L BOOT BOOT3 DOS B C R U H F"
 endif
 else
 if MONITOR_FEATURE_VDG
                fcc     "D DS M MAP RAMTEST G L B C R U UW H F"
 else
                fcc     "D M MAP RAMTEST G L B C R U H F"
 endif
 endif
 else
 if MONITOR_FEATURE_VDG
                fcc     "D DS M MAP RAMTEST G L B C R U UW H F"
 else
                fcc     "D M MAP RAMTEST G L B C R U H F"
 endif
 endif
 endif
                    fcb     $04
TXT_OK:         fcc     "OK"
                fcb     $04
TXT_RAMTEST_PREFIX: fcc     "RAMTEST "
                    fcb     $04
TXT_RAMTEST_NG:     fcc     "NG "
                    fcb     $04
 if MONITOR_PROFILE_BASE
TXT_MAP_BASE:       fcc     "MAP BASE"
                    fcb     $04
 endif
 if BUILD_MEMORY_CONFIG_BASE8K
TXT_MAP_BASE_RAM:   fcc     "RAM 0000-1FFF"
                    fcb     $04
TXT_MAP_BASE_USER:  fcc     "USER 0000-1FFF"
                    fcb     $04
TXT_MAP_BASE_WORK:  fcc     "WORK 1C00-1FFF"
                    fcb     $04
 if MONITOR_FEATURE_SD
TXT_MAP_BASE_SD:    fcc     "SD 1C00"
                    fcb     $04
 endif
TXT_MAP_BASE_MON:   fcc     "MON 1E00"
                    fcb     $04
 endif
 if MONITOR_PROFILE_SBCIO
 if MONITOR_FEATURE_VDG
TXT_MAP_SBCIO_VDG:  fcc     "MAP SBCIO VDG"
                    fcb     $04
 else
TXT_MAP_SBCIO:      fcc     "MAP SBCIO"
                    fcb     $04
 endif
 endif
 if MONITOR_PROFILE_SBCIO_4000
TXT_MAP_SBCIO_4000: fcc     "MAP SBCIO 4000"
                    fcb     $04
 endif
 if MONITOR_PROFILE_K6802_4000
TXT_MAP_K6802_4000: fcc     "MAP K6802 4000"
                    fcb     $04
 endif
 if MONITOR_PROFILE_K6802_VDG
TXT_MAP_K6802_VDG:  fcc     "MAP K6802 VDG"
                    fcb     $04
 endif
 if BUILD_MEMORY_CONFIG_RAM64_C000_WORK
TXT_MAP_SBCIO_RAM:  fcc     "RAM 0000-7FFF"
                    fcb     $04
TXT_MAP_SBCIO_USER: fcc     "USER 0000-7FFF"
                    fcb     $04
 endif
 if BUILD_MEMORY_CONFIG_RAM64_A000_WORK
TXT_MAP_SBCIO_RAM:  fcc     "RAM 0000-7FFF"
                    fcb     $04
TXT_MAP_SBCIO_USER: fcc     "USER 0000-7FFF"
                    fcb     $04
 endif
 if BUILD_MEMORY_CONFIG_RAM64_4000_WORK
TXT_MAP_RAM64_4000_RAM:  fcc     "RAM 0000-7FFF"
                    fcb     $04
TXT_MAP_RAM64_4000_USER: fcc     "USER 0000-3FFF"
                    fcb     $04
TXT_MAP_RAM64_4000_WORK: fcc     "WORK 4000-7FFF"
                    fcb     $04
 endif
 if BUILD_MEMORY_CONFIG_RAM64_C000_WORK
TXT_MAP_SBCIO_WORK: fcc     "WORK C000-DFFF"
                    fcb     $04
 endif
 if BUILD_MEMORY_CONFIG_RAM64_A000_WORK
TXT_MAP_K6802_WORK: fcc     "WORK A000-BFFF"
                    fcb     $04
 endif
 if MONITOR_FEATURE_SD
 if BUILD_MEMORY_CONFIG_RAM64_C000_WORK
TXT_MAP_SBCIO_SD:   fcc     "SD C000"
                    fcb     $04
 endif
 if BUILD_MEMORY_CONFIG_RAM64_A000_WORK
TXT_MAP_K6802_SD:   fcc     "SD A000"
                    fcb     $04
 endif
 if BUILD_MEMORY_CONFIG_RAM64_4000_WORK
 if BUILD_VDG_VRAM_C000
TXT_MAP_RAM64_4000_SD:   fcc     "SD A000"
                    fcb     $04
 else
TXT_MAP_RAM64_4000_SD:   fcc     "SD C000"
                    fcb     $04
 endif
 endif
 endif
 if BUILD_MEMORY_CONFIG_RAM64_C000_WORK
TXT_MAP_SBCIO_MON:  fcc     "MON C200"
                    fcb     $04
 endif
 if BUILD_MEMORY_CONFIG_RAM64_A000_WORK
TXT_MAP_K6802_MON:  fcc     "MON A200"
                    fcb     $04
 endif
 if BUILD_MEMORY_CONFIG_RAM64_4000_WORK
TXT_MAP_RAM64_4000_MON:  fcc     "MON 4200"
                    fcb     $04
 endif
 if BUILD_MEMORY_CONFIG_BASE8K
TXT_MAP_BASE_MIK:   fcc     "MIK 1F00"
                    fcb     $04
TXT_MAP_BASE_STK:   fcc     "STK 1F42"
                    fcb     $04
 endif
 if BUILD_MEMORY_CONFIG_RAM64_C000_WORK
TXT_MAP_SBCIO_MIK:  fcc     "MIK C300"
                    fcb     $04
 endif
 if BUILD_MEMORY_CONFIG_RAM64_A000_WORK
TXT_MAP_K6802_MIK:  fcc     "MIK A300"
                    fcb     $04
 endif
 if BUILD_MEMORY_CONFIG_RAM64_4000_WORK
TXT_MAP_RAM64_4000_MIK:  fcc     "MIK 4300"
                    fcb     $04
 endif
 if BUILD_MEMORY_CONFIG_RAM64_C000_WORK
TXT_MAP_SBCIO_STK:  fcc     "STK DFFF"
                    fcb     $04
 endif
 if BUILD_MEMORY_CONFIG_RAM64_A000_WORK
TXT_MAP_K6802_STK:  fcc     "STK BFFF"
                    fcb     $04
 endif
 if BUILD_MEMORY_CONFIG_RAM64_4000_WORK
TXT_MAP_RAM64_4000_STK:  fcc     "STK 7FFF"
                    fcb     $04
 endif
 if MONITOR_FEATURE_VDG
 if BUILD_VDG_VRAM_C000
TXT_MAP_K6802_VRAM: fcc     "VRAM C000-DFFF"
                    fcb     $04
 else
TXT_MAP_VDG_VRAM:   fcc     "VRAM A000-BFFF"
                    fcb     $04
 endif
TXT_MAP_VDG_CTL:    fcc     "VDG 8110"
                    fcb     $04
 endif
 if MONITOR_FEATURE_KEYBOARD
TXT_MAP_KEYBOARD:   fcc     "KEY 8094-8095"
                    fcb     $04
 endif
TXT_MAP_ROM:        fcc     "ROM E000-FFFF"
                    fcb     $04
TXT_BP:         fcc     "BP "
                fcb     $04
TXT_NONE:       fcc     "NONE"
                fcb     $04
 if MONITOR_FEATURE_VDG
TXT_UW:         fcc     "UW "
                fcb     $04
TXT_ON:         fcc     "ON"
                fcb     $04
TXT_OFF:        fcc     "OFF"
                fcb     $04
 endif
TXT_A:          fcc     "A="
                fcb     $04
TXT_B:          fcc     "B="
                fcb     $04
TXT_X:          fcc     "X="
                fcb     $04
TXT_SP:         fcc     "SP="
                fcb     $04
TXT_CC:         fcc     "CC="
                fcb     $04
TXT_DB:         fcc     "DB $"
                fcb     $04
TXT_LDAA_IMM:   fcc     "LDAA #$"
                fcb     $04
TXT_LDAB_IMM:   fcc     "LDAB #$"
                fcb     $04
TXT_LDX_IMM:    fcc     "LDX #$"
                fcb     $04
TXT_LDS_IMM:    fcc     "LDS #$"
                fcb     $04
TXT_STAA_EXT:   fcc     "STAA $"
                fcb     $04
TXT_STAB_EXT:   fcc     "STAB $"
                fcb     $04
TXT_JSR_EXT:    fcc     "JSR $"
                fcb     $04
TXT_JMP_EXT:    fcc     "JMP $"
                fcb     $04
TXT_BRA_REL:    fcc     "BRA $"
                fcb     $04
TXT_BNE_REL:    fcc     "BNE $"
                fcb     $04
TXT_BEQ_REL:    fcc     "BEQ $"
                fcb     $04
TXT_RTS:        fcc     "RTS"
                fcb     $04
TXT_SWI:        fcc     "SWI"
                fcb     $04
TXT_NOP:        fcc     "NOP"
                fcb     $04

HEX_TO_NIBBLE:
        cmpa    #'0'
        blo     HEX_TO_NIBBLE_FAIL
        cmpa    #'9'
        bls     HEX_TO_NIBBLE_DEC
        cmpa    #'A'
        blo     HEX_TO_NIBBLE_LOWER
        cmpa    #'F'
        bls     HEX_TO_NIBBLE_UPPER

HEX_TO_NIBBLE_LOWER:
        cmpa    #'a'
        blo     HEX_TO_NIBBLE_FAIL
        cmpa    #'f'
        bhi     HEX_TO_NIBBLE_FAIL
        suba    #'a'-10
        clc
        rts

HEX_TO_NIBBLE_UPPER:
        suba    #'A'-10
        clc
        rts

HEX_TO_NIBBLE_DEC:
        suba    #'0'
        clc
        rts

HEX_TO_NIBBLE_FAIL:
        sec
        rts

SPURIOUS_IRQ:
        rti

        include "acia6850.asm"
 if MONITOR_FEATURE_SD
        include "sdcard.asm"
 endif
 if MONITOR_FEATURE_FAT
FAT32_INCLUDE_FIND_API equ 1
FAT32_INCLUDE_FILE_API equ 1
        include "fat32.asm"
 endif

        org     VEC_IRQ
        fdb     SPURIOUS_IRQ     ; VEC_IRQ
        fdb     SWI_HANDLER      ; VEC_SWI
        fdb     SPURIOUS_IRQ     ; VEC_NMI
        fdb     RESET            ; VEC_RESET
