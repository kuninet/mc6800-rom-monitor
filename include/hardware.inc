; MC6800 ROM monitor hardware definitions

ROM_BASE         equ $E000
ROM_END          equ $FFFF

RAM_START        equ $0000
RAM_END          equ $1FFF
STACK_TOP        equ RAM_END

ACIA_CTRL        equ $8018
ACIA_DATA        equ $8019

CHR_CR           equ $0D
CHR_LF           equ $0A
CHR_BS           equ $08
CHR_DEL          equ $7F
CHR_SPACE        equ $20
CHR_PROMPT       equ ']'
CHR_ECHO         equ '='
CHR_QUESTION     equ '?'

LINE_BUF_SIZE    equ 32
LINE_BUF         equ RAM_START
LINE_PTR         equ LINE_BUF+LINE_BUF_SIZE
LINE_LEN         equ LINE_PTR+2
HEX_VALUE_HI     equ LINE_LEN+1
HEX_VALUE_LO     equ HEX_VALUE_HI+1
HEX_NIBBLE       equ HEX_VALUE_LO+1
DUMP_ADDR        equ HEX_NIBBLE+1
MOD_ADDR         equ DUMP_ADDR+2

ACIA_STAT_RDRF   equ $01
ACIA_STAT_TDRE   equ $02

ACIA_CTRL_RESET  equ $03
ACIA_CTRL_INIT   equ $15

VEC_IRQ          equ $FFF8
VEC_SWI          equ $FFFA
VEC_NMI          equ $FFFC
VEC_RESET        equ $FFFE
