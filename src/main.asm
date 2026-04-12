        cpu     6800

        include "../include/hardware.inc"
        include "../include/mikbug.inc"

        org     ROM_BASE

RESET:
        lds     #STACK_TOP
        jsr     ACIA_INIT
        ldaa    #'*'
        jsr     OUTEEE
        ldaa    #CHR_CR
        jsr     OUTEEE

MAIN_LOOP:
        jsr     PRINT_PROMPT
        jsr     READ_LINE
        jsr     PARSE_HEX_LINE
        bcs     MAIN_LOOP_ERROR
        bra     MAIN_LOOP

MAIN_LOOP_ERROR:
        jsr     SHOW_ERROR
        bra     MAIN_LOOP

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

PARSE_HEX_LINE:
        ldab    LINE_LEN
        beq     PARSE_HEX_FAIL
        cmpb    #5
        bhs     PARSE_HEX_FAIL

        clr     HEX_VALUE_HI
        clr     HEX_VALUE_LO
        ldx     #LINE_BUF

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
        fdb     SPURIOUS_IRQ
        fdb     SPURIOUS_IRQ
        fdb     SPURIOUS_IRQ
        fdb     RESET
