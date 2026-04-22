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
        jmp     MAIN_LOOP

RESET:
        lds     #STACK_TOP
        clr     DUMP_ADDR
        clr     DUMP_ADDR+1
        clr     BP_ACTIVE
        clr     BRK_ACTIVE
        jsr     ACIA_INIT
        ldaa    #'*'
        jsr     MON_OUTEEE
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
        jmp     CMD_DUMP
CHK_CMD_MOD:
        cmpa    #'M'
        bne     CHK_CMD_GO
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
        jmp     CMD_BREAK_SET
CHK_CMD_RESUME:
        cmpa    #'R'
        bne     CHK_CMD_CLEAR
        jmp     CMD_RESUME
CHK_CMD_CLEAR:
        cmpa    #'C'
        bne     CHK_CMD_UNASM
        jmp     CMD_BREAK_CLEAR
CHK_CMD_UNASM:
        cmpa    #'U'
        bne     MAIN_LOOP_ERROR
        jmp     CMD_UNASM

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
        beq     CMD_BREAK_SET_ERR
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
        jsr     READ_RECORD
        bcs     CMD_LOAD_ERROR

        ldab    LINE_LEN
        beq     CMD_LOAD_LOOP

        jsr     PARSE_LOADER_RECORD
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
        jsr     ACIA_GETC
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

READ_RECORD:
        ldx     #LINE_BUF
        stx     LINE_PTR
        clr     LINE_LEN

READ_RECORD_LOOP:
        jsr     ACIA_GETC
        cmpa    #CHR_LF
        beq     READ_RECORD_LF
        cmpa    #CHR_CR
        beq     READ_RECORD_DONE
        cmpa    #CHR_SPACE
        blo     READ_RECORD_LOOP

        ldab    LINE_LEN
        cmpb    #LINE_BUF_SIZE
        bhs     READ_RECORD_FAIL

        ldx     LINE_PTR
        staa    0,x
        inx
        stx     LINE_PTR
        inc     LINE_LEN
        bra     READ_RECORD_LOOP

READ_RECORD_LF:
        tst     LINE_LEN
        beq     READ_RECORD_LOOP
        bra     READ_RECORD_DONE

READ_RECORD_DONE:
        clc
        rts

READ_RECORD_FAIL:
        jsr     ACIA_GETC
        cmpa    #CHR_LF
        beq     READ_RECORD_FAIL_DONE
        cmpa    #CHR_CR
        bne     READ_RECORD_FAIL
READ_RECORD_FAIL_DONE:
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

PARSE_HEXBYTE_PTR:
        pshb
        ldaa    0,x
        jsr     HEX_TO_NIBBLE
        bcs     PARSE_HEXBYTE_PTR_FAIL
        lsla
        lsla
        lsla
        lsla
        tab
        inx
        ldaa    0,x
        jsr     HEX_TO_NIBBLE
        bcs     PARSE_HEXBYTE_PTR_FAIL
        aba
        inx
        pulb
        clc
        rts

PARSE_HEXBYTE_PTR_FAIL:
        pulb
        sec
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

PARSE_LOADER_RECORD:
        ldaa    LOADER_MODE
        bne     PARSE_LOADER_RECORD_MODE_SET

        ldaa    LINE_BUF
        cmpa    #'S'
        beq     PARSE_LOADER_RECORD_SET_SREC
        cmpa    #':'
        beq     PARSE_LOADER_RECORD_SET_IHEX
        sec
        rts

PARSE_LOADER_RECORD_SET_SREC:
        ldaa    #LOAD_MODE_SREC
        staa    LOADER_MODE
        bra     PARSE_LOADER_RECORD_MODE_SET

PARSE_LOADER_RECORD_SET_IHEX:
        ldaa    #LOAD_MODE_IHEX
        staa    LOADER_MODE

PARSE_LOADER_RECORD_MODE_SET:
        ldaa    LOADER_MODE
        cmpa    #LOAD_MODE_SREC
        beq     PARSE_SREC_RECORD
        cmpa    #LOAD_MODE_IHEX
        bne     PARSE_LOADER_RECORD_BADMODE
        jmp     PARSE_IHEX_RECORD
        sec
        rts

PARSE_LOADER_RECORD_BADMODE:
        sec
        rts

PARSE_SREC_RECORD:
        ldaa    #1
        staa    LOADER_STAGE
        ldaa    LINE_BUF
        cmpa    #'S'
        bne     PARSE_SREC_RECORD_FAIL_NEAR

        ldaa    LINE_BUF+1
        staa    LOADER_TYPE
        cmpa    #'0'
        beq     PARSE_SREC_RECORD_TYPE_OK
        cmpa    #'1'
        beq     PARSE_SREC_RECORD_TYPE_OK
        cmpa    #'2'
        beq     PARSE_SREC_RECORD_TYPE_OK
        cmpa    #'5'
        beq     PARSE_SREC_RECORD_TYPE_OK
        cmpa    #'8'
        beq     PARSE_SREC_RECORD_TYPE_OK
        cmpa    #'9'
        beq     PARSE_SREC_RECORD_TYPE_OK
        bra     PARSE_SREC_RECORD_FAIL_NEAR

PARSE_SREC_RECORD_FAIL_NEAR:
        jmp     PARSE_SREC_RECORD_FAIL

PARSE_SREC_RECORD_TYPE_OK:
        ldaa    #2
        staa    LOADER_STAGE
        ldx     #LINE_BUF+2
        jsr     PARSE_HEXBYTE_PTR
        bcs     PARSE_SREC_RECORD_FAIL_NEAR
        staa    LOADER_COUNT
        staa    LOADER_SUM
        asla
        adda    #4
        cmpa    LINE_LEN
        bne     PARSE_SREC_RECORD_FAIL_NEAR

        ldaa    LOADER_TYPE
        cmpa    #'2'
        beq     PARSE_SREC_ADDR24
        cmpa    #'8'
        beq     PARSE_SREC_ADDR24

        ldaa    #3
        staa    LOADER_STAGE
        ldaa    LOADER_COUNT
        cmpa    #3
        blo     PARSE_SREC_RECORD_FAIL_NEAR

        jsr     PARSE_HEXBYTE_PTR
        bcs     PARSE_SREC_RECORD_FAIL_MID
        staa    LOADER_ADDR
        jsr     ADD_TO_LOADER_SUM

        jsr     PARSE_HEXBYTE_PTR
        bcs     PARSE_SREC_RECORD_FAIL_MID
        staa    LOADER_ADDR+1
        jsr     ADD_TO_LOADER_SUM

        ldab    LOADER_COUNT
        subb    #3
        bra     PARSE_SREC_DATA_LOOP

PARSE_SREC_RECORD_FAIL_MID:
        jmp     PARSE_SREC_RECORD_FAIL

PARSE_SREC_ADDR24:
        ldaa    #3
        staa    LOADER_STAGE
        ldaa    LOADER_COUNT
        cmpa    #4
        blo     PARSE_SREC_RECORD_FAIL_MID

        jsr     PARSE_HEXBYTE_PTR
        bcs     PARSE_SREC_RECORD_FAIL_MID
        staa    HEX_NIBBLE
        jsr     ADD_TO_LOADER_SUM
        ldaa    HEX_NIBBLE
        cmpa    #0
        bne     PARSE_SREC_RECORD_FAIL

        jsr     PARSE_HEXBYTE_PTR
        bcs     PARSE_SREC_RECORD_FAIL
        staa    LOADER_ADDR
        jsr     ADD_TO_LOADER_SUM

        jsr     PARSE_HEXBYTE_PTR
        bcs     PARSE_SREC_RECORD_FAIL
        staa    LOADER_ADDR+1
        jsr     ADD_TO_LOADER_SUM

        ldab    LOADER_COUNT
        subb    #4

PARSE_SREC_DATA_LOOP:
        ldaa    #4
        staa    LOADER_STAGE
        tstb
        beq     PARSE_SREC_CHECKSUM
        jsr     PARSE_HEXBYTE_PTR
        bcs     PARSE_SREC_RECORD_FAIL
        staa    HEX_NIBBLE
        jsr     ADD_TO_LOADER_SUM
        ldaa    LOADER_TYPE
        cmpa    #'1'
        beq     PARSE_SREC_STORE
        cmpa    #'2'
        bne     PARSE_SREC_SKIP_STORE
PARSE_SREC_STORE:
        ldaa    HEX_NIBBLE
        pshb
        stx     LOADER_PARSE_PTR
        ldx     LOADER_ADDR
        staa    0,x
        inx
        stx     LOADER_ADDR
        ldx     LOADER_PARSE_PTR
        pulb
PARSE_SREC_SKIP_STORE:
        decb
        bra     PARSE_SREC_DATA_LOOP

PARSE_SREC_CHECKSUM:
        ldaa    #5
        staa    LOADER_STAGE
        jsr     PARSE_HEXBYTE_PTR
        bcs     PARSE_SREC_RECORD_FAIL
        jsr     ADD_TO_LOADER_SUM
        cmpa    #$FF
        bne     PARSE_SREC_RECORD_FAIL

        ldaa    LOADER_TYPE
        cmpa    #'8'
        beq     PARSE_SREC_RECORD_EOF
        cmpa    #'9'
        bne     PARSE_SREC_RECORD_CONT
PARSE_SREC_RECORD_EOF:
        jmp     PARSE_LOADER_RECORD_EOF
PARSE_SREC_RECORD_CONT:
        ldaa    #0
        clc
        rts

PARSE_SREC_RECORD_FAIL:
        jmp     PARSE_LOADER_RECORD_FAIL

PARSE_IHEX_RECORD:
        ldaa    #1
        staa    LOADER_STAGE
        ldaa    LINE_BUF
        cmpa    #':'
        bne     PARSE_IHEX_RECORD_FAIL_HEAD

        ldaa    #2
        staa    LOADER_STAGE
        ldx     #LINE_BUF+1
        jsr     PARSE_HEXBYTE_PTR
        bcs     PARSE_IHEX_RECORD_FAIL_HEAD
        staa    LOADER_COUNT
        staa    LOADER_SUM
        asla
        adda    #11
        cmpa    LINE_LEN
        bne     PARSE_IHEX_RECORD_FAIL_HEAD
        bra     PARSE_IHEX_RECORD_HEAD_OK

PARSE_IHEX_RECORD_FAIL_HEAD:
        jmp     PARSE_IHEX_RECORD_FAIL

PARSE_IHEX_RECORD_HEAD_OK:

        jsr     PARSE_HEXBYTE_PTR
        bcs     PARSE_IHEX_RECORD_FAIL
        staa    LOADER_ADDR
        jsr     ADD_TO_LOADER_SUM

        jsr     PARSE_HEXBYTE_PTR
        bcs     PARSE_IHEX_RECORD_FAIL
        staa    LOADER_ADDR+1
        jsr     ADD_TO_LOADER_SUM

        jsr     PARSE_HEXBYTE_PTR
        bcs     PARSE_IHEX_RECORD_FAIL
        staa    LOADER_TYPE
        jsr     ADD_TO_LOADER_SUM

        ldaa    #3
        staa    LOADER_STAGE
        ldaa    LOADER_TYPE
        cmpa    #$00
        beq     PARSE_IHEX_DATA
        cmpa    #$01
        beq     PARSE_IHEX_EOF
        bra     PARSE_IHEX_RECORD_FAIL

PARSE_IHEX_DATA:
        ldab    LOADER_COUNT

PARSE_IHEX_DATA_LOOP:
        ldaa    #4
        staa    LOADER_STAGE
        tstb
        beq     PARSE_IHEX_CHECKSUM
        jsr     PARSE_HEXBYTE_PTR
        bcs     PARSE_IHEX_RECORD_FAIL
        psha
        jsr     ADD_TO_LOADER_SUM
        pula
        pshb
        stx     LOADER_PARSE_PTR
        ldx     LOADER_ADDR
        staa    0,x
        inx
        stx     LOADER_ADDR
        ldx     LOADER_PARSE_PTR
        pulb
        decb
        bra     PARSE_IHEX_DATA_LOOP

PARSE_IHEX_EOF:
        ldab    LOADER_COUNT
        bne     PARSE_IHEX_RECORD_FAIL

PARSE_IHEX_CHECKSUM:
        ldaa    #5
        staa    LOADER_STAGE
        jsr     PARSE_HEXBYTE_PTR
        bcs     PARSE_IHEX_RECORD_FAIL
        jsr     ADD_TO_LOADER_SUM
        cmpa    #$00
        bne     PARSE_IHEX_RECORD_FAIL

        ldaa    LOADER_TYPE
        cmpa    #$01
        bne     PARSE_IHEX_RECORD_CONT
        jmp     PARSE_LOADER_RECORD_EOF
PARSE_IHEX_RECORD_CONT:
        ldaa    #0
        clc
        rts

PARSE_IHEX_RECORD_FAIL:
        jmp     PARSE_LOADER_RECORD_FAIL

PARSE_LOADER_RECORD_EOF:
        ldaa    #1
        clc
        rts

PARSE_LOADER_RECORD_FAIL:
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

        org     VEC_IRQ
        fdb     SPURIOUS_IRQ     ; VEC_IRQ
        fdb     SWI_HANDLER      ; VEC_SWI
        fdb     SPURIOUS_IRQ     ; VEC_NMI
        fdb     RESET            ; VEC_RESET
