; MIKBUG compatible console entry points used by BASIC
;
; INEEE
;   Returns: A = received character
;   Behavior: echoes the received character via OUTEEE
;
; OUTEEE
;   Input: A = character to output
;   Behavior: outputs CR as CR/LF on the serial console
