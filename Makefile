ASL ?= asl
P2BIN ?= p2bin
P2HEX ?= p2hex
MINIPRO ?= minipro

MONITOR_PROFILE ?= base
ifeq ($(MONITOR_PROFILE),base)
TARGET_SUFFIX :=
else ifeq ($(MONITOR_PROFILE),sbcio)
TARGET_SUFFIX := -sbcio
else
$(error Unsupported MONITOR_PROFILE '$(MONITOR_PROFILE)')
endif

TARGET := mc6800-monitor$(TARGET_SUFFIX)
OUTDIR := build
TOPSRC := src/main.asm
OBJ := $(OUTDIR)/$(TARGET).p
LST := $(OUTDIR)/$(TARGET).lst
BIN := $(OUTDIR)/$(TARGET).bin
SREC := $(OUTDIR)/$(TARGET).srec
IHEX := $(OUTDIR)/$(TARGET).hex
PROFILE_SRC := include/profiles/$(MONITOR_PROFILE).inc
PROFILE_INC := $(OUTDIR)/monitor_profile.inc
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
ASL_INCLUDE_ARG = "$(ASL_INCLUDE)"
MKDIR_P := python -c "from pathlib import Path; Path('$(OUTDIR)').mkdir(parents=True, exist_ok=True)"
RM_RF := python -c "import shutil; shutil.rmtree('$(OUTDIR)', ignore_errors=True)"
COPY_PROFILE := python -c "import shutil; shutil.copyfile('$(PROFILE_SRC)', '$(PROFILE_INC)')"
else
ASL_PATHSEP := :
ASL_INCLUDE_ARG = "$(ASL_INCLUDE)"
MKDIR_P := mkdir -p "$(OUTDIR)"
RM_RF := rm -rf "$(OUTDIR)"
COPY_PROFILE := cp "$(PROFILE_SRC)" "$(PROFILE_INC)"
endif

ASL_INCLUDE := $(CURDIR)/$(OUTDIR)$(ASL_PATHSEP)$(CURDIR)/include$(ASL_PATHSEP)$(CURDIR)/src

.PHONY: all clean bin srec ihex rombin rombin-27c64 rombin-27c128 rombin-27c256 rombin-28c256 rombin-w27c512 program verify readback program-27c64 program-27c128 program-27c256 program-28c256 program-w27c512 program-upd28c256 FORCE

all: srec ihex

$(OUTDIR):
	$(MKDIR_P)

$(PROFILE_INC): FORCE $(PROFILE_SRC) | $(OUTDIR)
	$(COPY_PROFILE)

$(OBJ): FORCE $(TOPSRC) include/hardware.inc include/mikbug.inc $(PROFILE_INC) src/acia6850.asm src/sdcard.asm src/fat32.asm | $(OUTDIR)
	"$(ASL)" -q -L -olist $(LST) -o $(OBJ) -i $(ASL_INCLUDE_ARG) $(TOPSRC)

bin: $(BIN)

$(BIN): $(OBJ)
	"$(P2BIN)" $(OBJ) $(BIN) -q

srec: $(SREC)

$(SREC): $(OBJ)
	"$(P2HEX)" $(OBJ) $(SREC) -q -F Moto -M 2

ihex: $(IHEX)

$(IHEX): $(OBJ)
	"$(P2HEX)" $(OBJ) $(IHEX) -q -F Intel -i 1

rombin: $(ROMBIN)

$(ROMBIN): $(OBJ)
	"$(P2BIN)" $(OBJ) $(ROMBIN) -q -r $(ROM_RANGE_START)-$(ROM_RANGE_END) -l $(ROM_FILL)

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
