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

ACIA_STAT_RDRF   equ $01
ACIA_STAT_TDRE   equ $02

ACIA_CTRL_RESET  equ $03
ACIA_CTRL_INIT   equ $15

VEC_IRQ          equ $FFF8
VEC_SWI          equ $FFFA
VEC_NMI          equ $FFFC
VEC_RESET        equ $FFFE
