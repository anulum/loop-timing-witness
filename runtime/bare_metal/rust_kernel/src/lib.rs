// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — audited pointer boundary for the safe Rust controller

//! Freestanding C ABI implementations backed by the maintained safe Rust kernel.
//! Callers supply live aligned C allocations and reset PID state before its first step.
//! Input values are copied before output writes; rejected coefficients leave outputs unchanged.
#![cfg_attr(not(test), no_std)]

use witness_controller::{Coefficients, Command, PidState, lqr_step};

const _: () = {
    assert!(core::mem::size_of::<Coefficients>() == 44);
    assert!(core::mem::size_of::<PidState>() == 16);
    assert!(core::mem::size_of::<Command>() == 20);
    assert!(core::mem::align_of::<Coefficients>() == 4);
    assert!(core::mem::align_of::<PidState>() == 4);
    assert!(core::mem::align_of::<Command>() == 4);
};

/// Validate the original C coefficient value through the safe Rust API.
///
/// # Safety
/// `coefficients` must point to an aligned, initialised readable C coefficient allocation.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn witness_coefficients_valid(coefficients: *const Coefficients) -> bool {
    // SAFETY: the caller provides the readable C allocation required above.
    let coefficients = unsafe { coefficients.read() };
    coefficients.validate().is_ok()
}

/// Initialise all PID memory, including a previously uninitialised C allocation.
///
/// # Safety
/// `state` must point to aligned writable storage for one complete PID state.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn witness_pid_reset(state: *mut PidState) {
    // SAFETY: write initialises the complete caller-owned allocation without reading it.
    unsafe { state.write(PidState::default()) };
}

/// Compute PID with exact C state/output ownership and unchanged refusal semantics.
///
/// # Safety
/// Inputs must be aligned readable initialised C allocations. `state` must have been reset
/// and must be writable; `command` must be aligned writable storage for a complete command.
/// No other thread or interrupt may access these allocations during the call.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn witness_pid_step(
    coefficients: *const Coefficients,
    state: *mut PidState,
    cycle: u32,
    reference: i32,
    position: i32,
    command: *mut Command,
) -> bool {
    // SAFETY: copy the readable inputs before creating any output, avoiding overlapping borrows.
    let coefficients = unsafe { coefficients.read() };
    // SAFETY: the caller owns one initialised state for this entire invocation.
    let mut current = unsafe { state.read() };
    let Ok(result) = current.step(&coefficients, cycle, reference, position) else {
        return false;
    };
    // SAFETY: the caller supplies complete writable allocations, including uninitialised output.
    unsafe {
        state.write(current);
        command.write(result);
    }
    true
}

/// Compute LQR through the safe Rust API and write only a successfully computed command.
///
/// # Safety
/// `coefficients` must be an aligned readable initialised C allocation. `command` must be
/// aligned writable storage for a complete command. Neither may be concurrently accessed.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn witness_lqr_step(
    coefficients: *const Coefficients,
    cycle: u32,
    reference: i32,
    position: i32,
    velocity: i32,
    command: *mut Command,
) -> bool {
    // SAFETY: copying the caller-owned readable value ends input access before any output write.
    let coefficients = unsafe { coefficients.read() };
    let Ok(result) = lqr_step(&coefficients, cycle, reference, position, velocity) else {
        return false;
    };
    // SAFETY: write initialises the complete caller-owned command without reading it.
    unsafe { command.write(result) };
    true
}

#[cfg(not(test))]
unsafe extern "C" {
    /// Stop IRQ service and publish the original firmware's terminal panic refusal.
    fn witness_amp_rust_panic() -> !;
}

#[cfg(not(test))]
#[panic_handler]
fn panic(_: &core::panic::PanicInfo<'_>) -> ! {
    // SAFETY: the linked platform provides this nonreturning C refusal entry.
    unsafe { witness_amp_rust_panic() }
}
