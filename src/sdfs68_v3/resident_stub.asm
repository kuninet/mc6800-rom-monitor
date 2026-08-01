        cpu     6800

        include "hardware.inc"

SDFS3_API_MAJOR    equ 1
SDFS3_API_MINOR    equ 0
SDFS3_API_COUNT    equ 7
SDFS3_API_HDR_SIZE equ $18
SDFS3_FLAG_NONE    equ 0
SDFS3_ERR_NONE     equ 0
SDFS3_ERR_NOT_IMPL equ 1

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

SDFS3_GET_INFO:
        ldaa    #SDFS3_API_MAJOR
        ldab    #SDFS3_FLAG_NONE
        ldx     #SDFS3_API_HEADER
        clc
        rts

SDFS3_CMD_DISPATCH:
        jmp     SDFS3_NOT_IMPLEMENTED

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
        staa    SDFS3_LAST_ERROR
        sec
        rts

SDFS3_GET_ERROR:
        ldaa    SDFS3_LAST_ERROR
        clc
        rts

SDFS3_LAST_ERROR:
        fcb     SDFS3_ERR_NONE

SDFS3_END:
        end
