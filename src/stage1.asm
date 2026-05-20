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
        clr     FAT_ERROR
        jmp     SD_INIT

S1_READ_SECTOR:
        clr     FAT_ERROR
        jmp     SD_READ_SECTOR

S1_MOUNT:
        jmp     FAT32_MOUNT

S1_FIND_83:
        jmp     FAT32_FIND_83

S1_LOAD_FILE_83:
        jsr     FAT32_FIND_83
        bcc     S1_LOAD_CHECK_SIZE
        rts
S1_LOAD_CHECK_SIZE:
        ldaa    FAT_FILE_SIZE0
        oraa    FAT_FILE_SIZE1
        bne     S1_LOAD_SIZE_FAIL
        ldaa    FAT_FILE_SIZE2
        cmpa    #$02
        bhi     S1_LOAD_SIZE_FAIL
        bne     S1_LOAD_NONZERO
        ldaa    FAT_FILE_SIZE3
        bne     S1_LOAD_SIZE_FAIL
S1_LOAD_NONZERO:
        ldaa    FAT_FILE_SIZE2
        oraa    FAT_FILE_SIZE3
        beq     S1_LOAD_SIZE_FAIL
        jsr     S1_COPY_FILE_TO_CUR
        jsr     FAT_CLUSTER_TO_SD_LBA
        ldx     #SDFS_LOAD_BASE
        jsr     SD_READ_SECTOR
        bcc     S1_LOAD_OK
        ldaa    #FAT_ERR_SD
        jmp     FAT_FAIL_A
S1_LOAD_OK:
        clr     FAT_ERROR
        clc
        rts
S1_LOAD_SIZE_FAIL:
        ldaa    #FAT_ERR_SIZE
        jmp     FAT_FAIL_A

S1_COPY_FILE_TO_CUR:
        ldaa    FAT_FILE_CLUS0
        staa    FAT_CUR_CLUS0
        ldaa    FAT_FILE_CLUS1
        staa    FAT_CUR_CLUS1
        ldaa    FAT_FILE_CLUS2
        staa    FAT_CUR_CLUS2
        ldaa    FAT_FILE_CLUS3
        staa    FAT_CUR_CLUS3
        rts

S1_GET_ERROR:
        ldaa    FAT_ERROR
        bne     S1_GET_ERROR_DONE
        ldaa    SD_ERROR
S1_GET_ERROR_DONE:
        clc
        rts

FAT32_INCLUDE_FIND_API equ 1
FAT32_INCLUDE_FILE_API equ 0

        include "sdcard.asm"
        include "fat32.asm"

S1_END:
        if S1_END-1 > S1_LIMIT
        error   "stage1 exceeds S1_LIMIT"
        endif
