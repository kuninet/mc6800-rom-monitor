; Minimal FAT32 read-only helpers.
; Internal API only. Monitor commands are added in later issues.

FAT32_MOUNT:
        clr     FAT_ERROR
        jsr     SD_INIT
        bcc     FAT32_MOUNT_READ_LBA0
        ldaa    #FAT_ERR_SD
        jmp     FAT_FAIL_A

FAT32_MOUNT_READ_LBA0:
        jsr     FAT_SET_SD_LBA_ZERO
        ldx     #SD_SECTOR_BUF
        jsr     SD_READ_SECTOR
        bcc     FAT32_CHECK_LBA0_SIG
        ldaa    #FAT_ERR_SD
        jmp     FAT_FAIL_A

FAT32_CHECK_LBA0_SIG:
        jsr     FAT_CHECK_SIG
        bcc     FAT32_CHECK_LBA0_BPB
        ldaa    #FAT_ERR_SIG
        jmp     FAT_FAIL_A

FAT32_CHECK_LBA0_BPB:
        jsr     FAT_IS_BPB512
        bcs     FAT32_PARSE_MBR
        jsr     FAT_CLEAR_VOLUME_LBA
        jmp     FAT32_PARSE_BPB

FAT32_PARSE_MBR:
        jsr     FAT_PARSE_MBR_PART0
        bcc     FAT32_READ_VOLUME_BPB
        ldaa    #FAT_ERR_MBR
        jmp     FAT_FAIL_A

FAT32_READ_VOLUME_BPB:
        jsr     FAT_COPY_VOLUME_TO_SD_LBA
        ldx     #SD_SECTOR_BUF
        jsr     SD_READ_SECTOR
        bcc     FAT32_CHECK_BPB_SIG
        ldaa    #FAT_ERR_SD
        jmp     FAT_FAIL_A

FAT32_CHECK_BPB_SIG:
        jsr     FAT_CHECK_SIG
        bcc     FAT32_PARSE_BPB
        ldaa    #FAT_ERR_SIG
        jmp     FAT_FAIL_A

FAT32_PARSE_BPB:
        jsr     FAT_PARSE_BPB
        bcc     FAT32_MOUNT_OK
        ldaa    #FAT_ERR_BPB
        jmp     FAT_FAIL_A

FAT32_MOUNT_OK:
        ldaa    #FAT_ERR_NONE
        staa    FAT_ERROR
        clc
        rts

FAT_SET_SD_LBA_ZERO:
        clr     SD_LBA0
        clr     SD_LBA1
        clr     SD_LBA2
        clr     SD_LBA3
        rts

FAT_CLEAR_VOLUME_LBA:
        clr     FAT_VOLUME_LBA0
        clr     FAT_VOLUME_LBA1
        clr     FAT_VOLUME_LBA2
        clr     FAT_VOLUME_LBA3
        rts

FAT_COPY_VOLUME_TO_SD_LBA:
        ldaa    FAT_VOLUME_LBA0
        staa    SD_LBA0
        ldaa    FAT_VOLUME_LBA1
        staa    SD_LBA1
        ldaa    FAT_VOLUME_LBA2
        staa    SD_LBA2
        ldaa    FAT_VOLUME_LBA3
        staa    SD_LBA3
        rts

FAT_CHECK_SIG:
        ldx     #SD_SECTOR_BUF+510
        ldaa    0,x
        cmpa    #$55
        bne     FAT_CHECK_SIG_FAIL
        ldaa    1,x
        cmpa    #$AA
        bne     FAT_CHECK_SIG_FAIL
        clc
        rts
FAT_CHECK_SIG_FAIL:
        sec
        rts

FAT_IS_BPB512:
        ldx     #SD_SECTOR_BUF+11
        ldaa    0,x
        cmpa    #$00
        bne     FAT_IS_BPB512_FAIL
        ldaa    1,x
        cmpa    #$02
        bne     FAT_IS_BPB512_FAIL
        ldx     #SD_SECTOR_BUF+82
        ldaa    0,x
        cmpa    #'F'
        bne     FAT_IS_BPB512_FAIL
        ldaa    1,x
        cmpa    #'A'
        bne     FAT_IS_BPB512_FAIL
        ldaa    2,x
        cmpa    #'T'
        bne     FAT_IS_BPB512_FAIL
        ldaa    3,x
        cmpa    #'3'
        bne     FAT_IS_BPB512_FAIL
        ldaa    4,x
        cmpa    #'2'
        bne     FAT_IS_BPB512_FAIL
        clc
        rts
FAT_IS_BPB512_FAIL:
        sec
        rts

FAT_PARSE_MBR_PART0:
        ldx     #SD_SECTOR_BUF+450
        ldaa    0,x
        cmpa    #$0B
        beq     FAT_PARSE_MBR_LBA
        cmpa    #$0C
        beq     FAT_PARSE_MBR_LBA
        sec
        rts
FAT_PARSE_MBR_LBA:
        ldx     #SD_SECTOR_BUF+454
        ldaa    3,x
        staa    FAT_VOLUME_LBA0
        ldaa    2,x
        staa    FAT_VOLUME_LBA1
        ldaa    1,x
        staa    FAT_VOLUME_LBA2
        ldaa    0,x
        staa    FAT_VOLUME_LBA3
        ldaa    FAT_VOLUME_LBA0
        oraa    FAT_VOLUME_LBA1
        oraa    FAT_VOLUME_LBA2
        oraa    FAT_VOLUME_LBA3
        bne     FAT_PARSE_MBR_OK
        sec
        rts
FAT_PARSE_MBR_OK:
        clc
        rts

FAT_PARSE_BPB:
        jsr     FAT_IS_BPB512
        bcc     FAT_PARSE_BPB_SEC_PER_CLUS
        sec
        rts

FAT_PARSE_BPB_SEC_PER_CLUS:
        ldx     #SD_SECTOR_BUF+13
        ldaa    0,x
        bne     FAT_PARSE_BPB_SEC_OK
        jmp     FAT_PARSE_BPB_FAIL
FAT_PARSE_BPB_SEC_OK:
        staa    FAT_SEC_PER_CLUS

        ldx     #SD_SECTOR_BUF+14
        ldaa    1,x
        staa    FAT_RSVD_HI
        ldaa    0,x
        staa    FAT_RSVD_LO
        oraa    FAT_RSVD_HI
        bne     FAT_PARSE_BPB_RSVD_OK
        jmp     FAT_PARSE_BPB_FAIL
FAT_PARSE_BPB_RSVD_OK:

        ldx     #SD_SECTOR_BUF+16
        ldaa    0,x
        bne     FAT_PARSE_BPB_FATS_OK
        jmp     FAT_PARSE_BPB_FAIL
FAT_PARSE_BPB_FATS_OK:
        staa    FAT_NUM_FATS

        ldx     #SD_SECTOR_BUF+17
        ldaa    0,x
        oraa    1,x
        beq     FAT_PARSE_BPB_ROOTENT_OK
        jmp     FAT_PARSE_BPB_FAIL
FAT_PARSE_BPB_ROOTENT_OK:

        ldx     #SD_SECTOR_BUF+22
        ldaa    0,x
        oraa    1,x
        beq     FAT_PARSE_BPB_FATSZ16_OK
        jmp     FAT_PARSE_BPB_FAIL
FAT_PARSE_BPB_FATSZ16_OK:

        ldx     #SD_SECTOR_BUF+36
        ldaa    3,x
        staa    FAT_FATSZ0
        ldaa    2,x
        staa    FAT_FATSZ1
        ldaa    1,x
        staa    FAT_FATSZ2
        ldaa    0,x
        staa    FAT_FATSZ3
        ldaa    FAT_FATSZ0
        oraa    FAT_FATSZ1
        oraa    FAT_FATSZ2
        oraa    FAT_FATSZ3
        bne     FAT_PARSE_BPB_FATSZ32_OK
        jmp     FAT_PARSE_BPB_FAIL
FAT_PARSE_BPB_FATSZ32_OK:

        ldx     #SD_SECTOR_BUF+44
        ldaa    3,x
        staa    FAT_ROOT_CLUS0
        ldaa    2,x
        staa    FAT_ROOT_CLUS1
        ldaa    1,x
        staa    FAT_ROOT_CLUS2
        ldaa    0,x
        staa    FAT_ROOT_CLUS3

        ldaa    FAT_ROOT_CLUS0
        oraa    FAT_ROOT_CLUS1
        oraa    FAT_ROOT_CLUS2
        bne     FAT_PARSE_BPB_CALC
        ldaa    FAT_ROOT_CLUS3
        cmpa    #$02
        blo     FAT_PARSE_BPB_FAIL

FAT_PARSE_BPB_CALC:
        jsr     FAT_COPY_VOLUME_TO_FAT_LBA
        jsr     FAT_ADD_RSVD_TO_FAT_LBA
        jsr     FAT_COPY_FAT_TO_DATA_LBA
        ldab    FAT_NUM_FATS
FAT_PARSE_BPB_DATA_LOOP:
        jsr     FAT_ADD_FATSZ_TO_DATA_LBA
        decb
        bne     FAT_PARSE_BPB_DATA_LOOP
        clc
        rts

FAT_PARSE_BPB_FAIL:
        sec
        rts

FAT_COPY_VOLUME_TO_FAT_LBA:
        ldaa    FAT_VOLUME_LBA0
        staa    FAT_FAT_LBA0
        ldaa    FAT_VOLUME_LBA1
        staa    FAT_FAT_LBA1
        ldaa    FAT_VOLUME_LBA2
        staa    FAT_FAT_LBA2
        ldaa    FAT_VOLUME_LBA3
        staa    FAT_FAT_LBA3
        rts

FAT_COPY_FAT_TO_DATA_LBA:
        ldaa    FAT_FAT_LBA0
        staa    FAT_DATA_LBA0
        ldaa    FAT_FAT_LBA1
        staa    FAT_DATA_LBA1
        ldaa    FAT_FAT_LBA2
        staa    FAT_DATA_LBA2
        ldaa    FAT_FAT_LBA3
        staa    FAT_DATA_LBA3
        rts

FAT_ADD_RSVD_TO_FAT_LBA:
        ldaa    FAT_FAT_LBA3
        adda    FAT_RSVD_LO
        staa    FAT_FAT_LBA3
        bcc     FAT_ADD_RSVD_HI
        inc     FAT_FAT_LBA2
        bne     FAT_ADD_RSVD_HI
        inc     FAT_FAT_LBA1
        bne     FAT_ADD_RSVD_HI
        inc     FAT_FAT_LBA0
FAT_ADD_RSVD_HI:
        ldaa    FAT_FAT_LBA2
        adda    FAT_RSVD_HI
        staa    FAT_FAT_LBA2
        bcc     FAT_ADD_RSVD_DONE
        inc     FAT_FAT_LBA1
        bne     FAT_ADD_RSVD_DONE
        inc     FAT_FAT_LBA0
FAT_ADD_RSVD_DONE:
        rts

FAT_ADD_FATSZ_TO_DATA_LBA:
        ldaa    FAT_DATA_LBA3
        adda    FAT_FATSZ3
        staa    FAT_DATA_LBA3
        bcc     FAT_ADD_FATSZ_B2
        inc     FAT_DATA_LBA2
        bne     FAT_ADD_FATSZ_B2
        inc     FAT_DATA_LBA1
        bne     FAT_ADD_FATSZ_B2
        inc     FAT_DATA_LBA0
FAT_ADD_FATSZ_B2:
        ldaa    FAT_DATA_LBA2
        adda    FAT_FATSZ2
        staa    FAT_DATA_LBA2
        bcc     FAT_ADD_FATSZ_B1
        inc     FAT_DATA_LBA1
        bne     FAT_ADD_FATSZ_B1
        inc     FAT_DATA_LBA0
FAT_ADD_FATSZ_B1:
        ldaa    FAT_DATA_LBA1
        adda    FAT_FATSZ1
        staa    FAT_DATA_LBA1
        bcc     FAT_ADD_FATSZ_B0
        inc     FAT_DATA_LBA0
FAT_ADD_FATSZ_B0:
        ldaa    FAT_DATA_LBA0
        adda    FAT_FATSZ0
        staa    FAT_DATA_LBA0
        rts

FAT_FAIL_A:
        staa    FAT_ERROR
        sec
        rts

 if FAT32_INCLUDE_FIND_API
FAT32_FIND_83:
        jsr     FAT_COPY_FIND_NAME
        jsr     FAT_COPY_ROOT_TO_CUR

FAT_FIND_DIR_CLUSTER:
        jsr     FAT_CLUSTER_TO_SD_LBA
        ldx     #SD_SECTOR_BUF
        jsr     SD_READ_SECTOR
        bcc     FAT_FIND_SCAN_PREP
        ldaa    #FAT_ERR_SD
        jmp     FAT_FAIL_A

FAT_FIND_SCAN_PREP:
        ldx     #SD_SECTOR_BUF
        stx     FAT_ENTRY_PTR
        ldaa    #16
        staa    FAT_DIR_COUNT

FAT_FIND_ENTRY_LOOP:
        ldx     FAT_ENTRY_PTR
        ldaa    0,x
        beq     FAT_FIND_NOT_FOUND
        cmpa    #$E5
        beq     FAT_FIND_SKIP_ENTRY
        ldaa    11,x
        anda    #$0F
        cmpa    #$0F
        beq     FAT_FIND_SKIP_ENTRY
        ldaa    11,x
        bita    #$18
        bne     FAT_FIND_SKIP_ENTRY
        jsr     FAT_COMPARE_ENTRY_NAME
        bcc     FAT_FIND_MATCH

FAT_FIND_SKIP_ENTRY:
        jsr     FAT_ADVANCE_ENTRY_PTR
        dec     FAT_DIR_COUNT
        bne     FAT_FIND_ENTRY_LOOP

        jsr     FAT32_NEXT_CLUSTER
        bcc     FAT_FIND_NEXT_CLUSTER
        ldaa    #FAT_ERR_NOT_FOUND
        jmp     FAT_FAIL_A
FAT_FIND_NEXT_CLUSTER:
        jsr     FAT_COPY_NEXT_TO_CUR
        jmp     FAT_FIND_DIR_CLUSTER

FAT_FIND_MATCH:
        jsr     FAT_STORE_FILE_ENTRY
        ldaa    #FAT_ERR_NONE
        staa    FAT_ERROR
        clc
        rts

FAT_FIND_NOT_FOUND:
        ldaa    #FAT_ERR_NOT_FOUND
        jmp     FAT_FAIL_A

 if FAT32_INCLUDE_FILE_API
FAT32_READ_FILE:
        stx     FAT_READ_PTR
        jsr     FAT_COPY_FILE_TO_CUR
        jsr     FAT_COPY_FILE_SIZE_TO_REM
        clr     FAT_SECTOR_IN_CLUS

FAT_READ_FILE_LOOP:
        jsr     FAT_BYTES_REMAIN
        bcc     FAT_READ_FILE_DONE
        jsr     FAT_SECTOR_TO_SD_LBA
        ldx     #SD_SECTOR_BUF
        jsr     SD_READ_SECTOR
        bcc     FAT_READ_COPY_PREP
        ldaa    #FAT_ERR_SD
        jmp     FAT_FAIL_A

FAT_READ_COPY_PREP:
        jsr     FAT_PREP_COPY_COUNT
        jsr     FAT_COPY_SECTOR_TO_FILE
        jsr     FAT_SUB_COPY_COUNT
        jsr     FAT_BYTES_REMAIN
        bcc     FAT_READ_FILE_DONE
        jsr     FAT_ADVANCE_FILE_SECTOR
        bcs     FAT_READ_FILE_ADVANCE_FAIL
        jmp     FAT_READ_FILE_LOOP
FAT_READ_FILE_ADVANCE_FAIL:
        rts

FAT_READ_FILE_DONE:
        ldaa    #FAT_ERR_NONE
        staa    FAT_ERROR
        clc
        rts

FAT32_STREAM_OPEN:
        jsr     FAT_COPY_FILE_TO_CUR
        jsr     FAT_COPY_FILE_SIZE_TO_REM
        clr     FAT_COPY_COUNT
        clr     FAT_COPY_COUNT+1
        clr     FAT_SECTOR_IN_CLUS
        ldx     #SD_SECTOR_BUF
        stx     FAT_ENTRY_PTR
        ldaa    #FAT_ERR_NONE
        staa    FAT_ERROR
        clc
        rts

FAT32_STREAM_GETC:
        jsr     FAT_BYTES_REMAIN
        bcs     FAT_STREAM_HAS_REMAIN
        sec
        rts
FAT_STREAM_HAS_REMAIN:
        ldaa    FAT_COPY_COUNT
        oraa    FAT_COPY_COUNT+1
        bne     FAT_STREAM_HAVE_SECTOR
        jsr     FAT_STREAM_LOAD_SECTOR
        bcc     FAT_STREAM_HAVE_SECTOR
        sec
        rts
FAT_STREAM_HAVE_SECTOR:
        ldx     FAT_ENTRY_PTR
        ldaa    0,x
        inx
        stx     FAT_ENTRY_PTR
        psha
        ldx     FAT_COPY_COUNT
        dex
        stx     FAT_COPY_COUNT
        jsr     FAT_DEC_BYTES_REM_ONE
        ldaa    FAT_COPY_COUNT
        oraa    FAT_COPY_COUNT+1
        bne     FAT_STREAM_RETURN_BYTE
        jsr     FAT_BYTES_REMAIN
        bcc     FAT_STREAM_RETURN_BYTE
        jsr     FAT_ADVANCE_FILE_SECTOR
        bcc     FAT_STREAM_RETURN_BYTE
        pula
        sec
        rts
FAT_STREAM_RETURN_BYTE:
        pula
        clc
        rts

FAT_STREAM_LOAD_SECTOR:
        jsr     FAT_SECTOR_TO_SD_LBA
        ldx     #SD_SECTOR_BUF
        jsr     SD_READ_SECTOR
        bcc     FAT_STREAM_LOAD_OK
        ldaa    #FAT_ERR_SD
        jmp     FAT_FAIL_A
FAT_STREAM_LOAD_OK:
        jsr     FAT_PREP_COPY_COUNT
        ldx     #SD_SECTOR_BUF
        stx     FAT_ENTRY_PTR
        clc
        rts
 endif

FAT_COPY_FIND_NAME:
        ldaa    0,x
        staa    FAT_FIND_NAME0
        ldaa    1,x
        staa    FAT_FIND_NAME1
        ldaa    2,x
        staa    FAT_FIND_NAME2
        ldaa    3,x
        staa    FAT_FIND_NAME3
        ldaa    4,x
        staa    FAT_FIND_NAME4
        ldaa    5,x
        staa    FAT_FIND_NAME5
        ldaa    6,x
        staa    FAT_FIND_NAME6
        ldaa    7,x
        staa    FAT_FIND_NAME7
        ldaa    8,x
        staa    FAT_FIND_NAME8
        ldaa    9,x
        staa    FAT_FIND_NAME9
        ldaa    10,x
        staa    FAT_FIND_NAME10
        rts

FAT_COPY_ROOT_TO_CUR:
        ldaa    FAT_ROOT_CLUS0
        staa    FAT_CUR_CLUS0
        ldaa    FAT_ROOT_CLUS1
        staa    FAT_CUR_CLUS1
        ldaa    FAT_ROOT_CLUS2
        staa    FAT_CUR_CLUS2
        ldaa    FAT_ROOT_CLUS3
        staa    FAT_CUR_CLUS3
        rts

 if FAT32_INCLUDE_FILE_API
FAT_COPY_FILE_TO_CUR:
        ldaa    FAT_FILE_CLUS0
        staa    FAT_CUR_CLUS0
        ldaa    FAT_FILE_CLUS1
        staa    FAT_CUR_CLUS1
        ldaa    FAT_FILE_CLUS2
        staa    FAT_CUR_CLUS2
        ldaa    FAT_FILE_CLUS3
        staa    FAT_CUR_CLUS3
        rts
 endif

FAT_COPY_NEXT_TO_CUR:
        ldaa    FAT_NEXT_CLUS0
        staa    FAT_CUR_CLUS0
        ldaa    FAT_NEXT_CLUS1
        staa    FAT_CUR_CLUS1
        ldaa    FAT_NEXT_CLUS2
        staa    FAT_CUR_CLUS2
        ldaa    FAT_NEXT_CLUS3
        staa    FAT_CUR_CLUS3
        rts

 if FAT32_INCLUDE_FILE_API
FAT_COPY_FILE_SIZE_TO_REM:
        ldaa    FAT_FILE_SIZE0
        staa    FAT_BYTES_REM0
        ldaa    FAT_FILE_SIZE1
        staa    FAT_BYTES_REM1
        ldaa    FAT_FILE_SIZE2
        staa    FAT_BYTES_REM2
        ldaa    FAT_FILE_SIZE3
        staa    FAT_BYTES_REM3
        rts
 endif

FAT_COMPARE_ENTRY_NAME:
        ldx     FAT_ENTRY_PTR
        ldaa    0,x
        cmpa    FAT_FIND_NAME0
        bne     FAT_COMPARE_ENTRY_FAIL
        ldaa    1,x
        cmpa    FAT_FIND_NAME1
        bne     FAT_COMPARE_ENTRY_FAIL
        ldaa    2,x
        cmpa    FAT_FIND_NAME2
        bne     FAT_COMPARE_ENTRY_FAIL
        ldaa    3,x
        cmpa    FAT_FIND_NAME3
        bne     FAT_COMPARE_ENTRY_FAIL
        ldaa    4,x
        cmpa    FAT_FIND_NAME4
        bne     FAT_COMPARE_ENTRY_FAIL
        ldaa    5,x
        cmpa    FAT_FIND_NAME5
        bne     FAT_COMPARE_ENTRY_FAIL
        ldaa    6,x
        cmpa    FAT_FIND_NAME6
        bne     FAT_COMPARE_ENTRY_FAIL
        ldaa    7,x
        cmpa    FAT_FIND_NAME7
        bne     FAT_COMPARE_ENTRY_FAIL
        ldaa    8,x
        cmpa    FAT_FIND_NAME8
        bne     FAT_COMPARE_ENTRY_FAIL
        ldaa    9,x
        cmpa    FAT_FIND_NAME9
        bne     FAT_COMPARE_ENTRY_FAIL
        ldaa    10,x
        cmpa    FAT_FIND_NAME10
        bne     FAT_COMPARE_ENTRY_FAIL
        clc
        rts
FAT_COMPARE_ENTRY_FAIL:
        sec
        rts

FAT_ADVANCE_ENTRY_PTR:
        ldx     FAT_ENTRY_PTR
        ldab    #32
FAT_ADVANCE_ENTRY_LOOP:
        inx
        decb
        bne     FAT_ADVANCE_ENTRY_LOOP
        stx     FAT_ENTRY_PTR
        rts

FAT_STORE_FILE_ENTRY:
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

FAT_CLUSTER_TO_SD_LBA:
        ldaa    FAT_DATA_LBA0
        staa    SD_LBA0
        ldaa    FAT_DATA_LBA1
        staa    SD_LBA1
        ldaa    FAT_DATA_LBA2
        staa    SD_LBA2
        ldaa    FAT_DATA_LBA3
        staa    SD_LBA3
        ldaa    FAT_CUR_CLUS3
        suba    #$02
        staa    FAT_TMP
FAT_CLUSTER_ADD_LOOP:
        ldaa    FAT_TMP
        beq     FAT_CLUSTER_ADD_DONE
        ldab    FAT_SEC_PER_CLUS
FAT_CLUSTER_ADD_SECTOR_LOOP:
        jsr     FAT_INC_SD_LBA
        decb
        bne     FAT_CLUSTER_ADD_SECTOR_LOOP
        dec     FAT_TMP
        bra     FAT_CLUSTER_ADD_LOOP
FAT_CLUSTER_ADD_DONE:
        rts

 if FAT32_INCLUDE_FILE_API
FAT_SECTOR_TO_SD_LBA:
        jsr     FAT_CLUSTER_TO_SD_LBA
        ldab    FAT_SECTOR_IN_CLUS
        beq     FAT_SECTOR_TO_SD_LBA_DONE
FAT_SECTOR_TO_SD_LBA_LOOP:
        jsr     FAT_INC_SD_LBA
        decb
        bne     FAT_SECTOR_TO_SD_LBA_LOOP
FAT_SECTOR_TO_SD_LBA_DONE:
        rts
 endif

FAT_INC_SD_LBA:
        inc     SD_LBA3
        bne     FAT_INC_SD_LBA_DONE
        inc     SD_LBA2
        bne     FAT_INC_SD_LBA_DONE
        inc     SD_LBA1
        bne     FAT_INC_SD_LBA_DONE
        inc     SD_LBA0
FAT_INC_SD_LBA_DONE:
        rts

FAT32_NEXT_CLUSTER:
        ldaa    FAT_FAT_LBA0
        staa    SD_LBA0
        ldaa    FAT_FAT_LBA1
        staa    SD_LBA1
        ldaa    FAT_FAT_LBA2
        staa    SD_LBA2
        ldaa    FAT_FAT_LBA3
        staa    SD_LBA3
        ldx     #SD_SECTOR_BUF
        jsr     SD_READ_SECTOR
        bcc     FAT_NEXT_OFFSET_PREP
        ldaa    #FAT_ERR_SD
        jmp     FAT_FAIL_A

FAT_NEXT_OFFSET_PREP:
        ldaa    FAT_CUR_CLUS3
        asla
        asla
        tab
        ldx     #SD_SECTOR_BUF
FAT_NEXT_OFFSET_LOOP:
        tstb
        beq     FAT_NEXT_READ
        inx
        decb
        bra     FAT_NEXT_OFFSET_LOOP
FAT_NEXT_READ:
        ldaa    3,x
        anda    #$0F
        staa    FAT_NEXT_CLUS0
        ldaa    2,x
        staa    FAT_NEXT_CLUS1
        ldaa    1,x
        staa    FAT_NEXT_CLUS2
        ldaa    0,x
        staa    FAT_NEXT_CLUS3
        ldaa    FAT_NEXT_CLUS0
        cmpa    #$0F
        bne     FAT_NEXT_NOT_EOC
        ldaa    FAT_NEXT_CLUS1
        cmpa    #$FF
        bne     FAT_NEXT_NOT_EOC
        ldaa    FAT_NEXT_CLUS2
        cmpa    #$FF
        bne     FAT_NEXT_NOT_EOC
        ldaa    FAT_NEXT_CLUS3
        cmpa    #$F8
        blo     FAT_NEXT_NOT_EOC
        sec
        rts
FAT_NEXT_NOT_EOC:
        clc
        rts

 if FAT32_INCLUDE_FILE_API
FAT_ADVANCE_FILE_SECTOR:
        inc     FAT_SECTOR_IN_CLUS
        ldaa    FAT_SECTOR_IN_CLUS
        cmpa    FAT_SEC_PER_CLUS
        blo     FAT_ADVANCE_SAME_CLUSTER
        clr     FAT_SECTOR_IN_CLUS
        jsr     FAT32_NEXT_CLUSTER
        bcc     FAT_ADVANCE_NEXT_CLUSTER
        ldaa    #FAT_ERR_CHAIN
        jmp     FAT_FAIL_A
FAT_ADVANCE_NEXT_CLUSTER:
        jsr     FAT_COPY_NEXT_TO_CUR
FAT_ADVANCE_SAME_CLUSTER:
        clc
        rts

FAT_BYTES_REMAIN:
        ldaa    FAT_BYTES_REM0
        oraa    FAT_BYTES_REM1
        oraa    FAT_BYTES_REM2
        oraa    FAT_BYTES_REM3
        bne     FAT_BYTES_REMAIN_YES
        clc
        rts
FAT_BYTES_REMAIN_YES:
        sec
        rts

FAT_PREP_COPY_COUNT:
        ldaa    FAT_BYTES_REM0
        oraa    FAT_BYTES_REM1
        bne     FAT_PREP_COPY_512
        ldaa    FAT_BYTES_REM2
        cmpa    #$02
        bhs     FAT_PREP_COPY_512
        staa    FAT_COPY_COUNT
        ldaa    FAT_BYTES_REM3
        staa    FAT_COPY_COUNT+1
        clr     FAT_TMP
        rts
FAT_PREP_COPY_512:
        ldaa    #$02
        staa    FAT_COPY_COUNT
        clr     FAT_COPY_COUNT+1
        ldaa    #$01
        staa    FAT_TMP
        rts

FAT_COPY_SECTOR_TO_FILE:
        ldx     #SD_SECTOR_BUF
        stx     FAT_ENTRY_PTR
FAT_COPY_SECTOR_LOOP:
        ldaa    FAT_COPY_COUNT
        oraa    FAT_COPY_COUNT+1
        beq     FAT_COPY_SECTOR_DONE
        ldx     FAT_ENTRY_PTR
        ldaa    0,x
        inx
        stx     FAT_ENTRY_PTR
        ldx     FAT_READ_PTR
        staa    0,x
        inx
        stx     FAT_READ_PTR
        ldx     FAT_COPY_COUNT
        dex
        stx     FAT_COPY_COUNT
        bra     FAT_COPY_SECTOR_LOOP
FAT_COPY_SECTOR_DONE:
        rts

FAT_SUB_COPY_COUNT:
        ldaa    FAT_TMP
        cmpa    #$01
        bne     FAT_SUB_FINAL
        ldaa    FAT_BYTES_REM2
        suba    #$02
        staa    FAT_BYTES_REM2
        rts
FAT_SUB_FINAL:
        clr     FAT_BYTES_REM0
        clr     FAT_BYTES_REM1
        clr     FAT_BYTES_REM2
        clr     FAT_BYTES_REM3
        rts

FAT_DEC_BYTES_REM_ONE:
        ldaa    FAT_BYTES_REM3
        bne     FAT_DEC_REM_LO
        ldaa    #$FF
        staa    FAT_BYTES_REM3
        ldaa    FAT_BYTES_REM2
        bne     FAT_DEC_REM_B2
        ldaa    #$FF
        staa    FAT_BYTES_REM2
        ldaa    FAT_BYTES_REM1
        bne     FAT_DEC_REM_B1
        ldaa    #$FF
        staa    FAT_BYTES_REM1
        dec     FAT_BYTES_REM0
        rts
FAT_DEC_REM_B1:
        dec     FAT_BYTES_REM1
        rts
FAT_DEC_REM_B2:
        dec     FAT_BYTES_REM2
        rts
FAT_DEC_REM_LO:
        dec     FAT_BYTES_REM3
        rts
 endif
 endif
