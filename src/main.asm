        cpu     6800

        include "../include/hardware.inc"
        include "../include/mikbug.inc"

        org     MIKBUG_OUTCH
OUTCH:  jmp     OUTEEE

INCH:   jmp     INEEE

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
CONTRL: jmp     MONITOR_ENTRY

        org     MIKBUG_INEEE
INEEE:  jmp     MIKBUG_INEEE_IMPL

        org     MIKBUG_OUTEEE
OUTEEE: jmp     MIKBUG_OUTEEE_IMPL

        org     MONITOR_BASE

MONITOR_ENTRY:
        lds     #STACK_TOP
        jsr     ACIA_INIT
        jmp     MAIN_LOOP

RESET:
        lds     #STACK_TOP
        clr     DUMP_ADDR
        clr     DUMP_ADDR+1
        clr     BP_ACTIVE
        clr     BRK_ACTIVE
        jsr     ACIA_INIT
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
        beq     MAIN_LOOP_JMP_DUMP
        cmpa    #'M'
        beq     MAIN_LOOP_JMP_MOD
        cmpa    #'G'
        beq     MAIN_LOOP_JMP_GO
        cmpa    #'L'
        beq     MAIN_LOOP_JMP_LOAD
        cmpa    #'B'
        beq     MAIN_LOOP_JMP_BRK
        cmpa    #'R'
        beq     MAIN_LOOP_JMP_RESUME
        cmpa    #'C'
        beq     MAIN_LOOP_JMP_CLEAR
        cmpa    #'U'
        beq     MAIN_LOOP_JMP_UNASM
        cmpa    #'I'
        beq     MAIN_LOOP_JMP_SDINIT
        cmpa    #'S'
        beq     MAIN_LOOP_JMP_SDREAD
        cmpa    #'V'
        beq     MAIN_LOOP_JMP_SDDIR
        cmpa    #'H'
        beq     MAIN_LOOP_JMP_HELP
        cmpa    #'F'
        beq     MAIN_LOOP_JMP_FILL
        jmp     MAIN_LOOP_ERROR

MAIN_LOOP_JMP_DUMP:     jmp     CMD_DUMP
MAIN_LOOP_JMP_MOD:      jmp     CMD_MOD
MAIN_LOOP_JMP_GO:       jmp     CMD_GO
MAIN_LOOP_JMP_BRK:      jmp     CMD_BREAK_SET
MAIN_LOOP_JMP_RESUME:   jmp     CMD_RESUME
MAIN_LOOP_JMP_CLEAR:    jmp     CMD_BREAK_CLEAR
MAIN_LOOP_JMP_UNASM:    jmp     CMD_UNASM
MAIN_LOOP_JMP_SDINIT:   jmp     CMD_SDINIT
MAIN_LOOP_JMP_SDREAD:   jmp     CMD_SDREAD
MAIN_LOOP_JMP_SDDIR:    jmp     CMD_SDDIR
MAIN_LOOP_JMP_HELP:     jmp     CMD_HELP
MAIN_LOOP_JMP_FILL:     jmp     CMD_FILL

MAIN_LOOP_JMP_LOAD:
        ldab    LINE_LEN
        cmpb    #1
        beq     CMD_LOAD_SERIAL_JMP
        ldaa    LINE_BUF+1
        cmpa    #'F'
        beq     CMD_LOAD_FILE_JMP
CMD_LOAD_SERIAL_JMP:
        jmp     CMD_LOAD
CMD_LOAD_FILE_JMP:
        jmp     CMD_LOAD_FILE

MAIN_LOOP_ERROR:
        jsr     SHOW_ERROR
        bra     MAIN_LOOP

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
        jsr     DUMP_RANGE
        jmp     MAIN_LOOP

DUMP_RANGE:
        ldx     DUMP_ADDR
        jsr     CMP_X_DUMP_END
        bhi     DUMP_RANGE_DONE
DUMP_RANGE_LINE:
        ldx     DUMP_ADDR
        stx     LINE_PTR
        clr     DUMP_COUNT
DUMP_COUNT_LOOP:
        ldx     DUMP_ADDR
        jsr     CMP_X_DUMP_END
        bhi     DUMP_COUNT_DONE
        ldab    DUMP_COUNT
        cmpb    #16
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
        jsr     ACIA_PUTC
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
        bls     DUMP_RANGE_LINE
DUMP_RANGE_DONE:
        rts

PARSE_DUMP_ARGS:
        ldx     #LINE_BUF+1
        stx     ARG_PTR
        ldab    LINE_LEN
        decb
        stab    ARG_LEN
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
        jsr     ACIA_PUTC
        jsr     PRINT_SPACE
        ldx     MOD_ADDR
        ldaa    0,x
        jsr     PRINT_HEX8
        jsr     PRINT_SPACE
        ldaa    #'-'
        jsr     ACIA_PUTC
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

CMD_SDINIT:
        jsr     SD_INIT
        tsta
        beq     CMD_SDINIT_OK
        jmp     MAIN_LOOP_ERROR
CMD_SDINIT_OK:
        ldaa    #'O'
        jsr     MON_OUTEEE
        ldaa    #'K'
        jsr     MON_OUTEEE
        jsr     PRINT_CRLF
        jmp     MAIN_LOOP

CMD_SDREAD:
        ldab    LINE_LEN
        cmpb    #1
        beq     CMD_SDREAD_LBA0
        ldx     #LINE_BUF+1
        decb
        jsr     PARSE_HEX
        bcs     CMD_SDREAD_ERR
        ldaa    HEX_VALUE_HI
        staa    SD_LBA+2
        ldaa    HEX_VALUE_LO
        staa    SD_LBA+3
        clr     SD_LBA
        clr     SD_LBA+1
        bra     CMD_SDREAD_EXEC
CMD_SDREAD_LBA0:
        clr     SD_LBA
        clr     SD_LBA+1
        clr     SD_LBA+2
        clr     SD_LBA+3
CMD_SDREAD_EXEC:
        ldx     #SECTOR_BUF
        stx     SD_BUF_PTR
        jsr     SD_READ_SECTOR
        tsta
        beq     CMD_SDREAD_OK
CMD_SDREAD_ERR:
        jmp     MAIN_LOOP_ERROR
CMD_SDREAD_OK:
        ldx     #SECTOR_BUF
        stx     DUMP_ADDR
        ldaa    #$1B
        staa    DUMP_END
        ldaa    #$FF
        staa    DUMP_END+1
        jsr     DUMP_RANGE
        jmp     MAIN_LOOP

CMD_SDDIR:
        jsr     SD_DIR
        jmp     MAIN_LOOP

CMD_LOAD_FILE:
        ldab    LINE_LEN
        cmpb    #2
        bls     CMD_LOAD_FILE_ERR_NEAR
        subb    #2
        stab    ARG_LEN
        ldx     #LINE_BUF+2
        stx     ARG_PTR
        ldx     #LINE_BUF + LINE_BUF_SIZE - 12
        stx     SD_NAME_PTR
        ldab    #11
CMD_LOAD_FILE_CLR_NAME:
        ldaa    #' '
        staa    0,x
        inx
        decb
        bne     CMD_LOAD_FILE_CLR_NAME
        ldx     ARG_PTR
        ldab    #0
CMD_LOAD_FILE_COPY_NAME:
        ldaa    0,x
        cmpa    #'.'
        beq     CMD_LOAD_FILE_FIND_EXT
        stx     ARG_PTR
        pshb
        ldab    #0
        jsr     SD_GET_NAME_X
        pula
        staa    0,x
        ldx     ARG_PTR
        incb
        cmpb    #8
        bhs     CMD_LOAD_FILE_SKIP_TO_DOT
        inx
        dec     ARG_LEN
        bne     CMD_LOAD_FILE_COPY_NAME
        bra     CMD_LOAD_FILE_OPEN
CMD_LOAD_FILE_ERR_NEAR:
        jmp     CMD_LOAD_FILE_ERR
CMD_LOAD_FILE_SKIP_TO_DOT:
        tst     ARG_LEN
        beq     CMD_LOAD_FILE_OPEN
        ldaa    0,x
        cmpa    #'.'
        beq     CMD_LOAD_FILE_FIND_EXT
        inx
        dec     ARG_LEN
        bne     CMD_LOAD_FILE_SKIP_TO_DOT
        bra     CMD_LOAD_FILE_OPEN
CMD_LOAD_FILE_FIND_EXT:
        inx
        dec     ARG_LEN
        beq     CMD_LOAD_FILE_OPEN
        ldab    #8
CMD_LOAD_FILE_COPY_EXT:
        ldaa    0,x
        stx     ARG_PTR
        pshb
        jsr     SD_GET_NAME_X
        pula
        staa    0,x
        ldx     ARG_PTR
        incb
        cmpb    #11
        bhs     CMD_LOAD_FILE_OPEN
        inx
        dec     ARG_LEN
        bne     CMD_LOAD_FILE_COPY_EXT
CMD_LOAD_FILE_OPEN:
        ldx     SD_NAME_PTR
        jsr     SD_OPEN_FILE
        tsta
        bne     CMD_LOAD_FILE_ERR
        ldaa    #'L'
        jsr     MON_OUTEEE
        ldaa    #'F'
        jsr     MON_OUTEEE
        jsr     PRINT_CRLF
        clr     LOADER_MODE
        clr     LOADER_STAGE
        jmp     CMD_LOAD_LOOP
CMD_LOAD_FILE_ERR:
        jmp     MAIN_LOOP_ERROR

SD_GET_NAME_X:
        ldx     SD_NAME_PTR
        stx     SD_X_SAVE
        ldaa    SD_X_SAVE+1
        aba
        staa    SD_X_SAVE+1
        ldaa    SD_X_SAVE
        adca    #0
        staa    SD_X_SAVE
        ldx     SD_X_SAVE
        rts

MON_GETC:
        tst     SD_LOAD_ACTIVE
        beq     MON_GETC_ACIA
        jsr     SD_GETC
        bcc     MON_GETC_DONE
        clr     SD_LOAD_ACTIVE
MON_GETC_ACIA:
        jsr     ACIA_GETC
MON_GETC_DONE:
        rts

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

CMD_LOAD:
        ldab    LINE_LEN
        cmpb    #1
        bne     CMD_LOAD_BADARG
        ldaa    #'L'
        jsr     MON_OUTEEE
        ldaa    #CHR_CR
        jsr     MON_OUTEEE
        clr     LOADER_MODE
        clr     LOADER_STAGE
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
        jsr     MON_GETC
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
        jsr     ACIA_PUTC
        ldaa    #CHR_SPACE
        jsr     ACIA_PUTC
        ldaa    #CHR_BS
        jsr     ACIA_PUTC
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
        jsr     MON_GETC
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
        jsr     MON_GETC
        cmpa    #CHR_LF
        beq     READ_RECORD_TRAILER_OK
        cmpa    #CHR_CR
        beq     READ_RECORD_TRAILER_OK
        sec
        rts
READ_RECORD_TRAILER_OK:
        clc
        rts

READ_HEXBYTE_INPUT:
        pshb
        jsr     MON_GETC
        jsr     HEX_TO_NIBBLE
        bcs     READ_HEXBYTE_INPUT_FAIL
        lsla
        lsla
        lsla
        lsla
        tab
        jsr     MON_GETC
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
        jsr     MON_GETC
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
        jsr     ACIA_PUTC
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
        jmp     MAIN_LOOP

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
TXT_HELP:       fcc     "D M G L B C R U H F"
                fcb     $04
TXT_BP:         fcc     "BP "
                fcb     $04
TXT_NONE:       fcc     "NONE"
                fcb     $04
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
        include "sdcard.asm"

        org     VEC_IRQ
        fdb     SPURIOUS_IRQ     ; VEC_IRQ
        fdb     SWI_HANDLER      ; VEC_SWI
        fdb     SPURIOUS_IRQ     ; VEC_NMI
        fdb     RESET            ; VEC_RESET
