        CPU     6800
; SDFS/68 .COM argument sample.
; Entry ABI: X=argument tail pointer, B=argument tail length, A=0.
;
OUTCH   EQU     $E075

        ORG     $0100
START   STX     ARG_PTR
        STAB    ARG_LEN
        LDX     #MSG
        JSR     PDATA
        LDAB    ARG_LEN
        BEQ     DONE
        LDX     ARG_PTR
ARGLOOP LDAA    0,X
        JSR     OUTCH
        INX
        DECB
        BNE     ARGLOOP
DONE    LDAA    #$0D
        JSR     OUTCH
        LDAA    #$0A
        JSR     OUTCH
        RTS

PDATA   LDAA    0,X
        BEQ     PEND
        JSR     OUTCH
        INX
        BRA     PDATA
PEND    RTS

ARG_PTR FDB     0
ARG_LEN FCB     0
MSG     FCB     $0D,$0A
        FCC     'ARGS '
        FCB     0
        END     START
