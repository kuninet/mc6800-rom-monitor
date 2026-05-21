        cpu     6800

        include "../include/hardware.inc"

SDFS_VERSION    equ 1
SDFS_HDR_SIZE   equ 16
SDFS_S1_VERSION equ 1
SDFS_S1_COUNT   equ 6

        if S1_SUPPORTED = 0
        error   "SDFS/68 is not supported for this memory configuration"
        endif

        org     SDFS_LOAD_BASE

SDFS_HEADER:
        fcc     "SDFS68"
        fcb     SDFS_VERSION
        fcb     SDFS_HDR_SIZE
        fdb     SDFS_ENTRY
        fdb     SDFS_END-SDFS_LOAD_BASE
        fcb     0,0,0,0

SDFS_ENTRY:
        jsr     SDFS_CHECK_S1
        bcc     SDFS_START
        ldx     #TXT_S1_ERROR
        jsr     SDFS_PRINT
        swi

SDFS_START:
        ldx     #TXT_BANNER
        jsr     SDFS_PRINT
        jsr     SDFS_API_GET_ERROR
        jsr     SDFS_PRINT_PROMPT

SDFS_LOOP:
        jsr     MIKBUG_INCH
        cmpa    #CHR_LF
        beq     SDFS_LOOP
        cmpa    #CHR_CR
        bne     SDFS_LOOP
        jsr     SDFS_PRINT_PROMPT
        bra     SDFS_LOOP

SDFS_CHECK_S1:
        ldx     #S1_BASE
        ldaa    0,x
        cmpa    #'S'
        bne     SDFS_CHECK_S1_FAIL
        ldaa    1,x
        cmpa    #'1'
        bne     SDFS_CHECK_S1_FAIL
        ldaa    2,x
        cmpa    #'A'
        bne     SDFS_CHECK_S1_FAIL
        ldaa    3,x
        cmpa    #'P'
        bne     SDFS_CHECK_S1_FAIL
        ldaa    4,x
        cmpa    #'I'
        bne     SDFS_CHECK_S1_FAIL
        ldaa    5,x
        cmpa    #'6'
        bne     SDFS_CHECK_S1_FAIL
        ldaa    6,x
        cmpa    #'8'
        bne     SDFS_CHECK_S1_FAIL
        ldaa    7,x
        cmpa    #SDFS_S1_VERSION
        bne     SDFS_CHECK_S1_FAIL
        ldaa    8,x
        cmpa    #SDFS_S1_COUNT
        blo     SDFS_CHECK_S1_FAIL
        clc
        rts
SDFS_CHECK_S1_FAIL:
        sec
        rts

SDFS_API_INIT:
        jsr     S1_BASE+16
        rts

SDFS_API_READ_SECTOR:
        jsr     S1_BASE+19
        rts

SDFS_API_MOUNT:
        jsr     S1_BASE+22
        rts

SDFS_API_FIND_83:
        jsr     S1_BASE+25
        rts

; S1_LOAD_FILE_83 loads to SDFS_LOAD_BASE. Resident SDFS/68 must not call it
; after boot because it would overwrite the running image.
SDFS_API_LOAD_FILE_83:
        jsr     S1_BASE+28
        rts

SDFS_API_GET_ERROR:
        jsr     S1_BASE+31
        rts

SDFS_PRINT_PROMPT:
        ldx     #TXT_PROMPT
        jmp     SDFS_PRINT

SDFS_PRINT:
        ldaa    0,x
        beq     SDFS_PRINT_DONE
        jsr     SDFS_PUTC
        inx
        bra     SDFS_PRINT
SDFS_PRINT_DONE:
        rts

SDFS_PUTC:
        psha
        jsr     MIKBUG_OUTCH
        pula
        cmpa    #CHR_CR
        bne     SDFS_PUTC_DONE
        ldaa    #CHR_LF
        jsr     MIKBUG_OUTCH
SDFS_PUTC_DONE:
        rts

TXT_BANNER:
        fcb     CHR_CR
        fcc     "SDFS/68 V1"
        fcb     CHR_CR,0

TXT_PROMPT:
        fcc     "SDFS> "
        fcb     0

TXT_S1_ERROR:
        fcb     CHR_CR
        fcc     "S1?"
        fcb     CHR_CR,0

SDFS_END:
        if SDFS_END-1 > SDFS_LOAD_LIMIT
        error   "SDFS/68 exceeds SDFS_LOAD_LIMIT"
        endif
