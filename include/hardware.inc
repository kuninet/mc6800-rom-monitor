; MC6800 ROM monitor unified definitions

; --- Memory Map ---
ROM_BASE         equ $E000
ROM_END          equ $FFFF
MONITOR_BASE     equ $E200
RAM_START        equ $0000
RAM_END          equ $1FFF
MIKBUG_VAR_BASE  equ $1F00
MIKBUG_STACK_TOP equ $1F42
STACK_TOP        equ MIKBUG_STACK_TOP
MONITOR_RAM_BASE equ $1E00

; --- Peripherals ---
ACIA_CTRL        equ $8018
ACIA_DATA        equ $8019
PIA_PRA          equ $8050
PIA_CRA          equ $8051
PIA_PRB          equ $8052
PIA_CRB          equ $8053

SPI_SCLK         equ $01
SPI_MOSI         equ $02
SPI_MISO         equ $04
SPI_CS           equ $08
SPI_CD           equ $10
SPI_WP           equ $20

; --- Characters ---
CHR_CR           equ $0D
CHR_LF           equ $0A
CHR_BS           equ $08
CHR_DEL          equ $7F
CHR_SPACE        equ $20
CHR_QUESTION     equ '?'
CHR_PROMPT       equ ']'

; --- Variables (RAM starting from MONITOR_RAM_BASE) ---
LINE_BUF_SIZE    equ 80
LINE_BUF         equ MONITOR_RAM_BASE
LINE_PTR         equ LINE_BUF+LINE_BUF_SIZE
LINE_LEN         equ LINE_PTR+2
HEX_VALUE_HI     equ LINE_LEN+1
HEX_VALUE_LO     equ HEX_VALUE_HI+1
HEX_NIBBLE       equ HEX_VALUE_LO+1

DUMP_ADDR        equ HEX_NIBBLE+1
MOD_ADDR         equ DUMP_ADDR+2
DUMP_END         equ MOD_ADDR+2
DUMP_COUNT       equ DUMP_END+2
DISASM_ADDR      equ DUMP_COUNT+1
DISASM_COUNT     equ DISASM_ADDR+2

LOADER_MODE      equ DISASM_COUNT+1
LOADER_STAGE     equ LOADER_MODE+1
LOADER_TYPE      equ LOADER_STAGE+1
LOADER_COUNT     equ LOADER_TYPE+1
LOADER_ADDR      equ LOADER_COUNT+1
LOADER_SUM       equ LOADER_ADDR+2
LOADER_PARSE_PTR equ LOADER_SUM+1

BP_ADDR          equ LOADER_PARSE_PTR+2
BP_ORIG          equ BP_ADDR+2
BP_ACTIVE        equ BP_ORIG+1
BRK_ACTIVE       equ BP_ACTIVE+1
BRK_ADDR         equ BRK_ACTIVE+1
BRK_FRAME        equ BRK_ADDR+2
BRK_USER_SP      equ BRK_FRAME+2
BRK_SAVE_CC      equ BRK_USER_SP+2
BRK_SAVE_B       equ BRK_SAVE_CC+1
BRK_SAVE_A       equ BRK_SAVE_B+1
BRK_SAVE_X       equ BRK_SAVE_A+1
BRK_SAVE_PC      equ BRK_SAVE_X+2
FILL_VALUE       equ BRK_SAVE_PC+2

; Common parser variables
ARG_PTR          equ FILL_VALUE+1
ARG_LEN          equ ARG_PTR+2
ARG2_PTR         equ ARG_LEN+1
ARG2_LEN         equ ARG2_PTR+2

; SD / FAT state vars
SD_NAME_PTR      equ ARG2_LEN+1
SD_ARG           equ SD_NAME_PTR+2
SD_LBA           equ SD_ARG+4
SD_BUF_PTR       equ SD_LBA+4
FAT_SEC_PER_CLUS equ SD_BUF_PTR+2
FAT_RSVD_SEC     equ FAT_SEC_PER_CLUS+1
FAT_NUM_FATS     equ FAT_RSVD_SEC+2
FAT_SIZE         equ FAT_NUM_FATS+1
FAT_ROOT_CLUS    equ FAT_SIZE+4
FAT_DATA_SEC     equ FAT_ROOT_CLUS+4
SD_X_SAVE        equ FAT_DATA_SEC+4
SD_LOAD_ACTIVE   equ SD_X_SAVE+2
SD_FILE_CLUS     equ SD_LOAD_ACTIVE+1
SD_SEC_IN_CLUS   equ SD_FILE_CLUS+4
SD_BYTE_PTR      equ SD_SEC_IN_CLUS+1

SECTOR_BUF       equ $1A00

; --- Loader Constants ---
LOAD_MODE_NONE   equ 0
LOAD_MODE_SREC   equ 1
LOAD_MODE_IHEX   equ 2

ACIA_STAT_RDRF   equ $01
ACIA_STAT_TDRE   equ $02
ACIA_CTRL_RESET  equ $03
ACIA_CTRL_INIT   equ $15

; --- Vector Addresses ---
VEC_IRQ          equ $FFF8
VEC_SWI          equ $FFFA
VEC_NMI          equ $FFFC
VEC_RESET        equ $FFFE

; --- MIKBUG Entry Points ---
MIKBUG_OUTCH     equ $E075
MIKBUG_INCH      equ $E078
MIKBUG_PDATA1    equ $E07E
MIKBUG_CONTRL    equ $E0E3
MIKBUG_INEEE     equ $E1AC
MIKBUG_OUTEEE    equ $E1D1
