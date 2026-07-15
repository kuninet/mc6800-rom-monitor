        cpu     6800

        include "../include/hardware.inc"

SDFS_FORMAT_VERSION equ 1
SDFS_HDR_SIZE   equ 16
SDFS_S1_VERSION equ 1
SDFS_S1_COUNT   equ 12
SDFS_COM_LOAD_BASE equ $0100
SDFS_COM_MAX_SIZE equ USER_RAM_END-SDFS_COM_LOAD_BASE+1
SDFS_COM_MAX_HI equ SDFS_COM_MAX_SIZE/256
SDFS_COM_MAX_LO equ SDFS_COM_MAX_SIZE-SDFS_COM_MAX_HI*256

        if S1_SUPPORTED = 0
        error   "SDFS/68 is not supported for this memory configuration"
        endif

        org     SDFS_LOAD_BASE

SDFS_HEADER:
        fcc     "SDFS68"
        fcb     SDFS_FORMAT_VERSION
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
        jsr     SDFS_READ_LINE
        ldab    LINE_LEN
        beq     SDFS_PROMPT_NEXT
        ldaa    LINE_BUF
        jsr     SDFS_TO_UPPER
        cmpa    #'L'
        bne     SDFS_CHECK_DUMP
        jsr     SDFS_CMD_IS_LOAD_LONG
        bcc     SDFS_DO_LOAD_LONG
        jsr     SDFS_CMD_IS_LOAD_LONG_PREFIX
        bcc     SDFS_COMMAND_ERROR
        jsr     SDFS_CMD_COM
        bcs     SDFS_TRY_LOAD_ALIAS
        bra     SDFS_PROMPT_NEXT
SDFS_TRY_LOAD_ALIAS:
        jsr     SDFS_CMD_LOAD_ALIAS
        bra     SDFS_LOAD_RESULT
SDFS_DO_LOAD_LONG:
        jsr     SDFS_CMD_LOAD_LONG
        bcc     SDFS_LOAD_RESULT
        jsr     SDFS_CMD_COM
        bcc     SDFS_PROMPT_NEXT
SDFS_LOAD_RESULT:
        bcc     SDFS_LOAD_OK
        jsr     SDFS_SHOW_LOADER_ERROR
        bra     SDFS_PROMPT_NEXT
SDFS_LOAD_OK:
        ldx     #TXT_OK
        jsr     SDFS_PRINT
        bra     SDFS_PROMPT_NEXT
SDFS_CHECK_DUMP:
        cmpa    #'D'
        bne     SDFS_CHECK_EXIT
        jsr     SDFS_CMD_IS_DIR
        bcs     SDFS_CHECK_DUMP_BYTE
        jsr     SDFS_CMD_DIR
        bcc     SDFS_PROMPT_NEXT
        jsr     SDFS_SHOW_ERROR
        bra     SDFS_PROMPT_NEXT
SDFS_CHECK_DUMP_BYTE:
        jsr     SDFS_CMD_DUMP_BYTE
        bcc     SDFS_PROMPT_NEXT
        bra     SDFS_COMMAND_ERROR
SDFS_CHECK_EXIT:
        cmpa    #'E'
        bne     SDFS_CHECK_RUN
        jsr     SDFS_CMD_IS_EXIT
        bcs     SDFS_COMMAND_ERROR
        jmp     SDFS_CMD_EXIT
SDFS_CHECK_RUN:
        cmpa    #'R'
        bne     SDFS_COMMAND_ERROR
        jsr     SDFS_CMD_RUN
        bcc     SDFS_PROMPT_NEXT
        bra     SDFS_COMMAND_ERROR
SDFS_PROMPT_NEXT:
        jsr     SDFS_PRINT_PROMPT
        bra     SDFS_LOOP
SDFS_COMMAND_ERROR:
        jsr     SDFS_CMD_COM
        bcc     SDFS_PROMPT_NEXT
        jsr     SDFS_SHOW_ERROR
        bra     SDFS_PROMPT_NEXT

SDFS_CMD_LOAD_ALIAS:
        ldab    LINE_LEN
        cmpb    #2
        blo     SDFS_CMD_LOAD_FAIL_NEAR
        subb    #1
        ldx     #LINE_BUF+1
        jmp     SDFS_K_LOAD_FILE

SDFS_CMD_LOAD_LONG:
        ldab    LINE_LEN
        cmpb    #5
        blo     SDFS_CMD_LOAD_FAIL_NEAR
        ldaa    LINE_BUF+4
        cmpa    #CHR_SPACE
        bne     SDFS_CMD_LOAD_FAIL_NEAR
        subb    #4
        ldx     #LINE_BUF+4
        jmp     SDFS_K_LOAD_FILE
SDFS_CMD_LOAD_FAIL_NEAR:
        jmp     SDFS_CMD_LOAD_FAIL

SDFS_CMD_IS_LOAD_LONG:
        ldab    LINE_LEN
        cmpb    #4
        blo     SDFS_CMD_IS_LOAD_LONG_FAIL
        ldaa    LINE_BUF+1
        jsr     SDFS_TO_UPPER
        cmpa    #'O'
        bne     SDFS_CMD_IS_LOAD_LONG_FAIL
        ldaa    LINE_BUF+2
        jsr     SDFS_TO_UPPER
        cmpa    #'A'
        bne     SDFS_CMD_IS_LOAD_LONG_FAIL
        ldaa    LINE_BUF+3
        jsr     SDFS_TO_UPPER
        cmpa    #'D'
        bne     SDFS_CMD_IS_LOAD_LONG_FAIL
        clc
        rts
SDFS_CMD_IS_LOAD_LONG_FAIL:
        sec
        rts

SDFS_CMD_IS_LOAD_LONG_PREFIX:
        ldab    LINE_LEN
        cmpb    #2
        blo     SDFS_CMD_IS_LOAD_LONG_PREFIX_FAIL
        ldaa    LINE_BUF+1
        jsr     SDFS_TO_UPPER
        cmpa    #'O'
        bne     SDFS_CMD_IS_LOAD_LONG_PREFIX_FAIL
        clc
        rts
SDFS_CMD_IS_LOAD_LONG_PREFIX_FAIL:
        sec
        rts

SDFS_K_LOAD_FILE:
        clr     LOADER_MODE
        clr     LOADER_STAGE
        clr     SDFS_RUN_ENTRY_SET
        stx     PATH_PTR
        stab    PATH_LEN
        jsr     SDFS_API_MOUNT
        bcs     SDFS_CMD_LOAD_FAIL
        jsr     SDFS_RESOLVE_FILE_SAVED
        bcs     SDFS_CMD_LOAD_FAIL
        jsr     SDFS_API_STREAM_OPEN
        bcs     SDFS_CMD_LOAD_FAIL
SDFS_LOAD_LOOP:
        jsr     SDFS_READ_LOADER_RECORD
        bcs     SDFS_CMD_LOAD_FAIL
        cmpa    #1
        beq     SDFS_CMD_LOAD_DONE
        bra     SDFS_LOAD_LOOP
SDFS_CMD_LOAD_DONE:
        clc
        rts
SDFS_CMD_LOAD_FAIL:
        sec
        rts

SDFS_CMD_DUMP_BYTE:
        ldab    LINE_LEN
        cmpb    #2
        blo     SDFS_CMD_DUMP_FAIL
        subb    #1
        ldx     #LINE_BUF+1
        jsr     SDFS_PARSE_HEX16
        bcs     SDFS_CMD_DUMP_FAIL
        ldaa    HEX_VALUE_HI
        jsr     SDFS_PRINT_HEX8
        ldaa    HEX_VALUE_LO
        jsr     SDFS_PRINT_HEX8
        ldaa    #CHR_SPACE
        jsr     SDFS_PUTC
        ldx     HEX_VALUE_HI
        ldaa    0,x
        jsr     SDFS_PRINT_HEX8
        ldaa    #CHR_CR
        jsr     SDFS_PUTC
        clc
        rts
SDFS_CMD_DUMP_FAIL:
        sec
        rts

SDFS_CMD_IS_DIR:
        ldab    LINE_LEN
        cmpb    #3
        blo     SDFS_CMD_IS_DIR_FAIL
        ldaa    LINE_BUF+1
        jsr     SDFS_TO_UPPER
        cmpa    #'I'
        bne     SDFS_CMD_IS_DIR_FAIL
        ldaa    LINE_BUF+2
        jsr     SDFS_TO_UPPER
        cmpa    #'R'
        bne     SDFS_CMD_IS_DIR_FAIL
        ldab    LINE_LEN
        cmpb    #3
        beq     SDFS_CMD_IS_DIR_OK
        ldaa    LINE_BUF+3
        cmpa    #CHR_SPACE
        bne     SDFS_CMD_IS_DIR_FAIL
SDFS_CMD_IS_DIR_OK:
        clc
        rts
SDFS_CMD_IS_DIR_FAIL:
        sec
        rts

SDFS_CMD_IS_EXIT:
        ldab    LINE_LEN
        cmpb    #4
        bne     SDFS_CMD_IS_EXIT_FAIL
        ldaa    LINE_BUF+1
        jsr     SDFS_TO_UPPER
        cmpa    #'X'
        bne     SDFS_CMD_IS_EXIT_FAIL
        ldaa    LINE_BUF+2
        jsr     SDFS_TO_UPPER
        cmpa    #'I'
        bne     SDFS_CMD_IS_EXIT_FAIL
        ldaa    LINE_BUF+3
        jsr     SDFS_TO_UPPER
        cmpa    #'T'
        bne     SDFS_CMD_IS_EXIT_FAIL
        clc
        rts
SDFS_CMD_IS_EXIT_FAIL:
        sec
        rts

SDFS_CMD_EXIT:
        lds     #STACK_TOP
        jmp     MONITOR_REENTRY

SDFS_CMD_RUN:
        ldab    LINE_LEN
        cmpb    #5
        blo     SDFS_CMD_RUN_FAIL
        ldaa    LINE_BUF+1
        jsr     SDFS_TO_UPPER
        cmpa    #'U'
        bne     SDFS_CMD_RUN_FAIL
        ldaa    LINE_BUF+2
        jsr     SDFS_TO_UPPER
        cmpa    #'N'
        bne     SDFS_CMD_RUN_FAIL
        ldaa    LINE_BUF+3
        cmpa    #CHR_SPACE
        bne     SDFS_CMD_RUN_FAIL
        subb    #3
        ldx     #LINE_BUF+3
        jsr     SDFS_PARSE_HEX16
        bcs     SDFS_CMD_RUN_FILE
        lds     #STACK_TOP
        ldx     HEX_VALUE_HI
        jmp     0,x
SDFS_CMD_RUN_FILE:
        ldab    LINE_LEN
        subb    #3
        ldx     #LINE_BUF+3
        jsr     SDFS_K_LOAD_FILE
        bcs     SDFS_CMD_RUN_FAIL
        ldaa    LOADER_MODE
        cmpa    #LOAD_MODE_SREC
        bne     SDFS_CMD_RUN_FAIL
        ldaa    SDFS_RUN_ENTRY_SET
        beq     SDFS_CMD_RUN_FAIL
        lds     #STACK_TOP
        ldx     SDFS_RUN_ENTRY
        jmp     0,x
SDFS_CMD_RUN_FAIL:
        sec
        rts

SDFS_CMD_COM:
        ldab    LINE_LEN
        ldx     #LINE_BUF
        jsr     SDFS_PARSE_COM_PATH_COMMAND
        bcs     SDFS_CMD_COM_FAIL
        jsr     SDFS_API_MOUNT
        bcs     SDFS_CMD_COM_FAIL
        jsr     SDFS_RESOLVE_FILE_SAVED
        bcs     SDFS_CMD_COM_FAIL
        jsr     SDFS_PARSE_COM_CHECK_EXT
        bcs     SDFS_CMD_COM_FAIL
        jsr     SDFS_COM_CHECK_SIZE
        bcs     SDFS_CMD_COM_FAIL
        jsr     SDFS_API_STREAM_OPEN
        bcs     SDFS_CMD_COM_FAIL
        jsr     SDFS_COM_LOAD_RAW
        bcs     SDFS_CMD_COM_FAIL
        jsr     SDFS_COM_RESTORE_ARGS
        lds     #STACK_TOP
        ldx     ARG2_PTR
        ldab    ARG2_LEN
        clra
        jsr     SDFS_COM_LOAD_BASE
        jmp     SDFS_PROMPT_NEXT
SDFS_CMD_COM_FAIL:
        sec
        rts

SDFS_COM_CHECK_SIZE:
        ldaa    FAT_FILE_SIZE0
        oraa    FAT_FILE_SIZE1
        bne     SDFS_COM_CHECK_FAIL
        ldaa    FAT_FILE_SIZE2
        oraa    FAT_FILE_SIZE3
        beq     SDFS_COM_CHECK_FAIL
        ldaa    FAT_FILE_SIZE2
        cmpa    #SDFS_COM_MAX_HI
        bhi     SDFS_COM_CHECK_FAIL
        blo     SDFS_COM_CHECK_OK
        ldaa    FAT_FILE_SIZE3
        cmpa    #SDFS_COM_MAX_LO
        bhi     SDFS_COM_CHECK_FAIL
SDFS_COM_CHECK_OK:
        clc
        rts
SDFS_COM_CHECK_FAIL:
        sec
        rts

SDFS_COM_LOAD_RAW:
        ldx     #SDFS_COM_LOAD_BASE
        stx     FAT_READ_PTR
SDFS_COM_LOAD_LOOP:
        jsr     SDFS_API_STREAM_BYTES_REMAIN
        bcc     SDFS_COM_LOAD_DONE
        jsr     SDFS_API_STREAM_GETC
        bcs     SDFS_COM_LOAD_FAIL
        ldx     FAT_READ_PTR
        staa    0,x
        inx
        stx     FAT_READ_PTR
        bra     SDFS_COM_LOAD_LOOP
SDFS_COM_LOAD_DONE:
        clc
        rts
SDFS_COM_LOAD_FAIL:
        sec
        rts

SDFS_COM_RESTORE_ARGS:
        ldx     PATH_ARG_PTR
        stx     ARG2_PTR
        ldaa    PATH_ARG_LEN
        staa    ARG2_LEN
        rts

SDFS_CMD_DIR:
        ldab    LINE_LEN
        cmpb    #3
        bne     SDFS_CMD_DIR_PATH
        jsr     SDFS_K_DIR_ROOT
        rts
SDFS_CMD_DIR_PATH:
        ldab    LINE_LEN
        subb    #3
        ldx     #LINE_BUF+3
        stx     PATH_PTR
        stab    PATH_LEN
        jsr     SDFS_K_DIR_PATH
        rts

SDFS_K_DIR_ROOT:
        jsr     SDFS_API_MOUNT
        bcs     SDFS_K_DIR_FAIL
        jsr     SDFS_K_COPY_ROOT_TO_CUR
        bra     SDFS_K_DIR_CLUSTER_LOOP

SDFS_K_DIR_PATH:
        jsr     SDFS_API_MOUNT
        bcs     SDFS_K_DIR_FAIL
        jsr     SDFS_RESOLVE_DIR_SAVED
        bcs     SDFS_K_DIR_FAIL
SDFS_K_DIR_CLUSTER_LOOP:
        jsr     SDFS_API_CLUSTER_TO_SD_LBA
        ldx     #SD_SECTOR_BUF
        jsr     SDFS_API_READ_SECTOR
        bcs     SDFS_K_DIR_FAIL
        ldx     #SD_SECTOR_BUF
        stx     FAT_ENTRY_PTR
        ldaa    #16
        staa    FAT_DIR_COUNT
SDFS_K_DIR_ENTRY_LOOP:
        ldx     FAT_ENTRY_PTR
        ldaa    0,x
        beq     SDFS_K_DIR_DONE
        cmpa    #$E5
        beq     SDFS_K_DIR_NEXT_ENTRY
        jsr     SDFS_K_DIR_ENTRY_VISIBLE
        bcs     SDFS_K_DIR_NEXT_ENTRY
        jsr     SDFS_K_PRINT_DIR_ENTRY
SDFS_K_DIR_NEXT_ENTRY:
        jsr     SDFS_K_ADVANCE_ENTRY_PTR
        dec     FAT_DIR_COUNT
        bne     SDFS_K_DIR_ENTRY_LOOP
        jsr     SDFS_API_NEXT_CLUSTER
        bcs     SDFS_K_DIR_DONE
        jsr     SDFS_API_COPY_NEXT_TO_CUR
        bra     SDFS_K_DIR_CLUSTER_LOOP
SDFS_K_DIR_DONE:
        clc
        rts
SDFS_K_DIR_FAIL:
        sec
        rts

SDFS_K_COPY_ROOT_TO_CUR:
        ldaa    FAT_ROOT_CLUS0
        staa    FAT_CUR_CLUS0
        ldaa    FAT_ROOT_CLUS1
        staa    FAT_CUR_CLUS1
        ldaa    FAT_ROOT_CLUS2
        staa    FAT_CUR_CLUS2
        ldaa    FAT_ROOT_CLUS3
        staa    FAT_CUR_CLUS3
        rts

SDFS_RESOLVE_FILE_SAVED:
        jsr     SDFS_PATH_START
        bcs     SDFS_RESOLVE_FAIL
SDFS_RESOLVE_FILE_LOOP:
        jsr     SDFS_PATH_COMPONENT
        bcs     SDFS_RESOLVE_FAIL
        jsr     SDFS_FIND_IN_CUR
        bcs     SDFS_RESOLVE_FAIL
        tst     PATH_DELIM
        beq     SDFS_RESOLVE_FILE_LAST
        jsr     SDFS_ENTRY_IS_DIR
        bcs     SDFS_RESOLVE_FAIL
        jsr     SDFS_COPY_FILE_TO_CUR
        bra     SDFS_RESOLVE_FILE_LOOP
SDFS_RESOLVE_FILE_LAST:
        jsr     SDFS_ENTRY_IS_FILE
        bcs     SDFS_RESOLVE_FAIL
        clc
        rts

SDFS_RESOLVE_DIR_SAVED:
        jsr     SDFS_PATH_START_ALLOW_ROOT
        bcs     SDFS_RESOLVE_FAIL
        tst     PATH_LEN
        beq     SDFS_RESOLVE_OK
SDFS_RESOLVE_DIR_LOOP:
        jsr     SDFS_PATH_COMPONENT
        bcs     SDFS_RESOLVE_FAIL
        jsr     SDFS_FIND_IN_CUR
        bcs     SDFS_RESOLVE_FAIL
        jsr     SDFS_ENTRY_IS_DIR
        bcs     SDFS_RESOLVE_FAIL
        jsr     SDFS_COPY_FILE_TO_CUR
        tst     PATH_DELIM
        bne     SDFS_RESOLVE_DIR_LOOP
SDFS_RESOLVE_OK:
        clc
        rts
SDFS_RESOLVE_FAIL:
        sec
        rts

SDFS_PATH_START:
        jsr     SDFS_PATH_SKIP_HEAD
        bcs     SDFS_PATH_START_FAIL
        tst     PATH_LEN
        beq     SDFS_PATH_START_FAIL
        jsr     SDFS_K_COPY_ROOT_TO_CUR
        clc
        rts
SDFS_PATH_START_ALLOW_ROOT:
        jsr     SDFS_PATH_SKIP_HEAD
        bcs     SDFS_PATH_START_FAIL
        jsr     SDFS_K_COPY_ROOT_TO_CUR
        clc
        rts
SDFS_PATH_START_FAIL:
        sec
        rts

SDFS_PATH_SKIP_HEAD:
        tst     PATH_LEN
        beq     SDFS_PATH_SKIP_DONE
        ldx     PATH_PTR
        ldaa    0,x
        cmpa    #CHR_SPACE
        beq     SDFS_PATH_SKIP_ONE
        cmpa    #'/'
        beq     SDFS_PATH_SKIP_SLASH
        bra     SDFS_PATH_SKIP_DONE
SDFS_PATH_SKIP_ONE:
        inx
        stx     PATH_PTR
        dec     PATH_LEN
        bra     SDFS_PATH_SKIP_HEAD
SDFS_PATH_SKIP_SLASH:
        inx
        stx     PATH_PTR
        dec     PATH_LEN
        beq     SDFS_PATH_SKIP_FAIL
SDFS_PATH_SKIP_DONE:
        clc
        rts
SDFS_PATH_SKIP_FAIL:
        sec
        rts

SDFS_PATH_COMPONENT:
        ldx     PATH_PTR
        stx     ARG2_PTR
        clr     ARG2_LEN
        clr     PATH_DELIM
SDFS_PATH_COMPONENT_LOOP:
        tst     PATH_LEN
        beq     SDFS_PATH_COMPONENT_DONE
        ldx     PATH_PTR
        ldaa    0,x
        cmpa    #'/'
        beq     SDFS_PATH_COMPONENT_SLASH
        cmpa    #CHR_SPACE
        beq     SDFS_PATH_COMPONENT_SPACE
        inx
        stx     PATH_PTR
        dec     PATH_LEN
        inc     ARG2_LEN
        bra     SDFS_PATH_COMPONENT_LOOP
SDFS_PATH_COMPONENT_SLASH:
        ldaa    ARG2_LEN
        beq     SDFS_PATH_COMPONENT_FAIL
        ldx     PATH_PTR
        inx
        stx     PATH_PTR
        dec     PATH_LEN
        ldaa    #1
        staa    PATH_DELIM
        tst     PATH_LEN
        beq     SDFS_PATH_COMPONENT_FAIL
        bra     SDFS_PATH_COMPONENT_PARSE
SDFS_PATH_COMPONENT_SPACE:
        jsr     SDFS_PATH_SKIP_TRAILING
        bcs     SDFS_PATH_COMPONENT_FAIL
SDFS_PATH_COMPONENT_DONE:
        ldaa    ARG2_LEN
        beq     SDFS_PATH_COMPONENT_FAIL
SDFS_PATH_COMPONENT_PARSE:
        ldx     ARG2_PTR
        ldab    ARG2_LEN
        jsr     SDFS_PARSE_FILENAME_83
        bcs     SDFS_PATH_COMPONENT_FAIL
        clc
        rts
SDFS_PATH_COMPONENT_FAIL:
        sec
        rts

SDFS_PATH_SKIP_TRAILING:
        tst     PATH_LEN
        beq     SDFS_PATH_SKIP_TRAILING_OK
        ldx     PATH_PTR
        ldaa    0,x
        cmpa    #CHR_SPACE
        bne     SDFS_PATH_SKIP_TRAILING_FAIL
        inx
        stx     PATH_PTR
        dec     PATH_LEN
        bra     SDFS_PATH_SKIP_TRAILING
SDFS_PATH_SKIP_TRAILING_OK:
        clc
        rts
SDFS_PATH_SKIP_TRAILING_FAIL:
        sec
        rts

SDFS_FIND_IN_CUR:
        jsr     SDFS_API_CLUSTER_TO_SD_LBA
        ldx     #SD_SECTOR_BUF
        jsr     SDFS_API_READ_SECTOR
        bcs     SDFS_FIND_IN_CUR_FAIL
        ldx     #SD_SECTOR_BUF
        stx     FAT_ENTRY_PTR
        ldaa    #16
        staa    FAT_DIR_COUNT
SDFS_FIND_IN_CUR_ENTRY_LOOP:
        ldx     FAT_ENTRY_PTR
        ldaa    0,x
        beq     SDFS_FIND_IN_CUR_FAIL
        cmpa    #$E5
        beq     SDFS_FIND_IN_CUR_NEXT_ENTRY
        ldaa    11,x
        anda    #$0F
        cmpa    #$0F
        beq     SDFS_FIND_IN_CUR_NEXT_ENTRY
        ldaa    11,x
        bita    #$08
        bne     SDFS_FIND_IN_CUR_NEXT_ENTRY
        jsr     SDFS_COMPARE_ENTRY_NAME
        bcc     SDFS_FIND_IN_CUR_MATCH
SDFS_FIND_IN_CUR_NEXT_ENTRY:
        jsr     SDFS_K_ADVANCE_ENTRY_PTR
        dec     FAT_DIR_COUNT
        bne     SDFS_FIND_IN_CUR_ENTRY_LOOP
        jsr     SDFS_API_NEXT_CLUSTER
        bcs     SDFS_FIND_IN_CUR_FAIL
        jsr     SDFS_API_COPY_NEXT_TO_CUR
        bra     SDFS_FIND_IN_CUR
SDFS_FIND_IN_CUR_MATCH:
        jsr     SDFS_STORE_FILE_ENTRY
        clc
        rts
SDFS_FIND_IN_CUR_FAIL:
        sec
        rts

SDFS_COMPARE_ENTRY_NAME:
        ldx     FAT_ENTRY_PTR
        ldaa    0,x
        cmpa    FAT_FIND_NAME0
        bne     SDFS_COMPARE_ENTRY_NAME_FAIL
        ldaa    1,x
        cmpa    FAT_FIND_NAME1
        bne     SDFS_COMPARE_ENTRY_NAME_FAIL
        ldaa    2,x
        cmpa    FAT_FIND_NAME2
        bne     SDFS_COMPARE_ENTRY_NAME_FAIL
        ldaa    3,x
        cmpa    FAT_FIND_NAME3
        bne     SDFS_COMPARE_ENTRY_NAME_FAIL
        ldaa    4,x
        cmpa    FAT_FIND_NAME4
        bne     SDFS_COMPARE_ENTRY_NAME_FAIL
        ldaa    5,x
        cmpa    FAT_FIND_NAME5
        bne     SDFS_COMPARE_ENTRY_NAME_FAIL
        ldaa    6,x
        cmpa    FAT_FIND_NAME6
        bne     SDFS_COMPARE_ENTRY_NAME_FAIL
        ldaa    7,x
        cmpa    FAT_FIND_NAME7
        bne     SDFS_COMPARE_ENTRY_NAME_FAIL
        ldaa    8,x
        cmpa    FAT_FIND_NAME8
        bne     SDFS_COMPARE_ENTRY_NAME_FAIL
        ldaa    9,x
        cmpa    FAT_FIND_NAME9
        bne     SDFS_COMPARE_ENTRY_NAME_FAIL
        ldaa    10,x
        cmpa    FAT_FIND_NAME10
        bne     SDFS_COMPARE_ENTRY_NAME_FAIL
        clc
        rts
SDFS_COMPARE_ENTRY_NAME_FAIL:
        sec
        rts

SDFS_STORE_FILE_ENTRY:
        ldx     FAT_ENTRY_PTR
        ldaa    21,x
        staa    FAT_FILE_CLUS0
        ldaa    20,x
        staa    FAT_FILE_CLUS1
        ldaa    27,x
        staa    FAT_FILE_CLUS2
        ldaa    26,x
        staa    FAT_FILE_CLUS3
        ldaa    31,x
        staa    FAT_FILE_SIZE0
        ldaa    30,x
        staa    FAT_FILE_SIZE1
        ldaa    29,x
        staa    FAT_FILE_SIZE2
        ldaa    28,x
        staa    FAT_FILE_SIZE3
        rts

SDFS_COPY_FILE_TO_CUR:
        ldaa    FAT_FILE_CLUS0
        staa    FAT_CUR_CLUS0
        ldaa    FAT_FILE_CLUS1
        staa    FAT_CUR_CLUS1
        ldaa    FAT_FILE_CLUS2
        staa    FAT_CUR_CLUS2
        ldaa    FAT_FILE_CLUS3
        staa    FAT_CUR_CLUS3
        rts

SDFS_ENTRY_IS_DIR:
        ldx     FAT_ENTRY_PTR
        ldaa    11,x
        bita    #$10
        beq     SDFS_ENTRY_IS_DIR_FAIL
        clc
        rts
SDFS_ENTRY_IS_DIR_FAIL:
        sec
        rts

SDFS_ENTRY_IS_FILE:
        ldx     FAT_ENTRY_PTR
        ldaa    11,x
        bita    #$18
        bne     SDFS_ENTRY_IS_FILE_FAIL
        clc
        rts
SDFS_ENTRY_IS_FILE_FAIL:
        sec
        rts

SDFS_K_ADVANCE_ENTRY_PTR:
        ldx     FAT_ENTRY_PTR
        ldab    #32
SDFS_K_ADVANCE_ENTRY_PTR_LOOP:
        inx
        decb
        bne     SDFS_K_ADVANCE_ENTRY_PTR_LOOP
        stx     FAT_ENTRY_PTR
        rts

SDFS_K_PRINT_DIR_ENTRY:
        ldx     FAT_ENTRY_PTR
        ldab    #8
SDFS_K_PRINT_DIR_NAME_LOOP:
        ldaa    0,x
        cmpa    #CHR_SPACE
        beq     SDFS_K_PRINT_DIR_NAME_DONE
        jsr     SDFS_PUTC
        inx
        decb
        bne     SDFS_K_PRINT_DIR_NAME_LOOP
SDFS_K_PRINT_DIR_NAME_DONE:
        jsr     SDFS_K_DIR_EXT_HAS_CHAR
        bcs     SDFS_K_PRINT_DIR_NO_EXT
        ldaa    #'.'
        jsr     SDFS_PUTC
        ldx     FAT_ENTRY_PTR
        ldab    #8
SDFS_K_PRINT_DIR_EXT_SKIP:
        inx
        decb
        bne     SDFS_K_PRINT_DIR_EXT_SKIP
        ldab    #3
SDFS_K_PRINT_DIR_EXT_LOOP:
        ldaa    0,x
        cmpa    #CHR_SPACE
        beq     SDFS_K_PRINT_DIR_EXT_DONE
        jsr     SDFS_PUTC
        inx
        decb
        bne     SDFS_K_PRINT_DIR_EXT_LOOP
SDFS_K_PRINT_DIR_EXT_DONE:
SDFS_K_PRINT_DIR_NO_EXT:
        ldaa    #CHR_SPACE
        jsr     SDFS_PUTC
        ldx     FAT_ENTRY_PTR
        ldaa    11,x
        bita    #$10
        beq     SDFS_K_PRINT_DIR_ATTR_FILE
        ldaa    #'D'
        bra     SDFS_K_PRINT_DIR_ATTR_OUT
SDFS_K_PRINT_DIR_ATTR_FILE:
        ldaa    #'A'
SDFS_K_PRINT_DIR_ATTR_OUT:
        jsr     SDFS_PUTC
        ldaa    #CHR_SPACE
        jsr     SDFS_PUTC
        ldx     FAT_ENTRY_PTR
        ldaa    31,x
        jsr     SDFS_PRINT_HEX8
        ldaa    30,x
        jsr     SDFS_PRINT_HEX8
        ldaa    29,x
        jsr     SDFS_PRINT_HEX8
        ldaa    28,x
        jsr     SDFS_PRINT_HEX8
        ldaa    #CHR_CR
        jsr     SDFS_PUTC
        rts

SDFS_K_DIR_EXT_HAS_CHAR:
        ldx     FAT_ENTRY_PTR
        ldab    #8
SDFS_K_DIR_EXT_SKIP:
        inx
        decb
        bne     SDFS_K_DIR_EXT_SKIP
        ldab    #3
SDFS_K_DIR_EXT_CHECK_LOOP:
        ldaa    0,x
        cmpa    #CHR_SPACE
        bne     SDFS_K_DIR_EXT_FOUND
        inx
        decb
        bne     SDFS_K_DIR_EXT_CHECK_LOOP
        sec
        rts
SDFS_K_DIR_EXT_FOUND:
        clc
        rts

SDFS_K_DIR_ENTRY_VISIBLE:
        ldx     FAT_ENTRY_PTR
        ldaa    11,x
        anda    #$0E
        bne     SDFS_K_DIR_ENTRY_SKIP
        ldaa    0,x
        cmpa    #'.'
        beq     SDFS_K_DIR_ENTRY_SKIP
        cmpa    #CHR_SPACE
        beq     SDFS_K_DIR_ENTRY_SKIP
        ldab    #11
SDFS_K_DIR_NAME_CHAR_LOOP:
        ldaa    0,x
        cmpa    #CHR_SPACE
        beq     SDFS_K_DIR_NAME_CHAR_OK
        blo     SDFS_K_DIR_ENTRY_SKIP
        cmpa    #$7F
        bhs     SDFS_K_DIR_ENTRY_SKIP
SDFS_K_DIR_NAME_CHAR_OK:
        inx
        decb
        bne     SDFS_K_DIR_NAME_CHAR_LOOP
        clc
        rts
SDFS_K_DIR_ENTRY_SKIP:
        sec
        rts

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

SDFS_API_STREAM_OPEN:
        jsr     S1_BASE+34
        rts

SDFS_API_STREAM_GETC:
        jsr     S1_BASE+37
        rts

SDFS_API_STREAM_BYTES_REMAIN:
        jsr     S1_BASE+40
        rts

SDFS_API_CLUSTER_TO_SD_LBA:
        jsr     S1_BASE+43
        rts

SDFS_API_NEXT_CLUSTER:
        jsr     S1_BASE+46
        rts

SDFS_API_COPY_NEXT_TO_CUR:
        jsr     S1_BASE+49
        rts

SDFS_READ_LINE:
        ldx     #LINE_BUF
        stx     LINE_PTR
        clr     LINE_LEN
SDFS_READ_LINE_LOOP:
        jsr     MIKBUG_INCH
        cmpa    #CHR_LF
        beq     SDFS_READ_LINE_LOOP
        cmpa    #CHR_CR
        beq     SDFS_READ_LINE_DONE
        cmpa    #CHR_BS
        beq     SDFS_READ_LINE_BACKSPACE_BS
        cmpa    #CHR_DEL
        beq     SDFS_READ_LINE_BACKSPACE_DEL
        cmpa    #CHR_SPACE
        blo     SDFS_READ_LINE_LOOP
        ldab    LINE_LEN
        cmpb    #LINE_BUF_SIZE
        bhs     SDFS_READ_LINE_LOOP
        ldx     LINE_PTR
        staa    0,x
        inx
        stx     LINE_PTR
        inc     LINE_LEN
        bra     SDFS_READ_LINE_LOOP
SDFS_READ_LINE_BACKSPACE_BS:
        jsr     SDFS_READ_LINE_BACKSPACE
        bcs     SDFS_READ_LINE_LOOP
        ldaa    #CHR_SPACE
        jsr     MIKBUG_OUTCH
        ldaa    #CHR_BS
        jsr     MIKBUG_OUTCH
        bra     SDFS_READ_LINE_LOOP
SDFS_READ_LINE_BACKSPACE_DEL:
        jsr     SDFS_READ_LINE_BACKSPACE
        bcs     SDFS_READ_LINE_LOOP
        ldaa    #CHR_BS
        jsr     MIKBUG_OUTCH
        ldaa    #CHR_SPACE
        jsr     MIKBUG_OUTCH
        ldaa    #CHR_BS
        jsr     MIKBUG_OUTCH
        bra     SDFS_READ_LINE_LOOP
SDFS_READ_LINE_BACKSPACE:
        tst     LINE_LEN
        beq     SDFS_READ_LINE_BACKSPACE_EMPTY
        ldx     LINE_PTR
        dex
        stx     LINE_PTR
        dec     LINE_LEN
        clc
        rts
SDFS_READ_LINE_BACKSPACE_EMPTY:
        sec
        rts
SDFS_READ_LINE_DONE:
        ldaa    #CHR_CR
        jsr     SDFS_PUTC
        rts

SDFS_PARSE_FILENAME_83:
        stx     ARG_PTR
        stab    ARG_LEN
        jsr     SDFS_CLEAR_FIND_NAME
SDFS_PARSE_FILENAME_SKIP_HEAD:
        tst     ARG_LEN
        bne     SDFS_PARSE_FILENAME_SKIP_HAS
        jmp     SDFS_PARSE_FILENAME_FAIL
SDFS_PARSE_FILENAME_SKIP_HAS:
        ldx     ARG_PTR
        ldaa    0,x
        cmpa    #CHR_SPACE
        bne     SDFS_PARSE_FILENAME_NAME_START
        inx
        stx     ARG_PTR
        dec     ARG_LEN
        bra     SDFS_PARSE_FILENAME_SKIP_HEAD

SDFS_PARSE_FILENAME_NAME_START:
        ldx     #FAT_FIND_NAME0
        stx     FAT_ENTRY_PTR
        clr     ARG2_LEN
SDFS_PARSE_FILENAME_NAME_LOOP:
        tst     ARG_LEN
        beq     SDFS_PARSE_FILENAME_NAME_DONE
        ldx     ARG_PTR
        ldaa    0,x
        cmpa    #CHR_SPACE
        bne     SDFS_PARSE_FILENAME_NAME_NOT_SPACE
        jmp     SDFS_PARSE_FILENAME_TRAILING
SDFS_PARSE_FILENAME_NAME_NOT_SPACE:
        cmpa    #'.'
        bne     SDFS_PARSE_FILENAME_NAME_NOT_DOT
        jmp     SDFS_PARSE_FILENAME_EXT_START
SDFS_PARSE_FILENAME_NAME_NOT_DOT:
        ldab    ARG2_LEN
        cmpb    #8
        blo     SDFS_PARSE_FILENAME_NAME_ROOM
        jmp     SDFS_PARSE_FILENAME_FAIL
SDFS_PARSE_FILENAME_NAME_ROOM:
        jsr     SDFS_TO_UPPER
        ldx     FAT_ENTRY_PTR
        staa    0,x
        inx
        stx     FAT_ENTRY_PTR
        inc     ARG2_LEN
        ldx     ARG_PTR
        inx
        stx     ARG_PTR
        dec     ARG_LEN
        bra     SDFS_PARSE_FILENAME_NAME_LOOP

SDFS_PARSE_FILENAME_NAME_DONE:
        tst     ARG2_LEN
        bne     SDFS_PARSE_FILENAME_NAME_OK
        jmp     SDFS_PARSE_FILENAME_FAIL
SDFS_PARSE_FILENAME_NAME_OK:
        jmp     SDFS_PARSE_FILENAME_OK

SDFS_PARSE_FILENAME_EXT_START:
        tst     ARG2_LEN
        bne     SDFS_PARSE_FILENAME_EXT_NAME_OK
        jmp     SDFS_PARSE_FILENAME_FAIL
SDFS_PARSE_FILENAME_EXT_NAME_OK:
        ldx     ARG_PTR
        inx
        stx     ARG_PTR
        dec     ARG_LEN
        ldx     #FAT_FIND_NAME8
        stx     FAT_ENTRY_PTR
        clr     ARG2_LEN
SDFS_PARSE_FILENAME_EXT_LOOP:
        tst     ARG_LEN
        bne     SDFS_PARSE_FILENAME_EXT_HAS_LEN
        jmp     SDFS_PARSE_FILENAME_OK
SDFS_PARSE_FILENAME_EXT_HAS_LEN:
        ldx     ARG_PTR
        ldaa    0,x
        cmpa    #CHR_SPACE
        bne     SDFS_PARSE_FILENAME_EXT_NOT_SPACE
        jmp     SDFS_PARSE_FILENAME_TRAILING
SDFS_PARSE_FILENAME_EXT_NOT_SPACE:
        cmpa    #'.'
        bne     SDFS_PARSE_FILENAME_EXT_CHAR_OK
        jmp     SDFS_PARSE_FILENAME_FAIL
SDFS_PARSE_FILENAME_EXT_CHAR_OK:
        ldab    ARG2_LEN
        cmpb    #3
        blo     SDFS_PARSE_FILENAME_EXT_ROOM
        jmp     SDFS_PARSE_FILENAME_FAIL
SDFS_PARSE_FILENAME_EXT_ROOM:
        jsr     SDFS_TO_UPPER
        ldx     FAT_ENTRY_PTR
        staa    0,x
        inx
        stx     FAT_ENTRY_PTR
        inc     ARG2_LEN
        ldx     ARG_PTR
        inx
        stx     ARG_PTR
        dec     ARG_LEN
        bra     SDFS_PARSE_FILENAME_EXT_LOOP

SDFS_PARSE_FILENAME_TRAILING:
        ldx     ARG_PTR
        inx
        stx     ARG_PTR
        dec     ARG_LEN
SDFS_PARSE_FILENAME_TRAILING_LOOP:
        tst     ARG_LEN
        beq     SDFS_PARSE_FILENAME_OK
        ldx     ARG_PTR
        ldaa    0,x
        cmpa    #CHR_SPACE
        beq     SDFS_PARSE_FILENAME_TRAILING_SPACE_OK
        jmp     SDFS_PARSE_FILENAME_FAIL
SDFS_PARSE_FILENAME_TRAILING_SPACE_OK:
        inx
        stx     ARG_PTR
        dec     ARG_LEN
        bra     SDFS_PARSE_FILENAME_TRAILING_LOOP

SDFS_PARSE_FILENAME_OK:
        clc
        rts
SDFS_PARSE_FILENAME_FAIL:
        sec
        rts

SDFS_PARSE_COM_PATH_COMMAND:
        stx     ARG_PTR
        stab    ARG_LEN
SDFS_PARSE_COM_PATH_SKIP_HEAD:
        tst     ARG_LEN
        beq     SDFS_PARSE_COM_PATH_FAIL
        ldx     ARG_PTR
        ldaa    0,x
        cmpa    #CHR_SPACE
        bne     SDFS_PARSE_COM_PATH_START
        inx
        stx     ARG_PTR
        dec     ARG_LEN
        bra     SDFS_PARSE_COM_PATH_SKIP_HEAD
SDFS_PARSE_COM_PATH_START:
        ldx     ARG_PTR
        stx     PATH_PTR
        clr     PATH_LEN
SDFS_PARSE_COM_PATH_TOKEN:
        tst     ARG_LEN
        beq     SDFS_PARSE_COM_PATH_NO_ARGS
        ldx     ARG_PTR
        ldaa    0,x
        cmpa    #CHR_SPACE
        beq     SDFS_PARSE_COM_PATH_ARG_SKIP
        inx
        stx     ARG_PTR
        dec     ARG_LEN
        inc     PATH_LEN
        bra     SDFS_PARSE_COM_PATH_TOKEN
SDFS_PARSE_COM_PATH_ARG_SKIP:
        ldaa    PATH_LEN
        beq     SDFS_PARSE_COM_PATH_FAIL
        ldx     ARG_PTR
        inx
        stx     ARG_PTR
        dec     ARG_LEN
SDFS_PARSE_COM_PATH_ARG_SKIP_LOOP:
        tst     ARG_LEN
        beq     SDFS_PARSE_COM_PATH_NO_ARGS
        ldx     ARG_PTR
        ldaa    0,x
        cmpa    #CHR_SPACE
        bne     SDFS_PARSE_COM_PATH_ARGS
        inx
        stx     ARG_PTR
        dec     ARG_LEN
        bra     SDFS_PARSE_COM_PATH_ARG_SKIP_LOOP
SDFS_PARSE_COM_PATH_ARGS:
        ldx     ARG_PTR
        stx     PATH_ARG_PTR
        ldaa    ARG_LEN
        staa    PATH_ARG_LEN
        clc
        rts
SDFS_PARSE_COM_PATH_NO_ARGS:
        ldaa    PATH_LEN
        beq     SDFS_PARSE_COM_PATH_FAIL
        ldx     ARG_PTR
        stx     PATH_ARG_PTR
        clr     PATH_ARG_LEN
        clc
        rts
SDFS_PARSE_COM_PATH_FAIL:
        sec
        rts

SDFS_PARSE_COM_CHECK_EXT:
        ldaa    FAT_FIND_NAME8
        cmpa    #'C'
        bne     SDFS_PARSE_COM_CHECK_FAIL
        ldaa    FAT_FIND_NAME9
        cmpa    #'O'
        bne     SDFS_PARSE_COM_CHECK_FAIL
        ldaa    FAT_FIND_NAME10
        cmpa    #'M'
        bne     SDFS_PARSE_COM_CHECK_FAIL
        clc
        rts
SDFS_PARSE_COM_CHECK_FAIL:
        sec
        rts

SDFS_CLEAR_FIND_NAME:
        ldx     #FAT_FIND_NAME0
        ldab    #11
SDFS_CLEAR_FIND_NAME_LOOP:
        ldaa    #CHR_SPACE
        staa    0,x
        inx
        decb
        bne     SDFS_CLEAR_FIND_NAME_LOOP
        rts

SDFS_TO_UPPER:
        cmpa    #'a'
        blo     SDFS_TO_UPPER_DONE
        cmpa    #'z'
        bhi     SDFS_TO_UPPER_DONE
        suba    #$20
SDFS_TO_UPPER_DONE:
        rts

SDFS_PARSE_HEX16:
        stx     ARG_PTR
        stab    ARG_LEN
        clr     HEX_VALUE_HI
        clr     HEX_VALUE_LO
        clr     ARG2_LEN
SDFS_PARSE_HEX16_SKIP:
        tst     ARG_LEN
        bne     SDFS_PARSE_HEX16_SKIP_HAS
        jmp     SDFS_PARSE_HEX16_FAIL
SDFS_PARSE_HEX16_SKIP_HAS:
        ldx     ARG_PTR
        ldaa    0,x
        cmpa    #CHR_SPACE
        bne     SDFS_PARSE_HEX16_LOOP
        inx
        stx     ARG_PTR
        dec     ARG_LEN
        bra     SDFS_PARSE_HEX16_SKIP
SDFS_PARSE_HEX16_LOOP:
        tst     ARG_LEN
        beq     SDFS_PARSE_HEX16_DONE
        ldx     ARG_PTR
        ldaa    0,x
        cmpa    #CHR_SPACE
        beq     SDFS_PARSE_HEX16_TRAILING
        jsr     SDFS_HEX_TO_NIBBLE
        bcs     SDFS_PARSE_HEX16_FAIL
        ldab    ARG2_LEN
        cmpb    #4
        bhs     SDFS_PARSE_HEX16_FAIL
        tstb
        beq     SDFS_PARSE_HEX16_HI_H
        cmpb    #1
        beq     SDFS_PARSE_HEX16_HI_L
        cmpb    #2
        beq     SDFS_PARSE_HEX16_LO_H
        oraa    HEX_VALUE_LO
        staa    HEX_VALUE_LO
        bra     SDFS_PARSE_HEX16_ADVANCE
SDFS_PARSE_HEX16_HI_H:
        lsla
        lsla
        lsla
        lsla
        staa    HEX_VALUE_HI
        bra     SDFS_PARSE_HEX16_ADVANCE
SDFS_PARSE_HEX16_HI_L:
        oraa    HEX_VALUE_HI
        staa    HEX_VALUE_HI
        bra     SDFS_PARSE_HEX16_ADVANCE
SDFS_PARSE_HEX16_LO_H:
        lsla
        lsla
        lsla
        lsla
        staa    HEX_VALUE_LO
SDFS_PARSE_HEX16_ADVANCE:
        ldx     ARG_PTR
        inx
        stx     ARG_PTR
        dec     ARG_LEN
        inc     ARG2_LEN
        bra     SDFS_PARSE_HEX16_LOOP
SDFS_PARSE_HEX16_TRAILING:
        ldx     ARG_PTR
        inx
        stx     ARG_PTR
        dec     ARG_LEN
SDFS_PARSE_HEX16_TRAILING_LOOP:
        tst     ARG_LEN
        beq     SDFS_PARSE_HEX16_DONE
        ldx     ARG_PTR
        ldaa    0,x
        cmpa    #CHR_SPACE
        bne     SDFS_PARSE_HEX16_FAIL
        inx
        stx     ARG_PTR
        dec     ARG_LEN
        bra     SDFS_PARSE_HEX16_TRAILING_LOOP
SDFS_PARSE_HEX16_DONE:
        ldaa    ARG2_LEN
        cmpa    #4
        bne     SDFS_PARSE_HEX16_FAIL
        clc
        rts
SDFS_PARSE_HEX16_FAIL:
        sec
        rts

SDFS_READ_LOADER_RECORD:
        jsr     SDFS_READ_RECORD_HEAD
        bcs     SDFS_READ_LOADER_RECORD_FAIL
        ldaa    LOADER_MODE
        bne     SDFS_READ_LOADER_RECORD_MODE_SET
        ldaa    HEX_NIBBLE
        cmpa    #'S'
        beq     SDFS_READ_LOADER_RECORD_SET_SREC
        cmpa    #':'
        beq     SDFS_READ_LOADER_RECORD_SET_IHEX
        sec
        rts
SDFS_READ_LOADER_RECORD_SET_SREC:
        ldaa    #LOAD_MODE_SREC
        staa    LOADER_MODE
        bra     SDFS_READ_LOADER_RECORD_MODE_SET
SDFS_READ_LOADER_RECORD_SET_IHEX:
        ldaa    #LOAD_MODE_IHEX
        staa    LOADER_MODE
SDFS_READ_LOADER_RECORD_MODE_SET:
        ldaa    LOADER_MODE
        cmpa    #LOAD_MODE_SREC
        beq     SDFS_READ_SREC_RECORD
        cmpa    #LOAD_MODE_IHEX
        bne     SDFS_READ_LOADER_RECORD_FAIL
        jmp     SDFS_READ_IHEX_RECORD
SDFS_READ_LOADER_RECORD_FAIL:
        sec
        rts

SDFS_READ_RECORD_HEAD:
        jsr     SDFS_API_STREAM_GETC
        bcs     SDFS_READ_RECORD_HEAD_FAIL
        cmpa    #CHR_LF
        beq     SDFS_READ_RECORD_HEAD
        cmpa    #CHR_CR
        beq     SDFS_READ_RECORD_HEAD
        cmpa    #CHR_SPACE
        blo     SDFS_READ_RECORD_HEAD
        staa    HEX_NIBBLE
        clc
        rts
SDFS_READ_RECORD_HEAD_FAIL:
        sec
        rts

SDFS_READ_RECORD_TRAILER:
        jsr     SDFS_API_STREAM_GETC
        bcs     SDFS_READ_RECORD_TRAILER_OK
        cmpa    #CHR_LF
        beq     SDFS_READ_RECORD_TRAILER_OK
        cmpa    #CHR_CR
        beq     SDFS_READ_RECORD_TRAILER_OK
SDFS_READ_RECORD_TRAILER_FAIL:
        sec
        rts
SDFS_READ_RECORD_TRAILER_OK:
        clc
        rts

SDFS_READ_HEXBYTE_INPUT:
        pshb
        jsr     SDFS_API_STREAM_GETC
        bcs     SDFS_READ_HEXBYTE_INPUT_FAIL
        jsr     SDFS_HEX_TO_NIBBLE
        bcs     SDFS_READ_HEXBYTE_INPUT_FAIL
        lsla
        lsla
        lsla
        lsla
        tab
        jsr     SDFS_API_STREAM_GETC
        bcs     SDFS_READ_HEXBYTE_INPUT_FAIL
        jsr     SDFS_HEX_TO_NIBBLE
        bcs     SDFS_READ_HEXBYTE_INPUT_FAIL
        aba
        pulb
        clc
        rts
SDFS_READ_HEXBYTE_INPUT_FAIL:
        pulb
        sec
        rts

SDFS_READ_SREC_RECORD:
        ldaa    HEX_NIBBLE
        cmpa    #'S'
        beq     SDFS_READ_SREC_HEAD_OK
        jmp     SDFS_READ_SREC_FAIL
SDFS_READ_SREC_HEAD_OK:
        ldaa    #1
        staa    LOADER_STAGE
        jsr     SDFS_API_STREAM_GETC
        bcs     SDFS_READ_SREC_FAIL_NEAR0
        staa    LOADER_TYPE
        cmpa    #'0'
        beq     SDFS_READ_SREC_TYPE_OK
        cmpa    #'1'
        beq     SDFS_READ_SREC_TYPE_OK
        cmpa    #'2'
        beq     SDFS_READ_SREC_TYPE_OK
        cmpa    #'5'
        beq     SDFS_READ_SREC_TYPE_OK
        cmpa    #'8'
        beq     SDFS_READ_SREC_TYPE_OK
        cmpa    #'9'
        beq     SDFS_READ_SREC_TYPE_OK
        jmp     SDFS_READ_SREC_FAIL
SDFS_READ_SREC_FAIL_NEAR0:
        jmp     SDFS_READ_SREC_FAIL
SDFS_READ_SREC_TYPE_OK:
        ldaa    #2
        staa    LOADER_STAGE
        jsr     SDFS_READ_HEXBYTE_INPUT
        bcs     SDFS_READ_SREC_FAIL_NEAR1
        staa    LOADER_COUNT
        staa    LOADER_SUM
        ldaa    LOADER_TYPE
        cmpa    #'2'
        beq     SDFS_READ_SREC_ADDR24
        cmpa    #'8'
        beq     SDFS_READ_SREC_ADDR24
        ldaa    LOADER_COUNT
        cmpa    #3
        blo     SDFS_READ_SREC_FAIL_NEAR1
        ldaa    #3
        staa    LOADER_STAGE
        jsr     SDFS_READ_HEXBYTE_INPUT
        bcs     SDFS_READ_SREC_FAIL_NEAR1
        staa    LOADER_ADDR
        jsr     SDFS_ADD_TO_LOADER_SUM
        jsr     SDFS_READ_HEXBYTE_INPUT
        bcs     SDFS_READ_SREC_FAIL_NEAR1
        staa    LOADER_ADDR+1
        jsr     SDFS_ADD_TO_LOADER_SUM
        ldab    LOADER_COUNT
        subb    #3
        bra     SDFS_READ_SREC_DATA_LOOP
SDFS_READ_SREC_FAIL_NEAR1:
        jmp     SDFS_READ_SREC_FAIL
SDFS_READ_SREC_ADDR24:
        ldaa    LOADER_COUNT
        cmpa    #4
        blo     SDFS_READ_SREC_FAIL_NEAR2
        ldaa    #3
        staa    LOADER_STAGE
        jsr     SDFS_READ_HEXBYTE_INPUT
        bcs     SDFS_READ_SREC_FAIL_NEAR2
        staa    HEX_NIBBLE
        jsr     SDFS_ADD_TO_LOADER_SUM
        ldaa    HEX_NIBBLE
        bne     SDFS_READ_SREC_FAIL_NEAR2
        jsr     SDFS_READ_HEXBYTE_INPUT
        bcs     SDFS_READ_SREC_FAIL_NEAR2
        staa    LOADER_ADDR
        jsr     SDFS_ADD_TO_LOADER_SUM
        jsr     SDFS_READ_HEXBYTE_INPUT
        bcs     SDFS_READ_SREC_FAIL_NEAR2
        staa    LOADER_ADDR+1
        jsr     SDFS_ADD_TO_LOADER_SUM
        ldab    LOADER_COUNT
        subb    #4
        bra     SDFS_READ_SREC_DATA_LOOP
SDFS_READ_SREC_FAIL_NEAR2:
        jmp     SDFS_READ_SREC_FAIL
SDFS_READ_SREC_DATA_LOOP:
        ldaa    #4
        staa    LOADER_STAGE
        tstb
        beq     SDFS_READ_SREC_CHECKSUM
        jsr     SDFS_READ_HEXBYTE_INPUT
        bcs     SDFS_READ_SREC_FAIL
        staa    HEX_NIBBLE
        jsr     SDFS_ADD_TO_LOADER_SUM
        ldaa    LOADER_TYPE
        cmpa    #'1'
        beq     SDFS_READ_SREC_STORE
        cmpa    #'2'
        bne     SDFS_READ_SREC_SKIP_STORE
SDFS_READ_SREC_STORE:
        ldaa    HEX_NIBBLE
        pshb
        ldx     LOADER_ADDR
        staa    0,x
        inx
        stx     LOADER_ADDR
        pulb
SDFS_READ_SREC_SKIP_STORE:
        decb
        bra     SDFS_READ_SREC_DATA_LOOP
SDFS_READ_SREC_CHECKSUM:
        ldaa    #5
        staa    LOADER_STAGE
        jsr     SDFS_READ_HEXBYTE_INPUT
        bcs     SDFS_READ_SREC_FAIL
        jsr     SDFS_ADD_TO_LOADER_SUM
        cmpa    #$FF
        bne     SDFS_READ_SREC_FAIL
        jsr     SDFS_READ_RECORD_TRAILER
        bcs     SDFS_READ_SREC_FAIL
        ldaa    LOADER_TYPE
        cmpa    #'8'
        beq     SDFS_READ_SREC_EOF
        cmpa    #'9'
        beq     SDFS_READ_SREC_EOF
        ldaa    #0
        clc
        rts
SDFS_READ_SREC_EOF:
        ldaa    LOADER_ADDR
        staa    SDFS_RUN_ENTRY
        ldaa    LOADER_ADDR+1
        staa    SDFS_RUN_ENTRY+1
        ldaa    #1
        staa    SDFS_RUN_ENTRY_SET
        ldaa    #1
        clc
        rts
SDFS_READ_SREC_FAIL:
        sec
        rts

SDFS_READ_IHEX_RECORD:
        ldaa    HEX_NIBBLE
        cmpa    #':'
        beq     SDFS_READ_IHEX_HEAD_OK
        jmp     SDFS_READ_IHEX_FAIL
SDFS_READ_IHEX_HEAD_OK:
        ldaa    #1
        staa    LOADER_STAGE
        ldaa    #2
        staa    LOADER_STAGE
        jsr     SDFS_READ_HEXBYTE_INPUT
        bcs     SDFS_READ_IHEX_FAIL_NEAR1
        staa    LOADER_COUNT
        staa    LOADER_SUM
        ldaa    #3
        staa    LOADER_STAGE
        jsr     SDFS_READ_HEXBYTE_INPUT
        bcs     SDFS_READ_IHEX_FAIL_NEAR1
        staa    LOADER_ADDR
        jsr     SDFS_ADD_TO_LOADER_SUM
        jsr     SDFS_READ_HEXBYTE_INPUT
        bcs     SDFS_READ_IHEX_FAIL_NEAR1
        staa    LOADER_ADDR+1
        jsr     SDFS_ADD_TO_LOADER_SUM
        jsr     SDFS_READ_HEXBYTE_INPUT
        bcs     SDFS_READ_IHEX_FAIL_NEAR1
        staa    LOADER_TYPE
        jsr     SDFS_ADD_TO_LOADER_SUM
        ldaa    LOADER_TYPE
        cmpa    #$00
        beq     SDFS_READ_IHEX_DATA
        cmpa    #$01
        bne     SDFS_READ_IHEX_FAIL
        ldaa    LOADER_COUNT
        bne     SDFS_READ_IHEX_FAIL
        bra     SDFS_READ_IHEX_DATA
SDFS_READ_IHEX_FAIL_NEAR1:
        jmp     SDFS_READ_IHEX_FAIL
SDFS_READ_IHEX_DATA:
        ldaa    #4
        staa    LOADER_STAGE
        ldab    LOADER_COUNT
SDFS_READ_IHEX_DATA_LOOP:
        tstb
        beq     SDFS_READ_IHEX_CHECKSUM
        jsr     SDFS_READ_HEXBYTE_INPUT
        bcs     SDFS_READ_IHEX_FAIL
        staa    HEX_NIBBLE
        jsr     SDFS_ADD_TO_LOADER_SUM
        ldaa    LOADER_TYPE
        cmpa    #$00
        bne     SDFS_READ_IHEX_SKIP_STORE
        ldaa    HEX_NIBBLE
        pshb
        ldx     LOADER_ADDR
        staa    0,x
        inx
        stx     LOADER_ADDR
        pulb
SDFS_READ_IHEX_SKIP_STORE:
        decb
        bra     SDFS_READ_IHEX_DATA_LOOP
SDFS_READ_IHEX_CHECKSUM:
        ldaa    #5
        staa    LOADER_STAGE
        jsr     SDFS_READ_HEXBYTE_INPUT
        bcs     SDFS_READ_IHEX_FAIL
        jsr     SDFS_ADD_TO_LOADER_SUM
        cmpa    #$00
        bne     SDFS_READ_IHEX_FAIL
        jsr     SDFS_READ_RECORD_TRAILER
        bcs     SDFS_READ_IHEX_FAIL
        ldaa    LOADER_TYPE
        cmpa    #$01
        beq     SDFS_READ_IHEX_EOF
        ldaa    #0
        clc
        rts
SDFS_READ_IHEX_EOF:
        ldaa    #1
        clc
        rts
SDFS_READ_IHEX_FAIL:
        sec
        rts

SDFS_HEX_TO_NIBBLE:
        cmpa    #'0'
        blo     SDFS_HEX_TO_NIBBLE_FAIL
        cmpa    #'9'
        bhi     SDFS_HEX_ALPHA
        suba    #'0'
        clc
        rts
SDFS_HEX_ALPHA:
        cmpa    #'A'
        blo     SDFS_HEX_LOWER
        cmpa    #'F'
        bhi     SDFS_HEX_LOWER
        suba    #'A'
        adda    #10
        clc
        rts
SDFS_HEX_LOWER:
        cmpa    #'a'
        blo     SDFS_HEX_TO_NIBBLE_FAIL
        cmpa    #'f'
        bhi     SDFS_HEX_TO_NIBBLE_FAIL
        suba    #'a'
        adda    #10
        clc
        rts
SDFS_HEX_TO_NIBBLE_FAIL:
        sec
        rts

SDFS_ADD_TO_LOADER_SUM:
        adda    LOADER_SUM
        staa    LOADER_SUM
        rts

SDFS_PRINT_HEX8:
        psha
        lsra
        lsra
        lsra
        lsra
        bsr     SDFS_PRINT_NIBBLE
        pula
        bsr     SDFS_PRINT_NIBBLE
        rts

SDFS_PRINT_NIBBLE:
        anda    #$0F
        adda    #'0'
        cmpa    #'9'+1
        blo     SDFS_PRINT_NIBBLE_OUT
        adda    #7
SDFS_PRINT_NIBBLE_OUT:
        jmp     SDFS_PUTC

SDFS_SHOW_ERROR:
        ldx     #TXT_ERROR
        jmp     SDFS_PRINT

SDFS_SHOW_LOADER_ERROR:
        ldx     #TXT_ERROR_PREFIX
        jsr     SDFS_PRINT
        ldaa    LOADER_MODE
        beq     SDFS_SHOW_LOADER_ERROR_CR
        cmpa    #LOAD_MODE_SREC
        bne     SDFS_SHOW_LOADER_ERROR_IHEX
        ldaa    #'S'
        jsr     SDFS_PUTC
        bra     SDFS_SHOW_LOADER_ERROR_STAGE
SDFS_SHOW_LOADER_ERROR_IHEX:
        ldaa    #'I'
        jsr     SDFS_PUTC
SDFS_SHOW_LOADER_ERROR_STAGE:
        ldaa    LOADER_STAGE
        adda    #'0'
        jsr     SDFS_PUTC
SDFS_SHOW_LOADER_ERROR_CR:
        ldaa    #CHR_CR
        jsr     SDFS_PUTC
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
        fcc     "SDFS/68 V1.3 #157"
        fcb     CHR_CR,0

TXT_PROMPT:
        fcc     "SDFS> "
        fcb     0

TXT_OK:
        fcc     "OK"
        fcb     CHR_CR,0

TXT_ERROR:
        fcc     "?"
        fcb     CHR_CR,0

TXT_ERROR_PREFIX:
        fcc     "?"
        fcb     0

TXT_S1_ERROR:
        fcb     CHR_CR
        fcc     "S1?"
        fcb     CHR_CR,0

SDFS_END:
        if SDFS_END-1 > SDFS_LOAD_LIMIT
        error   "SDFS/68 exceeds SDFS_LOAD_LIMIT"
        endif
