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
        bsr     ACIA_WAIT_TX
        staa    ACIA_DATA
        rts

ACIA_GETC:
        bsr     ACIA_WAIT_RX
        ldaa    ACIA_DATA
        rts

OUTEEE:
        psha
        jsr     ACIA_PUTC
        pula
        cmpa    #CHR_CR
        bne     OUTEEE_DONE
        ldaa    #CHR_LF
        jsr     ACIA_PUTC
OUTEEE_DONE:
        rts

INEEE:
        jsr     ACIA_GETC
        cmpa    #CHR_LF
        beq     INEEE
        jsr     OUTEEE
        rts
