        cpu     6800

        include "hardware.inc"

SDFS3_API_MAJOR    equ 1
SDFS3_API_MINOR    equ 0
SDFS3_API_COUNT    equ 9
SDFS3_API_HDR_SIZE equ $18
SDFS3_FLAG_NONE    equ 0
SDFS3_CAPS_NONE    equ 0
SDFS3_ERR_NONE     equ 0
SDFS3_ERR_NOT_IMPL equ 1
SDFS3_ERR_BAD_CMD  equ 2
SDFS3_ERR_DIR_IMPL equ $11
SDFS3_ERR_TYPE_IMPL equ $12
SDFS3_ERR_LOAD_IMPL equ $13
SDFS3_ERR_RUN_IMPL equ $14
SDFS3_ERR_COM_IMPL equ $15

        if S1_SUPPORTED = 0
        error   "SDFS/68 v3 resident is not supported for this memory configuration"
        endif

        org     SDFS_LOAD_BASE

SDFS3_API_HEADER:
        fcc     "SDFS3API"
        fcb     SDFS3_API_MAJOR
        fcb     SDFS3_API_MINOR
        fcb     SDFS3_API_COUNT
        fcb     SDFS3_FLAG_NONE
        fdb     SDFS3_JUMP_TABLE
        fdb     SDFS_LOAD_BASE
        fdb     SDFS3_END-1
        fdb     USER_RAM_END
        fdb     0
        fdb     0

SDFS3_JUMP_TABLE:
        fdb     SDFS3_GET_INFO
        fdb     SDFS3_CMD_DISPATCH
        fdb     SDFS3_LOAD_PATH
        fdb     SDFS3_READ_STREAM_OPEN
        fdb     SDFS3_READ_STREAM_GETC
        fdb     SDFS3_READ_STREAM_CLOSE
        fdb     SDFS3_GET_ERROR
        fdb     SDFS3_GET_MEMTOP
        fdb     SDFS3_GET_CAPS

SDFS3_GET_INFO:
        ldaa    #SDFS3_API_MAJOR
        ldab    #SDFS3_FLAG_NONE
        ldx     #SDFS3_API_HEADER
        clc
        rts

SDFS3_CMD_DISPATCH:
        stx     SDFS3_PARSE_PTR
        stab    SDFS3_PARSE_LEN
SDFS3_CMD_SKIP_SPACE:
        tst     SDFS3_PARSE_LEN
        beq     SDFS3_BAD_COMMAND
        ldx     SDFS3_PARSE_PTR
        ldaa    0,x
        cmpa    #CHR_SPACE
        bne     SDFS3_CMD_TOKEN_START
        inx
        stx     SDFS3_PARSE_PTR
        dec     SDFS3_PARSE_LEN
        bra     SDFS3_CMD_SKIP_SPACE
SDFS3_CMD_TOKEN_START:
        stx     SDFS3_TOKEN_PTR
        clr     SDFS3_TOKEN_LEN
SDFS3_CMD_TOKEN_SCAN:
        tst     SDFS3_PARSE_LEN
        beq     SDFS3_CMD_TOKEN_DONE
        ldx     SDFS3_PARSE_PTR
        ldaa    0,x
        cmpa    #CHR_SPACE
        beq     SDFS3_CMD_TOKEN_DONE
        inc     SDFS3_TOKEN_LEN
        inx
        stx     SDFS3_PARSE_PTR
        dec     SDFS3_PARSE_LEN
        bra     SDFS3_CMD_TOKEN_SCAN
SDFS3_CMD_TOKEN_DONE:
        ldaa    SDFS3_TOKEN_LEN
        beq     SDFS3_BAD_COMMAND
        cmpa    #3
        bne     SDFS3_CMD_CHECK_4
        jsr     SDFS3_IS_DIR
        bcc     SDFS3_CMD_DIR_STUB
        jsr     SDFS3_IS_RUN
        bcc     SDFS3_CMD_RUN_STUB
        bra     SDFS3_CMD_CHECK_COM
SDFS3_CMD_CHECK_4:
        cmpa    #4
        bne     SDFS3_CMD_CHECK_COM
        jsr     SDFS3_IS_TYPE
        bcc     SDFS3_CMD_TYPE_STUB
        jsr     SDFS3_IS_LOAD
        bcc     SDFS3_CMD_LOAD_STUB
SDFS3_CMD_CHECK_COM:
        jsr     SDFS3_IS_COM_TOKEN
        bcc     SDFS3_CMD_COM_STUB
        bra     SDFS3_BAD_COMMAND

SDFS3_CMD_DIR_STUB:
        ldaa    #SDFS3_ERR_DIR_IMPL
        bra     SDFS3_NOT_IMPLEMENTED_A
SDFS3_CMD_TYPE_STUB:
        ldaa    #SDFS3_ERR_TYPE_IMPL
        bra     SDFS3_NOT_IMPLEMENTED_A
SDFS3_CMD_LOAD_STUB:
        ldaa    #SDFS3_ERR_LOAD_IMPL
        bra     SDFS3_NOT_IMPLEMENTED_A
SDFS3_CMD_RUN_STUB:
        ldaa    #SDFS3_ERR_RUN_IMPL
        bra     SDFS3_NOT_IMPLEMENTED_A
SDFS3_CMD_COM_STUB:
        ldaa    #SDFS3_ERR_COM_IMPL
        bra     SDFS3_NOT_IMPLEMENTED_A
SDFS3_BAD_COMMAND:
        ldaa    #SDFS3_ERR_BAD_CMD
        staa    SDFS3_LAST_ERROR
        sec
        rts

SDFS3_LOAD_PATH:
        jmp     SDFS3_NOT_IMPLEMENTED

SDFS3_READ_STREAM_OPEN:
        jmp     SDFS3_NOT_IMPLEMENTED

SDFS3_READ_STREAM_GETC:
        jmp     SDFS3_NOT_IMPLEMENTED

SDFS3_READ_STREAM_CLOSE:
        jmp     SDFS3_NOT_IMPLEMENTED

SDFS3_NOT_IMPLEMENTED:
        ldaa    #SDFS3_ERR_NOT_IMPL
SDFS3_NOT_IMPLEMENTED_A:
        staa    SDFS3_LAST_ERROR
        sec
        rts

SDFS3_GET_ERROR:
        ldaa    SDFS3_LAST_ERROR
        clc
        rts

SDFS3_GET_MEMTOP:
        ldx     #USER_RAM_END
        clc
        rts

SDFS3_GET_CAPS:
        ldaa    #SDFS3_CAPS_NONE
        ldab    #SDFS3_CAPS_NONE
        ldx     #SDFS3_API_HEADER
        clc
        rts

SDFS3_IS_DIR:
        ldx     SDFS3_TOKEN_PTR
        ldaa    0,x
        jsr     SDFS3_TO_UPPER
        cmpa    #'D'
        bne     SDFS3_IS_DIR_FAIL
        ldaa    1,x
        jsr     SDFS3_TO_UPPER
        cmpa    #'I'
        bne     SDFS3_IS_DIR_FAIL
        ldaa    2,x
        jsr     SDFS3_TO_UPPER
        cmpa    #'R'
        bne     SDFS3_IS_DIR_FAIL
        clc
        rts
SDFS3_IS_DIR_FAIL:
        sec
        rts

SDFS3_IS_RUN:
        ldx     SDFS3_TOKEN_PTR
        ldaa    0,x
        jsr     SDFS3_TO_UPPER
        cmpa    #'R'
        bne     SDFS3_IS_RUN_FAIL
        ldaa    1,x
        jsr     SDFS3_TO_UPPER
        cmpa    #'U'
        bne     SDFS3_IS_RUN_FAIL
        ldaa    2,x
        jsr     SDFS3_TO_UPPER
        cmpa    #'N'
        bne     SDFS3_IS_RUN_FAIL
        clc
        rts
SDFS3_IS_RUN_FAIL:
        sec
        rts

SDFS3_IS_TYPE:
        ldx     SDFS3_TOKEN_PTR
        ldaa    0,x
        jsr     SDFS3_TO_UPPER
        cmpa    #'T'
        bne     SDFS3_IS_TYPE_FAIL
        ldaa    1,x
        jsr     SDFS3_TO_UPPER
        cmpa    #'Y'
        bne     SDFS3_IS_TYPE_FAIL
        ldaa    2,x
        jsr     SDFS3_TO_UPPER
        cmpa    #'P'
        bne     SDFS3_IS_TYPE_FAIL
        ldaa    3,x
        jsr     SDFS3_TO_UPPER
        cmpa    #'E'
        bne     SDFS3_IS_TYPE_FAIL
        clc
        rts
SDFS3_IS_TYPE_FAIL:
        sec
        rts

SDFS3_IS_LOAD:
        ldx     SDFS3_TOKEN_PTR
        ldaa    0,x
        jsr     SDFS3_TO_UPPER
        cmpa    #'L'
        bne     SDFS3_IS_LOAD_FAIL
        ldaa    1,x
        jsr     SDFS3_TO_UPPER
        cmpa    #'O'
        bne     SDFS3_IS_LOAD_FAIL
        ldaa    2,x
        jsr     SDFS3_TO_UPPER
        cmpa    #'A'
        bne     SDFS3_IS_LOAD_FAIL
        ldaa    3,x
        jsr     SDFS3_TO_UPPER
        cmpa    #'D'
        bne     SDFS3_IS_LOAD_FAIL
        clc
        rts
SDFS3_IS_LOAD_FAIL:
        sec
        rts

SDFS3_IS_COM_TOKEN:
        ldaa    SDFS3_TOKEN_LEN
        cmpa    #5
        blo     SDFS3_IS_COM_FAIL
        suba    #4
        tab
        ldx     SDFS3_TOKEN_PTR
SDFS3_COM_EXT_PTR_LOOP:
        tstb
        beq     SDFS3_COM_EXT_PTR_DONE
        inx
        decb
        bra     SDFS3_COM_EXT_PTR_LOOP
SDFS3_COM_EXT_PTR_DONE:
        ldaa    0,x
        cmpa    #'.'
        bne     SDFS3_IS_COM_FAIL
        ldaa    1,x
        jsr     SDFS3_TO_UPPER
        cmpa    #'C'
        bne     SDFS3_IS_COM_FAIL
        ldaa    2,x
        jsr     SDFS3_TO_UPPER
        cmpa    #'O'
        bne     SDFS3_IS_COM_FAIL
        ldaa    3,x
        jsr     SDFS3_TO_UPPER
        cmpa    #'M'
        bne     SDFS3_IS_COM_FAIL
        clc
        rts
SDFS3_IS_COM_FAIL:
        sec
        rts

SDFS3_TO_UPPER:
        cmpa    #'a'
        blo     SDFS3_TO_UPPER_DONE
        cmpa    #'z'
        bhi     SDFS3_TO_UPPER_DONE
        suba    #$20
SDFS3_TO_UPPER_DONE:
        rts

SDFS3_LAST_ERROR:
        fcb     SDFS3_ERR_NONE
SDFS3_PARSE_PTR:
        fdb     0
SDFS3_PARSE_LEN:
        fcb     0
SDFS3_TOKEN_PTR:
        fdb     0
SDFS3_TOKEN_LEN:
        fcb     0

SDFS3_END:
        end
