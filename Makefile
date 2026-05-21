ASL ?= asl
P2BIN ?= p2bin
P2HEX ?= p2hex
MINIPRO ?= minipro
PYTHON ?= python3

MONITOR_PROFILE ?= base
ifeq ($(MONITOR_PROFILE),base)
PROFILE_TARGET_SUFFIX :=
PROFILE_MEMORY_CONFIG := base8k
PROFILE_BOARD_IO := none
PROFILE_FEATURE_SD := 0
PROFILE_FEATURE_FAT := 0
PROFILE_FEATURE_VDG := 0
PROFILE_FEATURE_KEYBOARD := 0
PROFILE_FEATURE_I2C := 0
PROFILE_VDG_VRAM_CONFIG := a000
else ifeq ($(MONITOR_PROFILE),sbcio)
PROFILE_TARGET_SUFFIX := -sbcio
PROFILE_MEMORY_CONFIG := ram64_c000_work
PROFILE_BOARD_IO := sbcio
PROFILE_FEATURE_SD := 1
PROFILE_FEATURE_FAT := 1
PROFILE_FEATURE_VDG := 0
PROFILE_FEATURE_KEYBOARD := 1
PROFILE_FEATURE_I2C := 0
PROFILE_VDG_VRAM_CONFIG := a000
else ifeq ($(MONITOR_PROFILE),sbcio_vdg)
PROFILE_TARGET_SUFFIX := -sbcio-vdg
PROFILE_MEMORY_CONFIG := ram64_c000_work
PROFILE_BOARD_IO := sbcio
PROFILE_FEATURE_SD := 1
PROFILE_FEATURE_FAT := 0
PROFILE_FEATURE_VDG := 1
PROFILE_FEATURE_KEYBOARD := 1
PROFILE_FEATURE_I2C := 0
PROFILE_VDG_VRAM_CONFIG := a000
else ifeq ($(MONITOR_PROFILE),k6802_vdg)
PROFILE_TARGET_SUFFIX := -k6802-vdg
PROFILE_MEMORY_CONFIG := ram64_a000_work
PROFILE_BOARD_IO := sbcio
PROFILE_FEATURE_SD := 1
PROFILE_FEATURE_FAT := 0
PROFILE_FEATURE_VDG := 1
PROFILE_FEATURE_KEYBOARD := 1
PROFILE_FEATURE_I2C := 0
PROFILE_VDG_VRAM_CONFIG := c000
else
$(error Unsupported MONITOR_PROFILE '$(MONITOR_PROFILE)')
endif

AXIS_OVERRIDE :=
ifneq ($(filter command line environment environment override,$(origin MEMORY_CONFIG)),)
AXIS_OVERRIDE := 1
endif
ifneq ($(filter command line environment environment override,$(origin BOARD_IO)),)
AXIS_OVERRIDE := 1
endif
ifneq ($(filter command line environment environment override,$(origin FEATURE_SD)),)
AXIS_OVERRIDE := 1
endif
ifneq ($(filter command line environment environment override,$(origin FEATURE_FAT)),)
AXIS_OVERRIDE := 1
endif
ifneq ($(filter command line environment environment override,$(origin FEATURE_VDG)),)
AXIS_OVERRIDE := 1
endif
ifneq ($(filter command line environment environment override,$(origin FEATURE_KEYBOARD)),)
AXIS_OVERRIDE := 1
endif
ifneq ($(filter command line environment environment override,$(origin FEATURE_I2C)),)
AXIS_OVERRIDE := 1
endif
ifneq ($(filter command line environment environment override,$(origin VDG_VRAM_CONFIG)),)
AXIS_OVERRIDE := 1
endif

MEMORY_CONFIG ?= $(PROFILE_MEMORY_CONFIG)
BOARD_IO ?= $(PROFILE_BOARD_IO)
FEATURE_SD ?= $(PROFILE_FEATURE_SD)
FEATURE_FAT ?= $(PROFILE_FEATURE_FAT)
FEATURE_VDG ?= $(PROFILE_FEATURE_VDG)
FEATURE_KEYBOARD ?= $(PROFILE_FEATURE_KEYBOARD)
FEATURE_I2C ?= $(PROFILE_FEATURE_I2C)
VDG_VRAM_CONFIG ?= $(PROFILE_VDG_VRAM_CONFIG)

VALID_MEMORY_CONFIGS := base8k ram64_c000_work ram64_a000_work
VALID_BOARD_IO := none sbcio
VALID_FEATURE_VALUES := 0 1
VALID_VDG_VRAM_CONFIGS := a000 c000

ifeq ($(filter $(MEMORY_CONFIG),$(VALID_MEMORY_CONFIGS)),)
$(error Unsupported MEMORY_CONFIG '$(MEMORY_CONFIG)')
endif
ifeq ($(filter $(BOARD_IO),$(VALID_BOARD_IO)),)
$(error Unsupported BOARD_IO '$(BOARD_IO)')
endif
ifeq ($(filter $(FEATURE_SD),$(VALID_FEATURE_VALUES)),)
$(error Unsupported FEATURE_SD '$(FEATURE_SD)')
endif
ifeq ($(filter $(FEATURE_FAT),$(VALID_FEATURE_VALUES)),)
$(error Unsupported FEATURE_FAT '$(FEATURE_FAT)')
endif
ifeq ($(filter $(FEATURE_VDG),$(VALID_FEATURE_VALUES)),)
$(error Unsupported FEATURE_VDG '$(FEATURE_VDG)')
endif
ifeq ($(filter $(FEATURE_KEYBOARD),$(VALID_FEATURE_VALUES)),)
$(error Unsupported FEATURE_KEYBOARD '$(FEATURE_KEYBOARD)')
endif
ifeq ($(filter $(FEATURE_I2C),$(VALID_FEATURE_VALUES)),)
$(error Unsupported FEATURE_I2C '$(FEATURE_I2C)')
endif
ifeq ($(filter $(VDG_VRAM_CONFIG),$(VALID_VDG_VRAM_CONFIGS)),)
$(error Unsupported VDG_VRAM_CONFIG '$(VDG_VRAM_CONFIG)')
endif

ifneq ($(FEATURE_SD),0)
ifneq ($(BOARD_IO),sbcio)
$(error FEATURE_SD=1 requires BOARD_IO=sbcio)
endif
endif
ifneq ($(FEATURE_FAT),0)
ifeq ($(FEATURE_SD),0)
$(error FEATURE_FAT=1 requires FEATURE_SD=1)
endif
endif
ifneq ($(FEATURE_KEYBOARD),0)
ifneq ($(BOARD_IO),sbcio)
$(error FEATURE_KEYBOARD=1 requires BOARD_IO=sbcio)
endif
endif
ifneq ($(FEATURE_I2C),0)
ifneq ($(BOARD_IO),sbcio)
$(error FEATURE_I2C=1 requires BOARD_IO=sbcio)
endif
endif

ifneq ($(BUILD_CONFIG_NAME),)
TARGET_SUFFIX := -$(BUILD_CONFIG_NAME)
else ifeq ($(AXIS_OVERRIDE),1)
TARGET_SUFFIX := -$(MEMORY_CONFIG)-$(BOARD_IO)-sd$(FEATURE_SD)-vdg$(FEATURE_VDG)-vram$(VDG_VRAM_CONFIG)-key$(FEATURE_KEYBOARD)-i2c$(FEATURE_I2C)
else
TARGET_SUFFIX := $(PROFILE_TARGET_SUFFIX)
endif

TARGET := mc6800-monitor$(TARGET_SUFFIX)
OUTDIR := build
TOPSRC := src/main.asm
STAGE1_TOPSRC := src/stage1.asm
OBJ := $(OUTDIR)/$(TARGET).p
LST := $(OUTDIR)/$(TARGET).lst
BIN := $(OUTDIR)/$(TARGET).bin
SREC := $(OUTDIR)/$(TARGET).srec
IHEX := $(OUTDIR)/$(TARGET).hex
STAGE1_TARGET := stage1$(TARGET_SUFFIX)
STAGE1_OBJ := $(OUTDIR)/$(STAGE1_TARGET).p
STAGE1_LST := $(OUTDIR)/$(STAGE1_TARGET).lst
STAGE1_BIN := $(OUTDIR)/$(STAGE1_TARGET).bin
CONFIG_INC := $(OUTDIR)/monitor_config.inc
ROM_KIND ?= 27C64
ROM_FILL ?= 0xFF
ROM_CODE_LIMIT ?= 8192

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
else
ASL_PATHSEP := :
ASL_INCLUDE_ARG = "$(ASL_INCLUDE)"
MKDIR_P := mkdir -p "$(OUTDIR)"
RM_RF := rm -rf "$(OUTDIR)"
endif

ASL_INCLUDE := $(CURDIR)/$(OUTDIR)$(ASL_PATHSEP)$(CURDIR)/include$(ASL_PATHSEP)$(CURDIR)/src

.PHONY: all clean bin check-rom-size srec ihex stage1 check-stage1-profile rombin rombin-27c64 rombin-27c128 rombin-27c256 rombin-28c256 rombin-w27c512 program verify readback program-27c64 program-27c128 program-27c256 program-28c256 program-w27c512 program-upd28c256 FORCE

all: check-rom-size srec ihex

$(OUTDIR):
	$(MKDIR_P)

$(CONFIG_INC): FORCE tools/generate_monitor_config.py | $(OUTDIR)
	"$(PYTHON)" tools/generate_monitor_config.py --output "$(CONFIG_INC)" --monitor-profile "$(MONITOR_PROFILE)" --memory-config "$(MEMORY_CONFIG)" --board-io "$(BOARD_IO)" --feature-sd "$(FEATURE_SD)" --feature-fat "$(FEATURE_FAT)" --feature-vdg "$(FEATURE_VDG)" --feature-keyboard "$(FEATURE_KEYBOARD)" --feature-i2c "$(FEATURE_I2C)" --vdg-vram-config "$(VDG_VRAM_CONFIG)"

$(OBJ): FORCE $(TOPSRC) include/hardware.inc include/mikbug.inc $(CONFIG_INC) src/acia6850.asm src/sdcard.asm src/fat32.asm | $(OUTDIR)
	"$(ASL)" -q -L -olist $(LST) -o $(OBJ) -i $(ASL_INCLUDE_ARG) $(TOPSRC)

bin: check-rom-size

$(BIN): $(OBJ)
	"$(P2BIN)" $(OBJ) $(BIN) -q

check-rom-size: $(BIN)
	"$(PYTHON)" -c "from pathlib import Path; import sys; p=Path('$(BIN)'); size=p.stat().st_size; limit=int('$(ROM_CODE_LIMIT)', 0); print(f'{p}: {size}/{limit} bytes'); sys.exit(0 if limit <= 0 or size <= limit else 1)"

stage1: check-stage1-profile $(STAGE1_BIN)

check-stage1-profile:
	"$(PYTHON)" -c "import sys; profile='$(MONITOR_PROFILE)'; sys.exit(0 if profile in ('sbcio_vdg', 'k6802_vdg') else 1)" || (echo "stage1 target requires MONITOR_PROFILE=sbcio_vdg or MONITOR_PROFILE=k6802_vdg" && exit 1)

$(STAGE1_OBJ): FORCE $(STAGE1_TOPSRC) include/hardware.inc $(CONFIG_INC) src/sdcard.asm src/fat32.asm | $(OUTDIR)
	"$(ASL)" -q -L -olist $(STAGE1_LST) -o $(STAGE1_OBJ) -i $(ASL_INCLUDE_ARG) $(STAGE1_TOPSRC)

$(STAGE1_BIN): $(STAGE1_OBJ)
	"$(P2BIN)" $(STAGE1_OBJ) $(STAGE1_BIN) -q

srec: $(SREC)

$(SREC): $(OBJ)
	"$(P2HEX)" $(OBJ) $(SREC) -q -F Moto -M 2

ihex: $(IHEX)

$(IHEX): $(OBJ)
	"$(P2HEX)" $(OBJ) $(IHEX) -q -F Intel -i 1

rombin: check-rom-size $(ROMBIN)

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

program: check-rom-size $(ROMBIN)
	$(MINIPRO) -p "$(MINIPRO_DEVICE)" -w $(ROMBIN)

verify: check-rom-size $(ROMBIN)
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
