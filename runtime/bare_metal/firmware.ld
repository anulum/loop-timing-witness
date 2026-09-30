/* SPDX-License-Identifier: AGPL-3.0-or-later
 * Commercial license available
 * © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
 * © Code 2020–2026 Miroslav Šotek. All rights reserved.
 * ORCID: 0009-0009-3560-0851
 * Contact: www.anulum.li | protoscience@anulum.li
 * Loop Timing Witness — explicitly reserved firmware memory and integer stack
 */
OUTPUT_ARCH(riscv)
ENTRY(_start)
/* The image builder must supply all three symbols from the admitted platform. */
MEMORY {
    ram (rwx) : ORIGIN = __witness_ram_origin, LENGTH = __witness_ram_length
}
PHDRS { text PT_LOAD FLAGS(5); data PT_LOAD FLAGS(6); }
SECTIONS {
    .text : { KEEP(*(.text.start)) *(.text .text.*) } > ram :text
    .rodata : { *(.rodata .rodata.*) } > ram :text
    .data ALIGN(4096) : {
        __global_pointer$ = . + 0x800;
        *(.data .data.* .sdata .sdata.*)
    } > ram :data
    /* Only the ISA test image supplies HTIF; board completion parks the hart. */
    .tohost ALIGN(64) : { *(.tohost) } > ram :data
    .bss (NOLOAD) : ALIGN(8) {
        __bss_start = .;
        *(.bss .bss.* .sbss .sbss.* COMMON)
        . = ALIGN(8);
        __bss_end = .;
    } > ram :data
    .stack (NOLOAD) : ALIGN(16) {
        . += __witness_stack_size;
        __stack_top = .;
    } > ram :data
    /* No hosted unwinder or build-id orphan may overlap a loadable segment. */
    /DISCARD/ : { *(.comment .note.* .eh_frame .eh_frame.*) }
}
ASSERT(__witness_ram_origin % 4096 == 0, "firmware region must be page aligned")
ASSERT(__witness_ram_length > 0, "firmware region must be nonempty")
ASSERT(__witness_stack_size >= 4096 && __witness_stack_size % 16 == 0,
       "firmware stack must be at least 4096 bytes and 16-byte aligned")
ASSERT(_start == __witness_ram_origin, "firmware entry must begin the reserved region")
ASSERT(__stack_top <= __witness_ram_origin + __witness_ram_length,
       "firmware and stack exceed the reserved region")
