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

; --- Variables (RAM Zero Page) ---
LINE_BUF         equ RAM_START
LINE_BUF_SIZE    equ 80

; Monitor state vars
LINE_PTR         equ $0052
LINE_LEN         equ $0054
HEX_VALUE_HI     equ $0055
HEX_VALUE_LO     equ $0056
HEX_NIBBLE       equ $0057

DUMP_ADDR        equ $0058
MOD_ADDR         equ $005A
DUMP_END         equ $005C
DUMP_COUNT       equ $005E
DISASM_ADDR      equ $005F
DISASM_COUNT     equ $0061

; Loader state vars
LOADER_MODE      equ $0062
LOADER_STAGE     equ $0063
LOADER_TYPE      equ $0064
LOADER_COUNT     equ $0065
LOADER_ADDR      equ $0066
LOADER_SUM       equ $0068
LOADER_PARSE_PTR equ $0069

; Breakpoint / Register save area
BP_ADDR          equ $006B
BP_ORIG          equ $006D
BP_ACTIVE        equ $006E
BRK_ACTIVE       equ $006F
BRK_ADDR         equ $0070
BRK_FRAME        equ $0072
BRK_USER_SP      equ $0074
BRK_SAVE_CC      equ $0076
BRK_SAVE_B       equ $0077
BRK_SAVE_A       equ $0078
BRK_SAVE_X       equ $0079
BRK_SAVE_PC      equ $007B
FILL_VALUE       equ $007D

; Parser / Command variables
ARG_PTR          equ $0080
ARG_LEN          equ $0082
ARG2_PTR         equ $0083
ARG2_LEN         equ $0085

; SD / FAT state vars
SD_NAME_PTR      equ $0087
SD_ARG           equ $0089
SD_LBA           equ $008D
SD_BUF_PTR       equ $0091
FAT_SEC_PER_CLUS equ $0093
FAT_RSVD_SEC     equ $0094
FAT_NUM_FATS     equ $0096
FAT_SIZE         equ $0097
FAT_ROOT_CLUS    equ $009B
FAT_DATA_SEC     equ $009F
SD_X_SAVE        equ $00A3
SD_LOAD_ACTIVE   equ $00A5
SD_FILE_CLUS     equ $00A6
SD_SEC_IN_CLUS   equ $00AA
SD_BYTE_PTR      equ $00AB

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
