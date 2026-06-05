        CPU     6800
; SDFS/68 S-Record sample.
; Load with RUN HELLO.S. SWI returns to the ROM monitor.
;
OUTCH   EQU     $E075

        ORG     $0200
START   LDX     #MSG
        JSR     PDATA
        SWI

PDATA   LDAA    0,X
        BEQ     PEND
        JSR     OUTCH
        INX
        BRA     PDATA
PEND    RTS

MSG     FCB     $0D,$0A
        FCC     'HELLO SREC'
        FCB     $0D,$0A,0
        END     START
