        cpu     6800

        include "../include/hardware.inc"
        include "../include/mikbug.inc"

        org     ROM_BASE

RESET:
        lds     #STACK_TOP
        jsr     ACIA_INIT
        ldaa    #'*'
        jsr     OUTEEE

MAIN_LOOP:
        jsr     INEEE
        bra     MAIN_LOOP

SPURIOUS_IRQ:
        rti

        include "acia6850.asm"

        org     VEC_IRQ
        fdb     SPURIOUS_IRQ
        fdb     SPURIOUS_IRQ
        fdb     SPURIOUS_IRQ
        fdb     RESET
