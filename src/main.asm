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
        jsr     ECHO_LINE
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

ECHO_LINE:
        ldaa    #CHR_ECHO
        jsr     OUTEEE
        ldaa    #CHR_SPACE
        jsr     OUTEEE

        ldab    LINE_LEN
        ldx     #LINE_BUF

ECHO_LINE_LOOP:
        cmpb    #0
        beq     ECHO_LINE_DONE
        ldaa    0,x
        jsr     OUTEEE
        inx
        decb
        bra     ECHO_LINE_LOOP

ECHO_LINE_DONE:
        ldaa    #CHR_CR
        jsr     OUTEEE
        rts

SPURIOUS_IRQ:
        rti

        include "acia6850.asm"

        org     VEC_IRQ
        fdb     SPURIOUS_IRQ
        fdb     SPURIOUS_IRQ
        fdb     SPURIOUS_IRQ
        fdb     RESET
