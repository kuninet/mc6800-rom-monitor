        CPU     6800
; 2ND ACIA KEY TEST PROGRAM
;
OUTCH   EQU     $E075
ACIA2CS EQU     $8094
ACIA2DA EQU     $8095
        ORG     $0200
START   LDAA    #$03
        STAA    ACIA2CS
        LDAA    #$15
        STAA    ACIA2CS
        LDX     #WAITMSG
        JSR     PDATA
WAIT    LDAA    ACIA2CS
        BITA    #$01
        BEQ     WAIT
        LDAA    ACIA2DA
        PSHA
        LDX     #KEYMSG
        JSR     PDATA
        PULA
        PSHA
        JSR     PHEX
        LDAA    #$20
        JSR     OUTCH
        PULA
        ANDA    #$7F
        CMPA    #$20
        BLO     DOT
        CMPA    #$7F
        BHS     DOT
        BRA     PRINT
DOT     LDAA    #'.'
PRINT   JSR     OUTCH
        LDAA    #$0D
        JSR     OUTCH
        LDAA    #$0A
        JSR     OUTCH
        SWI
PHEX    PSHA
        LSRA
        LSRA
        LSRA
        LSRA
        JSR     PNIB
        PULA
        JSR     PNIB
        RTS
PNIB    ANDA    #$0F
        CMPA    #10
        BHS     PNIBAF
        ADDA    #'0'
        BRA     PNIBOUT
PNIBAF  ADDA    #'A'-10
PNIBOUT JSR     OUTCH
        RTS
PDATA   LDAA    0,X
        BEQ     PEND
        JSR     OUTCH
        INX
        BRA     PDATA
PEND    RTS
WAITMSG FCB     $0D,$0A
        FCC     'KEY WAIT'
        FCB     $0D,$0A,0
KEYMSG  FCC     'KEY '
        FCB     0
        END     START
