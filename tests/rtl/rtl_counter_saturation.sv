// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — original 32-bit counter saturation through public ports
module rtl_counter_saturation #(parameter int OVERFLOW_COUNTER_BITS = 32) (
 input logic clock, reset_n,
 input logic enable, sample_read, actuator_write, freeze_actuator, safe_interrupt, trip_now, injected,
 input logic [31:0] stop_after_cycle, command_cycle,
 input logic signed [31:0] command_value,
 input logic monitor_start, monitor_deadline, monitor_write,
 input logic event_valid, drain_request,
 input logic [7:0] event_code,
 input logic [31:0] event_cycle,
 output logic finished [6], sample_tick [6], deadline [6], timely_write [6], sample_valid [6],
 output logic [31:0] cycle_number [6], sample_cycle [6], late_commands [6],
 output logic signed [31:0] actuator_value [6], plant_actuator [6],
 output logic [7:0] event_mask [6],
 output logic [255:0] event_cycles [6],
 output logic monitor_trip [3], monitor_safe [3],
 output logic [31:0] total_misses [3], consecutive_misses [3],
 output logic capture_active, buffer_full, event_dropped, overflowed, drain_valid, drain_empty,
 output logic [63:0] counter_ticks,
 output logic [31:0] overflow_count,
 output logic [127:0] drain_record
);
 for(genvar i=0;i<6;i=i+1) begin : cycles
  localparam logic [31:0] PERIOD=i==0?100000:i==1?64:i==2?256:i==3?512:i==4?16384:32768;
  control_cycle #(.PERIOD_TICKS(PERIOD)) dut (
   .capture_clock(clock),.reset_n(reset_n),.enable(enable),.stop_after_cycle(stop_after_cycle),
   .sample_read(sample_read),.actuator_write(actuator_write),.command_cycle(command_cycle),.command_value(command_value),
   .freeze_actuator(freeze_actuator),.safe_interrupt(safe_interrupt),.trip_now(trip_now),.injected(injected),
   .finished(finished[i]),.sample_tick(sample_tick[i]),.deadline(deadline[i]),.timely_write(timely_write[i]),.sample_valid(sample_valid[i]),
   .cycle_number(cycle_number[i]),.sample_cycle(sample_cycle[i]),.late_commands(late_commands[i]),
   .actuator_value(actuator_value[i]),.plant_actuator(plant_actuator[i]),.event_mask(event_mask[i]),.event_cycles(event_cycles[i])
  );
 end
 for(genvar i=0;i<3;i=i+1) begin : monitors
  localparam logic [31:0] LIMIT=i==0?3:i==1?1:2;
  deadline_monitor #(.MISS_LIMIT(LIMIT)) dut (
   .clock(clock),.reset_n(reset_n),.cycle_start(monitor_start),.deadline(monitor_deadline),.timely_write(monitor_write),
   .trip_now(monitor_trip[i]),.safe_latched(monitor_safe[i]),.total_misses(total_misses[i]),.consecutive_misses(consecutive_misses[i])
  );
 end
 event_witness #(.ADDRESS_BITS(3),.OVERFLOW_COUNTER_BITS(OVERFLOW_COUNTER_BITS)) events (
  .capture_clock(clock),.drain_clock(clock),.run_reset_n(reset_n),.event_valid(event_valid),.event_code(event_code),.cycle_number(event_cycle),
  .capture_active(capture_active),.counter_ticks(counter_ticks),.buffer_full(buffer_full),.event_dropped(event_dropped),.overflowed(overflowed),.overflow_count(overflow_count),
  .drain_request(drain_request),.drain_valid(drain_valid),.drain_record(drain_record),.drain_empty(drain_empty)
 );
endmodule
