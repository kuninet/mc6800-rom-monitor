ASL ?= asl
P2BIN ?= p2bin
P2HEX ?= p2hex
MINIPRO ?= minipro

TARGET := mc6800-monitor
OUTDIR := build
TOPSRC := src/main.asm
OBJ := $(OUTDIR)/$(TARGET).p
LST := $(OUTDIR)/$(TARGET).lst
BIN := $(OUTDIR)/$(TARGET).bin
SREC := $(OUTDIR)/$(TARGET).srec
IHEX := $(OUTDIR)/$(TARGET).hex
ROM_KIND ?= 27C64
ROM_FILL ?= 0xFF

ifeq ($(ROM_KIND),27C64)
ROM_CHIP_SIZE := 0x2000
ROM_RANGE_START := 0xE000
ROM_RANGE_END := 0xFFFF
MINIPRO_DEVICE ?= 27C64@DIP28
else ifeq ($(ROM_KIND),27C128)
ROM_CHIP_SIZE := 0x4000
ROM_RANGE_START := 0xC000
ROM_RANGE_END := 0xFFFF
MINIPRO_DEVICE ?= 27C128@DIP28
else ifeq ($(ROM_KIND),27C256)
ROM_CHIP_SIZE := 0x8000
ROM_RANGE_START := 0x8000
ROM_RANGE_END := 0xFFFF
MINIPRO_DEVICE ?= 27C256@DIP28
else ifeq ($(ROM_KIND),28C256)
ROM_CHIP_SIZE := 0x8000
ROM_RANGE_START := 0x8000
ROM_RANGE_END := 0xFFFF
MINIPRO_DEVICE ?= 28C256@DIP28
else ifeq ($(ROM_KIND),UPD28C256)
ROM_CHIP_SIZE := 0x8000
ROM_RANGE_START := 0x8000
ROM_RANGE_END := 0xFFFF
MINIPRO_DEVICE ?= UPD28C256
else ifeq ($(ROM_KIND),W27C512)
ROM_CHIP_SIZE := 0x10000
ROM_RANGE_START := 0x0000
ROM_RANGE_END := 0xFFFF
MINIPRO_DEVICE ?= W27C512@DIP28
else
$(error Unsupported ROM_KIND '$(ROM_KIND)')
endif

ROMBIN := $(OUTDIR)/$(TARGET)-$(ROM_KIND).bin

ifeq ($(OS),Windows_NT)
ASL_PATHSEP := ;
ASL_INCLUDE_ARG = $(ASL_INCLUDE)
MKDIR_P := if not exist "$(OUTDIR)" mkdir "$(OUTDIR)"
RM_RF := if exist "$(OUTDIR)" rmdir /s /q "$(OUTDIR)"
else
ASL_PATHSEP := :
ASL_INCLUDE_ARG = "$(ASL_INCLUDE)"
MKDIR_P := mkdir -p "$(OUTDIR)"
RM_RF := rm -rf "$(OUTDIR)"
endif

ASL_INCLUDE := $(CURDIR)/include$(ASL_PATHSEP)$(CURDIR)/src

.PHONY: all clean bin srec ihex rombin rombin-27c64 rombin-27c128 rombin-27c256 rombin-28c256 rombin-w27c512 program verify readback program-27c64 program-27c128 program-27c256 program-28c256 program-w27c512 program-upd28c256

all: srec ihex

$(OUTDIR):
	$(MKDIR_P)

$(OBJ): $(TOPSRC) include/hardware.inc include/mikbug.inc src/acia6850.asm | $(OUTDIR)
	$(ASL) -q -L -olist $(LST) -o $(OBJ) -i $(ASL_INCLUDE_ARG) $(TOPSRC)

bin: $(BIN)

$(BIN): $(OBJ)
	$(P2BIN) $(OBJ) $(BIN) -q

srec: $(SREC)

$(SREC): $(OBJ)
	$(P2HEX) $(OBJ) $(SREC) -q -F Moto -M 2

ihex: $(IHEX)

$(IHEX): $(OBJ)
	$(P2HEX) $(OBJ) $(IHEX) -q -F Intel -i 1

rombin: $(ROMBIN)

$(ROMBIN): $(OBJ)
	$(P2BIN) $(OBJ) $(ROMBIN) -q -r $(ROM_RANGE_START)-$(ROM_RANGE_END) -l $(ROM_FILL)

rombin-27c64:
	$(MAKE) rombin ROM_KIND=27C64

rombin-27c128:
	$(MAKE) rombin ROM_KIND=27C128

rombin-27c256:
	$(MAKE) rombin ROM_KIND=27C256

rombin-28c256:
	$(MAKE) rombin ROM_KIND=28C256

rombin-w27c512:
	$(MAKE) rombin ROM_KIND=W27C512

program: $(ROMBIN)
	$(MINIPRO) -p "$(MINIPRO_DEVICE)" -w $(ROMBIN)

verify: $(ROMBIN)
	$(MINIPRO) -p "$(MINIPRO_DEVICE)" -m $(ROMBIN)

readback:
	$(MINIPRO) -p "$(MINIPRO_DEVICE)" -r $(OUTDIR)/$(TARGET)-$(ROM_KIND)-readback.bin

program-27c64:
	$(MAKE) program ROM_KIND=27C64

program-27c128:
	$(MAKE) program ROM_KIND=27C128

program-27c256:
	$(MAKE) program ROM_KIND=27C256

program-28c256:
	$(MAKE) program ROM_KIND=28C256

program-w27c512:
	$(MAKE) program ROM_KIND=W27C512

program-upd28c256:
	$(MAKE) program ROM_KIND=UPD28C256


clean:
	$(RM_RF)
