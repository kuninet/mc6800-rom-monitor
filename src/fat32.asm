; Minimal FAT32 BPB/MBR parser.
; Internal API only. It does not read FAT entries or directory entries.

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
