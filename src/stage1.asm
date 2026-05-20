        cpu     6800

        include "../include/hardware.inc"

S1_API_VERSION  equ 1
S1_API_COUNT    equ 6
S1_FLAG_NONE    equ 0
S1_ERR_NONE     equ 0
S1_ERR_UNIMPL   equ 1

SDFS_VERSION    equ 1
SDFS_HDR_SIZE   equ 16

        if S1_SUPPORTED = 0
        error   "stage1 is not supported for this memory configuration"
        endif

        org     S1_BASE

S1_HEADER:
        fcc     "S1API68"
        fcb     S1_API_VERSION
        fcb     S1_API_COUNT
        fcb     S1_FLAG_NONE
        fcb     0,0,0,0,0,0

S1_JUMP_TABLE:
        jmp     S1_INIT
        jmp     S1_READ_SECTOR
        jmp     S1_MOUNT
        jmp     S1_FIND_83
        jmp     S1_LOAD_FILE_83
        jmp     S1_GET_ERROR

S1_INIT:
        jmp     SD_INIT

S1_READ_SECTOR:
        jmp     SD_READ_SECTOR

S1_MOUNT:
        ldaa    #S1_ERR_UNIMPL
        sec
        rts

S1_FIND_83:
        ldaa    #S1_ERR_UNIMPL
        sec
        rts

S1_LOAD_FILE_83:
        ldaa    #S1_ERR_UNIMPL
        sec
        rts

S1_GET_ERROR:
        ldaa    SD_ERROR
        clc
        rts

        include "sdcard.asm"

S1_END:
        if S1_END-1 > S1_LIMIT
        error   "stage1 exceeds S1_LIMIT"
        endif
