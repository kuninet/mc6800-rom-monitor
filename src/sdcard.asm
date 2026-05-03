; Minimal SDHC SPI sector read via MC6821 PIA Port B.
; This module is an internal API for later FAT code. It adds no monitor command.

SD_INIT:
        clr     SD_ERROR
        jsr     SD_PIA_INIT

        ldab    #10
SD_INIT_DUMMY_LOOP:
        ldaa    #$FF
        jsr     SD_SPI_XFER
        decb
        bne     SD_INIT_DUMMY_LOOP

        jsr     SD_SELECT

        ldaa    #$40
        staa    SD_CMD_BYTE
        clr     SD_LBA0
        clr     SD_LBA1
        clr     SD_LBA2
        clr     SD_LBA3
        ldaa    #$95
        staa    SD_CRC_BYTE
        jsr     SD_SEND_CMD
        bcc     SD_INIT_CMD0_R1
        jmp     SD_INIT_FAIL
SD_INIT_CMD0_R1:
        cmpa    #$01
        beq     SD_INIT_CMD8
        ldaa    #SD_ERR_R1
        jmp     SD_FAIL_A

SD_INIT_CMD8:
        ldaa    #$48
        staa    SD_CMD_BYTE
        clr     SD_LBA0
        clr     SD_LBA1
        ldaa    #$01
        staa    SD_LBA2
        ldaa    #$AA
        staa    SD_LBA3
        ldaa    #$87
        staa    SD_CRC_BYTE
        jsr     SD_SEND_CMD
        bcc     SD_INIT_CMD8_R1
        jmp     SD_INIT_FAIL
SD_INIT_CMD8_R1:
        cmpa    #$01
        beq     SD_INIT_R7_1
        ldaa    #SD_ERR_R1
        jmp     SD_FAIL_A

SD_INIT_R7_1:
        ldaa    #$FF
        jsr     SD_SPI_XFER
        bne     SD_INIT_R7_FAIL
        ldaa    #$FF
        jsr     SD_SPI_XFER
        bne     SD_INIT_R7_FAIL
        ldaa    #$FF
        jsr     SD_SPI_XFER
        cmpa    #$01
        bne     SD_INIT_R7_FAIL
        ldaa    #$FF
        jsr     SD_SPI_XFER
        cmpa    #$AA
        beq     SD_INIT_ACMD41_PREP
SD_INIT_R7_FAIL:
        ldaa    #SD_ERR_R7
        jmp     SD_FAIL_A

SD_INIT_ACMD41_PREP:
        ldx     #$0100
        stx     SD_TIMEOUT_HI

SD_INIT_ACMD41_LOOP:
        ldaa    #$77
        staa    SD_CMD_BYTE
        clr     SD_LBA0
        clr     SD_LBA1
        clr     SD_LBA2
        clr     SD_LBA3
        ldaa    #$FF
        staa    SD_CRC_BYTE
        jsr     SD_SEND_CMD
        bcc     SD_INIT_CMD55_R1
        jmp     SD_INIT_FAIL
SD_INIT_CMD55_R1:
        cmpa    #$02
        bhs     SD_INIT_R1_FAIL

        ldaa    #$69
        staa    SD_CMD_BYTE
        ldaa    #$40
        staa    SD_LBA0
        clr     SD_LBA1
        clr     SD_LBA2
        clr     SD_LBA3
        ldaa    #$FF
        staa    SD_CRC_BYTE
        jsr     SD_SEND_CMD
        bcc     SD_INIT_ACMD41_R1
        jmp     SD_INIT_FAIL
SD_INIT_ACMD41_R1:
        cmpa    #$00
        beq     SD_INIT_CMD58
        cmpa    #$01
        bne     SD_INIT_R1_FAIL

        ldx     SD_TIMEOUT_HI
        dex
        stx     SD_TIMEOUT_HI
        bne     SD_INIT_ACMD41_LOOP
        ldaa    #SD_ERR_TIMEOUT
        jmp     SD_FAIL_A

SD_INIT_R1_FAIL:
        ldaa    #SD_ERR_R1
        jmp     SD_FAIL_A

SD_INIT_CMD58:
        ldaa    #$7A
        staa    SD_CMD_BYTE
        clr     SD_LBA0
        clr     SD_LBA1
        clr     SD_LBA2
        clr     SD_LBA3
        ldaa    #$FF
        staa    SD_CRC_BYTE
        jsr     SD_SEND_CMD
        bcc     SD_INIT_CMD58_R1
        jmp     SD_INIT_FAIL
SD_INIT_CMD58_R1:
        cmpa    #$00
        beq     SD_INIT_OCR
        ldaa    #SD_ERR_R1
        jmp     SD_FAIL_A

SD_INIT_OCR:
        ldaa    #$FF
        jsr     SD_SPI_XFER
        anda    #$40
        beq     SD_INIT_OCR_FAIL
        ldaa    #$FF
        jsr     SD_SPI_XFER
        ldaa    #$FF
        jsr     SD_SPI_XFER
        ldaa    #$FF
        jsr     SD_SPI_XFER
        jsr     SD_DESELECT
        ldaa    #SD_ERR_NONE
        staa    SD_ERROR
        clc
        rts

SD_INIT_OCR_FAIL:
        ldaa    #SD_ERR_OCR
        jmp     SD_FAIL_A

SD_INIT_FAIL:
        jmp     SD_FAIL

SD_READ_SECTOR:
        stx     SD_BUF_PTR
        jsr     SD_SELECT
        ldaa    #$51
        staa    SD_CMD_BYTE
        ldaa    #$FF
        staa    SD_CRC_BYTE
        jsr     SD_SEND_CMD
        bcc     SD_READ_R1
        jmp     SD_READ_FAIL
SD_READ_R1:
        cmpa    #$00
        beq     SD_READ_WAIT_TOKEN_PREP
        ldaa    #SD_ERR_R1
        jmp     SD_FAIL_A

SD_READ_WAIT_TOKEN_PREP:
        ldx     #$0200
        stx     SD_TIMEOUT_HI
SD_READ_WAIT_TOKEN:
        ldaa    #$FF
        jsr     SD_SPI_XFER
        cmpa    #$FE
        beq     SD_READ_DATA_PREP
        cmpa    #$FF
        bne     SD_READ_TOKEN_FAIL
        ldx     SD_TIMEOUT_HI
        dex
        stx     SD_TIMEOUT_HI
        bne     SD_READ_WAIT_TOKEN
        ldaa    #SD_ERR_TIMEOUT
        jmp     SD_FAIL_A

SD_READ_TOKEN_FAIL:
        ldaa    #SD_ERR_TOKEN
        jmp     SD_FAIL_A

SD_READ_DATA_PREP:
        ldx     #$0200
        stx     SD_TIMEOUT_HI
SD_READ_DATA_LOOP:
        ldaa    #$FF
        jsr     SD_SPI_XFER
        ldx     SD_BUF_PTR
        staa    0,x
        inx
        stx     SD_BUF_PTR
        ldx     SD_TIMEOUT_HI
        dex
        stx     SD_TIMEOUT_HI
        bne     SD_READ_DATA_LOOP

        ldaa    #$FF
        jsr     SD_SPI_XFER
        ldaa    #$FF
        jsr     SD_SPI_XFER
        jsr     SD_DESELECT
        ldaa    #SD_ERR_NONE
        staa    SD_ERROR
        clc
        rts

SD_READ_FAIL:
        jmp     SD_FAIL

SD_SEND_CMD:
        ldaa    SD_CMD_BYTE
        jsr     SD_SPI_XFER
        ldaa    SD_LBA0
        jsr     SD_SPI_XFER
        ldaa    SD_LBA1
        jsr     SD_SPI_XFER
        ldaa    SD_LBA2
        jsr     SD_SPI_XFER
        ldaa    SD_LBA3
        jsr     SD_SPI_XFER
        ldaa    SD_CRC_BYTE
        jsr     SD_SPI_XFER
        jmp     SD_WAIT_R1

SD_WAIT_R1:
        ldab    #16
SD_WAIT_R1_LOOP:
        ldaa    #$FF
        jsr     SD_SPI_XFER
        cmpa    #$FF
        bne     SD_WAIT_R1_OK
        decb
        bne     SD_WAIT_R1_LOOP
        ldaa    #SD_ERR_TIMEOUT
        staa    SD_ERROR
        sec
        rts
SD_WAIT_R1_OK:
        staa    SD_RX
        clc
        rts

SD_PIA_INIT:
        clr     PIA_CRB
        ldaa    #SPI_OUTPUT_MASK
        staa    PIA_PRB
        ldaa    #PIA_DDR_SELECT
        staa    PIA_CRB
        ldaa    #SPI_CS
        staa    SD_PORTB_SHADOW
        staa    PIA_PRB
        rts

SD_SELECT:
        ldaa    SD_PORTB_SHADOW
        anda    #$FF-SPI_CS-SPI_SCLK
        staa    SD_PORTB_SHADOW
        staa    PIA_PRB
        rts

SD_DESELECT:
        ldaa    SD_PORTB_SHADOW
        oraa    #SPI_CS
        anda    #$FF-SPI_SCLK
        staa    SD_PORTB_SHADOW
        staa    PIA_PRB
        ldaa    #$FF
        jsr     SD_SPI_XFER
        rts

SD_SPI_XFER:
        staa    SD_TX
        clr     SD_RX
        ldaa    #8
        staa    SD_BIT_COUNT
SD_SPI_XFER_LOOP:
        asl     SD_TX
        bcs     SD_SPI_XFER_MOSI_1
        ldaa    SD_PORTB_SHADOW
        anda    #$FF-SPI_MOSI-SPI_SCLK
        bra     SD_SPI_XFER_MOSI_SET
SD_SPI_XFER_MOSI_1:
        ldaa    SD_PORTB_SHADOW
        oraa    #SPI_MOSI
        anda    #$FF-SPI_SCLK
SD_SPI_XFER_MOSI_SET:
        staa    SD_PORTB_SHADOW
        staa    PIA_PRB

        ldaa    SD_PORTB_SHADOW
        oraa    #SPI_SCLK
        staa    PIA_PRB

        ldaa    SD_RX
        asla
        staa    SD_RX
        ldaa    PIA_PRB
        anda    #SPI_MISO
        beq     SD_SPI_XFER_CLOCK_LOW
        inc     SD_RX

SD_SPI_XFER_CLOCK_LOW:
        ldaa    SD_PORTB_SHADOW
        staa    PIA_PRB
        dec     SD_BIT_COUNT
        bne     SD_SPI_XFER_LOOP
        ldaa    SD_RX
        clc
        rts

SD_FAIL_A:
        staa    SD_ERROR
SD_FAIL:
        jsr     SD_DESELECT
        sec
        rts
