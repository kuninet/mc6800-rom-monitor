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
        bne     MAIN_LOOP_ERROR
        jmp     CMD_LOAD

MAIN_LOOP_ERROR:
        jsr     SHOW_ERROR
        bra     MAIN_LOOP

CMD_DUMP:
        ldab    LINE_LEN
        cmpb    #1
        beq     CMD_DUMP_NOARG
        ldx     #LINE_BUF+1
        decb
        jsr     PARSE_HEX
        bcc     CMD_DUMP_ADDR_OK
        jmp     MAIN_LOOP_ERROR
CMD_DUMP_ADDR_OK:
        ldx     HEX_VALUE_HI
        stx     DUMP_ADDR
CMD_DUMP_NOARG:
        ldx     DUMP_ADDR
        jsr     PRINT_HEX16
        jsr     PRINT_SPACE
        
        ldab    #16
CMD_DUMP_HEX_LOOP:
        ldaa    0,x
        jsr     PRINT_HEX8
        jsr     PRINT_SPACE
        inx
        decb
        bne     CMD_DUMP_HEX_LOOP
        
        jsr     PRINT_SPACE
        
        ldx     DUMP_ADDR
        ldab    #16
CMD_DUMP_ASCII_LOOP:
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
        bne     CMD_DUMP_ASCII_LOOP
        
        stx     DUMP_ADDR
        jsr     PRINT_CRLF
        jmp     MAIN_LOOP

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
        fdb     MONITOR_ENTRY    ; VEC_SWI
        fdb     SPURIOUS_IRQ     ; VEC_NMI
        fdb     RESET            ; VEC_RESET
