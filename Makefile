ASL ?= asl
P2BIN ?= p2bin
P2HEX ?= p2hex

TARGET := mc6800-monitor
OUTDIR := build
TOPSRC := src/main.asm
OBJ := $(OUTDIR)/$(TARGET).p
LST := $(OUTDIR)/$(TARGET).lst
BIN := $(OUTDIR)/$(TARGET).bin
SREC := $(OUTDIR)/$(TARGET).srec
IHEX := $(OUTDIR)/$(TARGET).hex

ifeq ($(OS),Windows_NT)
ASL_PATHSEP := ;
MKDIR_P := if not exist "$(OUTDIR)" mkdir "$(OUTDIR)"
RM_RF := if exist "$(OUTDIR)" rmdir /s /q "$(OUTDIR)"
else
ASL_PATHSEP := :
MKDIR_P := mkdir -p "$(OUTDIR)"
RM_RF := rm -rf "$(OUTDIR)"
endif

ASL_INCLUDE := $(CURDIR)/include$(ASL_PATHSEP)$(CURDIR)/src

.PHONY: all clean bin srec ihex

all: srec ihex

$(OUTDIR):
	$(MKDIR_P)

$(OBJ): $(TOPSRC) include/hardware.inc include/mikbug.inc src/acia6850.asm | $(OUTDIR)
	$(ASL) -q -L -olist $(LST) -o $(OBJ) -i '$(ASL_INCLUDE)' $(TOPSRC)

bin: $(BIN)

$(BIN): $(OBJ)
	$(P2BIN) $(OBJ) $(BIN) -q

srec: $(SREC)

$(SREC): $(OBJ)
	$(P2HEX) -q -F Moto -M 2 -o $(SREC) $(OBJ)

ihex: $(IHEX)

$(IHEX): $(OBJ)
	$(P2HEX) -q -F Intel -i 1 -o $(IHEX) $(OBJ)

clean:
	$(RM_RF)
