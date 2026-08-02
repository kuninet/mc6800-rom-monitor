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
SDFS3_ERR_IO       equ 3
SDFS3_ERR_NOT_FOUND equ 4
SDFS3_ERR_LOAD    equ 5
SDFS3_ERR_RUN     equ 6
SDFS3_ERR_COM     equ 7

SDFS3_COM_LOAD_BASE equ $0100
SDFS3_COM_MAX_SIZE equ USER_RAM_END-SDFS3_COM_LOAD_BASE+1
SDFS3_COM_MAX_HI equ SDFS3_COM_MAX_SIZE/256
SDFS3_COM_MAX_LO equ SDFS3_COM_MAX_SIZE-SDFS3_COM_MAX_HI*256

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
        jmp     SDFS3_CMD_DIR
SDFS3_CMD_TYPE_STUB:
        jmp     SDFS3_CMD_TYPE
SDFS3_CMD_LOAD_STUB:
        jmp     SDFS3_CMD_LOAD
SDFS3_CMD_RUN_STUB:
        jmp     SDFS3_CMD_RUN
SDFS3_CMD_COM_STUB:
        jmp     SDFS3_CMD_COM
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

SDFS3_CMD_DIR:
        ldx     SDFS3_PARSE_PTR
        stx     PATH_PTR
        ldaa    SDFS3_PARSE_LEN
        staa    PATH_LEN
        jsr     FAT32_MOUNT
        bcs     SDFS3_CMD_DIR_FAIL
        jsr     SDFS3_DIR_PATH
        bcs     SDFS3_CMD_DIR_PATH_FAIL
        clr     SDFS3_LAST_ERROR
        clc
        rts
SDFS3_CMD_DIR_PATH_FAIL:
        ldaa    FAT_ERROR
        beq     SDFS3_CMD_DIR_NOT_FOUND
SDFS3_CMD_DIR_FAIL:
        jmp     SDFS3_FAT_FAIL
SDFS3_CMD_DIR_NOT_FOUND:
        jmp     SDFS3_NOT_FOUND

SDFS3_CMD_TYPE:
        ldx     SDFS3_PARSE_PTR
        stx     PATH_PTR
        ldaa    SDFS3_PARSE_LEN
        staa    PATH_LEN
        jsr     FAT32_MOUNT
        bcs     SDFS3_CMD_TYPE_FAT_FAIL
        jsr     SDFS3_RESOLVE_FILE_SAVED
        bcs     SDFS3_CMD_TYPE_NOT_FOUND
        jsr     FAT32_STREAM_OPEN
        bcs     SDFS3_CMD_TYPE_FAT_FAIL
SDFS3_TYPE_LOOP:
        jsr     FAT32_STREAM_GETC
        bcc     SDFS3_TYPE_PUTC
        jsr     FAT_BYTES_REMAIN
        bcs     SDFS3_CMD_TYPE_FAT_FAIL
        clr     SDFS3_LAST_ERROR
        clc
        rts
SDFS3_TYPE_PUTC:
        jsr     SDFS3_PUTC
        bra     SDFS3_TYPE_LOOP
SDFS3_CMD_TYPE_NOT_FOUND:
        jmp     SDFS3_NOT_FOUND
SDFS3_CMD_TYPE_FAT_FAIL:
        jmp     SDFS3_FAT_FAIL

SDFS3_CMD_LOAD:
        ldx     SDFS3_PARSE_PTR
        ldab    SDFS3_PARSE_LEN
        jsr     SDFS3_LOAD_FILE
        bcs     SDFS3_CMD_LOAD_FAIL
        ldx     #SDFS3_TXT_OK
        jsr     SDFS3_PRINT
        clr     SDFS3_LAST_ERROR
        clc
        rts
SDFS3_CMD_LOAD_FAIL:
        ldaa    #SDFS3_ERR_LOAD
        jmp     SDFS3_FAIL_A

SDFS3_LOAD_FILE:
        clr     LOADER_MODE
        clr     LOADER_STAGE
        clr     SDFS_RUN_ENTRY_SET
        stx     PATH_PTR
        stab    PATH_LEN
        jsr     FAT32_MOUNT
        bcs     SDFS3_LOAD_FILE_FAIL
        jsr     SDFS3_RESOLVE_FILE_SAVED
        bcs     SDFS3_LOAD_FILE_FAIL
        jsr     FAT32_STREAM_OPEN
        bcs     SDFS3_LOAD_FILE_FAIL
SDFS3_LOAD_LOOP:
        jsr     SDFS3_READ_LOADER_RECORD
        bcs     SDFS3_LOAD_FILE_FAIL
        cmpa    #1
        beq     SDFS3_LOAD_FILE_DONE
        bra     SDFS3_LOAD_LOOP
SDFS3_LOAD_FILE_DONE:
        clc
        rts
SDFS3_LOAD_FILE_FAIL:
        sec
        rts

SDFS3_CMD_RUN:
        ldx     SDFS3_PARSE_PTR
        ldab    SDFS3_PARSE_LEN
        jsr     SDFS3_PARSE_HEX16
        bcs     SDFS3_CMD_RUN_FILE
        lds     #STACK_TOP
        ldx     HEX_VALUE_HI
        jmp     0,x
SDFS3_CMD_RUN_FILE:
        ldx     SDFS3_PARSE_PTR
        ldab    SDFS3_PARSE_LEN
        jsr     SDFS3_LOAD_FILE
        bcs     SDFS3_CMD_RUN_FAIL
        ldaa    LOADER_MODE
        cmpa    #LOAD_MODE_SREC
        bne     SDFS3_CMD_RUN_FAIL
        ldaa    SDFS_RUN_ENTRY_SET
        beq     SDFS3_CMD_RUN_FAIL
        lds     #STACK_TOP
        ldx     SDFS_RUN_ENTRY
        jmp     0,x
SDFS3_CMD_RUN_FAIL:
        ldaa    #SDFS3_ERR_RUN
        jmp     SDFS3_FAIL_A

SDFS3_CMD_COM:
        ldx     SDFS3_TOKEN_PTR
        ldab    SDFS3_TOKEN_LEN
        addb    SDFS3_PARSE_LEN
        jsr     SDFS3_PARSE_COM_PATH_COMMAND
        bcs     SDFS3_CMD_COM_FAIL
        jsr     FAT32_MOUNT
        bcs     SDFS3_CMD_COM_FAIL
        jsr     SDFS3_RESOLVE_FILE_SAVED
        bcs     SDFS3_CMD_COM_FAIL
        jsr     SDFS3_PARSE_COM_CHECK_EXT
        bcs     SDFS3_CMD_COM_FAIL
        jsr     SDFS3_COM_CHECK_SIZE
        bcs     SDFS3_CMD_COM_FAIL
        jsr     FAT32_STREAM_OPEN
        bcs     SDFS3_CMD_COM_FAIL
        jsr     SDFS3_COM_LOAD_RAW
        bcs     SDFS3_CMD_COM_FAIL
        jsr     SDFS3_COM_RESTORE_ARGS
        ldx     ARG2_PTR
        ldab    ARG2_LEN
        clra
        jsr     SDFS3_COM_LOAD_BASE
        clr     SDFS3_LAST_ERROR
        clc
        rts
SDFS3_CMD_COM_FAIL:
        ldaa    #SDFS3_ERR_COM
        jmp     SDFS3_FAIL_A

SDFS3_COM_CHECK_SIZE:
        ldaa    FAT_FILE_SIZE0
        oraa    FAT_FILE_SIZE1
        bne     SDFS3_COM_CHECK_FAIL
        ldaa    FAT_FILE_SIZE2
        oraa    FAT_FILE_SIZE3
        beq     SDFS3_COM_CHECK_FAIL
        ldaa    FAT_FILE_SIZE2
        cmpa    #SDFS3_COM_MAX_HI
        bhi     SDFS3_COM_CHECK_FAIL
        blo     SDFS3_COM_CHECK_OK
        ldaa    FAT_FILE_SIZE3
        cmpa    #SDFS3_COM_MAX_LO
        bhi     SDFS3_COM_CHECK_FAIL
SDFS3_COM_CHECK_OK:
        clc
        rts
SDFS3_COM_CHECK_FAIL:
        sec
        rts

SDFS3_COM_LOAD_RAW:
        ldx     #SDFS3_COM_LOAD_BASE
        stx     FAT_READ_PTR
SDFS3_COM_LOAD_LOOP:
        jsr     FAT_BYTES_REMAIN
        bcc     SDFS3_COM_LOAD_DONE
        jsr     FAT32_STREAM_GETC
        bcs     SDFS3_COM_LOAD_FAIL
        ldx     FAT_READ_PTR
        staa    0,x
        inx
        stx     FAT_READ_PTR
        bra     SDFS3_COM_LOAD_LOOP
SDFS3_COM_LOAD_DONE:
        clc
        rts
SDFS3_COM_LOAD_FAIL:
        sec
        rts

SDFS3_COM_RESTORE_ARGS:
        ldx     PATH_ARG_PTR
        stx     ARG2_PTR
        ldaa    PATH_ARG_LEN
        staa    ARG2_LEN
        rts

SDFS3_DIR_PATH:
        jsr     SDFS3_RESOLVE_DIR_SAVED
        bcs     SDFS3_DIR_FAIL
SDFS3_DIR_CLUSTER_LOOP:
        jsr     FAT_CLUSTER_TO_SD_LBA
        bcs     SDFS3_DIR_FAIL
        ldx     #SD_SECTOR_BUF
        jsr     SD_READ_SECTOR
        bcs     SDFS3_DIR_SD_FAIL
        ldx     #SD_SECTOR_BUF
        stx     FAT_ENTRY_PTR
        ldaa    #16
        staa    FAT_DIR_COUNT
SDFS3_DIR_ENTRY_LOOP:
        ldx     FAT_ENTRY_PTR
        ldaa    0,x
        beq     SDFS3_DIR_DONE
        cmpa    #$E5
        beq     SDFS3_DIR_NEXT_ENTRY
        jsr     SDFS3_DIR_ENTRY_VISIBLE
        bcs     SDFS3_DIR_NEXT_ENTRY
        jsr     SDFS3_PRINT_DIR_ENTRY
SDFS3_DIR_NEXT_ENTRY:
        jsr     FAT_ADVANCE_ENTRY_PTR
        dec     FAT_DIR_COUNT
        bne     SDFS3_DIR_ENTRY_LOOP
        jsr     FAT32_NEXT_CLUSTER
        bcs     SDFS3_DIR_NEXT_DONE_OR_FAIL
        jsr     FAT_COPY_NEXT_TO_CUR
        bra     SDFS3_DIR_CLUSTER_LOOP
SDFS3_DIR_NEXT_DONE_OR_FAIL:
        ldaa    FAT_ERROR
        bne     SDFS3_DIR_FAIL
SDFS3_DIR_DONE:
        clc
        rts
SDFS3_DIR_SD_FAIL:
        ldaa    #FAT_ERR_SD
        staa    FAT_ERROR
SDFS3_DIR_FAIL:
        sec
        rts

SDFS3_RESOLVE_FILE_SAVED:
        jsr     SDFS3_PATH_START
        bcs     SDFS3_RESOLVE_FAIL
SDFS3_RESOLVE_FILE_LOOP:
        jsr     SDFS3_PATH_COMPONENT
        bcs     SDFS3_RESOLVE_FAIL
        jsr     SDFS3_FIND_IN_CUR
        bcs     SDFS3_RESOLVE_FAIL
        tst     PATH_DELIM
        beq     SDFS3_RESOLVE_FILE_LAST
        jsr     SDFS3_ENTRY_IS_DIR
        bcs     SDFS3_RESOLVE_FAIL
        jsr     FAT_COPY_FILE_TO_CUR
        bra     SDFS3_RESOLVE_FILE_LOOP
SDFS3_RESOLVE_FILE_LAST:
        jsr     SDFS3_ENTRY_IS_FILE
        bcs     SDFS3_RESOLVE_FAIL
        clc
        rts

SDFS3_RESOLVE_DIR_SAVED:
        jsr     SDFS3_PATH_START_ALLOW_ROOT
        bcs     SDFS3_RESOLVE_FAIL
        tst     PATH_LEN
        beq     SDFS3_RESOLVE_OK
SDFS3_RESOLVE_DIR_LOOP:
        jsr     SDFS3_PATH_COMPONENT
        bcs     SDFS3_RESOLVE_FAIL
        jsr     SDFS3_FIND_IN_CUR
        bcs     SDFS3_RESOLVE_FAIL
        jsr     SDFS3_ENTRY_IS_DIR
        bcs     SDFS3_RESOLVE_FAIL
        jsr     FAT_COPY_FILE_TO_CUR
        tst     PATH_DELIM
        bne     SDFS3_RESOLVE_DIR_LOOP
SDFS3_RESOLVE_OK:
        clc
        rts
SDFS3_RESOLVE_FAIL:
        sec
        rts

SDFS3_PATH_START:
        jsr     SDFS3_PATH_SKIP_HEAD
        bcs     SDFS3_PATH_START_FAIL
        tst     PATH_LEN
        beq     SDFS3_PATH_START_FAIL
        jsr     FAT_COPY_ROOT_TO_CUR
        clc
        rts
SDFS3_PATH_START_ALLOW_ROOT:
        jsr     SDFS3_PATH_SKIP_HEAD
        bcs     SDFS3_PATH_START_FAIL
        jsr     FAT_COPY_ROOT_TO_CUR
        clc
        rts
SDFS3_PATH_START_FAIL:
        sec
        rts

SDFS3_PATH_SKIP_HEAD:
        tst     PATH_LEN
        beq     SDFS3_PATH_SKIP_DONE
        ldx     PATH_PTR
        ldaa    0,x
        cmpa    #CHR_SPACE
        beq     SDFS3_PATH_SKIP_ONE
        cmpa    #'/'
        beq     SDFS3_PATH_SKIP_SLASH
        bra     SDFS3_PATH_SKIP_DONE
SDFS3_PATH_SKIP_ONE:
        inx
        stx     PATH_PTR
        dec     PATH_LEN
        bra     SDFS3_PATH_SKIP_HEAD
SDFS3_PATH_SKIP_SLASH:
        inx
        stx     PATH_PTR
        dec     PATH_LEN
        beq     SDFS3_PATH_SKIP_FAIL
SDFS3_PATH_SKIP_DONE:
        clc
        rts
SDFS3_PATH_SKIP_FAIL:
        sec
        rts

SDFS3_PATH_COMPONENT:
        ldx     PATH_PTR
        stx     ARG2_PTR
        clr     ARG2_LEN
        clr     PATH_DELIM
SDFS3_PATH_COMPONENT_LOOP:
        tst     PATH_LEN
        beq     SDFS3_PATH_COMPONENT_DONE
        ldx     PATH_PTR
        ldaa    0,x
        cmpa    #'/'
        beq     SDFS3_PATH_COMPONENT_SLASH
        cmpa    #CHR_SPACE
        beq     SDFS3_PATH_COMPONENT_SPACE
        inx
        stx     PATH_PTR
        dec     PATH_LEN
        inc     ARG2_LEN
        bra     SDFS3_PATH_COMPONENT_LOOP
SDFS3_PATH_COMPONENT_SLASH:
        ldaa    ARG2_LEN
        beq     SDFS3_PATH_COMPONENT_FAIL
        ldx     PATH_PTR
        inx
        stx     PATH_PTR
        dec     PATH_LEN
        ldaa    #1
        staa    PATH_DELIM
        tst     PATH_LEN
        beq     SDFS3_PATH_COMPONENT_FAIL
        bra     SDFS3_PATH_COMPONENT_PARSE
SDFS3_PATH_COMPONENT_SPACE:
        jsr     SDFS3_PATH_SKIP_TRAILING
        bcs     SDFS3_PATH_COMPONENT_FAIL
SDFS3_PATH_COMPONENT_DONE:
        ldaa    ARG2_LEN
        beq     SDFS3_PATH_COMPONENT_FAIL
SDFS3_PATH_COMPONENT_PARSE:
        ldx     ARG2_PTR
        ldab    ARG2_LEN
        jsr     SDFS3_PARSE_FILENAME_83
        bcs     SDFS3_PATH_COMPONENT_FAIL
        clc
        rts
SDFS3_PATH_COMPONENT_FAIL:
        sec
        rts

SDFS3_PATH_SKIP_TRAILING:
        tst     PATH_LEN
        beq     SDFS3_PATH_SKIP_TRAILING_OK
        ldx     PATH_PTR
        ldaa    0,x
        cmpa    #CHR_SPACE
        bne     SDFS3_PATH_SKIP_TRAILING_FAIL
        inx
        stx     PATH_PTR
        dec     PATH_LEN
        bra     SDFS3_PATH_SKIP_TRAILING
SDFS3_PATH_SKIP_TRAILING_OK:
        clc
        rts
SDFS3_PATH_SKIP_TRAILING_FAIL:
        sec
        rts

SDFS3_FIND_IN_CUR:
        jsr     FAT_CLUSTER_TO_SD_LBA
        bcs     SDFS3_FIND_IN_CUR_FAIL
        ldx     #SD_SECTOR_BUF
        jsr     SD_READ_SECTOR
        bcs     SDFS3_FIND_IN_CUR_SD_FAIL
        ldx     #SD_SECTOR_BUF
        stx     FAT_ENTRY_PTR
        ldaa    #16
        staa    FAT_DIR_COUNT
SDFS3_FIND_IN_CUR_ENTRY_LOOP:
        ldx     FAT_ENTRY_PTR
        ldaa    0,x
        beq     SDFS3_FIND_IN_CUR_FAIL
        cmpa    #$E5
        beq     SDFS3_FIND_IN_CUR_NEXT_ENTRY
        ldaa    11,x
        anda    #$0F
        cmpa    #$0F
        beq     SDFS3_FIND_IN_CUR_NEXT_ENTRY
        ldaa    11,x
        bita    #$08
        bne     SDFS3_FIND_IN_CUR_NEXT_ENTRY
        jsr     FAT_COMPARE_ENTRY_NAME
        bcc     SDFS3_FIND_IN_CUR_MATCH
SDFS3_FIND_IN_CUR_NEXT_ENTRY:
        jsr     FAT_ADVANCE_ENTRY_PTR
        dec     FAT_DIR_COUNT
        bne     SDFS3_FIND_IN_CUR_ENTRY_LOOP
        jsr     FAT32_NEXT_CLUSTER
        bcs     SDFS3_FIND_IN_CUR_NEXT_DONE_OR_FAIL
        jsr     FAT_COPY_NEXT_TO_CUR
        bra     SDFS3_FIND_IN_CUR
SDFS3_FIND_IN_CUR_NEXT_DONE_OR_FAIL:
        ldaa    FAT_ERROR
        bne     SDFS3_FIND_IN_CUR_FAIL
        bra     SDFS3_FIND_IN_CUR_FAIL
SDFS3_FIND_IN_CUR_MATCH:
        jsr     FAT_STORE_FILE_ENTRY
        clc
        rts
SDFS3_FIND_IN_CUR_SD_FAIL:
        ldaa    #FAT_ERR_SD
        staa    FAT_ERROR
SDFS3_FIND_IN_CUR_FAIL:
        sec
        rts

SDFS3_ENTRY_IS_DIR:
        ldx     FAT_ENTRY_PTR
        ldaa    11,x
        bita    #$10
        beq     SDFS3_ENTRY_IS_DIR_FAIL
        clc
        rts
SDFS3_ENTRY_IS_DIR_FAIL:
        sec
        rts

SDFS3_ENTRY_IS_FILE:
        ldx     FAT_ENTRY_PTR
        ldaa    11,x
        bita    #$18
        bne     SDFS3_ENTRY_IS_FILE_FAIL
        clc
        rts
SDFS3_ENTRY_IS_FILE_FAIL:
        sec
        rts

SDFS3_PARSE_FILENAME_83:
        stx     ARG_PTR
        stab    ARG_LEN
        jsr     SDFS3_CLEAR_FIND_NAME
SDFS3_PARSE_FILENAME_SKIP_HEAD:
        tst     ARG_LEN
        bne     SDFS3_PARSE_FILENAME_SKIP_HAS
        jmp     SDFS3_PARSE_FILENAME_FAIL
SDFS3_PARSE_FILENAME_SKIP_HAS:
        ldx     ARG_PTR
        ldaa    0,x
        cmpa    #CHR_SPACE
        bne     SDFS3_PARSE_FILENAME_NAME_START
        inx
        stx     ARG_PTR
        dec     ARG_LEN
        bra     SDFS3_PARSE_FILENAME_SKIP_HEAD
SDFS3_PARSE_FILENAME_NAME_START:
        ldx     #FAT_FIND_NAME0
        stx     FAT_ENTRY_PTR
        clr     ARG2_LEN
SDFS3_PARSE_FILENAME_NAME_LOOP:
        tst     ARG_LEN
        beq     SDFS3_PARSE_FILENAME_NAME_DONE
        ldx     ARG_PTR
        ldaa    0,x
        cmpa    #CHR_SPACE
        bne     SDFS3_PARSE_FILENAME_NAME_NOT_SPACE
        jmp     SDFS3_PARSE_FILENAME_TRAILING
SDFS3_PARSE_FILENAME_NAME_NOT_SPACE:
        cmpa    #'.'
        bne     SDFS3_PARSE_FILENAME_NAME_NOT_DOT
        jmp     SDFS3_PARSE_FILENAME_EXT_START
SDFS3_PARSE_FILENAME_NAME_NOT_DOT:
        ldab    ARG2_LEN
        cmpb    #8
        blo     SDFS3_PARSE_FILENAME_NAME_ROOM
        jmp     SDFS3_PARSE_FILENAME_FAIL
SDFS3_PARSE_FILENAME_NAME_ROOM:
        jsr     SDFS3_TO_UPPER
        ldx     FAT_ENTRY_PTR
        staa    0,x
        inx
        stx     FAT_ENTRY_PTR
        inc     ARG2_LEN
        ldx     ARG_PTR
        inx
        stx     ARG_PTR
        dec     ARG_LEN
        bra     SDFS3_PARSE_FILENAME_NAME_LOOP
SDFS3_PARSE_FILENAME_NAME_DONE:
        tst     ARG2_LEN
        bne     SDFS3_PARSE_FILENAME_NAME_OK
        jmp     SDFS3_PARSE_FILENAME_FAIL
SDFS3_PARSE_FILENAME_NAME_OK:
        jmp     SDFS3_PARSE_FILENAME_OK
SDFS3_PARSE_FILENAME_EXT_START:
        tst     ARG2_LEN
        bne     SDFS3_PARSE_FILENAME_EXT_NAME_OK
        jmp     SDFS3_PARSE_FILENAME_FAIL
SDFS3_PARSE_FILENAME_EXT_NAME_OK:
        ldx     ARG_PTR
        inx
        stx     ARG_PTR
        dec     ARG_LEN
        ldx     #FAT_FIND_NAME8
        stx     FAT_ENTRY_PTR
        clr     ARG2_LEN
SDFS3_PARSE_FILENAME_EXT_LOOP:
        tst     ARG_LEN
        bne     SDFS3_PARSE_FILENAME_EXT_HAS_LEN
        jmp     SDFS3_PARSE_FILENAME_OK
SDFS3_PARSE_FILENAME_EXT_HAS_LEN:
        ldx     ARG_PTR
        ldaa    0,x
        cmpa    #CHR_SPACE
        bne     SDFS3_PARSE_FILENAME_EXT_NOT_SPACE
        jmp     SDFS3_PARSE_FILENAME_TRAILING
SDFS3_PARSE_FILENAME_EXT_NOT_SPACE:
        cmpa    #'.'
        bne     SDFS3_PARSE_FILENAME_EXT_CHAR_OK
        jmp     SDFS3_PARSE_FILENAME_FAIL
SDFS3_PARSE_FILENAME_EXT_CHAR_OK:
        ldab    ARG2_LEN
        cmpb    #3
        blo     SDFS3_PARSE_FILENAME_EXT_ROOM
        jmp     SDFS3_PARSE_FILENAME_FAIL
SDFS3_PARSE_FILENAME_EXT_ROOM:
        jsr     SDFS3_TO_UPPER
        ldx     FAT_ENTRY_PTR
        staa    0,x
        inx
        stx     FAT_ENTRY_PTR
        inc     ARG2_LEN
        ldx     ARG_PTR
        inx
        stx     ARG_PTR
        dec     ARG_LEN
        bra     SDFS3_PARSE_FILENAME_EXT_LOOP
SDFS3_PARSE_FILENAME_TRAILING:
        ldx     ARG_PTR
        inx
        stx     ARG_PTR
        dec     ARG_LEN
SDFS3_PARSE_FILENAME_TRAILING_LOOP:
        tst     ARG_LEN
        beq     SDFS3_PARSE_FILENAME_OK
        ldx     ARG_PTR
        ldaa    0,x
        cmpa    #CHR_SPACE
        beq     SDFS3_PARSE_FILENAME_TRAILING_SPACE_OK
        jmp     SDFS3_PARSE_FILENAME_FAIL
SDFS3_PARSE_FILENAME_TRAILING_SPACE_OK:
        inx
        stx     ARG_PTR
        dec     ARG_LEN
        bra     SDFS3_PARSE_FILENAME_TRAILING_LOOP
SDFS3_PARSE_FILENAME_OK:
        clc
        rts
SDFS3_PARSE_FILENAME_FAIL:
        sec
        rts

SDFS3_CLEAR_FIND_NAME:
        ldx     #FAT_FIND_NAME0
        ldab    #11
SDFS3_CLEAR_FIND_NAME_LOOP:
        ldaa    #CHR_SPACE
        staa    0,x
        inx
        decb
        bne     SDFS3_CLEAR_FIND_NAME_LOOP
        rts

SDFS3_PARSE_COM_PATH_COMMAND:
        stx     ARG_PTR
        stab    ARG_LEN
SDFS3_PARSE_COM_PATH_SKIP_HEAD:
        tst     ARG_LEN
        beq     SDFS3_PARSE_COM_PATH_FAIL
        ldx     ARG_PTR
        ldaa    0,x
        cmpa    #CHR_SPACE
        bne     SDFS3_PARSE_COM_PATH_START
        inx
        stx     ARG_PTR
        dec     ARG_LEN
        bra     SDFS3_PARSE_COM_PATH_SKIP_HEAD
SDFS3_PARSE_COM_PATH_START:
        ldx     ARG_PTR
        stx     PATH_PTR
        clr     PATH_LEN
SDFS3_PARSE_COM_PATH_TOKEN:
        tst     ARG_LEN
        beq     SDFS3_PARSE_COM_PATH_NO_ARGS
        ldx     ARG_PTR
        ldaa    0,x
        cmpa    #CHR_SPACE
        beq     SDFS3_PARSE_COM_PATH_ARG_SKIP
        inx
        stx     ARG_PTR
        dec     ARG_LEN
        inc     PATH_LEN
        bra     SDFS3_PARSE_COM_PATH_TOKEN
SDFS3_PARSE_COM_PATH_ARG_SKIP:
        ldaa    PATH_LEN
        beq     SDFS3_PARSE_COM_PATH_FAIL
        ldx     ARG_PTR
        inx
        stx     ARG_PTR
        dec     ARG_LEN
SDFS3_PARSE_COM_PATH_ARG_SKIP_LOOP:
        tst     ARG_LEN
        beq     SDFS3_PARSE_COM_PATH_NO_ARGS
        ldx     ARG_PTR
        ldaa    0,x
        cmpa    #CHR_SPACE
        bne     SDFS3_PARSE_COM_PATH_ARGS
        inx
        stx     ARG_PTR
        dec     ARG_LEN
        bra     SDFS3_PARSE_COM_PATH_ARG_SKIP_LOOP
SDFS3_PARSE_COM_PATH_ARGS:
        ldx     ARG_PTR
        stx     PATH_ARG_PTR
        ldaa    ARG_LEN
        staa    PATH_ARG_LEN
        clc
        rts
SDFS3_PARSE_COM_PATH_NO_ARGS:
        ldaa    PATH_LEN
        beq     SDFS3_PARSE_COM_PATH_FAIL
        ldx     ARG_PTR
        stx     PATH_ARG_PTR
        clr     PATH_ARG_LEN
        clc
        rts
SDFS3_PARSE_COM_PATH_FAIL:
        sec
        rts

SDFS3_PARSE_COM_CHECK_EXT:
        ldaa    FAT_FIND_NAME8
        cmpa    #'C'
        bne     SDFS3_PARSE_COM_CHECK_FAIL
        ldaa    FAT_FIND_NAME9
        cmpa    #'O'
        bne     SDFS3_PARSE_COM_CHECK_FAIL
        ldaa    FAT_FIND_NAME10
        cmpa    #'M'
        bne     SDFS3_PARSE_COM_CHECK_FAIL
        clc
        rts
SDFS3_PARSE_COM_CHECK_FAIL:
        sec
        rts

SDFS3_PARSE_HEX16:
        stx     ARG_PTR
        stab    ARG_LEN
        clr     HEX_VALUE_HI
        clr     HEX_VALUE_LO
        clr     ARG2_LEN
SDFS3_PARSE_HEX16_SKIP:
        tst     ARG_LEN
        bne     SDFS3_PARSE_HEX16_SKIP_HAS
        jmp     SDFS3_PARSE_HEX16_FAIL
SDFS3_PARSE_HEX16_SKIP_HAS:
        ldx     ARG_PTR
        ldaa    0,x
        cmpa    #CHR_SPACE
        bne     SDFS3_PARSE_HEX16_LOOP
        inx
        stx     ARG_PTR
        dec     ARG_LEN
        bra     SDFS3_PARSE_HEX16_SKIP
SDFS3_PARSE_HEX16_LOOP:
        tst     ARG_LEN
        beq     SDFS3_PARSE_HEX16_DONE
        ldx     ARG_PTR
        ldaa    0,x
        cmpa    #CHR_SPACE
        beq     SDFS3_PARSE_HEX16_TRAILING
        jsr     SDFS3_HEX_TO_NIBBLE
        bcs     SDFS3_PARSE_HEX16_FAIL
        ldab    ARG2_LEN
        cmpb    #4
        bhs     SDFS3_PARSE_HEX16_FAIL
        tstb
        beq     SDFS3_PARSE_HEX16_HI_H
        cmpb    #1
        beq     SDFS3_PARSE_HEX16_HI_L
        cmpb    #2
        beq     SDFS3_PARSE_HEX16_LO_H
        oraa    HEX_VALUE_LO
        staa    HEX_VALUE_LO
        bra     SDFS3_PARSE_HEX16_ADVANCE
SDFS3_PARSE_HEX16_HI_H:
        lsla
        lsla
        lsla
        lsla
        staa    HEX_VALUE_HI
        bra     SDFS3_PARSE_HEX16_ADVANCE
SDFS3_PARSE_HEX16_HI_L:
        oraa    HEX_VALUE_HI
        staa    HEX_VALUE_HI
        bra     SDFS3_PARSE_HEX16_ADVANCE
SDFS3_PARSE_HEX16_LO_H:
        lsla
        lsla
        lsla
        lsla
        staa    HEX_VALUE_LO
SDFS3_PARSE_HEX16_ADVANCE:
        ldx     ARG_PTR
        inx
        stx     ARG_PTR
        dec     ARG_LEN
        inc     ARG2_LEN
        bra     SDFS3_PARSE_HEX16_LOOP
SDFS3_PARSE_HEX16_TRAILING:
        ldx     ARG_PTR
        inx
        stx     ARG_PTR
        dec     ARG_LEN
SDFS3_PARSE_HEX16_TRAILING_LOOP:
        tst     ARG_LEN
        beq     SDFS3_PARSE_HEX16_DONE
        ldx     ARG_PTR
        ldaa    0,x
        cmpa    #CHR_SPACE
        bne     SDFS3_PARSE_HEX16_FAIL
        inx
        stx     ARG_PTR
        dec     ARG_LEN
        bra     SDFS3_PARSE_HEX16_TRAILING_LOOP
SDFS3_PARSE_HEX16_DONE:
        ldaa    ARG2_LEN
        cmpa    #4
        bne     SDFS3_PARSE_HEX16_FAIL
        clc
        rts
SDFS3_PARSE_HEX16_FAIL:
        sec
        rts

SDFS3_READ_LOADER_RECORD:
        jsr     SDFS3_READ_RECORD_HEAD
        bcs     SDFS3_READ_LOADER_RECORD_FAIL
        ldaa    LOADER_MODE
        bne     SDFS3_READ_LOADER_RECORD_MODE_SET
        ldaa    HEX_NIBBLE
        cmpa    #'S'
        beq     SDFS3_READ_LOADER_RECORD_SET_SREC
        cmpa    #':'
        beq     SDFS3_READ_LOADER_RECORD_SET_IHEX
        sec
        rts
SDFS3_READ_LOADER_RECORD_SET_SREC:
        ldaa    #LOAD_MODE_SREC
        staa    LOADER_MODE
        bra     SDFS3_READ_LOADER_RECORD_MODE_SET
SDFS3_READ_LOADER_RECORD_SET_IHEX:
        ldaa    #LOAD_MODE_IHEX
        staa    LOADER_MODE
SDFS3_READ_LOADER_RECORD_MODE_SET:
        ldaa    LOADER_MODE
        cmpa    #LOAD_MODE_SREC
        beq     SDFS3_READ_SREC_RECORD
        cmpa    #LOAD_MODE_IHEX
        bne     SDFS3_READ_LOADER_RECORD_FAIL
        jmp     SDFS3_READ_IHEX_RECORD
SDFS3_READ_LOADER_RECORD_FAIL:
        sec
        rts

SDFS3_READ_RECORD_HEAD:
        jsr     FAT32_STREAM_GETC
        bcs     SDFS3_READ_RECORD_HEAD_FAIL
        cmpa    #CHR_LF
        beq     SDFS3_READ_RECORD_HEAD
        cmpa    #CHR_CR
        beq     SDFS3_READ_RECORD_HEAD
        cmpa    #CHR_SPACE
        blo     SDFS3_READ_RECORD_HEAD
        staa    HEX_NIBBLE
        clc
        rts
SDFS3_READ_RECORD_HEAD_FAIL:
        sec
        rts

SDFS3_READ_RECORD_TRAILER:
        jsr     FAT32_STREAM_GETC
        bcs     SDFS3_READ_RECORD_TRAILER_EOF_OR_FAIL
        cmpa    #CHR_LF
        beq     SDFS3_READ_RECORD_TRAILER_OK
        cmpa    #CHR_CR
        beq     SDFS3_READ_RECORD_TRAILER_OK
SDFS3_READ_RECORD_TRAILER_FAIL:
        sec
        rts
SDFS3_READ_RECORD_TRAILER_EOF_OR_FAIL:
        jsr     FAT_BYTES_REMAIN
        bcs     SDFS3_READ_RECORD_TRAILER_FAIL
SDFS3_READ_RECORD_TRAILER_OK:
        clc
        rts

SDFS3_READ_HEXBYTE_INPUT:
        pshb
        jsr     FAT32_STREAM_GETC
        bcs     SDFS3_READ_HEXBYTE_INPUT_FAIL
        jsr     SDFS3_HEX_TO_NIBBLE
        bcs     SDFS3_READ_HEXBYTE_INPUT_FAIL
        lsla
        lsla
        lsla
        lsla
        tab
        jsr     FAT32_STREAM_GETC
        bcs     SDFS3_READ_HEXBYTE_INPUT_FAIL
        jsr     SDFS3_HEX_TO_NIBBLE
        bcs     SDFS3_READ_HEXBYTE_INPUT_FAIL
        aba
        pulb
        clc
        rts
SDFS3_READ_HEXBYTE_INPUT_FAIL:
        pulb
        sec
        rts

SDFS3_READ_SREC_RECORD:
        ldaa    HEX_NIBBLE
        cmpa    #'S'
        beq     SDFS3_READ_SREC_HEAD_OK
        jmp     SDFS3_READ_SREC_FAIL
SDFS3_READ_SREC_HEAD_OK:
        ldaa    #1
        staa    LOADER_STAGE
        jsr     FAT32_STREAM_GETC
        bcs     SDFS3_READ_SREC_FAIL_NEAR0
        staa    LOADER_TYPE
        cmpa    #'0'
        beq     SDFS3_READ_SREC_TYPE_OK
        cmpa    #'1'
        beq     SDFS3_READ_SREC_TYPE_OK
        cmpa    #'2'
        beq     SDFS3_READ_SREC_TYPE_OK
        cmpa    #'5'
        beq     SDFS3_READ_SREC_TYPE_OK
        cmpa    #'8'
        beq     SDFS3_READ_SREC_TYPE_OK
        cmpa    #'9'
        beq     SDFS3_READ_SREC_TYPE_OK
        jmp     SDFS3_READ_SREC_FAIL
SDFS3_READ_SREC_FAIL_NEAR0:
        jmp     SDFS3_READ_SREC_FAIL
SDFS3_READ_SREC_TYPE_OK:
        ldaa    #2
        staa    LOADER_STAGE
        jsr     SDFS3_READ_HEXBYTE_INPUT
        bcs     SDFS3_READ_SREC_FAIL_NEAR1
        staa    LOADER_COUNT
        staa    LOADER_SUM
        ldaa    LOADER_TYPE
        cmpa    #'2'
        beq     SDFS3_READ_SREC_ADDR24
        cmpa    #'8'
        beq     SDFS3_READ_SREC_ADDR24
        ldaa    LOADER_COUNT
        cmpa    #3
        blo     SDFS3_READ_SREC_FAIL_NEAR1
        ldaa    #3
        staa    LOADER_STAGE
        jsr     SDFS3_READ_HEXBYTE_INPUT
        bcs     SDFS3_READ_SREC_FAIL_NEAR1
        staa    LOADER_ADDR
        jsr     SDFS3_ADD_TO_LOADER_SUM
        jsr     SDFS3_READ_HEXBYTE_INPUT
        bcs     SDFS3_READ_SREC_FAIL_NEAR1
        staa    LOADER_ADDR+1
        jsr     SDFS3_ADD_TO_LOADER_SUM
        ldab    LOADER_COUNT
        subb    #3
        bra     SDFS3_READ_SREC_DATA_LOOP
SDFS3_READ_SREC_FAIL_NEAR1:
        jmp     SDFS3_READ_SREC_FAIL
SDFS3_READ_SREC_ADDR24:
        ldaa    LOADER_COUNT
        cmpa    #4
        blo     SDFS3_READ_SREC_FAIL_NEAR2
        ldaa    #3
        staa    LOADER_STAGE
        jsr     SDFS3_READ_HEXBYTE_INPUT
        bcs     SDFS3_READ_SREC_FAIL_NEAR2
        staa    HEX_NIBBLE
        jsr     SDFS3_ADD_TO_LOADER_SUM
        ldaa    HEX_NIBBLE
        bne     SDFS3_READ_SREC_FAIL_NEAR2
        jsr     SDFS3_READ_HEXBYTE_INPUT
        bcs     SDFS3_READ_SREC_FAIL_NEAR2
        staa    LOADER_ADDR
        jsr     SDFS3_ADD_TO_LOADER_SUM
        jsr     SDFS3_READ_HEXBYTE_INPUT
        bcs     SDFS3_READ_SREC_FAIL_NEAR2
        staa    LOADER_ADDR+1
        jsr     SDFS3_ADD_TO_LOADER_SUM
        ldab    LOADER_COUNT
        subb    #4
        bra     SDFS3_READ_SREC_DATA_LOOP
SDFS3_READ_SREC_FAIL_NEAR2:
        jmp     SDFS3_READ_SREC_FAIL
SDFS3_READ_SREC_DATA_LOOP:
        ldaa    #4
        staa    LOADER_STAGE
        tstb
        beq     SDFS3_READ_SREC_CHECKSUM
        jsr     SDFS3_READ_HEXBYTE_INPUT
        bcs     SDFS3_READ_SREC_FAIL
        staa    HEX_NIBBLE
        jsr     SDFS3_ADD_TO_LOADER_SUM
        ldaa    LOADER_TYPE
        cmpa    #'1'
        beq     SDFS3_READ_SREC_STORE
        cmpa    #'2'
        bne     SDFS3_READ_SREC_SKIP_STORE
SDFS3_READ_SREC_STORE:
        ldaa    HEX_NIBBLE
        pshb
        ldx     LOADER_ADDR
        staa    0,x
        inx
        stx     LOADER_ADDR
        pulb
SDFS3_READ_SREC_SKIP_STORE:
        decb
        bra     SDFS3_READ_SREC_DATA_LOOP
SDFS3_READ_SREC_CHECKSUM:
        ldaa    #5
        staa    LOADER_STAGE
        jsr     SDFS3_READ_HEXBYTE_INPUT
        bcs     SDFS3_READ_SREC_FAIL
        jsr     SDFS3_ADD_TO_LOADER_SUM
        cmpa    #$FF
        bne     SDFS3_READ_SREC_FAIL
        jsr     SDFS3_READ_RECORD_TRAILER
        bcs     SDFS3_READ_SREC_FAIL
        ldaa    LOADER_TYPE
        cmpa    #'8'
        beq     SDFS3_READ_SREC_EOF
        cmpa    #'9'
        beq     SDFS3_READ_SREC_EOF
        ldaa    #0
        clc
        rts
SDFS3_READ_SREC_EOF:
        ldaa    LOADER_ADDR
        staa    SDFS_RUN_ENTRY
        ldaa    LOADER_ADDR+1
        staa    SDFS_RUN_ENTRY+1
        ldaa    #1
        staa    SDFS_RUN_ENTRY_SET
        ldaa    #1
        clc
        rts
SDFS3_READ_SREC_FAIL:
        sec
        rts

SDFS3_READ_IHEX_RECORD:
        ldaa    HEX_NIBBLE
        cmpa    #':'
        beq     SDFS3_READ_IHEX_HEAD_OK
        jmp     SDFS3_READ_IHEX_FAIL
SDFS3_READ_IHEX_HEAD_OK:
        ldaa    #1
        staa    LOADER_STAGE
        ldaa    #2
        staa    LOADER_STAGE
        jsr     SDFS3_READ_HEXBYTE_INPUT
        bcs     SDFS3_READ_IHEX_FAIL_NEAR1
        staa    LOADER_COUNT
        staa    LOADER_SUM
        ldaa    #3
        staa    LOADER_STAGE
        jsr     SDFS3_READ_HEXBYTE_INPUT
        bcs     SDFS3_READ_IHEX_FAIL_NEAR1
        staa    LOADER_ADDR
        jsr     SDFS3_ADD_TO_LOADER_SUM
        jsr     SDFS3_READ_HEXBYTE_INPUT
        bcs     SDFS3_READ_IHEX_FAIL_NEAR1
        staa    LOADER_ADDR+1
        jsr     SDFS3_ADD_TO_LOADER_SUM
        jsr     SDFS3_READ_HEXBYTE_INPUT
        bcs     SDFS3_READ_IHEX_FAIL_NEAR1
        staa    LOADER_TYPE
        jsr     SDFS3_ADD_TO_LOADER_SUM
        ldaa    LOADER_TYPE
        cmpa    #$00
        beq     SDFS3_READ_IHEX_DATA
        cmpa    #$01
        bne     SDFS3_READ_IHEX_FAIL
        ldaa    LOADER_COUNT
        bne     SDFS3_READ_IHEX_FAIL
        bra     SDFS3_READ_IHEX_DATA
SDFS3_READ_IHEX_FAIL_NEAR1:
        jmp     SDFS3_READ_IHEX_FAIL
SDFS3_READ_IHEX_DATA:
        ldaa    #4
        staa    LOADER_STAGE
        ldab    LOADER_COUNT
SDFS3_READ_IHEX_DATA_LOOP:
        tstb
        beq     SDFS3_READ_IHEX_CHECKSUM
        jsr     SDFS3_READ_HEXBYTE_INPUT
        bcs     SDFS3_READ_IHEX_FAIL
        staa    HEX_NIBBLE
        jsr     SDFS3_ADD_TO_LOADER_SUM
        ldaa    LOADER_TYPE
        cmpa    #$00
        bne     SDFS3_READ_IHEX_SKIP_STORE
        ldaa    HEX_NIBBLE
        pshb
        ldx     LOADER_ADDR
        staa    0,x
        inx
        stx     LOADER_ADDR
        pulb
SDFS3_READ_IHEX_SKIP_STORE:
        decb
        bra     SDFS3_READ_IHEX_DATA_LOOP
SDFS3_READ_IHEX_CHECKSUM:
        ldaa    #5
        staa    LOADER_STAGE
        jsr     SDFS3_READ_HEXBYTE_INPUT
        bcs     SDFS3_READ_IHEX_FAIL
        jsr     SDFS3_ADD_TO_LOADER_SUM
        cmpa    #$00
        bne     SDFS3_READ_IHEX_FAIL
        jsr     SDFS3_READ_RECORD_TRAILER
        bcs     SDFS3_READ_IHEX_FAIL
        ldaa    LOADER_TYPE
        cmpa    #$01
        beq     SDFS3_READ_IHEX_EOF
        ldaa    #0
        clc
        rts
SDFS3_READ_IHEX_EOF:
        ldaa    #1
        clc
        rts
SDFS3_READ_IHEX_FAIL:
        sec
        rts

SDFS3_HEX_TO_NIBBLE:
        cmpa    #'0'
        blo     SDFS3_HEX_TO_NIBBLE_FAIL
        cmpa    #'9'
        bhi     SDFS3_HEX_ALPHA
        suba    #'0'
        clc
        rts
SDFS3_HEX_ALPHA:
        cmpa    #'A'
        blo     SDFS3_HEX_LOWER
        cmpa    #'F'
        bhi     SDFS3_HEX_LOWER
        suba    #'A'
        adda    #10
        clc
        rts
SDFS3_HEX_LOWER:
        cmpa    #'a'
        blo     SDFS3_HEX_TO_NIBBLE_FAIL
        cmpa    #'f'
        bhi     SDFS3_HEX_TO_NIBBLE_FAIL
        suba    #'a'
        adda    #10
        clc
        rts
SDFS3_HEX_TO_NIBBLE_FAIL:
        sec
        rts

SDFS3_ADD_TO_LOADER_SUM:
        adda    LOADER_SUM
        staa    LOADER_SUM
        rts

SDFS3_PRINT_DIR_ENTRY:
        ldx     FAT_ENTRY_PTR
        ldab    #8
SDFS3_PRINT_DIR_NAME_LOOP:
        ldaa    0,x
        cmpa    #CHR_SPACE
        beq     SDFS3_PRINT_DIR_NAME_DONE
        jsr     SDFS3_PUTC
        inx
        decb
        bne     SDFS3_PRINT_DIR_NAME_LOOP
SDFS3_PRINT_DIR_NAME_DONE:
        jsr     SDFS3_DIR_EXT_HAS_CHAR
        bcs     SDFS3_PRINT_DIR_NO_EXT
        ldaa    #'.'
        jsr     SDFS3_PUTC
        ldx     FAT_ENTRY_PTR
        ldab    #8
SDFS3_PRINT_DIR_EXT_SKIP:
        inx
        decb
        bne     SDFS3_PRINT_DIR_EXT_SKIP
        ldab    #3
SDFS3_PRINT_DIR_EXT_LOOP:
        ldaa    0,x
        cmpa    #CHR_SPACE
        beq     SDFS3_PRINT_DIR_EXT_DONE
        jsr     SDFS3_PUTC
        inx
        decb
        bne     SDFS3_PRINT_DIR_EXT_LOOP
SDFS3_PRINT_DIR_EXT_DONE:
SDFS3_PRINT_DIR_NO_EXT:
        ldaa    #CHR_SPACE
        jsr     SDFS3_PUTC
        ldx     FAT_ENTRY_PTR
        ldaa    11,x
        bita    #$10
        beq     SDFS3_PRINT_DIR_ATTR_FILE
        ldaa    #'D'
        bra     SDFS3_PRINT_DIR_ATTR_OUT
SDFS3_PRINT_DIR_ATTR_FILE:
        ldaa    #'A'
SDFS3_PRINT_DIR_ATTR_OUT:
        jsr     SDFS3_PUTC
        ldaa    #CHR_SPACE
        jsr     SDFS3_PUTC
        ldx     FAT_ENTRY_PTR
        ldaa    31,x
        jsr     SDFS3_PRINT_HEX8
        ldaa    30,x
        jsr     SDFS3_PRINT_HEX8
        ldaa    29,x
        jsr     SDFS3_PRINT_HEX8
        ldaa    28,x
        jsr     SDFS3_PRINT_HEX8
        ldaa    #CHR_CR
        jsr     SDFS3_PUTC
        rts

SDFS3_DIR_EXT_HAS_CHAR:
        ldx     FAT_ENTRY_PTR
        ldab    #8
SDFS3_DIR_EXT_SKIP:
        inx
        decb
        bne     SDFS3_DIR_EXT_SKIP
        ldab    #3
SDFS3_DIR_EXT_CHECK_LOOP:
        ldaa    0,x
        cmpa    #CHR_SPACE
        bne     SDFS3_DIR_EXT_FOUND
        inx
        decb
        bne     SDFS3_DIR_EXT_CHECK_LOOP
        sec
        rts
SDFS3_DIR_EXT_FOUND:
        clc
        rts

SDFS3_DIR_ENTRY_VISIBLE:
        ldx     FAT_ENTRY_PTR
        ldaa    11,x
        anda    #$0E
        bne     SDFS3_DIR_ENTRY_SKIP
        ldaa    0,x
        cmpa    #'.'
        beq     SDFS3_DIR_ENTRY_SKIP
        cmpa    #CHR_SPACE
        beq     SDFS3_DIR_ENTRY_SKIP
        ldab    #11
SDFS3_DIR_NAME_CHAR_LOOP:
        ldaa    0,x
        cmpa    #CHR_SPACE
        beq     SDFS3_DIR_NAME_CHAR_OK
        blo     SDFS3_DIR_ENTRY_SKIP
        cmpa    #$7F
        bhs     SDFS3_DIR_ENTRY_SKIP
SDFS3_DIR_NAME_CHAR_OK:
        inx
        decb
        bne     SDFS3_DIR_NAME_CHAR_LOOP
        clc
        rts
SDFS3_DIR_ENTRY_SKIP:
        sec
        rts

SDFS3_PRINT_HEX8:
        psha
        lsra
        lsra
        lsra
        lsra
        bsr     SDFS3_PRINT_NIBBLE
        pula
        bsr     SDFS3_PRINT_NIBBLE
        rts

SDFS3_PRINT_NIBBLE:
        anda    #$0F
        adda    #'0'
        cmpa    #'9'+1
        blo     SDFS3_PRINT_NIBBLE_OUT
        adda    #7
SDFS3_PRINT_NIBBLE_OUT:
        jmp     SDFS3_PUTC

SDFS3_PRINT:
        ldaa    0,x
        beq     SDFS3_PRINT_DONE
        jsr     SDFS3_PUTC
        inx
        bra     SDFS3_PRINT
SDFS3_PRINT_DONE:
        rts

SDFS3_PUTC:
        psha
        jsr     MIKBUG_OUTCH
        pula
        cmpa    #CHR_CR
        bne     SDFS3_PUTC_DONE
        ldaa    #CHR_LF
        jsr     MIKBUG_OUTCH
SDFS3_PUTC_DONE:
        rts

SDFS3_NOT_FOUND:
        ldaa    #SDFS3_ERR_NOT_FOUND
        bra     SDFS3_FAIL_A
SDFS3_FAT_FAIL:
        ldaa    #SDFS3_ERR_IO
SDFS3_FAIL_A:
        staa    SDFS3_LAST_ERROR
        sec
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
SDFS3_TXT_OK:
        fcc     "OK"
        fcb     CHR_CR,0

FAT32_INCLUDE_FIND_API equ 1
FAT32_INCLUDE_FILE_API equ 1

        include "sdcard.asm"
        include "fat32.asm"

SDFS3_END:
        end
