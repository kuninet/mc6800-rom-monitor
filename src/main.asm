        cpu     6800

        include "../include/hardware.inc"
        include "../include/mikbug.inc"

        org     ROM_BASE

RESET:
        lds     #STACK_TOP
        clr     DUMP_ADDR
        clr     DUMP_ADDR+1
        jsr     ACIA_INIT
        ldaa    #'*'
        jsr     OUTEEE
        ldaa    #CHR_CR
        jsr     OUTEEE

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
        bne     MAIN_LOOP_ERROR
        jmp     CMD_GO

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

PRINT_PROMPT:
        ldaa    #CHR_PROMPT
        jsr     OUTEEE
        ldaa    #CHR_SPACE
        jsr     OUTEEE
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
        jsr     OUTEEE
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
        jsr     OUTEEE
        rts

SHOW_ERROR:
        ldaa    #CHR_QUESTION
        jsr     OUTEEE
        ldaa    #CHR_CR
        jsr     OUTEEE
        rts

PRINT_SPACE:
        ldaa    #CHR_SPACE
        jsr     OUTEEE
        rts

PRINT_CRLF:
        ldaa    #CHR_CR
        jsr     OUTEEE
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
        fdb     RESET            ; VEC_SWI (Return to monitor via SWI)
        fdb     SPURIOUS_IRQ     ; VEC_NMI
        fdb     RESET            ; VEC_RESET
