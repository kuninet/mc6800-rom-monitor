#ifndef _XC_H
#define _XC_H

/* include CCI features.  */
#include <cci.h>

/* include device header file.  */
#include <avr/io.h>

/* define ei and di macros to enable/ disable interrupt respectively.  */
#ifndef ei
#define ei()  __asm__ __volatile__ ("sei" ::: "memory")
#endif

#ifndef di
#define di()  __asm__ __volatile__ ("cli" ::: "memory")
#endif

#endif

