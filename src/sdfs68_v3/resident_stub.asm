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
        jmp     SDFS3_CMD_DIR
SDFS3_CMD_TYPE_STUB:
        jmp     SDFS3_CMD_TYPE
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

FAT32_INCLUDE_FIND_API equ 1
FAT32_INCLUDE_FILE_API equ 1

        include "sdcard.asm"
        include "fat32.asm"

SDFS3_END:
        end
