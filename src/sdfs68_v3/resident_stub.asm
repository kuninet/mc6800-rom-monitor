        cpu     6800

        include "hardware.inc"
        include "sdfs3_layout.inc"

SDFS3_API_MAJOR    equ 2
SDFS3_API_MINOR    equ 1    ; slot 16 SD_WRITE を足した(#303)
SDFS3_API_COUNT    equ 17
SDFS3_API_HDR_SIZE equ $18
SDFS3_FLAG_NONE    equ 0
SDFS3_CAPS_NONE    equ 0
SDFS3_CAPS_RAW_WRITE equ $10 ; GET_CAPS の A bit4: raw SD write(#259 の caps 表、#303)
SDFS3_ERR_NONE     equ 0
SDFS3_ERR_NOT_IMPL equ 1
SDFS3_ERR_BAD_CMD  equ 2
SDFS3_ERR_IO       equ 3
SDFS3_ERR_NOT_FOUND equ 4
SDFS3_ERR_LOAD    equ 5
SDFS3_ERR_RUN     equ 6
SDFS3_ERR_COM     equ 7
SDFS3_ERR_TOO_BIG equ 8    ; LOAD_PATH: 空のファイル、または load〜limit に入らない(#315)
SDFS3_ERR_NOT_OPEN equ 9   ; READ_STREAM_GETC: 取っ手が開いていない(#315)
SDFS3_ERR_WR_RANGE equ 10  ; SD_WRITE: LBA が書いてよい範囲の外。SD に何も送らない(#303)
SDFS3_ERR_WR_CMD  equ 11   ; SD_WRITE: CMD24 の R1 が 0 でない、または来ない
SDFS3_ERR_WR_DATA equ 12   ; SD_WRITE: データ応答が「受理」でない(CRC・書き込みエラー、無応答)
SDFS3_ERR_WR_BUSY equ 13   ; SD_WRITE: busy が上限回数のうちに解けない
SDFS3_ERR_WR_VERIFY equ 14 ; SD_WRITE: 読み戻しが書いた内容と違う

; LOAD_PATH の flags(#315)
SDFS3_LP_EXEC      equ $01 ; 読み終えたら BIOS_EXEC で起動して戻らない

; SD_WRITE の flags と書いてよい LBA(#303、#300 の配置)
SDFS3_SDW_SYSTEM   equ $01 ; 1: system 領域 [48, 128)、0: データ領域 [128, ...)
SDFS3_SDW_VERIFY   equ $02 ; 書いたあと読み戻して比べる
SDFS3_SDW_SYS_LO   equ 48  ; active marker(#300)
SDFS3_SDW_DATA_LO  equ 128 ; system slot B の次。FAT32 partition はここより後(#300)
SDFS3_SDW_RESP_TRIES equ 8 ; データ応答の前の $FF を読み飛ばす回数
SDFS3_SDW_BUSY_LIMIT equ 2048 ; busy を待つ XFER の回数(1MHz で約 1.5 秒、推測)
SDFS3_SDW_READ_LIMIT equ $0200 ; 読み戻しのトークンを待つ回数(ROM の SD_READ_SECTOR と同じ)

; 書き換わる変数はイメージの外(窓の resident ワーク)に置く。#311
SDFS3_LAST_ERROR equ SDFS3_WORK_BASE
SDFS3_PARSE_PTR  equ SDFS3_WORK_BASE+1
SDFS3_PARSE_LEN  equ SDFS3_WORK_BASE+3
SDFS3_TOKEN_PTR  equ SDFS3_WORK_BASE+4
SDFS3_TOKEN_LEN  equ SDFS3_WORK_BASE+6
SDFS3_PENDING_ERR equ SDFS3_WORK_BASE+7
SDFS3_EXEC_BLOCK equ SDFS3_WORK_BASE+8   ; BIOS_EXEC に渡す {entry(2), argptr(2)}
; ファイル API(#315)。取っ手は 1 本で、0 なら閉じている
SDFS3_STREAM_OPEN equ SDFS3_WORK_BASE+$0C
SDFS3_LP_FLAGS   equ SDFS3_WORK_BASE+$0D
SDFS3_LP_ARG_LEN equ SDFS3_WORK_BASE+$0E
SDFS3_LP_ROOM    equ SDFS3_WORK_BASE+$0F  ; 2B。limit、検査のあとは limit-load
SDFS3_GETC_X     equ SDFS3_WORK_BASE+$11  ; 2B。GETC が X を保つための退避
SDFS3_CCP_LP_BLOCK equ SDFS3_WORK_BASE+$13 ; 11B。CCP が .COM の起動で組む LOAD_PATH のブロック
SDFS3_COM_IMPLICIT equ SDFS3_WORK_BASE+$1E ; 1B。0 = 語は .COM の名前、1 = 暗黙の検索(決定 5)
SDFS3_COM_PATH   equ SDFS3_WORK_BASE+$1F  ; 40B。暗黙の検索で組む "/BIN/" + 語 + ".COM"
SDFS3_COM_WORD_MAX equ 40-9
; SD_WRITE(#303)。バッファの先頭・末尾の次・ループのポインタ、flags、待つ回数の残り
SDFS3_SDW_START  equ SDFS3_WORK_BASE+$47  ; 2B
SDFS3_SDW_END    equ SDFS3_WORK_BASE+$49  ; 2B
SDFS3_SDW_PTR    equ SDFS3_WORK_BASE+$4B  ; 2B
SDFS3_SDW_FLAGS  equ SDFS3_WORK_BASE+$4D  ; 1B
SDFS3_SDW_COUNT  equ SDFS3_WORK_BASE+$4E  ; 2B
SDFS3_SDW_BAD    equ SDFS3_WORK_BASE+$50  ; 1B。読み戻しで違ったら 0 以外
SDFS3_WORK_USED  equ $51
 if SDFS3_WORK_USED > $E0
        error   "SDFS/68 v3 resident work overflows W+$0320-$03FF"
 endif

        if S1_SUPPORTED = 0
        error   "SDFS/68 v3 resident is not supported for this memory configuration"
        endif

; ---------------------------------------------------------------------------
; CCP(DOS のプロンプトとコマンド解釈部)。ROM の BOOT3 が +0、WBOOT と DOS が +3 に入る。
; どちらも ROM が lds #STACK_TOP したあとで飛んでくる。
; ---------------------------------------------------------------------------
        org     SDFS3_CCP_BASE

SDFS3_CCP_START:
SDFS3_CCP_VECTORS:
        jmp     SDFS3_CCP_COLD
        jmp     SDFS3_CCP_WARM
        jmp     SDFS3_CCP_WARM

SDFS3_CCP_COLD:
        jsr     SDFS3_INIT
        ldx     #SDFS3_TXT_WELCOME
        jsr     SDFS3_PRINT
        jsr     SDFS3_AUTOEXEC      ; 核に置く(#304)。起動したら戻らない
        bcs     SDFS3_CCP_ERROR
        bra     SDFS3_CCP_PROMPT
SDFS3_CCP_WARM:
        clr     SDFS3_STREAM_OPEN   ; 前のプログラムの取っ手を持ち越さない
        tst     SDFS3_PENDING_ERR
        beq     SDFS3_CCP_PROMPT
        clr     SDFS3_PENDING_ERR
SDFS3_CCP_ERROR:
        ldaa    #'?'
        jsr     SDFS3_PUTC
        ldaa    #CHR_CR
        jsr     SDFS3_PUTC
SDFS3_CCP_PROMPT:
        ldx     #SDFS3_TXT_PROMPT
        jsr     SDFS3_PRINT
        jsr     BIOS_READ_LINE
        tstb
        beq     SDFS3_CCP_PROMPT
        jsr     SDFS3_CMD_DISPATCH
        bcs     SDFS3_CCP_ERROR
        bra     SDFS3_CCP_PROMPT

; 語(TOKEN_PTR、TOKEN_LEN 文字)が X の文字列(大文字)と同じなら C=0。大文字と小文字は区別しない。
SDFS3_MATCH_TOKEN:
        ldab    SDFS3_TOKEN_LEN
        stx     ARG2_PTR
        ldx     SDFS3_TOKEN_PTR
        stx     ARG_PTR
        ldx     ARG2_PTR
; ARG_PTR からの B 文字(1 以上)が X の文字列(大文字)と同じなら C=0。
SDFS3_MATCH:
        stx     ARG2_PTR
SDFS3_MATCH_LOOP:
        ldx     ARG_PTR
        ldaa    0,x
        jsr     SDFS3_TO_UPPER
        inx
        stx     ARG_PTR
        ldx     ARG2_PTR
        cmpa    0,x
        bne     SDFS3_MATCH_FAIL
        inx
        stx     ARG2_PTR
        decb
        bne     SDFS3_MATCH_LOOP
        clc
        rts
SDFS3_MATCH_FAIL:
        sec
        rts

SDFS3_BAD_COMMAND:
        ldaa    #SDFS3_ERR_BAD_CMD
        staa    SDFS3_LAST_ERROR
        sec
        rts

SDFS3_CMD_DISPATCH:
        stx     SDFS3_PARSE_PTR
        stab    SDFS3_PARSE_LEN
SDFS3_CMD_SKIP_SPACE:
        tst     SDFS3_PARSE_LEN
        beq     SDFS3_BAD_COMMAND
        ldx     SDFS3_PARSE_PTR
        ldaa    0,x
        cmpa    #CHR_SPACE
        bne     SDFS3_CMD_TOKEN_START
        inx
        stx     SDFS3_PARSE_PTR
        dec     SDFS3_PARSE_LEN
        bra     SDFS3_CMD_SKIP_SPACE
SDFS3_CMD_TOKEN_START:
        stx     SDFS3_TOKEN_PTR
        clr     SDFS3_TOKEN_LEN
SDFS3_CMD_TOKEN_SCAN:
        tst     SDFS3_PARSE_LEN
        beq     SDFS3_CMD_TOKEN_DONE
        ldx     SDFS3_PARSE_PTR
        ldaa    0,x
        cmpa    #CHR_SPACE
        beq     SDFS3_CMD_TOKEN_DONE
        inc     SDFS3_TOKEN_LEN
        inx
        stx     SDFS3_PARSE_PTR
        dec     SDFS3_PARSE_LEN
        bra     SDFS3_CMD_TOKEN_SCAN
SDFS3_CMD_TOKEN_DONE:
        ldaa    SDFS3_TOKEN_LEN
        beq     SDFS3_BAD_COMMAND
        ldx     #SDFS3_TXT_DIR
        cmpa    #3
        bne     SDFS3_CMD_CHECK_4
        jsr     SDFS3_MATCH_TOKEN
        bcc     SDFS3_CMD_DIR_STUB
        bra     SDFS3_CMD_CHECK_COM
SDFS3_CMD_CHECK_4:
        cmpa    #4
        bne     SDFS3_CMD_CHECK_COM
        ldx     #SDFS3_TXT_TYPE
        jsr     SDFS3_MATCH_TOKEN
        bcc     SDFS3_CMD_TYPE_STUB
        ldx     #SDFS3_TXT_EXIT
        jsr     SDFS3_MATCH_TOKEN
        bcc     SDFS3_CMD_EXIT
; 内蔵でない語は .COM として探す(仕様 2-4、決定 5)。語に「.」があれば .COM の名前そのもの
; (最初の「.」から後ろが .COM でなければ不明なコマンド)、なければ <語>.COM をルート → /BIN の
; 順に探す。
SDFS3_CMD_CHECK_COM:
        clr     SDFS3_COM_IMPLICIT
        ldx     SDFS3_TOKEN_PTR
        ldab    SDFS3_TOKEN_LEN
SDFS3_CMD_FIND_DOT:
        ldaa    0,x
        cmpa    #'.'
        beq     SDFS3_CMD_HAS_DOT
        inx
        decb
        bne     SDFS3_CMD_FIND_DOT
        inc     SDFS3_COM_IMPLICIT
        bra     SDFS3_CMD_COM
SDFS3_CMD_HAS_DOT:
        stx     ARG_PTR
        cmpb    #4
        bne     SDFS3_CMD_BAD_FAR
        ldx     #SDFS3_TXT_BIN+5
        jsr     SDFS3_MATCH
        bcc     SDFS3_CMD_COM
SDFS3_CMD_BAD_FAR:
        jmp     SDFS3_BAD_COMMAND

; EXIT はモニタへ(決定 2)。BIOS_MONITOR が lds #STACK_TOP してモニタの門へ入る。
SDFS3_CMD_EXIT:
        jmp     BIOS_MONITOR
SDFS3_CMD_DIR_STUB:
        jmp     SDFS3_CMD_DIR
SDFS3_CMD_TYPE_STUB:
        jmp     SDFS3_CMD_TYPE

; .COM は核の LOAD_PATH(exec)で $0100 から GET_MEMTOP まで読んで起動する(#315)。
; 読み込みは CCP を潰してよい。戻ってくるのは読み込みを始める前の失敗(C=1)だけ。
; 暗黙の検索では、ルートで見つからなかった(コード 4)ときだけ /BIN を探す(決定 5)。
SDFS3_CMD_COM_FAIL:
        ldaa    #SDFS3_ERR_COM
        jmp     SDFS3_FAIL_A
SDFS3_CMD_COM:
        ldx     SDFS3_TOKEN_PTR
        ldab    SDFS3_TOKEN_LEN
        addb    SDFS3_PARSE_LEN
        jsr     SDFS3_PARSE_COM_PATH_COMMAND
        bcs     SDFS3_CMD_COM_FAIL
        ldx     PATH_PTR
        stx     SDFS3_CCP_LP_BLOCK
        ldaa    PATH_LEN
        staa    SDFS3_CCP_LP_BLOCK+2
        ldx     #SDFS3_COM_BASE
        stx     SDFS3_CCP_LP_BLOCK+3
        ldx     #SDFS3_MEMTOP
        stx     SDFS3_CCP_LP_BLOCK+5
        ldaa    #SDFS3_LP_EXEC
        staa    SDFS3_CCP_LP_BLOCK+7
        ldx     PATH_ARG_PTR
        stx     SDFS3_CCP_LP_BLOCK+8
        ldaa    PATH_ARG_LEN
        staa    SDFS3_CCP_LP_BLOCK+10
        tst     SDFS3_COM_IMPLICIT
        beq     SDFS3_CMD_COM_GO
; 暗黙: SDFS3_COM_PATH に "/BIN/" + 語 + ".COM" を組む。ルートは +5 から、/BIN は先頭から
        ldab    PATH_LEN
        cmpb    #SDFS3_COM_WORD_MAX
        bhi     SDFS3_CMD_COM_FAIL
        ldx     #SDFS3_COM_PATH
        stx     ARG2_PTR
        ldx     #SDFS3_TXT_BIN
        ldab    #5
        bsr     SDFS3_COPY_B
        ldx     PATH_PTR
        ldab    PATH_LEN
        bsr     SDFS3_COPY_B
        ldx     #SDFS3_TXT_BIN+5
        ldab    #4
        bsr     SDFS3_COPY_B
        ldx     #SDFS3_COM_PATH+5
        stx     SDFS3_CCP_LP_BLOCK
        ldaa    PATH_LEN
        adda    #4
        staa    SDFS3_CCP_LP_BLOCK+2
        ldx     #SDFS3_CCP_LP_BLOCK
        jsr     SDFS3_LOAD_PATH
        ldaa    SDFS3_LAST_ERROR
        cmpa    #SDFS3_ERR_NOT_FOUND
        bne     SDFS3_CMD_COM_KEEP
        ldx     #SDFS3_COM_PATH
        stx     SDFS3_CCP_LP_BLOCK
        ldaa    SDFS3_CCP_LP_BLOCK+2
        adda    #5
        staa    SDFS3_CCP_LP_BLOCK+2
SDFS3_CMD_COM_GO:
        ldx     #SDFS3_CCP_LP_BLOCK
        jmp     SDFS3_LOAD_PATH
SDFS3_CMD_COM_KEEP:
        sec
        rts

; X から B バイト(1 以上)を ARG2_PTR へ写し、ARG2_PTR を進める。
SDFS3_COPY_B:
        ldaa    0,x
        inx
        stx     ARG_PTR
        ldx     ARG2_PTR
        staa    0,x
        inx
        stx     ARG2_PTR
        ldx     ARG_PTR
        decb
        bne     SDFS3_COPY_B
        rts

SDFS3_CMD_DIR:
        ldx     SDFS3_PARSE_PTR
        stx     PATH_PTR
        ldaa    SDFS3_PARSE_LEN
        staa    PATH_LEN
        jsr     FAT32_MOUNT
        bcs     SDFS3_CMD_DIR_FAIL
        jsr     SDFS3_DIR_PATH
        bcs     SDFS3_CMD_DIR_PATH_FAIL
        clr     SDFS3_LAST_ERROR
        clc
        rts
SDFS3_CMD_DIR_PATH_FAIL:
        ldaa    FAT_ERROR
        beq     SDFS3_CMD_DIR_NOT_FOUND
SDFS3_CMD_DIR_FAIL:
        jmp     SDFS3_FAT_FAIL
SDFS3_CMD_DIR_NOT_FOUND:
        jmp     SDFS3_NOT_FOUND

SDFS3_CMD_TYPE:
        ldx     SDFS3_PARSE_PTR
        stx     PATH_PTR
        ldaa    SDFS3_PARSE_LEN
        staa    PATH_LEN
        jsr     FAT32_MOUNT
        bcs     SDFS3_CMD_TYPE_FAT_FAIL
        jsr     SDFS3_RESOLVE_FILE_SAVED
        bcs     SDFS3_CMD_TYPE_NOT_FOUND
        jsr     FAT32_STREAM_OPEN
        bcs     SDFS3_CMD_TYPE_FAT_FAIL
SDFS3_TYPE_LOOP:
        jsr     FAT32_STREAM_GETC
        bcc     SDFS3_TYPE_PUTC
        jsr     FAT_BYTES_REMAIN
        bcs     SDFS3_CMD_TYPE_FAT_FAIL
        clr     SDFS3_LAST_ERROR
        clc
        rts
SDFS3_TYPE_PUTC:
        jsr     SDFS3_PUTC
        bra     SDFS3_TYPE_LOOP
SDFS3_CMD_TYPE_NOT_FOUND:
        jmp     SDFS3_NOT_FOUND
SDFS3_CMD_TYPE_FAT_FAIL:
        jmp     SDFS3_FAT_FAIL

SDFS3_DIR_PATH:
        jsr     SDFS3_RESOLVE_DIR_SAVED
        bcs     SDFS3_DIR_FAIL
SDFS3_DIR_CLUSTER_LOOP:
        jsr     FAT_CLUSTER_TO_SD_LBA
        bcs     SDFS3_DIR_FAIL
        ldx     #SD_SECTOR_BUF
        jsr     SD_READ_SECTOR
        bcs     SDFS3_DIR_SD_FAIL
        ldx     #SD_SECTOR_BUF
        stx     FAT_ENTRY_PTR
        ldaa    #16
        staa    FAT_DIR_COUNT
SDFS3_DIR_ENTRY_LOOP:
        ldx     FAT_ENTRY_PTR
        ldaa    0,x
        beq     SDFS3_DIR_DONE
        cmpa    #$E5
        beq     SDFS3_DIR_NEXT_ENTRY
        jsr     SDFS3_DIR_ENTRY_VISIBLE
        bcs     SDFS3_DIR_NEXT_ENTRY
        jsr     SDFS3_PRINT_DIR_ENTRY
SDFS3_DIR_NEXT_ENTRY:
        jsr     FAT_ADVANCE_ENTRY_PTR
        dec     FAT_DIR_COUNT
        bne     SDFS3_DIR_ENTRY_LOOP
        jsr     FAT32_NEXT_CLUSTER
        bcs     SDFS3_DIR_NEXT_DONE_OR_FAIL
        jsr     FAT_COPY_NEXT_TO_CUR
        bra     SDFS3_DIR_CLUSTER_LOOP
SDFS3_DIR_NEXT_DONE_OR_FAIL:
        ldaa    FAT_ERROR
        bne     SDFS3_DIR_FAIL
SDFS3_DIR_DONE:
        clc
        rts
SDFS3_DIR_SD_FAIL:
        ldaa    #FAT_ERR_SD
        staa    FAT_ERROR
SDFS3_DIR_FAIL:
        sec
        rts

SDFS3_PARSE_COM_PATH_COMMAND:
        stx     ARG_PTR
        stab    ARG_LEN
SDFS3_PARSE_COM_PATH_SKIP_HEAD:
        tst     ARG_LEN
        beq     SDFS3_PARSE_COM_PATH_FAIL
        ldx     ARG_PTR
        ldaa    0,x
        cmpa    #CHR_SPACE
        bne     SDFS3_PARSE_COM_PATH_START
        inx
        stx     ARG_PTR
        dec     ARG_LEN
        bra     SDFS3_PARSE_COM_PATH_SKIP_HEAD
SDFS3_PARSE_COM_PATH_START:
        ldx     ARG_PTR
        stx     PATH_PTR
        clr     PATH_LEN
SDFS3_PARSE_COM_PATH_TOKEN:
        tst     ARG_LEN
        beq     SDFS3_PARSE_COM_PATH_NO_ARGS
        ldx     ARG_PTR
        ldaa    0,x
        cmpa    #CHR_SPACE
        beq     SDFS3_PARSE_COM_PATH_ARG_SKIP
        inx
        stx     ARG_PTR
        dec     ARG_LEN
        inc     PATH_LEN
        bra     SDFS3_PARSE_COM_PATH_TOKEN
SDFS3_PARSE_COM_PATH_ARG_SKIP:
        ldaa    PATH_LEN
        beq     SDFS3_PARSE_COM_PATH_FAIL
        ldx     ARG_PTR
        inx
        stx     ARG_PTR
        dec     ARG_LEN
SDFS3_PARSE_COM_PATH_ARG_SKIP_LOOP:
        tst     ARG_LEN
        beq     SDFS3_PARSE_COM_PATH_NO_ARGS
        ldx     ARG_PTR
        ldaa    0,x
        cmpa    #CHR_SPACE
        bne     SDFS3_PARSE_COM_PATH_ARGS
        inx
        stx     ARG_PTR
        dec     ARG_LEN
        bra     SDFS3_PARSE_COM_PATH_ARG_SKIP_LOOP
SDFS3_PARSE_COM_PATH_ARGS:
        ldx     ARG_PTR
        stx     PATH_ARG_PTR
        ldaa    ARG_LEN
        staa    PATH_ARG_LEN
        clc
        rts
SDFS3_PARSE_COM_PATH_NO_ARGS:
        ldaa    PATH_LEN
        beq     SDFS3_PARSE_COM_PATH_FAIL
        ldx     ARG_PTR
        stx     PATH_ARG_PTR
        clr     PATH_ARG_LEN
        clc
        rts
SDFS3_PARSE_COM_PATH_FAIL:
        sec
        rts

SDFS3_PRINT_DIR_ENTRY:
        ldx     FAT_ENTRY_PTR
        ldab    #8
SDFS3_PRINT_DIR_NAME_LOOP:
        ldaa    0,x
        cmpa    #CHR_SPACE
        beq     SDFS3_PRINT_DIR_NAME_DONE
        jsr     SDFS3_PUTC
        inx
        decb
        bne     SDFS3_PRINT_DIR_NAME_LOOP
SDFS3_PRINT_DIR_NAME_DONE:
        jsr     SDFS3_DIR_EXT_HAS_CHAR
        bcs     SDFS3_PRINT_DIR_NO_EXT
        ldaa    #'.'
        jsr     SDFS3_PUTC
        ldx     FAT_ENTRY_PTR
        ldab    #8
SDFS3_PRINT_DIR_EXT_SKIP:
        inx
        decb
        bne     SDFS3_PRINT_DIR_EXT_SKIP
        ldab    #3
SDFS3_PRINT_DIR_EXT_LOOP:
        ldaa    0,x
        cmpa    #CHR_SPACE
        beq     SDFS3_PRINT_DIR_EXT_DONE
        jsr     SDFS3_PUTC
        inx
        decb
        bne     SDFS3_PRINT_DIR_EXT_LOOP
SDFS3_PRINT_DIR_EXT_DONE:
SDFS3_PRINT_DIR_NO_EXT:
        ldaa    #CHR_SPACE
        jsr     SDFS3_PUTC
        ldx     FAT_ENTRY_PTR
        ldaa    11,x
        bita    #$10
        beq     SDFS3_PRINT_DIR_ATTR_FILE
        ldaa    #'D'
        bra     SDFS3_PRINT_DIR_ATTR_OUT
SDFS3_PRINT_DIR_ATTR_FILE:
        ldaa    #'A'
SDFS3_PRINT_DIR_ATTR_OUT:
        jsr     SDFS3_PUTC
        ldaa    #CHR_SPACE
        jsr     SDFS3_PUTC
        ldx     FAT_ENTRY_PTR
        ldaa    31,x
        jsr     SDFS3_PRINT_HEX8
        ldaa    30,x
        jsr     SDFS3_PRINT_HEX8
        ldaa    29,x
        jsr     SDFS3_PRINT_HEX8
        ldaa    28,x
        jsr     SDFS3_PRINT_HEX8
        ldaa    #CHR_CR
        jsr     SDFS3_PUTC
        rts

SDFS3_DIR_EXT_HAS_CHAR:
        ldx     FAT_ENTRY_PTR
        ldab    #8
SDFS3_DIR_EXT_SKIP:
        inx
        decb
        bne     SDFS3_DIR_EXT_SKIP
        ldab    #3
SDFS3_DIR_EXT_CHECK_LOOP:
        ldaa    0,x
        cmpa    #CHR_SPACE
        bne     SDFS3_DIR_EXT_FOUND
        inx
        decb
        bne     SDFS3_DIR_EXT_CHECK_LOOP
        sec
        rts
SDFS3_DIR_EXT_FOUND:
        clc
        rts

SDFS3_DIR_ENTRY_VISIBLE:
        ldx     FAT_ENTRY_PTR
        ldaa    11,x
        anda    #$0E
        bne     SDFS3_DIR_ENTRY_SKIP
        ldaa    0,x
        cmpa    #'.'
        beq     SDFS3_DIR_ENTRY_SKIP
        cmpa    #CHR_SPACE
        beq     SDFS3_DIR_ENTRY_SKIP
        ldab    #11
SDFS3_DIR_NAME_CHAR_LOOP:
        ldaa    0,x
        cmpa    #CHR_SPACE
        beq     SDFS3_DIR_NAME_CHAR_OK
        blo     SDFS3_DIR_ENTRY_SKIP
        cmpa    #$7F
        bhs     SDFS3_DIR_ENTRY_SKIP
SDFS3_DIR_NAME_CHAR_OK:
        inx
        decb
        bne     SDFS3_DIR_NAME_CHAR_LOOP
        clc
        rts
SDFS3_DIR_ENTRY_SKIP:
        sec
        rts

; Welcome はアセンブル時に組み立てる(版と範囲を 16 進の文字にする)
SDFS3_HEXCH function n,'0'+n+7*(n>9)
SDFS3_TXT_WELCOME:
        fcc     "SDFS/68 V3 "
        fcb     SDFS3_HEXCH(SDFS3_API_MAJOR>>4),SDFS3_HEXCH(SDFS3_API_MAJOR&15),'.'
        fcb     SDFS3_HEXCH(SDFS3_API_MINOR>>4),SDFS3_HEXCH(SDFS3_API_MINOR&15),CHR_CR
        fcc     "BASE="
        fcb     SDFS3_HEXCH(SDFS3_CCP_BASE>>12),SDFS3_HEXCH((SDFS3_CCP_BASE>>8)&15)
        fcb     SDFS3_HEXCH((SDFS3_CCP_BASE>>4)&15),SDFS3_HEXCH(SDFS3_CCP_BASE&15)
        fcc     " END="
        fcb     SDFS3_HEXCH((SDFS3_END-1)>>12),SDFS3_HEXCH(((SDFS3_END-1)>>8)&15)
        fcb     SDFS3_HEXCH(((SDFS3_END-1)>>4)&15),SDFS3_HEXCH((SDFS3_END-1)&15),CHR_CR,0
SDFS3_TXT_DIR:
        fcc     "DIR"
SDFS3_TXT_TYPE:
        fcc     "TYPE"
SDFS3_TXT_EXIT:
        fcc     "EXIT"
SDFS3_TXT_PROMPT:
        fcc     "SDFS3> "
        fcb     0
SDFS3_TXT_BIN:
        fcc     "/BIN/.COM"

SDFS3_CCP_END:
        if SDFS3_CCP_END > SDFS3_CORE_BASE
        error   "CCP overflows into the core; lower SDFS3_CCP_BASE"
        endif

; ---------------------------------------------------------------------------
; 核(BDOS 相当)。SDFS3API ヘッダはここ(SDFS3_CORE_BASE)に置く。核から CCP は参照しない。
; ---------------------------------------------------------------------------
        org     SDFS3_CORE_BASE

SDFS3_CORE_START:
SDFS3_API_HEADER:
        fcc     "SDFS3API"
        fcb     SDFS3_API_MAJOR
        fcb     SDFS3_API_MINOR
        fcb     SDFS3_API_COUNT
        fcb     SDFS3_FLAG_NONE
        fdb     SDFS3_JUMP_TABLE
        fdb     SDFS3_CCP_BASE
        fdb     SDFS3_END-1
        fdb     SDFS3_MEMTOP
        fdb     0
        fdb     0

SDFS3_JUMP_TABLE:
        fdb     SDFS3_GET_INFO
        fdb     SDFS3_NOT_IMPLEMENTED
        fdb     SDFS3_LOAD_PATH
        fdb     SDFS3_READ_STREAM_OPEN
        fdb     SDFS3_READ_STREAM_GETC
        fdb     SDFS3_READ_STREAM_CLOSE
        fdb     SDFS3_GET_ERROR
        fdb     SDFS3_GET_MEMTOP
        fdb     SDFS3_GET_CAPS
        fdb     SDFS3_NOT_IMPLEMENTED
        fdb     SDFS3_NOT_IMPLEMENTED
        fdb     SDFS3_NOT_IMPLEMENTED
        fdb     SDFS3_NOT_IMPLEMENTED
        fdb     SDFS3_INIT
        fdb     SDFS3_NOT_IMPLEMENTED
        fdb     SDFS3_NOT_IMPLEMENTED
        fdb     SDFS3_SD_WRITE
SDFS3_JUMP_TABLE_END:
        if (SDFS3_JUMP_TABLE_END-SDFS3_JUMP_TABLE)/2 <> SDFS3_API_COUNT
        error   "SDFS3 jump table size does not match SDFS3_API_COUNT"
        endif

SDFS3_GET_INFO:
        ldaa    #SDFS3_API_MAJOR
        ldab    #SDFS3_FLAG_NONE
        ldx     #SDFS3_API_HEADER
        clc
        rts

; ---------------------------------------------------------------------------
; ファイル API(slot 2〜5、#315。仕様 2-3)。パスを取る API(LOAD_PATH・OPEN)は、コマンドと同じく
; 頭で FAT32_MOUNT し直す(ROM の読み直しなどが SD_SECTOR_BUF と FAT_* を上書きしてよいように)。
; 取っ手は 1 本。LOAD_PATH と OPEN はまず前の取っ手を閉じる。
; ---------------------------------------------------------------------------

; slot 2 LOAD_PATH。X -> {path(2), path_len(1), load(2), limit(2), flags(1), argptr(2), arg_len(1)}
; ファイルを load〜limit(limit を含む)に読む。limit は GET_MEMTOP 以下(核と窓を潰さない)。
; 読み込みを始める前の失敗は C=1(見つからない 4、SD 3、空・入らない 8)で戻る。
; 読み込みの途中の失敗は LAST_ERROR と PENDING_ERR に 3 を入れて BIOS_WBOOT へ飛び、戻らない。
; flags bit0 なら BIOS_EXEC(entry = load、X = argptr、B = arg_len)で起動して戻らない。
; bit0 でなければ C=0、LAST_ERROR = 0、X = 読み込んだ末尾の次の番地。
; ブロックは最初に写すので、読み込みで潰れてもよい。
SDFS3_LOAD_PATH:
        ldaa    7,x
        staa    SDFS3_LP_FLAGS
        ldaa    10,x
        staa    SDFS3_LP_ARG_LEN
        ldaa    2,x
        staa    PATH_LEN
        ldaa    5,x
        staa    SDFS3_LP_ROOM
        ldaa    6,x
        staa    SDFS3_LP_ROOM+1
        ldaa    3,x
        staa    SDFS3_EXEC_BLOCK
        ldaa    4,x
        staa    SDFS3_EXEC_BLOCK+1
        ldaa    8,x
        staa    SDFS3_EXEC_BLOCK+2
        ldaa    9,x
        staa    SDFS3_EXEC_BLOCK+3
        ldx     0,x
        stx     PATH_PTR
        jsr     SDFS3_OPEN_PATH
        bcs     SDFS3_LP_RTS
; 大きさ: 1 バイト以上 $FFFF 以下、limit <= MEMTOP、load <= limit、size-1 <= limit-load
        ldaa    FAT_FILE_SIZE0
        oraa    FAT_FILE_SIZE1
        bne     SDFS3_LP_TOO_BIG
        ldaa    FAT_FILE_SIZE2
        oraa    FAT_FILE_SIZE3
        beq     SDFS3_LP_TOO_BIG
        ldaa    SDFS3_LP_ROOM
        ldab    SDFS3_LP_ROOM+1
        cmpa    #SDFS3_MEMTOP/$0100
        bhi     SDFS3_LP_TOO_BIG
        blo     SDFS3_LP_LIMIT_OK
        cmpb    #SDFS3_MEMTOP&$00FF
        bhi     SDFS3_LP_TOO_BIG
SDFS3_LP_LIMIT_OK:
        subb    SDFS3_EXEC_BLOCK+1
        sbca    SDFS3_EXEC_BLOCK
        bcs     SDFS3_LP_TOO_BIG
        staa    SDFS3_LP_ROOM
        stab    SDFS3_LP_ROOM+1
        ldaa    FAT_FILE_SIZE2
        ldab    FAT_FILE_SIZE3
        subb    #1
        sbca    #0
        cmpa    SDFS3_LP_ROOM
        bhi     SDFS3_LP_TOO_BIG
        blo     SDFS3_LP_SIZE_OK
        cmpb    SDFS3_LP_ROOM+1
        bhi     SDFS3_LP_TOO_BIG
SDFS3_LP_SIZE_OK:
        ldx     SDFS3_EXEC_BLOCK
        stx     FAT_READ_PTR
SDFS3_LP_LOOP:
        jsr     FAT_BYTES_REMAIN
        bcc     SDFS3_LP_DONE
        jsr     FAT32_STREAM_GETC
        bcs     SDFS3_LP_MID_FAIL
        ldx     FAT_READ_PTR
        staa    0,x
        inx
        stx     FAT_READ_PTR
        bra     SDFS3_LP_LOOP
SDFS3_LP_DONE:
        ldaa    SDFS3_LP_FLAGS
        bita    #SDFS3_LP_EXEC
        bne     SDFS3_LP_EXEC_IT
        clr     SDFS3_LAST_ERROR
        ldx     FAT_READ_PTR
        clc
SDFS3_LP_RTS:
        rts
SDFS3_LP_EXEC_IT:
        ldab    SDFS3_LP_ARG_LEN
; BIOS_EXEC で起動する(EXEC_BLOCK と B は呼び手が用意する)。プログラムの RTS は ROM の
; WBOOT を通って CCP の warm に戻る。CCP の RUN もここを使う。
SDFS3_EXEC:
        clr     SDFS3_LAST_ERROR
        ldx     #SDFS3_EXEC_BLOCK
        jmp     BIOS_EXEC
SDFS3_LP_TOO_BIG:
        ldaa    #SDFS3_ERR_TOO_BIG
        jmp     SDFS3_FAIL_A
; 読み込みの途中の失敗。呼び手(CCP など)は潰れているかもしれないので戻らない。WBOOT は
; 壊れた区画を読み直して CCP の warm に入り、warm が PENDING_ERR を見て「?」を出す。
SDFS3_LP_MID_FAIL:
        ldaa    #SDFS3_ERR_IO
        staa    SDFS3_LAST_ERROR
        staa    SDFS3_PENDING_ERR
        jmp     BIOS_WBOOT

; slot 3 READ_STREAM_OPEN。X = パス、B = 長さ。C=1 なら見つからない 4、SD 3。
SDFS3_READ_STREAM_OPEN:
        stx     PATH_PTR
        stab    PATH_LEN
        jsr     SDFS3_OPEN_PATH
        bcs     SDFS3_LP_RTS
        ldaa    #1
        staa    SDFS3_STREAM_OPEN
        clr     SDFS3_LAST_ERROR
        clc
        rts

; slot 4 READ_STREAM_GETC。A = 1 バイト(B と X は保つ)。終わりで C=1・LAST_ERROR = 0。
; SD の失敗は C=1・3、取っ手が開いていなければ C=1・9。
SDFS3_READ_STREAM_GETC:
        stx     SDFS3_GETC_X
        pshb
        tst     SDFS3_STREAM_OPEN
        beq     SDFS3_GETC_NOT_OPEN
        jsr     FAT32_STREAM_GETC
        bcc     SDFS3_GETC_DONE
        jsr     FAT_BYTES_REMAIN
        bcs     SDFS3_GETC_IO
        clra
        bra     SDFS3_GETC_FAIL
SDFS3_GETC_IO:
        ldaa    #SDFS3_ERR_IO
        bra     SDFS3_GETC_FAIL
SDFS3_GETC_NOT_OPEN:
        ldaa    #SDFS3_ERR_NOT_OPEN
SDFS3_GETC_FAIL:
        staa    SDFS3_LAST_ERROR
        sec
SDFS3_GETC_DONE:
        pulb
        ldx     SDFS3_GETC_X
        rts

; slot 5 READ_STREAM_CLOSE。取っ手を閉じる。C=0。
SDFS3_READ_STREAM_CLOSE:
        clr     SDFS3_STREAM_OPEN
        clc
        rts

; 取っ手を閉じ、mount し直して PATH_PTR/PATH_LEN のファイルを開く(LOAD_PATH と OPEN が共用)。
SDFS3_OPEN_PATH:
        clr     SDFS3_STREAM_OPEN
        jsr     FAT32_MOUNT
        bcs     SDFS3_OPEN_PATH_IO
        jsr     SDFS3_RESOLVE_FILE_SAVED
        bcs     SDFS3_OPEN_PATH_RESOLVE_FAIL
        jmp     FAT32_STREAM_OPEN
SDFS3_OPEN_PATH_RESOLVE_FAIL:
        ldaa    FAT_ERROR
        bne     SDFS3_OPEN_PATH_IO
        jmp     SDFS3_NOT_FOUND
SDFS3_OPEN_PATH_IO:
        jmp     SDFS3_FAT_FAIL

SDFS3_NOT_IMPLEMENTED:
        ldaa    #SDFS3_ERR_NOT_IMPL
SDFS3_NOT_IMPLEMENTED_A:
        staa    SDFS3_LAST_ERROR
        sec
        rts

SDFS3_GET_ERROR:
        ldaa    SDFS3_LAST_ERROR
        clc
        rts

SDFS3_GET_MEMTOP:
        ldx     #SDFS3_MEMTOP
        clc
        rts

SDFS3_GET_CAPS:
        ldaa    #SDFS3_CAPS_RAW_WRITE
        ldab    #SDFS3_CAPS_NONE
        ldx     #SDFS3_API_HEADER
        clc
        rts

; ---------------------------------------------------------------------------
; slot 16 SD_WRITE(#303)。1 セクタ(512B)を SD に書く。CCP からは呼ばない。
; X -> {buf(2), lba(4, 上位から), flags(1)}。flags bit0 = system 領域 [48, 128)、
; bit0 = 0 ならデータ領域 [128, ...)。0〜47(MBR・予約・stage1)はどちらでも拒む。
; bit1 = 書いたあと読み戻して buf と比べる(SD_SECTOR_BUF は使わない)。
; C=0 で成功。C=1 なら A = コード(LAST_ERROR と同じ)、B = カードが返した生のバイト。
; A・B・X を壊す。FAT_* と SD_SECTOR_BUF に触らないので、開いた取っ手はそのまま続く。
; ROM の SD 低レベル入口(BIOS_SD_SELECT〜WAIT_R1)だけを使う(決定 7)。XFER が X・B を
; 保つことは当てにしない。
SDFS3_SD_WRITE:
        ldaa    0,x
        staa    SDFS3_SDW_START
        adda    #2
        staa    SDFS3_SDW_END
        ldaa    1,x
        staa    SDFS3_SDW_START+1
        staa    SDFS3_SDW_END+1
        ldaa    2,x                     ; SD_LBA* は ROM の SEND_CMD が読むだけで変えない
        staa    SD_LBA0
        ldaa    3,x
        staa    SD_LBA1
        ldaa    4,x
        staa    SD_LBA2
        ldaa    5,x
        staa    SD_LBA3
        ldab    6,x
        stab    SDFS3_SDW_FLAGS
        ; 範囲。上位 3 バイトのどれかが 0 でなければ LBA >= 256
        ldaa    SD_LBA0
        oraa    SD_LBA1
        oraa    SD_LBA2
        andb    #SDFS3_SDW_SYSTEM
        bne     SDFS3_SDW_CHECK_SYS
        tsta
        bne     SDFS3_SDW_IN_RANGE
        ldaa    SD_LBA3
        cmpa    #SDFS3_SDW_DATA_LO
        bhs     SDFS3_SDW_IN_RANGE
        bra     SDFS3_SDW_RANGE_FAIL
SDFS3_SDW_CHECK_SYS:
        tsta
        bne     SDFS3_SDW_RANGE_FAIL
        ldaa    SD_LBA3
        cmpa    #SDFS3_SDW_SYS_LO
        blo     SDFS3_SDW_RANGE_FAIL
        cmpa    #SDFS3_SDW_DATA_LO
        blo     SDFS3_SDW_IN_RANGE
SDFS3_SDW_RANGE_FAIL:
        clrb
        ldaa    #SDFS3_ERR_WR_RANGE
        jmp     SDFS3_SDW_FAIL_AB

SDFS3_SDW_IN_RANGE:
        ldaa    #$58                    ; CMD24 WRITE_BLOCK
        bsr     SDFS3_SDW_CMD
        bcs     SDFS3_SDW_CMD_NO_R1
        tab
        tsta
        beq     SDFS3_SDW_SEND_DATA
        bra     SDFS3_SDW_CMD_FAIL
SDFS3_SDW_CMD_NO_R1:
        ldab    #$FF
SDFS3_SDW_CMD_FAIL:
        ldaa    #SDFS3_ERR_WR_CMD
        bra     SDFS3_SDW_DESELECT_FAIL

SDFS3_SDW_SEND_DATA:
        bsr     SDFS3_SDW_FF            ; Nwr の間
        ldaa    #$FE                    ; データの開始トークン
        jsr     BIOS_SD_XFER
        bsr     SDFS3_SDW_REWIND
SDFS3_SDW_DATA_LOOP:
        ldx     SDFS3_SDW_PTR
        ldaa    0,x
        inx
        stx     SDFS3_SDW_PTR
        jsr     BIOS_SD_XFER
        ldx     SDFS3_SDW_PTR
        cpx     SDFS3_SDW_END
        bne     SDFS3_SDW_DATA_LOOP
        bsr     SDFS3_SDW_FF            ; CRC 2 バイト(SPI では見ない)
        bsr     SDFS3_SDW_FF
        ; データ応答 xxx0sss1。$FF は RESP_TRIES 回まで読み飛ばす
        ldab    #SDFS3_SDW_RESP_TRIES
SDFS3_SDW_RESP_LOOP:
        pshb
        bsr     SDFS3_SDW_FF
        pulb
        cmpa    #$FF
        bne     SDFS3_SDW_RESP_GOT
        decb
        bne     SDFS3_SDW_RESP_LOOP
SDFS3_SDW_RESP_GOT:
        tab
        anda    #$1F
        cmpa    #$05
        beq     SDFS3_SDW_BUSY_PREP
        ldaa    #SDFS3_ERR_WR_DATA
        bra     SDFS3_SDW_DESELECT_FAIL

; 小さな部品。SDW_CMD: A = コマンドで SELECT → SEND_CMD(C=1 なら R1 なし、A = R1。A・B を壊す)。
; SDW_FF: $FF を送って A に受ける。SDW_REWIND: PTR を START に戻す(X を壊す)。
SDFS3_SDW_CMD:
        staa    SD_CMD_BYTE
        ldaa    #$FF
        staa    SD_CRC_BYTE
        jsr     BIOS_SD_SELECT
        jmp     BIOS_SD_SEND_CMD
SDFS3_SDW_FF:
        ldaa    #$FF
        jmp     BIOS_SD_XFER
SDFS3_SDW_REWIND:
        ldx     SDFS3_SDW_START
        stx     SDFS3_SDW_PTR
        rts

SDFS3_SDW_BUSY_PREP:
        ldx     #SDFS3_SDW_BUSY_LIMIT
        stx     SDFS3_SDW_COUNT
SDFS3_SDW_BUSY_LOOP:
        bsr     SDFS3_SDW_FF
        cmpa    #$FF
        beq     SDFS3_SDW_WRITTEN
        ldx     SDFS3_SDW_COUNT
        dex
        stx     SDFS3_SDW_COUNT
        bne     SDFS3_SDW_BUSY_LOOP
        clrb
        ldaa    #SDFS3_ERR_WR_BUSY
SDFS3_SDW_DESELECT_FAIL:
        psha
        pshb
        jsr     BIOS_SD_DESELECT
        pulb
        pula
SDFS3_SDW_FAIL_AB:
        staa    SDFS3_LAST_ERROR
        sec
        rts

SDFS3_SDW_WRITTEN:
        jsr     BIOS_SD_DESELECT
        ldaa    SDFS3_SDW_FLAGS
        anda    #SDFS3_SDW_VERIFY
        beq     SDFS3_SDW_OK
        ; 読み戻し。CMD17 を出し、受けたバイトを buf と比べる。不一致でも最後まで読む
        clr     SDFS3_SDW_BAD
        ldaa    #$51                    ; CMD17 READ_SINGLE_BLOCK
        bsr     SDFS3_SDW_CMD
        bcs     SDFS3_SDW_READ_FAIL
        tsta
        bne     SDFS3_SDW_READ_FAIL
        ldx     #SDFS3_SDW_READ_LIMIT
        stx     SDFS3_SDW_COUNT
SDFS3_SDW_TOKEN_LOOP:
        bsr     SDFS3_SDW_FF
        cmpa    #$FE
        beq     SDFS3_SDW_CMP_START
        cmpa    #$FF
        bne     SDFS3_SDW_READ_FAIL
        ldx     SDFS3_SDW_COUNT
        dex
        stx     SDFS3_SDW_COUNT
        bne     SDFS3_SDW_TOKEN_LOOP
        bra     SDFS3_SDW_READ_FAIL
SDFS3_SDW_CMP_START:
        bsr     SDFS3_SDW_REWIND
SDFS3_SDW_CMP_LOOP:
        bsr     SDFS3_SDW_FF
        ldx     SDFS3_SDW_PTR
        cmpa    0,x
        beq     SDFS3_SDW_CMP_NEXT
        inc     SDFS3_SDW_BAD
SDFS3_SDW_CMP_NEXT:
        inx
        stx     SDFS3_SDW_PTR
        cpx     SDFS3_SDW_END
        bne     SDFS3_SDW_CMP_LOOP
        bsr     SDFS3_SDW_FF
        bsr     SDFS3_SDW_FF
        jsr     BIOS_SD_DESELECT
        tst     SDFS3_SDW_BAD
        beq     SDFS3_SDW_OK
        clrb
        ldaa    #SDFS3_ERR_WR_VERIFY
        bra     SDFS3_SDW_FAIL_AB
SDFS3_SDW_READ_FAIL:
        tab
        ldaa    #SDFS3_ERR_IO
        bra     SDFS3_SDW_DESELECT_FAIL
SDFS3_SDW_OK:
        clr     SDFS3_LAST_ERROR
        clc
        rts

; 核の初期化(slot 13)。出力しない。ROM は呼ばず、CCP の cold 入口が呼ぶ(仕様 2-3)。
; LAST_ERROR・PENDING_ERR・取っ手はイメージの外にあり初期値を持たないので、ここで 0 にする。
SDFS3_INIT:
        clr     SDFS3_LAST_ERROR
        clr     SDFS3_PENDING_ERR
        clr     SDFS3_STREAM_OPEN
        clc
        rts

; AUTOEXEC(#304)。CCP の cold 入口だけが呼ぶ(warm では呼ばない)。ルートの AUTOEXEC.COM を
; .COM と同じく LOAD_PATH(exec)で起動し、戻らない(RTS は WBOOT → CCP の warm)。
; 抑止: コンソール(ACIA1、キーボードの ACIA2)に受信済みの文字があれば、SD を読まずに C=0 で
; 戻る。文字は読まずに残し、プロンプトの最初の入力にする(6850 は読むと戻せないため)。
; 見つからなければ LAST_ERROR = 0、C=0。読み込みの前のほかの失敗は C=1(LAST_ERROR はそのコード)。
; 読み込みの途中の失敗は LOAD_PATH のとおり PENDING_ERR を立てて WBOOT へ飛ぶ。
SDFS3_AUTOEXEC:
        ldaa    ACIA_CTRL
 if MONITOR_FEATURE_KEYBOARD
        oraa    ACIA2_CTRL
 endif
        bita    #ACIA_STAT_RDRF
        bne     SDFS3_AE_QUIET
        ldx     #SDFS3_AE_BLOCK
        jsr     SDFS3_LOAD_PATH
        ldaa    SDFS3_LAST_ERROR
        cmpa    #SDFS3_ERR_NOT_FOUND
        sec
        bne     SDFS3_AE_RTS
        clr     SDFS3_LAST_ERROR
SDFS3_AE_QUIET:
        clc
SDFS3_AE_RTS:
        rts
; LOAD_PATH のブロック。引数はなし(B=0)。argptr は 0 のバイト(このブロックの arg_len)を指す。
SDFS3_AE_BLOCK:
        fdb     SDFS3_TXT_AUTOEXEC
        fcb     SDFS3_TXT_AUTOEXEC_END-SDFS3_TXT_AUTOEXEC
        fdb     SDFS3_COM_BASE
        fdb     SDFS3_MEMTOP
        fcb     SDFS3_LP_EXEC
        fdb     SDFS3_AE_BLOCK+10
        fcb     0
SDFS3_TXT_AUTOEXEC:
        fcc     "AUTOEXEC.COM"
SDFS3_TXT_AUTOEXEC_END:

SDFS3_TO_UPPER:
        cmpa    #'a'
        blo     SDFS3_TO_UPPER_DONE
        cmpa    #'z'
        bhi     SDFS3_TO_UPPER_DONE
        suba    #$20
SDFS3_TO_UPPER_DONE:
        rts

SDFS3_RESOLVE_FILE_SAVED:
        jsr     SDFS3_PATH_START
        bcs     SDFS3_RESOLVE_FAIL
SDFS3_RESOLVE_FILE_LOOP:
        jsr     SDFS3_PATH_COMPONENT
        bcs     SDFS3_RESOLVE_FAIL
        jsr     SDFS3_FIND_IN_CUR
        bcs     SDFS3_RESOLVE_FAIL
        tst     PATH_DELIM
        beq     SDFS3_RESOLVE_FILE_LAST
        jsr     SDFS3_ENTRY_IS_DIR
        bcs     SDFS3_RESOLVE_FAIL
        jsr     FAT_COPY_FILE_TO_CUR
        bra     SDFS3_RESOLVE_FILE_LOOP
SDFS3_RESOLVE_FILE_LAST:
        jsr     SDFS3_ENTRY_IS_FILE
        bcs     SDFS3_RESOLVE_FAIL
        clc
        rts

SDFS3_RESOLVE_DIR_SAVED:
        jsr     SDFS3_PATH_START_ALLOW_ROOT
        bcs     SDFS3_RESOLVE_FAIL
        tst     PATH_LEN
        beq     SDFS3_RESOLVE_OK
SDFS3_RESOLVE_DIR_LOOP:
        jsr     SDFS3_PATH_COMPONENT
        bcs     SDFS3_RESOLVE_FAIL
        jsr     SDFS3_FIND_IN_CUR
        bcs     SDFS3_RESOLVE_FAIL
        jsr     SDFS3_ENTRY_IS_DIR
        bcs     SDFS3_RESOLVE_FAIL
        jsr     FAT_COPY_FILE_TO_CUR
        tst     PATH_DELIM
        bne     SDFS3_RESOLVE_DIR_LOOP
SDFS3_RESOLVE_OK:
        clc
        rts
SDFS3_RESOLVE_FAIL:
        sec
        rts

SDFS3_PATH_START:
        jsr     SDFS3_PATH_SKIP_HEAD
        bcs     SDFS3_PATH_START_FAIL
        tst     PATH_LEN
        beq     SDFS3_PATH_START_FAIL
        jsr     FAT_COPY_ROOT_TO_CUR
        clc
        rts
SDFS3_PATH_START_ALLOW_ROOT:
        jsr     SDFS3_PATH_SKIP_HEAD
        bcs     SDFS3_PATH_START_FAIL
        jsr     FAT_COPY_ROOT_TO_CUR
        clc
        rts
SDFS3_PATH_START_FAIL:
        sec
        rts

SDFS3_PATH_SKIP_HEAD:
        tst     PATH_LEN
        beq     SDFS3_PATH_SKIP_DONE
        ldx     PATH_PTR
        ldaa    0,x
        cmpa    #CHR_SPACE
        beq     SDFS3_PATH_SKIP_ONE
        cmpa    #'/'
        beq     SDFS3_PATH_SKIP_SLASH
        bra     SDFS3_PATH_SKIP_DONE
SDFS3_PATH_SKIP_ONE:
        inx
        stx     PATH_PTR
        dec     PATH_LEN
        bra     SDFS3_PATH_SKIP_HEAD
SDFS3_PATH_SKIP_SLASH:
        inx
        stx     PATH_PTR
        dec     PATH_LEN
        beq     SDFS3_PATH_SKIP_FAIL
SDFS3_PATH_SKIP_DONE:
        clc
        rts
SDFS3_PATH_SKIP_FAIL:
        sec
        rts

SDFS3_PATH_COMPONENT:
        ldx     PATH_PTR
        stx     ARG2_PTR
        clr     ARG2_LEN
        clr     PATH_DELIM
SDFS3_PATH_COMPONENT_LOOP:
        tst     PATH_LEN
        beq     SDFS3_PATH_COMPONENT_DONE
        ldx     PATH_PTR
        ldaa    0,x
        cmpa    #'/'
        beq     SDFS3_PATH_COMPONENT_SLASH
        cmpa    #CHR_SPACE
        beq     SDFS3_PATH_COMPONENT_SPACE
        inx
        stx     PATH_PTR
        dec     PATH_LEN
        inc     ARG2_LEN
        bra     SDFS3_PATH_COMPONENT_LOOP
SDFS3_PATH_COMPONENT_SLASH:
        ldaa    ARG2_LEN
        beq     SDFS3_PATH_COMPONENT_FAIL
        ldx     PATH_PTR
        inx
        stx     PATH_PTR
        dec     PATH_LEN
        ldaa    #1
        staa    PATH_DELIM
        tst     PATH_LEN
        beq     SDFS3_PATH_COMPONENT_FAIL
        bra     SDFS3_PATH_COMPONENT_PARSE
SDFS3_PATH_COMPONENT_SPACE:
        jsr     SDFS3_PATH_SKIP_TRAILING
        bcs     SDFS3_PATH_COMPONENT_FAIL
SDFS3_PATH_COMPONENT_DONE:
        ldaa    ARG2_LEN
        beq     SDFS3_PATH_COMPONENT_FAIL
SDFS3_PATH_COMPONENT_PARSE:
        ldx     ARG2_PTR
        ldab    ARG2_LEN
        jsr     SDFS3_PARSE_FILENAME_83
        bcs     SDFS3_PATH_COMPONENT_FAIL
        clc
        rts
SDFS3_PATH_COMPONENT_FAIL:
        sec
        rts

SDFS3_PATH_SKIP_TRAILING:
        tst     PATH_LEN
        beq     SDFS3_PATH_SKIP_TRAILING_OK
        ldx     PATH_PTR
        ldaa    0,x
        cmpa    #CHR_SPACE
        bne     SDFS3_PATH_SKIP_TRAILING_FAIL
        inx
        stx     PATH_PTR
        dec     PATH_LEN
        bra     SDFS3_PATH_SKIP_TRAILING
SDFS3_PATH_SKIP_TRAILING_OK:
        clc
        rts
SDFS3_PATH_SKIP_TRAILING_FAIL:
        sec
        rts

SDFS3_FIND_IN_CUR:
        jsr     FAT_CLUSTER_TO_SD_LBA
        bcs     SDFS3_FIND_IN_CUR_FAIL
        ldx     #SD_SECTOR_BUF
        jsr     SD_READ_SECTOR
        bcs     SDFS3_FIND_IN_CUR_SD_FAIL
        ldx     #SD_SECTOR_BUF
        stx     FAT_ENTRY_PTR
        ldaa    #16
        staa    FAT_DIR_COUNT
SDFS3_FIND_IN_CUR_ENTRY_LOOP:
        ldx     FAT_ENTRY_PTR
        ldaa    0,x
        beq     SDFS3_FIND_IN_CUR_FAIL
        cmpa    #$E5
        beq     SDFS3_FIND_IN_CUR_NEXT_ENTRY
        ldaa    11,x
        anda    #$0F
        cmpa    #$0F
        beq     SDFS3_FIND_IN_CUR_NEXT_ENTRY
        ldaa    11,x
        bita    #$08
        bne     SDFS3_FIND_IN_CUR_NEXT_ENTRY
        jsr     FAT_COMPARE_ENTRY_NAME
        bcc     SDFS3_FIND_IN_CUR_MATCH
SDFS3_FIND_IN_CUR_NEXT_ENTRY:
        jsr     FAT_ADVANCE_ENTRY_PTR
        dec     FAT_DIR_COUNT
        bne     SDFS3_FIND_IN_CUR_ENTRY_LOOP
        jsr     FAT32_NEXT_CLUSTER
        bcs     SDFS3_FIND_IN_CUR_NEXT_DONE_OR_FAIL
        jsr     FAT_COPY_NEXT_TO_CUR
        bra     SDFS3_FIND_IN_CUR
SDFS3_FIND_IN_CUR_NEXT_DONE_OR_FAIL:
        ldaa    FAT_ERROR
        bne     SDFS3_FIND_IN_CUR_FAIL
        bra     SDFS3_FIND_IN_CUR_FAIL
SDFS3_FIND_IN_CUR_MATCH:
        jsr     FAT_STORE_FILE_ENTRY
        clc
        rts
SDFS3_FIND_IN_CUR_SD_FAIL:
        ldaa    #FAT_ERR_SD
        staa    FAT_ERROR
SDFS3_FIND_IN_CUR_FAIL:
        sec
        rts

SDFS3_ENTRY_IS_DIR:
        ldx     FAT_ENTRY_PTR
        ldaa    11,x
        bita    #$10
        beq     SDFS3_ENTRY_IS_DIR_FAIL
        clc
        rts
SDFS3_ENTRY_IS_DIR_FAIL:
        sec
        rts

SDFS3_ENTRY_IS_FILE:
        ldx     FAT_ENTRY_PTR
        ldaa    11,x
        bita    #$18
        bne     SDFS3_ENTRY_IS_FILE_FAIL
        clc
        rts
SDFS3_ENTRY_IS_FILE_FAIL:
        sec
        rts

SDFS3_PARSE_FILENAME_83:
        stx     ARG_PTR
        stab    ARG_LEN
        jsr     SDFS3_CLEAR_FIND_NAME
SDFS3_PARSE_FILENAME_SKIP_HEAD:
        tst     ARG_LEN
        bne     SDFS3_PARSE_FILENAME_SKIP_HAS
        jmp     SDFS3_PARSE_FILENAME_FAIL
SDFS3_PARSE_FILENAME_SKIP_HAS:
        ldx     ARG_PTR
        ldaa    0,x
        cmpa    #CHR_SPACE
        bne     SDFS3_PARSE_FILENAME_NAME_START
        inx
        stx     ARG_PTR
        dec     ARG_LEN
        bra     SDFS3_PARSE_FILENAME_SKIP_HEAD
SDFS3_PARSE_FILENAME_NAME_START:
        ldx     #FAT_FIND_NAME0
        stx     FAT_ENTRY_PTR
        clr     ARG2_LEN
SDFS3_PARSE_FILENAME_NAME_LOOP:
        tst     ARG_LEN
        beq     SDFS3_PARSE_FILENAME_NAME_DONE
        ldx     ARG_PTR
        ldaa    0,x
        cmpa    #CHR_SPACE
        bne     SDFS3_PARSE_FILENAME_NAME_NOT_SPACE
        jmp     SDFS3_PARSE_FILENAME_TRAILING
SDFS3_PARSE_FILENAME_NAME_NOT_SPACE:
        cmpa    #'.'
        bne     SDFS3_PARSE_FILENAME_NAME_NOT_DOT
        jmp     SDFS3_PARSE_FILENAME_EXT_START
SDFS3_PARSE_FILENAME_NAME_NOT_DOT:
        ldab    ARG2_LEN
        cmpb    #8
        blo     SDFS3_PARSE_FILENAME_NAME_ROOM
        jmp     SDFS3_PARSE_FILENAME_FAIL
SDFS3_PARSE_FILENAME_NAME_ROOM:
        jsr     SDFS3_TO_UPPER
        ldx     FAT_ENTRY_PTR
        staa    0,x
        inx
        stx     FAT_ENTRY_PTR
        inc     ARG2_LEN
        ldx     ARG_PTR
        inx
        stx     ARG_PTR
        dec     ARG_LEN
        bra     SDFS3_PARSE_FILENAME_NAME_LOOP
SDFS3_PARSE_FILENAME_NAME_DONE:
        tst     ARG2_LEN
        bne     SDFS3_PARSE_FILENAME_NAME_OK
        jmp     SDFS3_PARSE_FILENAME_FAIL
SDFS3_PARSE_FILENAME_NAME_OK:
        jmp     SDFS3_PARSE_FILENAME_OK
SDFS3_PARSE_FILENAME_EXT_START:
        tst     ARG2_LEN
        bne     SDFS3_PARSE_FILENAME_EXT_NAME_OK
        jmp     SDFS3_PARSE_FILENAME_FAIL
SDFS3_PARSE_FILENAME_EXT_NAME_OK:
        ldx     ARG_PTR
        inx
        stx     ARG_PTR
        dec     ARG_LEN
        ldx     #FAT_FIND_NAME8
        stx     FAT_ENTRY_PTR
        clr     ARG2_LEN
SDFS3_PARSE_FILENAME_EXT_LOOP:
        tst     ARG_LEN
        bne     SDFS3_PARSE_FILENAME_EXT_HAS_LEN
        jmp     SDFS3_PARSE_FILENAME_OK
SDFS3_PARSE_FILENAME_EXT_HAS_LEN:
        ldx     ARG_PTR
        ldaa    0,x
        cmpa    #CHR_SPACE
        bne     SDFS3_PARSE_FILENAME_EXT_NOT_SPACE
        jmp     SDFS3_PARSE_FILENAME_TRAILING
SDFS3_PARSE_FILENAME_EXT_NOT_SPACE:
        cmpa    #'.'
        bne     SDFS3_PARSE_FILENAME_EXT_CHAR_OK
        jmp     SDFS3_PARSE_FILENAME_FAIL
SDFS3_PARSE_FILENAME_EXT_CHAR_OK:
        ldab    ARG2_LEN
        cmpb    #3
        blo     SDFS3_PARSE_FILENAME_EXT_ROOM
        jmp     SDFS3_PARSE_FILENAME_FAIL
SDFS3_PARSE_FILENAME_EXT_ROOM:
        jsr     SDFS3_TO_UPPER
        ldx     FAT_ENTRY_PTR
        staa    0,x
        inx
        stx     FAT_ENTRY_PTR
        inc     ARG2_LEN
        ldx     ARG_PTR
        inx
        stx     ARG_PTR
        dec     ARG_LEN
        bra     SDFS3_PARSE_FILENAME_EXT_LOOP
SDFS3_PARSE_FILENAME_TRAILING:
        ldx     ARG_PTR
        inx
        stx     ARG_PTR
        dec     ARG_LEN
SDFS3_PARSE_FILENAME_TRAILING_LOOP:
        tst     ARG_LEN
        beq     SDFS3_PARSE_FILENAME_OK
        ldx     ARG_PTR
        ldaa    0,x
        cmpa    #CHR_SPACE
        beq     SDFS3_PARSE_FILENAME_TRAILING_SPACE_OK
        jmp     SDFS3_PARSE_FILENAME_FAIL
SDFS3_PARSE_FILENAME_TRAILING_SPACE_OK:
        inx
        stx     ARG_PTR
        dec     ARG_LEN
        bra     SDFS3_PARSE_FILENAME_TRAILING_LOOP
SDFS3_PARSE_FILENAME_OK:
        clc
        rts
SDFS3_PARSE_FILENAME_FAIL:
        sec
        rts

SDFS3_CLEAR_FIND_NAME:
        ldx     #FAT_FIND_NAME0
        ldab    #11
SDFS3_CLEAR_FIND_NAME_LOOP:
        ldaa    #CHR_SPACE
        staa    0,x
        inx
        decb
        bne     SDFS3_CLEAR_FIND_NAME_LOOP
        rts

SDFS3_PRINT_HEX8:
        psha
        lsra
        lsra
        lsra
        lsra
        bsr     SDFS3_PRINT_NIBBLE
        pula
        bsr     SDFS3_PRINT_NIBBLE
        rts

SDFS3_PRINT_NIBBLE:
        anda    #$0F
        adda    #'0'
        cmpa    #'9'+1
        blo     SDFS3_PRINT_NIBBLE_OUT
        adda    #7
SDFS3_PRINT_NIBBLE_OUT:
        jmp     SDFS3_PUTC

SDFS3_PRINT:
        ldaa    0,x
        beq     SDFS3_PRINT_DONE
        jsr     SDFS3_PUTC
        inx
        bra     SDFS3_PRINT
SDFS3_PRINT_DONE:
        rts

SDFS3_PUTC:
        psha
        jsr     MIKBUG_OUTCH
        pula
        cmpa    #CHR_CR
        bne     SDFS3_PUTC_DONE
        ldaa    #CHR_LF
        jsr     MIKBUG_OUTCH
SDFS3_PUTC_DONE:
        rts

SDFS3_NOT_FOUND:
        ldaa    #SDFS3_ERR_NOT_FOUND
        bra     SDFS3_FAIL_A
SDFS3_FAT_FAIL:
        ldaa    #SDFS3_ERR_IO
SDFS3_FAIL_A:
        staa    SDFS3_LAST_ERROR
        sec
        rts

FAT32_INCLUDE_FIND_API equ 1
FAT32_INCLUDE_FILE_API equ 1

; SD ドライバは持たず、ROM の BIOS 入口を呼ぶ(#310 の 1-6、決定 8)。変数 SD_* は ROM と共通。
SD_INIT          equ BIOS_SD_INIT
SD_READ_SECTOR   equ BIOS_SD_READ
        include "fat32.asm"

SDFS3_END:
        if SDFS3_END-1 > USER_RAM_END
        error   "SDFS/68 v3 core exceeds USER_RAM_END"
        endif
        end
