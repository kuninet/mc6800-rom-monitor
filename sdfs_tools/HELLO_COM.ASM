        CPU     6800
; SDFS/68 .COM sample.
; Load address and entry are both $0100. RTS returns to SDFS/68.
;
OUTCH   EQU     $E075

        ORG     $0100
START   LDX     #MSG
        JSR     PDATA
        RTS

PDATA   LDAA    0,X
        BEQ     PEND
        JSR     OUTCH
        INX
        BRA     PDATA
PEND    RTS

MSG     FCB     $0D,$0A
        FCC     'HELLO COM'
        FCB     $0D,$0A,0
        END     START
