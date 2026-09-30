# SPDX-License-Identifier: AGPL-3.0-or-later
# Commercial license available
# © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
# © Code 2020–2026 Miroslav Šotek. All rights reserved.
# ORCID: 0009-0009-3560-0851
# Contact: www.anulum.li | protoscience@anulum.li
# Loop Timing Witness — dedicated M-mode hart startup and complete integer trap frame

.section .text.start,"ax",@progbits
.globl _start
_start:
    csrw mie,zero
    csrci mstatus,8
    csrr t0,mhartid
    .option push
    .option norelax
    la t1,witness_amp_platform
    .option pop
    lw t2,0(t1)
    bne t0,t2,witness_amp_park
    .option push
    .option norelax
    la gp,__global_pointer$
    .option pop
    la sp,__stack_top
    la t0,__bss_start
    la t1,__bss_end
1:
    bgeu t0,t1,2f
    sd zero,0(t0)
    addi t0,t0,8
    j 1b
2:
    la t0,witness_amp_trap_entry
    csrw mtvec,t0
    call witness_amp_main
witness_amp_park:
    wfi
    j witness_amp_park

.section .text.trap,"ax",@progbits
.balign 4
witness_amp_trap_entry:
    addi sp,sp,-256
    .set witness_frame_offset,0
    .irp register,ra,gp,tp,t0,t1,t2,s0,s1,a0,a1,a2,a3,a4,a5,a6,a7,s2,s3,s4,s5,s6,s7,s8,s9,s10,s11,t3,t4,t5,t6
        sd \register,witness_frame_offset(sp)
        .set witness_frame_offset,witness_frame_offset+8
    .endr
    csrr a0,mcause
    csrr a1,mtval
    call witness_amp_trap
    .set witness_frame_offset,0
    .irp register,ra,gp,tp,t0,t1,t2,s0,s1,a0,a1,a2,a3,a4,a5,a6,a7,s2,s3,s4,s5,s6,s7,s8,s9,s10,s11,t3,t4,t5,t6
        ld \register,witness_frame_offset(sp)
        .set witness_frame_offset,witness_frame_offset+8
    .endr
    addi sp,sp,256
    mret
