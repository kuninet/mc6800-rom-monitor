ACIA_INIT:
        ldaa    #ACIA_CTRL_RESET
        staa    ACIA_CTRL
        ldaa    #ACIA_CTRL_INIT
        staa    ACIA_CTRL
        rts

ACIA_WAIT_TX:
        ldaa    ACIA_CTRL
        bita    #ACIA_STAT_TDRE
        beq     ACIA_WAIT_TX
        rts

ACIA_WAIT_RX:
        ldaa    ACIA_CTRL
        bita    #ACIA_STAT_RDRF
        beq     ACIA_WAIT_RX
        rts

ACIA_PUTC:
        psha
        bsr     ACIA_WAIT_TX
        pula
        staa    ACIA_DATA
        rts

ACIA_GETC:
        bsr     ACIA_WAIT_RX
        ldaa    ACIA_DATA
        rts

MIKBUG_OUTEEE_IMPL:
        jsr     ACIA_PUTC
        rts

MON_OUTEEE:
        psha
        jsr     ACIA_PUTC
        pula
        cmpa    #CHR_CR
        bne     MON_OUTEEE_DONE
        psha
        ldaa    #CHR_LF
        jsr     ACIA_PUTC
        pula
MON_OUTEEE_DONE:
        rts

MIKBUG_INEEE_IMPL:
MIKBUG_INEEE_LOOP:
        jsr     ACIA_GETC
        cmpa    #CHR_LF
        beq     MIKBUG_INEEE_LOOP
        jsr     MIKBUG_OUTEEE_IMPL
        rts
