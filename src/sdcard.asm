; SD card SPI driver using MC6821 PIA

; ---------------------------------------------------------------------------
; PIA_INIT: Initialize PIA Port B for SPI
; ---------------------------------------------------------------------------
PIA_INIT:
        psha
        ldaa    PIA_CRB
        anda    #%11111011
        staa    PIA_CRB
        ldaa    #%00001011
        staa    PIA_PRB
        ldaa    PIA_CRB
        oraa    #%00000100
        staa    PIA_CRB
        ldaa    #SPI_CS
        staa    PIA_PRB
        pula
        rts

; ---------------------------------------------------------------------------
; SPI_XFER: Transfer 1 byte via SPI
; ---------------------------------------------------------------------------
SPI_XFER:
        pshb
        ldab    #8
SPI_XFER_LOOP:
        asla
        psha
        ldaa    PIA_PRB
        anda    #~(SPI_MOSI | SPI_SCLK)
        bcc     SPI_XFER_L0
        oraa    #SPI_MOSI
SPI_XFER_L0:
        staa    PIA_PRB
        oraa    #SPI_SCLK
        staa    PIA_PRB
        ldaa    PIA_PRB
        anda    #SPI_MISO
        beq     SPI_XFER_L_MISO_LOW
        pula
        oraa    #$01
        psha
        bra     SPI_XFER_L1
SPI_XFER_L_MISO_LOW:
        pula
        psha
SPI_XFER_L1:
        ldaa    PIA_PRB
        anda    #~SPI_SCLK
        staa    PIA_PRB
        pula
        decb
        bne     SPI_XFER_LOOP
        pulb
        rts

; ---------------------------------------------------------------------------
; SD_CMD: Send Command to SD card (Caller must assert CS=0)
; ---------------------------------------------------------------------------
SD_CMD:
        pshb
        psha
        pula
        oraa    #$40
        jsr     SPI_XFER
        ldaa    SD_ARG
        jsr     SPI_XFER
        ldaa    SD_ARG+1
        jsr     SPI_XFER
        ldaa    SD_ARG+2
        jsr     SPI_XFER
        ldaa    SD_ARG+3
        jsr     SPI_XFER
        pula
        jsr     SPI_XFER
        ldab    #10
SD_CMD_WAIT:
        ldaa    #$FF
        jsr     SPI_XFER
        tsta
        bpl     SD_CMD_DONE
        decb
        bne     SD_CMD_WAIT
SD_CMD_DONE:
        rts

; ---------------------------------------------------------------------------
; SD_INIT: Initialize SD card into SPI mode
; ---------------------------------------------------------------------------
SD_INIT:
        jsr     PIA_INIT
        ldaa    #SPI_CS
        staa    PIA_PRB
        ldab    #10
SD_INIT_DUMMY:
        ldaa    #$FF
        jsr     SPI_XFER
        decb
        bne     SD_INIT_DUMMY
        ldaa    #~SPI_CS
        anda    PIA_PRB
        staa    PIA_PRB
        clr     SD_ARG
        clr     SD_ARG+1
        clr     SD_ARG+2
        clr     SD_ARG+3
        ldaa    #0
        ldab    #$95
        jsr     SD_CMD
        cmpa    #$01
        bne     SD_INIT_FAIL
        clr     SD_ARG
        clr     SD_ARG+1
        ldaa    #$01
        staa    SD_ARG+2
        ldaa    #$AA
        staa    SD_ARG+3
        ldaa    #8
        ldab    #$87
        jsr     SD_CMD
        cmpa    #$01
        beq     SD_INIT_CMD8_R7
        bra     SD_INIT_ACMD41
SD_INIT_CMD8_R7:
        ldab    #4
SD_INIT_CMD8_SKIP:
        ldaa    #$FF
        jsr     SPI_XFER
        decb
        bne     SD_INIT_CMD8_SKIP
SD_INIT_ACMD41:
        ldx     #500
SD_INIT_ACMD_LOOP:
        clr     SD_ARG
        clr     SD_ARG+1
        clr     SD_ARG+2
        clr     SD_ARG+3
        ldaa    #55
        ldab    #$FF
        jsr     SD_CMD
        cmpa    #$01
        bhi     SD_INIT_FAIL
        ldaa    #$40
        staa    SD_ARG
        clr     SD_ARG+1
        clr     SD_ARG+2
        clr     SD_ARG+3
        ldaa    #41
        ldab    #$FF
        jsr     SD_CMD
        tsta
        beq     SD_INIT_OK
        dex
        bne     SD_INIT_ACMD_LOOP
        bra     SD_INIT_FAIL
SD_INIT_FAIL:
        ldaa    #SPI_CS
        oraa    PIA_PRB
        staa    PIA_PRB
        ldaa    #$FF
        rts
SD_INIT_OK:
        ldaa    #SPI_CS
        oraa    PIA_PRB
        staa    PIA_PRB
        clra
        rts

; ---------------------------------------------------------------------------
; SD_READ_SECTOR: Read 512 bytes from SD card
; ---------------------------------------------------------------------------
SD_READ_SECTOR:
        ldaa    SD_LBA
        staa    SD_ARG
        ldaa    SD_LBA+1
        staa    SD_ARG+1
        ldaa    SD_LBA+2
        staa    SD_ARG+2
        ldaa    SD_LBA+3
        staa    SD_ARG+3
        ldaa    #~SPI_CS
        anda    PIA_PRB
        staa    PIA_PRB
        ldaa    #17
        ldab    #$FF
        jsr     SD_CMD
        tsta
        beq     SD_READ_WAIT_TOKEN
        jmp     SD_READ_FAIL
SD_READ_WAIT_TOKEN:
        ldx     #$FFFF
SD_READ_TOKEN_LOOP:
        ldaa    #$FF
        jsr     SPI_XFER
        cmpa    #$FE
        beq     SD_READ_DATA
        dex
        bne     SD_READ_TOKEN_LOOP
        bra     SD_READ_FAIL
SD_READ_DATA:
        ldx     SD_BUF_PTR
        ldab    #0
SD_READ_LOOP1:
        ldaa    #$FF
        jsr     SPI_XFER
        staa    0,x
        inx
        decb
        bne     SD_READ_LOOP1
        ldab    #0
SD_READ_LOOP2:
        ldaa    #$FF
        jsr     SPI_XFER
        staa    0,x
        inx
        decb
        bne     SD_READ_LOOP2
        ldaa    #$FF
        jsr     SPI_XFER
        ldaa    #$FF
        jsr     SPI_XFER
        ldaa    #SPI_CS
        oraa    PIA_PRB
        staa    PIA_PRB
        clra
        rts
SD_READ_FAIL:
        ldaa    #SPI_CS
        oraa    PIA_PRB
        staa    PIA_PRB
        ldaa    #$FF
        rts

; ---------------------------------------------------------------------------
; SD_FAT_INIT: Initialize FAT32 parameters from Sector 0
; ---------------------------------------------------------------------------
SD_FAT_INIT:
        clr     SD_LBA
        clr     SD_LBA+1
        clr     SD_LBA+2
        clr     SD_LBA+3
        ldx     #SECTOR_BUF
        stx     SD_BUF_PTR
        jsr     SD_READ_SECTOR
        tsta
        beq     SD_FAT_PARSE
        rts
SD_FAT_PARSE:
        ldx     #SECTOR_BUF
        ldaa    13,x
        staa    FAT_SEC_PER_CLUS
        ldaa    14,x
        staa    FAT_RSVD_SEC+1
        ldaa    15,x
        staa    FAT_RSVD_SEC
        ldaa    16,x
        staa    FAT_NUM_FATS
        ldaa    36,x
        staa    FAT_SIZE+3
        ldaa    37,x
        staa    FAT_SIZE+2
        ldaa    38,x
        staa    FAT_SIZE+1
        ldaa    39,x
        staa    FAT_SIZE
        ldaa    44,x
        staa    FAT_ROOT_CLUS+3
        ldaa    45,x
        staa    FAT_ROOT_CLUS+2
        ldaa    46,x
        staa    FAT_ROOT_CLUS+1
        ldaa    47,x
        staa    FAT_ROOT_CLUS
        ldaa    FAT_SIZE+3
        asla
        staa    FAT_DATA_SEC+3
        ldaa    FAT_SIZE+2
        rola
        staa    FAT_DATA_SEC+2
        ldaa    FAT_SIZE+1
        rola
        staa    FAT_DATA_SEC+1
        ldaa    FAT_SIZE
        rola
        staa    FAT_DATA_SEC
        ldaa    FAT_DATA_SEC+3
        adda    FAT_RSVD_SEC+1
        staa    FAT_DATA_SEC+3
        ldaa    FAT_DATA_SEC+2
        adca    FAT_RSVD_SEC
        staa    FAT_DATA_SEC+2
        ldaa    FAT_DATA_SEC+1
        adca    #0
        staa    FAT_DATA_SEC+1
        ldaa    FAT_DATA_SEC
        adca    #0
        staa    FAT_DATA_SEC
        clra
        rts

; ---------------------------------------------------------------------------
; SD_DIR: List files in root directory
; ---------------------------------------------------------------------------
SD_DIR:
        jsr     SD_FAT_INIT
        tsta
        beq     SD_DIR_START
        rts
SD_DIR_START:
        ldaa    FAT_DATA_SEC
        staa    SD_LBA
        ldaa    FAT_DATA_SEC+1
        staa    SD_LBA+1
        ldaa    FAT_DATA_SEC+2
        staa    SD_LBA+2
        ldaa    FAT_DATA_SEC+3
        staa    SD_LBA+3
        ldx     #SECTOR_BUF
        stx     SD_BUF_PTR
        jsr     SD_READ_SECTOR
        tsta
        beq     SD_DIR_SHOW
        rts
SD_DIR_SHOW:
        ldx     #SECTOR_BUF
SD_DIR_LOOP:
        ldaa    0,x
        beq     SD_DIR_DONE
        cmpa    #$E5
        beq     SD_DIR_NEXT
        ldaa    11,x
        cmpa    #$0F
        beq     SD_DIR_NEXT
        stx     SD_X_SAVE
        ldab    #8
SD_DIR_NAME:
        ldaa    0,x
        jsr     MON_OUTEEE
        inx
        decb
        bne     SD_DIR_NAME
        ldaa    #'.'
        jsr     MON_OUTEEE
        ldab    #3
SD_DIR_EXT:
        ldaa    0,x
        jsr     MON_OUTEEE
        inx
        decb
        bne     SD_DIR_EXT
        jsr     PRINT_CRLF
        ldx     SD_X_SAVE
SD_DIR_NEXT:
        ldab    #32
SD_DIR_ADV:
        inx
        decb
        bne     SD_DIR_ADV
        cpx     #SECTOR_BUF + 512
        blo     SD_DIR_LOOP
SD_DIR_DONE:
        rts

; ---------------------------------------------------------------------------
; SD_OPEN_FILE: Find file in root dir and prepare for reading
; Input:  X = Pointer to 11-byte filename (padded with spaces)
; ---------------------------------------------------------------------------
SD_OPEN_FILE:
        stx     SD_ARG
        jsr     SD_FAT_INIT
        tsta
        bne     SD_OPEN_FAIL
        ldaa    FAT_DATA_SEC
        staa    SD_LBA
        ldaa    FAT_DATA_SEC+1
        staa    SD_LBA+1
        ldaa    FAT_DATA_SEC+2
        staa    SD_LBA+2
        ldaa    FAT_DATA_SEC+3
        staa    SD_LBA+3
        ldx     #SECTOR_BUF
        stx     SD_BUF_PTR
        jsr     SD_READ_SECTOR
        tsta
        bne     SD_OPEN_FAIL
        ldx     #SECTOR_BUF
SD_OPEN_SEARCH_LOOP:
        stx     SD_BYTE_PTR ; Save start of current entry
        ldaa    0,x
        beq     SD_OPEN_FAIL
        cmpa    #$E5
        beq     SD_OPEN_NEXT
        ldaa    11,x
        cmpa    #$0F
        beq     SD_OPEN_NEXT
        stx     SD_X_SAVE
        ldab    #0          ; B is our character index (0 to 10)
SD_OPEN_CMP:
        pshb                ; Save index
        jsr     SD_GET_NAME_X ; X = SD_ARG + B
        ldaa    0,x         ; Load target character
        ldx     SD_X_SAVE   ; Load directory entry pointer
        cmpa    0,x         ; Compare
        bne     SD_OPEN_CMP_FAIL
        inx                 ; Next char in dir entry
        stx     SD_X_SAVE   ; Save updated pointer
        pulb                ; Restore index
        incb                ; Next char
        cmpb    #11         ; Checked all 11?
        blo     SD_OPEN_CMP
        ldx     SD_X_SAVE
        bra     SD_OPEN_FOUND
SD_OPEN_CMP_FAIL:
        pulb                ; Restore index to keep stack balanced
SD_OPEN_NEXT:
        ldx     SD_BYTE_PTR ; Restore X to start of entry
        ldab    #32
SD_OPEN_ADV:
        inx
        decb
        bne     SD_OPEN_ADV
        cpx     #SECTOR_BUF + 512
        blo     SD_OPEN_SEARCH_LOOP
SD_OPEN_FAIL:
        ldaa    #$FF
        rts
SD_OPEN_FOUND:
        ldx     SD_BYTE_PTR ; Restore X to start of entry
        ldaa    21,x
        staa    SD_FILE_CLUS
        ldaa    20,x
        staa    SD_FILE_CLUS+1
        ldaa    27,x
        staa    SD_FILE_CLUS+2
        ldaa    26,x
        staa    SD_FILE_CLUS+3
        clr     SD_SEC_IN_CLUS
        ldx     #0
        stx     SD_BYTE_PTR
        jsr     SD_LOAD_NEXT_SECTOR
        tsta
        bne     SD_OPEN_FAIL
        ldaa    #1
        staa    SD_LOAD_ACTIVE
        clra
        rts

SD_LOAD_NEXT_SECTOR:
        ldaa    SD_FILE_CLUS+3
        suba    #2
        staa    SD_LBA+3
        ldaa    SD_FILE_CLUS+2
        sbca    #0
        staa    SD_LBA+2
        ldaa    SD_FILE_CLUS+1
        sbca    #0
        staa    SD_LBA+1
        ldaa    SD_FILE_CLUS
        sbca    #0
        staa    SD_LBA
        ldaa    SD_LBA+3
        adda    FAT_DATA_SEC+3
        staa    SD_LBA+3
        ldaa    SD_LBA+2
        adca    FAT_DATA_SEC+2
        staa    SD_LBA+2
        ldaa    SD_LBA+1
        adca    FAT_DATA_SEC+1
        staa    SD_LBA+1
        ldaa    SD_LBA
        adca    FAT_DATA_SEC
        staa    SD_LBA
        ldaa    SD_LBA+3
        adda    SD_SEC_IN_CLUS
        staa    SD_LBA+3
        ldaa    SD_LBA+2
        adca    #0
        staa    SD_LBA+2
        ldaa    SD_LBA+1
        adca    #0
        staa    SD_LBA+1
        ldaa    SD_LBA
        adca    #0
        staa    SD_LBA
        ldx     #SECTOR_BUF
        stx     SD_BUF_PTR
        jsr     SD_READ_SECTOR
        rts

SD_GETC:
        pshb
        tst     SD_LOAD_ACTIVE
        beq     SD_GETC_EOF_POP
        ldaa    SD_BYTE_PTR     ; High byte
        cmpa    #2              ; < 512?
        blo     SD_GETC_READ
        inc     SD_SEC_IN_CLUS
        ldaa    SD_SEC_IN_CLUS
        cmpa    FAT_SEC_PER_CLUS
        blo     SD_GETC_NEXT_SEC
        bra     SD_GETC_EOF_POP
SD_GETC_NEXT_SEC:
        jsr     SD_LOAD_NEXT_SECTOR
        tsta
        bne     SD_GETC_EOF_POP
        ldx     #0
        stx     SD_BYTE_PTR
SD_GETC_READ:
        ldab    SD_BYTE_PTR+1
        ldaa    SD_BYTE_PTR
        beq     SD_GETC_PAGE0
        ldx     #SECTOR_BUF + 256
        bra     SD_GETC_FETCH
SD_GETC_PAGE0:
        ldx     #SECTOR_BUF
SD_GETC_FETCH:
        stx     SD_X_SAVE
        ldaa    SD_X_SAVE+1
        aba
        staa    SD_X_SAVE+1
        ldaa    SD_X_SAVE
        adca    #0
        staa    SD_X_SAVE
        ldx     SD_X_SAVE
        ldaa    0,x
        psha
        ldx     SD_BYTE_PTR
        inx
        stx     SD_BYTE_PTR
        pula
        pulb
        clc
        rts
SD_GETC_EOF_POP:
        pulb
SD_GETC_EOF:
        clr     SD_LOAD_ACTIVE
        sec
        rts
