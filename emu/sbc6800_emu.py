#!/usr/bin/env python3
"""SBC6800 向け最小 MC6800 エミュレータ

このプロジェクト専用の最小エミュレータです。
MC6800 の全命令ではなく、ROM モニタが使用する命令のみ実装しています。
"""

import sys
import os

# プラットフォーム判定
_IS_WINDOWS = (os.name == 'nt')

if _IS_WINDOWS:
    import msvcrt
else:
    import select
    import tty
    import termios

# ---------------------------------------------------------------------------
# メモリマップ定数（hardware.inc と一致させる）
# ---------------------------------------------------------------------------
ROM_BASE = 0xE000
ROM_END = 0xFFFF
RAM_START = 0x0000
RAM_END = 0x1FFF
ACIA_CTRL = 0x8018
ACIA_DATA = 0x8019

# PIA (MC6821) レジスタ
PIA_PRA = 0x8050
PIA_CRA = 0x8051
PIA_PRB = 0x8052
PIA_CRB = 0x8053

# SPI 信号 (PIA Port B)
SPI_SCLK = 0x01
SPI_MOSI = 0x02
SPI_MISO = 0x04
SPI_CS   = 0x08

# ACIA ステータスビット
ACIA_STAT_RDRF = 0x01  # 受信データレディ
ACIA_STAT_TDRE = 0x02  # 送信データレジスタ空

# 割り込みベクタ
VEC_IRQ = 0xFFF8
VEC_SWI = 0xFFFA
VEC_NMI = 0xFFFC
VEC_RESET = 0xFFFE


class ACIA:
    """MC6850 ACIA の擬似実装（標準入出力をシリアル端末として扱う）"""

    def __init__(self, input_data=None):
        self._input_buf = []
        self._input_data = input_data  # スクリプト入力用
        self._input_pos = 0
        self._interactive = input_data is None
        self._exit_on_eof = input_data is not None
        self._old_termios = None
        if self._interactive and sys.stdin.isatty() and not _IS_WINDOWS:
            self._old_termios = termios.tcgetattr(sys.stdin)
            tty.setcbreak(sys.stdin.fileno())

    def cleanup(self):
        """ターミナル設定を復元する"""
        if self._old_termios is not None:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self._old_termios)

    def read_status(self):
        """ACIA ステータスレジスタを読む"""
        if self._exit_on_eof and self._input_data is not None and self._input_pos >= len(self._input_data):
            raise SystemExit(0)
        status = ACIA_STAT_TDRE  # 送信は常にレディ
        if self._has_input():
            status |= ACIA_STAT_RDRF
        return status

    def read_data(self):
        """ACIA データレジスタを読む（1文字受信）"""
        if self._input_data is not None:
            # スクリプト入力モード
            if self._input_pos < len(self._input_data):
                ch = self._input_data[self._input_pos]
                self._input_pos += 1
                return ch
            else:
                # 入力が尽きたら終了
                raise SystemExit(0)
        else:
            # 対話モード
            if _IS_WINDOWS:
                # Windows: msvcrt で1文字取得
                ch = msvcrt.getch()
                val = ch[0] if isinstance(ch, bytes) else ord(ch)
            else:
                # Unix: stdin から1文字取得
                ch = sys.stdin.read(1)
                if ch == '':
                    raise SystemExit(0)
                val = ord(ch)
            # Enter キー (LF or CR) をモニタが期待する CR に変換
            if val == 0x0A:
                val = 0x0D
            return val

    def write_data(self, value):
        """ACIA データレジスタへ書く（1文字送信）"""
        ch = chr(value & 0x7F)
        sys.stdout.write(ch)
        sys.stdout.flush()

    def write_ctrl(self, value):
        """ACIA 制御レジスタへ書く（リセット等）"""
        pass  # 擬似実装では何もしない

    def _has_input(self):
        """入力データが存在するか"""
        if self._input_data is not None:
            return self._input_pos < len(self._input_data)
        if _IS_WINDOWS:
            return msvcrt.kbhit()
        if sys.stdin.isatty():
            dr, _, _ = select.select([sys.stdin], [], [], 0)
            return len(dr) > 0
        return True


class SDCard:
    """SPI モードの擬似 SD カード (CMD0 に 0x01 を返すだけの最小実装)"""
    def __init__(self, image_path=None):
        self.selected = False
        self.bit_count = 0
        self.shift_in = 0
        self.shift_out = 0xFF
        self.miso = 1
        self.command = []
        self.response = []
        self.app_cmd = False # CMD55 flag
        self.image = None
        if image_path:
            try:
                with open(image_path, "rb") as f:
                    self.image = f.read()
                # print(f"[SD] Loaded disk image: {image_path} ({len(self.image)} bytes)")
            except Exception as e:
                print(f"[SD] Error loading image: {e}")

    def handle_bit(self, sclk, mosi, cs):
        """SPI ビット処理 (Mode 0: Rising edge sample, Falling edge shift)"""
        self.selected = (cs == 0)

        if not self.selected:
            self.bit_count = 0
            self.miso = 1
            return 1

        if sclk == 1: # Rising Edge (Sample)
            if self.bit_count == 0:
                if self.response:
                    self.shift_out = self.response.pop(0)
                    # print(f"[SD] Sending response byte: ${self.shift_out:02X}")
                else:
                    self.shift_out = 0xFF

            self.shift_in = ((self.shift_in << 1) | (mosi & 1)) & 0xFF
            self.miso = (self.shift_out >> 7) & 1
            self.bit_count += 1
            if self.bit_count >= 8:
                self.bit_count = 0
                self._process_byte(self.shift_in)
        
        return self.miso

    def shift_next(self):
        """Falling Edge 相当の処理 (次のビットへ)"""
        if self.selected:
            self.shift_out = ((self.shift_out << 1) | 1) & 0xFF

    def _process_byte(self, byte):
        if not self.response:
            if self.command:
                self.command.append(byte)
                if len(self.command) >= 6:
                    cmd = self.command[0] & 0x3F
                    
                    if self.app_cmd:
                        self.app_cmd = False
                        if cmd == 41: # ACMD41
                            self.response = [0x00] # Ready
                        else:
                            self.response = [0x04] # Illegal Command
                    else:
                        if cmd == 0: # CMD0
                            self.response = [0x01]
                        elif cmd == 8: # CMD8
                            # R7 response: R1 + 4 bytes
                            self.response = [0x01, 0x00, 0x00, 0x01, 0xAA]
                        elif cmd == 17: # CMD17: READ_SINGLE_BLOCK
                            lba = (self.command[1] << 24) | (self.command[2] << 16) | \
                                  (self.command[3] << 8) | self.command[4]
                            self.response = [0x00] # R1: Success
                            # Data token ($FE) + 512 bytes + 2 bytes CRC
                            data_block = [0xFE]
                            if self.image and (lba * 512 < len(self.image)):
                                offset = lba * 512
                                data_block.extend(self.image[offset:offset+512])
                            else:
                                data_block.extend([0] * 512)
                            data_block.extend([0xFF, 0xFF]) # Dummy CRC
                            self.response.extend(data_block)
                        elif cmd == 55: # CMD55
                            self.app_cmd = True
                            self.response = [0x01]
                        else:
                            self.response = [0x00]
                    self.command = []
            elif (byte & 0xC0) == 0x40: # Command Start
                self.command = [byte]
            elif byte == 0xFF: # Idle
                pass

class PIA:
    """MC6821 PIA の擬似実装"""
    def __init__(self, sdcard):
        self.pra = 0x00
        self.ddra = 0x00
        self.cra = 0x00
        self.prb = 0x00
        self.ddrb = 0x00
        self.crb = 0x00
        self.sdcard = sdcard
        self._last_sclk = 0

    def read(self, addr, pc=0):
        val = 0
        if addr == PIA_PRA:
            val = self.pra if (self.cra & 0x04) else self.ddra
        elif addr == PIA_CRA:
            val = self.cra
        elif addr == PIA_PRB:
            # Port B 読み込み時、MISO ビットを SD カードから取得
            val = self.prb & ~SPI_MISO
            if self.sdcard.miso:
                val |= SPI_MISO
            val = val if (self.crb & 0x04) else self.ddrb
        elif addr == PIA_CRB:
            val = self.crb
        return val

    def write(self, addr, val, pc=0):
        if addr == 0x00A0:
            print(f"[TRACE] Write to SD_LOAD_ACTIVE ($00A0) at PC=${pc:04X}: val=${val:02X}")
        if addr == PIA_PRA:
            if self.cra & 0x04: self.pra = val
            else: self.ddra = val
        elif addr == PIA_CRA:
            self.cra = val
        elif addr == PIA_PRB:
            if self.crb & 0x04:
                # SPI 信号の変化を SD カードに伝える
                sclk = (val & SPI_SCLK)
                mosi = (val & SPI_MOSI) >> 1
                cs = (val & SPI_CS) >> 3
                
                if sclk == 1 and self._last_sclk == 0:
                    self.sdcard.handle_bit(1, mosi, cs)
                elif sclk == 0 and self._last_sclk == 1:
                    self.sdcard.shift_next()
                self._last_sclk = sclk
                self.prb = val
            else:
                self.ddrb = val
        elif addr == PIA_CRB:
            self.crb = val


class MC6800:
    """MC6800 CPU エミュレータコア"""

    def __init__(self, acia, pia=None):
        # レジスタ
        self.a = 0x00       # アキュムレータ A
        self.b = 0x00       # アキュムレータ B
        self.x = 0x0000     # インデックスレジスタ
        self.sp = 0x00FF    # スタックポインタ
        self.pc = 0x0000    # プログラムカウンタ
        # コンディションコード: H I N Z V C
        self.cc_h = False
        self.cc_i = False
        self.cc_n = False
        self.cc_z = False
        self.cc_v = False
        self.cc_c = False

        # メモリ（64KB）
        self.mem = bytearray(0x10000)

        # ACIA / PIA
        self.acia = acia
        self.pia = pia

        # 実行カウンタ（暴走検知用）
        self.cycles = 0
        self.max_cycles = 100_000_000  # 安全弁
        self.pc_trace = []

    # ----- メモリアクセス -----
    def read(self, addr):
        """1バイト読み出し"""
        addr &= 0xFFFF
        if addr == ACIA_CTRL:
            return self.acia.read_status()
        elif addr == ACIA_DATA:
            return self.acia.read_data()
        elif self.pia and PIA_PRA <= addr <= PIA_CRB:
            return self.pia.read(addr, pc=self.pc)
        return self.mem[addr]

    def write(self, addr, val):
        """1バイト書き込み"""
        addr &= 0xFFFF
        val &= 0xFF
        if addr == ACIA_CTRL:
            self.acia.write_ctrl(val)
            return
        elif addr == ACIA_DATA:
            self.acia.write_data(val)
            return
        elif self.pia and PIA_PRA <= addr <= PIA_CRB:
            self.pia.write(addr, val, pc=self.pc)
            return
        # ROM 領域への書き込みは無視
        if ROM_BASE <= addr <= ROM_END:
            return
        self.mem[addr] = val

    def read16(self, addr):
        """2バイト（ビッグエンディアン）読み出し"""
        return (self.read(addr) << 8) | self.read(addr + 1)

    def write16(self, addr, val):
        """2バイト（ビッグエンディアン）書き込み"""
        self.write(addr, (val >> 8) & 0xFF)
        self.write(addr + 1, val & 0xFF)

    # ----- フェッチ -----
    def fetch(self):
        """PC から1バイトフェッチして PC をインクリメント"""
        val = self.read(self.pc)
        self.pc = (self.pc + 1) & 0xFFFF
        return val

    def fetch16(self):
        """PC から2バイトフェッチ"""
        hi = self.fetch()
        lo = self.fetch()
        return (hi << 8) | lo

    # ----- アドレッシングモード -----
    def addr_imm8(self):
        """即値8ビット: 値を返す"""
        return self.fetch()

    def addr_imm16(self):
        """即値16ビット: 値を返す"""
        return self.fetch16()

    def addr_direct(self):
        """ダイレクト: アドレスを返す"""
        return self.fetch()

    def addr_extended(self):
        """拡張: アドレスを返す"""
        return self.fetch16()

    def addr_indexed(self):
        """インデックス: アドレスを返す"""
        offset = self.fetch()
        return (self.x + offset) & 0xFFFF

    def addr_relative(self):
        """相対: 分岐先アドレスを返す"""
        offset = self.fetch()
        if offset >= 0x80:
            offset -= 0x100
        return (self.pc + offset) & 0xFFFF

    # ----- コンディションコード操作 -----
    def get_cc(self):
        """コンディションコードレジスタの値を取得"""
        cc = 0xC0  # 上位2ビットは常に1
        if self.cc_h:
            cc |= 0x20
        if self.cc_i:
            cc |= 0x10
        if self.cc_n:
            cc |= 0x08
        if self.cc_z:
            cc |= 0x04
        if self.cc_v:
            cc |= 0x02
        if self.cc_c:
            cc |= 0x01
        return cc

    def set_cc(self, val):
        """コンディションコードレジスタの値を設定"""
        self.cc_h = bool(val & 0x20)
        self.cc_i = bool(val & 0x10)
        self.cc_n = bool(val & 0x08)
        self.cc_z = bool(val & 0x04)
        self.cc_v = bool(val & 0x02)
        self.cc_c = bool(val & 0x01)

    def update_nz(self, val):
        """N, Z フラグを8ビット値で更新"""
        val &= 0xFF
        self.cc_n = bool(val & 0x80)
        self.cc_z = (val == 0)

    def update_nz16(self, val):
        """N, Z フラグを16ビット値で更新"""
        val &= 0xFFFF
        self.cc_n = bool(val & 0x8000)
        self.cc_z = (val == 0)

    # ----- スタック操作 -----
    def push8(self, val):
        """スタックに1バイトプッシュ"""
        self.write(self.sp, val & 0xFF)
        self.sp = (self.sp - 1) & 0xFFFF

    def pull8(self):
        """スタックから1バイトプル"""
        self.sp = (self.sp + 1) & 0xFFFF
        return self.read(self.sp)

    def push16(self, val):
        """スタックに2バイトプッシュ"""
        self.push8(val & 0xFF)
        self.push8((val >> 8) & 0xFF)

    def pull16(self):
        """スタックから2バイトプル"""
        hi = self.pull8()
        lo = self.pull8()
        return (hi << 8) | lo

    # ----- ROM ロードとリセット -----
    def load_rom(self, data, base=ROM_BASE):
        """ROM データをメモリにロード"""
        for i, b in enumerate(data):
            addr = base + i
            if addr <= 0xFFFF:
                self.mem[addr] = b

    def reset(self):
        """CPU リセット"""
        self.pc = self.read16(VEC_RESET)
        self.cc_i = True

    # ----- 命令実行 -----
    def step(self):
        """1命令実行"""
        self.pc_trace.append(self.pc)
        if len(self.pc_trace) > 20:
            self.pc_trace.pop(0)

        opcode = self.fetch()
        self.cycles += 1

        # --- NOP ---
        if opcode == 0x01:
            pass

        # --- TAP (A -> CC) ---
        elif opcode == 0x06:
            self.set_cc(self.a)

        # --- TPA (CC -> A) ---
        elif opcode == 0x07:
            self.a = self.get_cc()

        # --- INX ---
        elif opcode == 0x08:
            self.x = (self.x + 1) & 0xFFFF
            self.cc_z = (self.x == 0)

        # --- DEX ---
        elif opcode == 0x09:
            self.x = (self.x - 1) & 0xFFFF
            self.cc_z = (self.x == 0)

        # --- CLC ---
        elif opcode == 0x0C:
            self.cc_c = False

        # --- SEC ---
        elif opcode == 0x0D:
            self.cc_c = True

        # --- CLI ---
        elif opcode == 0x0E:
            self.cc_i = False

        # --- SEI ---
        elif opcode == 0x0F:
            self.cc_i = True

        # --- TAB (A -> B) ---
        elif opcode == 0x16:
            self.b = self.a
            self.update_nz(self.b)
            self.cc_v = False

        # --- TBA (B -> A) ---
        elif opcode == 0x17:
            self.a = self.b
            self.update_nz(self.a)
            self.cc_v = False

        # --- INS ---
        elif opcode == 0x31:
            self.sp = (self.sp + 1) & 0xFFFF

        # --- DES ---
        elif opcode == 0x34:
            self.sp = (self.sp - 1) & 0xFFFF

        # --- RTS ---
        elif opcode == 0x39:
            self.pc = self.pull16()

        # --- RTI ---
        elif opcode == 0x3B:
            self.set_cc(self.pull8())
            self.b = self.pull8()
            self.a = self.pull8()
            self.x = self.pull16()
            self.pc = self.pull16()

        # --- WAI ---
        elif opcode == 0x3E:
            # 簡易実装: 割り込み待ち → 今回は終了扱い
            raise SystemExit(0)

        # --- SWI ---
        elif opcode == 0x3F:
            self.push16(self.pc)
            self.push16(self.x)
            self.push8(self.a)
            self.push8(self.b)
            self.push8(self.get_cc())
            self.cc_i = True
            self.pc = self.read16(VEC_SWI)

        # --- ABA (A = A + B) ---
        elif opcode == 0x1B:
            result = self.a + self.b
            self.cc_c = result > 0xFF
            self.cc_v = bool((~(self.a ^ self.b) & (self.a ^ result)) & 0x80)
            self.a = result & 0xFF
            self.update_nz(self.a)

        # --- NEGA ---
        elif opcode == 0x40:
            result = (0 - self.a) & 0xFF
            self.cc_c = (self.a != 0)
            self.cc_v = (self.a == 0x80)
            self.a = result
            self.update_nz(self.a)

        # --- COMA ---
        elif opcode == 0x43:
            self.a = (~self.a) & 0xFF
            self.update_nz(self.a)
            self.cc_v = False
            self.cc_c = True

        # --- LSRA ---
        elif opcode == 0x44:
            self.cc_c = bool(self.a & 0x01)
            self.a = (self.a >> 1) & 0xFF
            self.update_nz(self.a)
            self.cc_v = self.cc_n ^ self.cc_c

        # --- RORA ---
        elif opcode == 0x46:
            old_c = self.cc_c
            self.cc_c = bool(self.a & 0x01)
            self.a = ((self.a >> 1) | (0x80 if old_c else 0)) & 0xFF
            self.update_nz(self.a)
            self.cc_v = self.cc_n ^ self.cc_c

        # --- ASRA ---
        elif opcode == 0x47:
            self.cc_c = bool(self.a & 0x01)
            self.a = ((self.a >> 1) | (self.a & 0x80)) & 0xFF
            self.update_nz(self.a)
            self.cc_v = self.cc_n ^ self.cc_c

        # --- ASLA / LSLA ---
        elif opcode == 0x48:
            self.cc_c = bool(self.a & 0x80)
            self.a = (self.a << 1) & 0xFF
            self.update_nz(self.a)
            self.cc_v = self.cc_n ^ self.cc_c

        # --- ROLA ---
        elif opcode == 0x49:
            old_c = self.cc_c
            self.cc_c = bool(self.a & 0x80)
            self.a = ((self.a << 1) | (1 if old_c else 0)) & 0xFF
            self.update_nz(self.a)
            self.cc_v = self.cc_n ^ self.cc_c

        # --- DECA ---
        elif opcode == 0x4A:
            self.cc_v = (self.a == 0x80)
            self.a = (self.a - 1) & 0xFF
            self.update_nz(self.a)

        # --- INCA ---
        elif opcode == 0x4C:
            self.cc_v = (self.a == 0x7F)
            self.a = (self.a + 1) & 0xFF
            self.update_nz(self.a)

        # --- TSTA ---
        elif opcode == 0x4D:
            self.update_nz(self.a)
            self.cc_v = False
            self.cc_c = False

        # --- CLRA ---
        elif opcode == 0x4F:
            self.a = 0
            self.cc_n = False
            self.cc_z = True
            self.cc_v = False
            self.cc_c = False

        # --- NEGB ---
        elif opcode == 0x50:
            result = (0 - self.b) & 0xFF
            self.cc_c = (self.b != 0)
            self.cc_v = (self.b == 0x80)
            self.b = result
            self.update_nz(self.b)

        # --- COMB ---
        elif opcode == 0x53:
            self.b = (~self.b) & 0xFF
            self.update_nz(self.b)
            self.cc_v = False
            self.cc_c = True

        # --- LSRB ---
        elif opcode == 0x54:
            self.cc_c = bool(self.b & 0x01)
            self.b = (self.b >> 1) & 0xFF
            self.update_nz(self.b)
            self.cc_v = self.cc_n ^ self.cc_c

        # --- ASLB / LSLB ---
        elif opcode == 0x58:
            self.cc_c = bool(self.b & 0x80)
            self.b = (self.b << 1) & 0xFF
            self.update_nz(self.b)
            self.cc_v = self.cc_n ^ self.cc_c

        # --- DECB ---
        elif opcode == 0x5A:
            self.cc_v = (self.b == 0x80)
            self.b = (self.b - 1) & 0xFF
            self.update_nz(self.b)

        # --- INCB ---
        elif opcode == 0x5C:
            self.cc_v = (self.b == 0x7F)
            self.b = (self.b + 1) & 0xFF
            self.update_nz(self.b)

        # --- TSTB ---
        elif opcode == 0x5D:
            self.update_nz(self.b)
            self.cc_v = False
            self.cc_c = False

        # --- CLRB ---
        elif opcode == 0x5F:
            self.b = 0
            self.cc_n = False
            self.cc_z = True
            self.cc_v = False
            self.cc_c = False

        # --- NEG indexed ---
        elif opcode == 0x60:
            addr = self.addr_indexed()
            val = self.read(addr)
            result = (0 - val) & 0xFF
            self.cc_c = (val != 0)
            self.cc_v = (val == 0x80)
            self.write(addr, result)
            self.update_nz(result)

        # --- COM indexed ---
        elif opcode == 0x63:
            addr = self.addr_indexed()
            val = (~self.read(addr)) & 0xFF
            self.write(addr, val)
            self.update_nz(val)
            self.cc_v = False
            self.cc_c = True

        # --- LSR indexed ---
        elif opcode == 0x64:
            addr = self.addr_indexed()
            val = self.read(addr)
            self.cc_c = bool(val & 0x01)
            result = (val >> 1) & 0xFF
            self.write(addr, result)
            self.update_nz(result)
            self.cc_v = self.cc_n ^ self.cc_c

        # --- ROR indexed ---
        elif opcode == 0x66:
            addr = self.addr_indexed()
            val = self.read(addr)
            old_c = self.cc_c
            self.cc_c = bool(val & 0x01)
            result = ((val >> 1) | (0x80 if old_c else 0)) & 0xFF
            self.write(addr, result)
            self.update_nz(result)
            self.cc_v = self.cc_n ^ self.cc_c

        # --- ASR indexed ---
        elif opcode == 0x67:
            addr = self.addr_indexed()
            val = self.read(addr)
            self.cc_c = bool(val & 0x01)
            result = ((val >> 1) | (val & 0x80)) & 0xFF
            self.write(addr, result)
            self.update_nz(result)
            self.cc_v = self.cc_n ^ self.cc_c

        # --- ASL indexed ---
        elif opcode == 0x68:
            addr = self.addr_indexed()
            val = self.read(addr)
            self.cc_c = bool(val & 0x80)
            result = (val << 1) & 0xFF
            self.write(addr, result)
            self.update_nz(result)
            self.cc_v = self.cc_n ^ self.cc_c

        # --- ROL indexed ---
        elif opcode == 0x69:
            addr = self.addr_indexed()
            val = self.read(addr)
            old_c = self.cc_c
            self.cc_c = bool(val & 0x80)
            result = ((val << 1) | (1 if old_c else 0)) & 0xFF
            self.write(addr, result)
            self.update_nz(result)
            self.cc_v = self.cc_n ^ self.cc_c

        # --- DEC indexed ---
        elif opcode == 0x6A:
            addr = self.addr_indexed()
            val = self.read(addr)
            self.cc_v = (val == 0x80)
            result = (val - 1) & 0xFF
            self.write(addr, result)
            self.update_nz(result)

        # --- INC indexed ---
        elif opcode == 0x6C:
            addr = self.addr_indexed()
            val = self.read(addr)
            self.cc_v = (val == 0x7F)
            result = (val + 1) & 0xFF
            self.write(addr, result)
            self.update_nz(result)

        # --- TST indexed ---
        elif opcode == 0x6D:
            addr = self.addr_indexed()
            val = self.read(addr)
            self.update_nz(val)
            self.cc_v = False
            self.cc_c = False

        # --- JMP indexed ---
        elif opcode == 0x6E:
            self.pc = self.addr_indexed()

        # --- CLR indexed ---
        elif opcode == 0x6F:
            addr = self.addr_indexed()
            self.write(addr, 0)
            self.cc_n = False
            self.cc_z = True
            self.cc_v = False
            self.cc_c = False

        # --- NEG extended ---
        elif opcode == 0x70:
            addr = self.addr_extended()
            val = self.read(addr)
            result = (0 - val) & 0xFF
            self.cc_c = (val != 0)
            self.cc_v = (val == 0x80)
            self.write(addr, result)
            self.update_nz(result)

        # --- COM extended ---
        elif opcode == 0x73:
            addr = self.addr_extended()
            val = (~self.read(addr)) & 0xFF
            self.write(addr, val)
            self.update_nz(val)
            self.cc_v = False
            self.cc_c = True

        # --- LSR extended ---
        elif opcode == 0x74:
            addr = self.addr_extended()
            val = self.read(addr)
            self.cc_c = bool(val & 0x01)
            result = (val >> 1) & 0xFF
            self.write(addr, result)
            self.update_nz(result)
            self.cc_v = self.cc_n ^ self.cc_c

        # --- ROR extended ---
        elif opcode == 0x76:
            addr = self.addr_extended()
            val = self.read(addr)
            old_c = self.cc_c
            self.cc_c = bool(val & 0x01)
            result = ((val >> 1) | (0x80 if old_c else 0)) & 0xFF
            self.write(addr, result)
            self.update_nz(result)
            self.cc_v = self.cc_n ^ self.cc_c

        # --- ASR extended ---
        elif opcode == 0x77:
            addr = self.addr_extended()
            val = self.read(addr)
            self.cc_c = bool(val & 0x01)
            result = ((val >> 1) | (val & 0x80)) & 0xFF
            self.write(addr, result)
            self.update_nz(result)
            self.cc_v = self.cc_n ^ self.cc_c

        # --- ASL extended ---
        elif opcode == 0x78:
            addr = self.addr_extended()
            val = self.read(addr)
            self.cc_c = bool(val & 0x80)
            result = (val << 1) & 0xFF
            self.write(addr, result)
            self.update_nz(result)
            self.cc_v = self.cc_n ^ self.cc_c

        # --- ROL extended ---
        elif opcode == 0x79:
            addr = self.addr_extended()
            val = self.read(addr)
            old_c = self.cc_c
            self.cc_c = bool(val & 0x80)
            result = ((val << 1) | (1 if old_c else 0)) & 0xFF
            self.write(addr, result)
            self.update_nz(result)
            self.cc_v = self.cc_n ^ self.cc_c

        # --- DEC extended ---
        elif opcode == 0x7A:
            addr = self.addr_extended()
            val = self.read(addr)
            self.cc_v = (val == 0x80)
            result = (val - 1) & 0xFF
            self.write(addr, result)
            self.update_nz(result)

        # --- INC extended ---
        elif opcode == 0x7C:
            addr = self.addr_extended()
            val = self.read(addr)
            self.cc_v = (val == 0x7F)
            result = (val + 1) & 0xFF
            self.write(addr, result)
            self.update_nz(result)

        # --- TST extended ---
        elif opcode == 0x7D:
            addr = self.addr_extended()
            val = self.read(addr)
            self.update_nz(val)
            self.cc_v = False
            self.cc_c = False

        # --- JMP extended ---
        elif opcode == 0x7E:
            self.pc = self.addr_extended()

        # --- CLR extended ---
        elif opcode == 0x7F:
            addr = self.addr_extended()
            self.write(addr, 0)
            self.cc_n = False
            self.cc_z = True
            self.cc_v = False
            self.cc_c = False

        # --- BSR ---
        elif opcode == 0x8D:
            target = self.addr_relative()
            self.push16(self.pc)
            self.pc = target

        # --- BRA ---
        elif opcode == 0x20:
            self.pc = self.addr_relative()

        # --- BHI ---
        elif opcode == 0x22:
            target = self.addr_relative()
            if not self.cc_c and not self.cc_z:
                self.pc = target

        # --- BLS ---
        elif opcode == 0x23:
            target = self.addr_relative()
            if self.cc_c or self.cc_z:
                self.pc = target

        # --- BCC / BHS ---
        elif opcode == 0x24:
            target = self.addr_relative()
            if not self.cc_c:
                self.pc = target

        # --- BCS / BLO ---
        elif opcode == 0x25:
            target = self.addr_relative()
            if self.cc_c:
                self.pc = target

        # --- BNE ---
        elif opcode == 0x26:
            target = self.addr_relative()
            if not self.cc_z:
                self.pc = target

        # --- BEQ ---
        elif opcode == 0x27:
            target = self.addr_relative()
            if self.cc_z:
                self.pc = target

        # --- BVC ---
        elif opcode == 0x28:
            target = self.addr_relative()
            if not self.cc_v:
                self.pc = target

        # --- BVS ---
        elif opcode == 0x29:
            target = self.addr_relative()
            if self.cc_v:
                self.pc = target

        # --- BPL ---
        elif opcode == 0x2A:
            target = self.addr_relative()
            if not self.cc_n:
                self.pc = target

        # --- BMI ---
        elif opcode == 0x2B:
            target = self.addr_relative()
            if self.cc_n:
                self.pc = target

        # --- BGE ---
        elif opcode == 0x2C:
            target = self.addr_relative()
            if self.cc_n == self.cc_v:
                self.pc = target

        # --- BLT ---
        elif opcode == 0x2D:
            target = self.addr_relative()
            if self.cc_n != self.cc_v:
                self.pc = target

        # --- BGT ---
        elif opcode == 0x2E:
            target = self.addr_relative()
            if not self.cc_z and (self.cc_n == self.cc_v):
                self.pc = target

        # --- BLE ---
        elif opcode == 0x2F:
            target = self.addr_relative()
            if self.cc_z or (self.cc_n != self.cc_v):
                self.pc = target

        # --- TSX ---
        elif opcode == 0x30:
            self.x = (self.sp + 1) & 0xFFFF

        # --- TXS ---
        elif opcode == 0x35:
            self.sp = (self.x - 1) & 0xFFFF

        # --- PSHA ---
        elif opcode == 0x36:
            self.push8(self.a)

        # --- PULA ---
        elif opcode == 0x32:
            self.a = self.pull8()
            self.update_nz(self.a)

        # --- TST ext ---
        elif opcode == 0x7D:
            addr = self.addr_extended()
            val = self.read(addr)
            self.update_nz(val)
            self.cc_v = False
            self.cc_c = False

        # --- CLR ext ---
        elif opcode == 0x7F:
            addr = self.addr_extended()
            self.write(addr, 0)
            self.update_nz(0)
            self.cc_v = False
            self.cc_c = False
            if (self.pc - 3) == 0xF0B8:
                print("[SD] SD_GETC EOF reached!")

        # --- PSHB ---
        elif opcode == 0x37:
            self.push8(self.b)

        # --- PULB ---
        elif opcode == 0x33:
            self.b = self.pull8()

        # ===== LDAA / CMPA / ADDA / SUBA / ANDA / ORAA / EORA / BITA / STAA =====
        # -- immediate --
        elif opcode == 0x86:  # LDAA #imm
            self.a = self.addr_imm8()
            self.update_nz(self.a)
            self.cc_v = False

        elif opcode == 0x82:  # SBCA #imm
            val = self.addr_imm8()
            c = 1 if self.cc_c else 0
            result = self.a - val - c
            self.cc_c = result < 0
            self.cc_v = bool(((self.a ^ val) & (self.a ^ result)) & 0x80)
            self.a = result & 0xFF
            self.update_nz(self.a)

        elif opcode == 0x81:  # CMPA imm
            val = self.addr_imm8()
            result = self.a - val
            self.cc_c = result < 0
            result &= 0xFF
            self.update_nz(result)
            self.cc_v = bool(((self.a ^ val) & (self.a ^ result)) & 0x80)

        elif opcode == 0x8B:  # ADDA #imm
            val = self.addr_imm8()
            result = self.a + val
            self.cc_c = result > 0xFF
            self.cc_v = bool((~(self.a ^ val) & (self.a ^ result)) & 0x80)
            self.a = result & 0xFF
            self.update_nz(self.a)

        elif opcode == 0x89:  # ADCA #imm
            val = self.addr_imm8()
            c = 1 if self.cc_c else 0
            result = self.a + val + c
            self.cc_c = result > 0xFF
            self.cc_v = bool((~(self.a ^ val) & (self.a ^ result)) & 0x80)
            self.a = result & 0xFF
            self.update_nz(self.a)

        elif opcode == 0x99:  # ADCA direct
            addr = self.addr_direct()
            val = self.read(addr)
            c = 1 if self.cc_c else 0
            result = self.a + val + c
            self.cc_c = result > 0xFF
            self.cc_v = bool((~(self.a ^ val) & (self.a ^ result)) & 0x80)
            self.a = result & 0xFF
            self.update_nz(self.a)

        elif opcode == 0xB9:  # ADCA extended
            addr = self.addr_extended()
            val = self.read(addr)
            c = 1 if self.cc_c else 0
            result = self.a + val + c
            self.cc_c = result > 0xFF
            self.cc_v = bool((~(self.a ^ val) & (self.a ^ result)) & 0x80)
            self.a = result & 0xFF
            self.update_nz(self.a)

        elif opcode == 0x80:  # SUBA #imm
            val = self.addr_imm8()
            result = self.a - val
            self.cc_c = result < 0
            self.cc_v = bool(((self.a ^ val) & (self.a ^ result)) & 0x80)
            self.a = result & 0xFF
            self.update_nz(self.a)

        elif opcode == 0x84:  # ANDA #imm
            self.a &= self.addr_imm8()
            self.update_nz(self.a)
            self.cc_v = False

        elif opcode == 0x8A:  # ORAA #imm
            self.a |= self.addr_imm8()
            self.update_nz(self.a)
            self.cc_v = False

        elif opcode == 0x88:  # EORA #imm
            self.a ^= self.addr_imm8()
            self.update_nz(self.a)
            self.cc_v = False

        elif opcode == 0x85:  # BITA #imm
            val = self.a & self.addr_imm8()
            self.update_nz(val)
            self.cc_v = False

        # -- direct --
        elif opcode == 0x96:  # LDAA direct
            addr = self.addr_direct()
            self.a = self.read(addr)
            self.update_nz(self.a)
            self.cc_v = False

        elif opcode == 0x91:  # CMPA direct
            addr = self.addr_direct()
            val = self.read(addr)
            result = self.a - val
            self.cc_c = result < 0
            result &= 0xFF
            self.update_nz(result)
            self.cc_v = bool(((self.a ^ val) & (self.a ^ result)) & 0x80)

        elif opcode == 0x9B:  # ADDA direct
            addr = self.addr_direct()
            val = self.read(addr)
            result = self.a + val
            self.cc_c = result > 0xFF
            self.cc_v = bool((~(self.a ^ val) & (self.a ^ result)) & 0x80)
            self.a = result & 0xFF
            self.update_nz(self.a)

        elif opcode == 0x90:  # SUBA direct
            addr = self.addr_direct()
            val = self.read(addr)
            result = self.a - val
            self.cc_c = result < 0
            self.cc_v = bool(((self.a ^ val) & (self.a ^ result)) & 0x80)
            self.a = result & 0xFF
            self.update_nz(self.a)

        elif opcode == 0x97:  # STAA direct
            addr = self.addr_direct()
            self.write(addr, self.a)
            self.update_nz(self.a)
            self.cc_v = False

        elif opcode == 0x94:  # ANDA direct
            addr = self.addr_direct()
            self.a &= self.read(addr)
            self.update_nz(self.a)
            self.cc_v = False

        elif opcode == 0x9A:  # ORAA direct
            addr = self.addr_direct()
            self.a |= self.read(addr)
            self.update_nz(self.a)
            self.cc_v = False

        elif opcode == 0x95:  # BITA direct
            addr = self.addr_direct()
            val = self.a & self.read(addr)
            self.update_nz(val)
            self.cc_v = False

        # -- indexed --
        elif opcode == 0xA6:  # LDAA indexed
            addr = self.addr_indexed()
            self.a = self.read(addr)
            self.update_nz(self.a)
            self.cc_v = False

        elif opcode == 0xA1:  # CMPA indexed
            addr = self.addr_indexed()
            val = self.read(addr)
            result = self.a - val
            self.cc_c = result < 0
            result &= 0xFF
            self.update_nz(result)
            self.cc_v = bool(((self.a ^ val) & (self.a ^ result)) & 0x80)

        elif opcode == 0xAB:  # ADDA indexed
            addr = self.addr_indexed()
            val = self.read(addr)
            result = self.a + val
            self.cc_c = result > 0xFF
            self.cc_v = bool((~(self.a ^ val) & (self.a ^ result)) & 0x80)
            self.a = result & 0xFF
            self.update_nz(self.a)

        elif opcode == 0xA0:  # SUBA indexed
            addr = self.addr_indexed()
            val = self.read(addr)
            result = self.a - val
            self.cc_c = result < 0
            self.cc_v = bool(((self.a ^ val) & (self.a ^ result)) & 0x80)
            self.a = result & 0xFF
            self.update_nz(self.a)

        elif opcode == 0xA7:  # STAA indexed
            addr = self.addr_indexed()
            self.write(addr, self.a)
            self.update_nz(self.a)
            self.cc_v = False

        elif opcode == 0xA4:  # ANDA indexed
            addr = self.addr_indexed()
            self.a &= self.read(addr)
            self.update_nz(self.a)
            self.cc_v = False

        elif opcode == 0xAA:  # ORAA indexed
            addr = self.addr_indexed()
            self.a |= self.read(addr)
            self.update_nz(self.a)
            self.cc_v = False

        elif opcode == 0xA5:  # BITA indexed
            addr = self.addr_indexed()
            val = self.a & self.read(addr)
            self.update_nz(val)
            self.cc_v = False

        # -- extended --
        elif opcode == 0xB6:  # LDAA extended
            addr = self.addr_extended()
            self.a = self.read(addr)
            self.update_nz(self.a)
            self.cc_v = False

        elif opcode == 0xB1:  # CMPA extended
            addr = self.addr_extended()
            val = self.read(addr)
            result = self.a - val
            self.cc_c = result < 0
            result &= 0xFF
            self.update_nz(result)
            self.cc_v = bool(((self.a ^ val) & (self.a ^ result)) & 0x80)

        elif opcode == 0xBB:  # ADDA extended
            addr = self.addr_extended()
            val = self.read(addr)
            result = self.a + val
            self.cc_c = result > 0xFF
            self.cc_v = bool((~(self.a ^ val) & (self.a ^ result)) & 0x80)
            self.a = result & 0xFF
            self.update_nz(self.a)

        elif opcode == 0xB0:  # SUBA extended
            addr = self.addr_extended()
            val = self.read(addr)
            result = self.a - val
            self.cc_c = result < 0
            self.cc_v = bool(((self.a ^ val) & (self.a ^ result)) & 0x80)
            self.a = result & 0xFF
            self.update_nz(self.a)

        elif opcode == 0xB7:  # STAA extended
            addr = self.addr_extended()
            self.write(addr, self.a)
            self.update_nz(self.a)
            self.cc_v = False

        elif opcode == 0xB4:  # ANDA extended
            addr = self.addr_extended()
            self.a &= self.read(addr)
            self.update_nz(self.a)
            self.cc_v = False

        elif opcode == 0xBA:  # ORAA extended
            addr = self.addr_extended()
            self.a |= self.read(addr)
            self.update_nz(self.a)
            self.cc_v = False

        elif opcode == 0xB5:  # BITA extended
            addr = self.addr_extended()
            val = self.a & self.read(addr)
            self.update_nz(val)
            self.cc_v = False

        # ===== LDAB / CMPB / ADDB / SUBB / STAB =====
        # -- immediate --
        elif opcode == 0xC6:  # LDAB #imm
            self.b = self.addr_imm8()
            self.update_nz(self.b)
            self.cc_v = False

        elif opcode == 0xC1:  # CMPB #imm
            val = self.addr_imm8()
            result = self.b - val
            self.cc_c = result < 0
            result &= 0xFF
            self.update_nz(result)
            self.cc_v = bool(((self.b ^ val) & (self.b ^ result)) & 0x80)

        elif opcode == 0xCB:  # ADDB #imm
            val = self.addr_imm8()
            result = self.b + val
            self.cc_c = result > 0xFF
            self.cc_v = bool((~(self.b ^ val) & (self.b ^ result)) & 0x80)
            self.b = result & 0xFF
            self.update_nz(self.b)

        elif opcode == 0xC0:  # SUBB #imm
            val = self.addr_imm8()
            result = self.b - val
            self.cc_c = result < 0
            self.cc_v = bool(((self.b ^ val) & (self.b ^ result)) & 0x80)
            self.b = result & 0xFF
            self.update_nz(self.b)

        elif opcode == 0xC4:  # ANDB #imm
            self.b &= self.addr_imm8()
            self.update_nz(self.b)
            self.cc_v = False

        elif opcode == 0xCA:  # ORAB #imm
            self.b |= self.addr_imm8()
            self.update_nz(self.b)
            self.cc_v = False

        elif opcode == 0xC8:  # EORB #imm
            self.b ^= self.addr_imm8()
            self.update_nz(self.b)
            self.cc_v = False

        elif opcode == 0xC5:  # BITB #imm
            val = self.b & self.addr_imm8()
            self.update_nz(val)
            self.cc_v = False

        # -- direct --
        elif opcode == 0xD6:  # LDAB direct
            addr = self.addr_direct()
            self.b = self.read(addr)
            self.update_nz(self.b)
            self.cc_v = False

        elif opcode == 0xD1:  # CMPB direct
            addr = self.addr_direct()
            val = self.read(addr)
            result = self.b - val
            self.cc_c = result < 0
            result &= 0xFF
            self.update_nz(result)
            self.cc_v = bool(((self.b ^ val) & (self.b ^ result)) & 0x80)

        elif opcode == 0xD7:  # STAB direct
            addr = self.addr_direct()
            self.write(addr, self.b)
            self.update_nz(self.b)
            self.cc_v = False

        # -- indexed --
        elif opcode == 0xE6:  # LDAB indexed
            addr = self.addr_indexed()
            self.b = self.read(addr)
            self.update_nz(self.b)
            self.cc_v = False

        elif opcode == 0xE1:  # CMPB indexed
            addr = self.addr_indexed()
            val = self.read(addr)
            result = self.b - val
            self.cc_c = result < 0
            result &= 0xFF
            self.update_nz(result)
            self.cc_v = bool(((self.b ^ val) & (self.b ^ result)) & 0x80)

        elif opcode == 0xE7:  # STAB indexed
            addr = self.addr_indexed()
            self.write(addr, self.b)
            self.update_nz(self.b)
            self.cc_v = False

        # -- extended --
        elif opcode == 0xF6:  # LDAB extended
            addr = self.addr_extended()
            self.b = self.read(addr)
            self.update_nz(self.b)
            self.cc_v = False

        elif opcode == 0xF1:  # CMPB extended
            addr = self.addr_extended()
            val = self.read(addr)
            result = self.b - val
            self.cc_c = result < 0
            result &= 0xFF
            self.update_nz(result)
            self.cc_v = bool(((self.b ^ val) & (self.b ^ result)) & 0x80)

        elif opcode == 0xF7:  # STAB extended
            addr = self.addr_extended()
            self.write(addr, self.b)
            self.update_nz(self.b)
            self.cc_v = False

        # ===== LDX / STX / CPX =====
        # -- immediate --
        elif opcode == 0xCE:  # LDX #imm16
            self.x = self.addr_imm16()
            self.update_nz16(self.x)
            self.cc_v = False

        elif opcode == 0x8C:  # CPX #imm16
            val = self.addr_imm16()
            result = self.x - val
            self.cc_z = (result & 0xFFFF) == 0
            self.cc_n = bool(result & 0x8000)
            self.cc_v = bool(((self.x ^ val) & (self.x ^ result)) & 0x8000)

        # -- direct --
        elif opcode == 0xDE:  # LDX direct
            addr = self.addr_direct()
            self.x = self.read16(addr)
            self.update_nz16(self.x)
            self.cc_v = False

        elif opcode == 0xDF:  # STX direct
            addr = self.addr_direct()
            self.write16(addr, self.x)
            self.update_nz16(self.x)
            self.cc_v = False

        elif opcode == 0x9C:  # CPX direct
            addr = self.addr_direct()
            val = self.read16(addr)
            result = self.x - val
            self.cc_z = (result & 0xFFFF) == 0
            self.cc_n = bool(result & 0x8000)
            self.cc_v = bool(((self.x ^ val) & (self.x ^ result)) & 0x8000)

        # -- indexed --
        elif opcode == 0xEE:  # LDX indexed
            addr = self.addr_indexed()
            self.x = self.read16(addr)
            self.update_nz16(self.x)
            self.cc_v = False

        elif opcode == 0xEF:  # STX indexed
            addr = self.addr_indexed()
            self.write16(addr, self.x)
            self.update_nz16(self.x)
            self.cc_v = False

        # -- extended --
        elif opcode == 0xFE:  # LDX extended
            addr = self.addr_extended()
            self.x = self.read16(addr)
            self.update_nz16(self.x)
            self.cc_v = False

        elif opcode == 0xFF:  # STX extended
            addr = self.addr_extended()
            self.write16(addr, self.x)
            self.update_nz16(self.x)
            self.cc_v = False

        elif opcode == 0xBC:  # CPX extended
            addr = self.addr_extended()
            val = self.read16(addr)
            result = self.x - val
            self.cc_z = (result & 0xFFFF) == 0
            self.cc_n = bool(result & 0x8000)
            self.cc_v = bool(((self.x ^ val) & (self.x ^ result)) & 0x8000)

        # ===== LDS / STS =====
        elif opcode == 0x8E:  # LDS #imm16
            self.sp = self.addr_imm16()
            self.update_nz16(self.sp)
            self.cc_v = False

        elif opcode == 0x9E:  # LDS direct
            addr = self.addr_direct()
            self.sp = self.read16(addr)
            self.update_nz16(self.sp)
            self.cc_v = False

        elif opcode == 0xAE:  # LDS indexed
            addr = self.addr_indexed()
            self.sp = self.read16(addr)
            self.update_nz16(self.sp)
            self.cc_v = False

        elif opcode == 0xBE:  # LDS extended
            addr = self.addr_extended()
            self.sp = self.read16(addr)
            self.update_nz16(self.sp)
            self.cc_v = False

        elif opcode == 0x9F:  # STS direct
            addr = self.addr_direct()
            self.write16(addr, self.sp)
            self.update_nz16(self.sp)
            self.cc_v = False

        elif opcode == 0xAF:  # STS indexed
            addr = self.addr_indexed()
            self.write16(addr, self.sp)
            self.update_nz16(self.sp)
            self.cc_v = False

        elif opcode == 0xBF:  # STS extended
            addr = self.addr_extended()
            self.write16(addr, self.sp)
            self.update_nz16(self.sp)
            self.cc_v = False

        # ===== JSR =====
        elif opcode == 0xAD:  # JSR indexed
            addr = self.addr_indexed()
            self.push16(self.pc)
            self.pc = addr

        elif opcode == 0xBD:  # JSR extended
            addr = self.addr_extended()
            self.push16(self.pc)
            self.pc = addr

        # ===== SBA (A = A - B) =====
        elif opcode == 0x10:
            result = self.a - self.b
            self.cc_c = result < 0
            self.cc_v = bool(((self.a ^ self.b) & (self.a ^ result)) & 0x80)
            self.a = result & 0xFF
            self.update_nz(self.a)

        # ===== CBA (A - B, flags only) =====
        elif opcode == 0x11:
            result = self.a - self.b
            self.cc_c = result < 0
            result &= 0xFF
            self.update_nz(result)
            self.cc_v = bool(((self.a ^ self.b) & (self.a ^ result)) & 0x80)

        # ===== DAA =====
        elif opcode == 0x19:
            # BCD 補正（簡易実装）
            upper = (self.a >> 4) & 0x0F
            lower = self.a & 0x0F
            correction = 0
            if lower > 9 or self.cc_h:
                correction += 0x06
            if upper > 9 or self.cc_c or (upper >= 9 and lower > 9):
                correction += 0x60
                self.cc_c = True
            self.a = (self.a + correction) & 0xFF
            self.update_nz(self.a)

        # ===== ADDB / SUBB direct, indexed, extended =====
        elif opcode == 0xDB:  # ADDB direct
            addr = self.addr_direct()
            val = self.read(addr)
            result = self.b + val
            self.cc_c = result > 0xFF
            self.cc_v = bool((~(self.b ^ val) & (self.b ^ result)) & 0x80)
            self.b = result & 0xFF
            self.update_nz(self.b)

        elif opcode == 0xEB:  # ADDB indexed
            addr = self.addr_indexed()
            val = self.read(addr)
            result = self.b + val
            self.cc_c = result > 0xFF
            self.cc_v = bool((~(self.b ^ val) & (self.b ^ result)) & 0x80)
            self.b = result & 0xFF
            self.update_nz(self.b)

        elif opcode == 0xFB:  # ADDB extended
            addr = self.addr_extended()
            val = self.read(addr)
            result = self.b + val
            self.cc_c = result > 0xFF
            self.cc_v = bool((~(self.b ^ val) & (self.b ^ result)) & 0x80)
            self.b = result & 0xFF
            self.update_nz(self.b)

        elif opcode == 0xD0:  # SUBB direct
            addr = self.addr_direct()
            val = self.read(addr)
            result = self.b - val
            self.cc_c = result < 0
            self.cc_v = bool(((self.b ^ val) & (self.b ^ result)) & 0x80)
            self.b = result & 0xFF
            self.update_nz(self.b)

        elif opcode == 0xE0:  # SUBB indexed
            addr = self.addr_indexed()
            val = self.read(addr)
            result = self.b - val
            self.cc_c = result < 0
            self.cc_v = bool(((self.b ^ val) & (self.b ^ result)) & 0x80)
            self.b = result & 0xFF
            self.update_nz(self.b)

        elif opcode == 0xF0:  # SUBB extended
            addr = self.addr_extended()
            val = self.read(addr)
            result = self.b - val
            self.cc_c = result < 0
            self.cc_v = bool(((self.b ^ val) & (self.b ^ result)) & 0x80)
            self.b = result & 0xFF
            self.update_nz(self.b)

        else:
            print(f"\n[EMU] 未実装オペコード: ${opcode:02X} at PC=${self.pc - 1:04X} SP=${self.sp:04X}",
                  file=sys.stderr)
            print(f"[EMU] PC Trace: {[f'${p:04X}' for p in self.pc_trace]}", file=sys.stderr)
            raise SystemExit(1)

    def run(self):
        """メインループ"""
        self.reset()
        try:
            while self.cycles < self.max_cycles:
                self.step()
            print("\n[EMU] サイクル上限に到達しました", file=sys.stderr)
        except SystemExit as e:
            raise e
        except KeyboardInterrupt:
            print("\n[EMU] 中断されました", file=sys.stderr)
        except Exception as e:
            print(f"\n[EMU] エラー: {e} at PC=${self.pc:04X}", file=sys.stderr)
            raise SystemExit(1)


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="SBC6800 向け最小 MC6800 エミュレータ")
    parser.add_argument("rom", help="ROM バイナリファイル (.bin)")
    parser.add_argument("--input", "-i",
                        help="入力スクリプトファイル（省略時は対話モード）")
    parser.add_argument("--max-cycles", type=int, default=100_000_000,
                        help="最大実行サイクル数（デフォルト: 100000000）")
    parser.add_argument("--sd", help="SDカードイメージファイル (.img)")
    args = parser.parse_args()

    # ROM ロード
    with open(args.rom, "rb") as f:
        rom_data = f.read()

    # 入力スクリプト
    input_data = None
    if args.input:
        with open(args.input, "rb") as f:
            input_data = list(f.read())

    acia = ACIA(input_data=input_data)
    sdcard = SDCard(image_path=args.sd)
    pia = PIA(sdcard)
    cpu = MC6800(acia, pia=pia)
    cpu.max_cycles = args.max_cycles

    # ROM のサイズに応じて配置を決定
    # p2bin の出力は ROM_BASE からのオフセットなので、そのまま配置
    rom_size = len(rom_data)
    rom_start = ROM_END - rom_size + 1
    cpu.load_rom(rom_data, rom_start)

    try:
        cpu.run()
    finally:
        acia.cleanup()


if __name__ == "__main__":
    main()
