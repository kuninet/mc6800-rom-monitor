        CPU     6800
; K68-VDG TEST PROGRAM FOR VRAM C000
;
VDGCTL  EQU     $8110
VRAM    EQU     $C000
VEND    EQU     $C1FF
        ORG     $0200
START   LDAA    #$00
        STAA    VDGCTL
        LDX     #VRAM
        STX     CUR
CLRLP   LDAA    #$60
        STAA    0,X
        CPX     #VEND
        BEQ     CLRDONE
        INX
        STX     CUR
        BRA     CLRLP
CLRDONE LDX     #VRAM
        STX     CUR
        LDX     #MESG
        STX     PTR
WRLP    LDX     PTR
        LDAA    0,X
        CMPA    #$04
        BEQ     DONE
        INX
        STX     PTR
        LDX     CUR
        STAA    0,X
        INX
        STX     CUR
        BRA     WRLP
DONE    SWI
CUR     FDB     0
PTR     FDB     0
MESG    FCC     'K68'
        FCB     $2D
        FCC     'VDG'
        FCB     $60
        FCC     'C'
        FCB     $70,$70,$70
        FCB     $04
        END     START
