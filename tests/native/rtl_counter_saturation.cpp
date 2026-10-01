// SPDX-License-Identifier: AGPL-3.0-or-later
// Commercial license available
// © Concepts 1996–2026 Miroslav Šotek. All rights reserved.
// © Code 2020–2026 Miroslav Šotek. All rights reserved.
// ORCID: 0009-0009-3560-0851
// Contact: www.anulum.li | protoscience@anulum.li
// Loop Timing Witness — original 32-bit counter saturation through public ports
#include "Vrtl_counter_saturation.h"
#include "verilated.h"
#include "verilated_cov.h"
#include <algorithm>
#include <chrono>
#include <cstdint>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
static void require(bool passed,const char *message){if(!passed)throw std::runtime_error(message);}
int main(int argc,char **argv){
 require(argc==3,"expected tick count and coverage destination");
 const std::uint64_t steps=std::stoull(argv[1]);
 require(steps>0 && steps<=0x100000100ULL,"bounded original32bit run");
 VerilatedContext context; context.commandArgs(argc,argv); Vrtl_counter_saturation model{&context};
 model.clock=0;model.reset_n=0;model.enable=0;model.sample_read=0;model.actuator_write=0;model.freeze_actuator=0;model.safe_interrupt=0;model.trip_now=0;model.injected=0;
 model.stop_after_cycle=0xffffffffU;model.command_cycle=0xffffffffU;model.command_value=7;
 model.monitor_start=0;model.monitor_deadline=0;model.monitor_write=0;model.event_valid=0;model.drain_request=0;model.event_code=1;model.event_cycle=0;
 const auto tick=[&](){model.clock=0;model.eval();model.clock=1;model.eval();};
 tick();model.reset_n=1;model.enable=1;model.event_valid=1;
 for(unsigned i=0;i<32;++i)tick();
 require(model.capture_active && model.buffer_full && model.event_dropped,"real FIFO filled and dropping");
 const std::uint32_t overflow_baseline=model.overflow_count;
 require(overflow_baseline>0,"warmup produced real overflow");
 for(unsigned i=0;i<6;++i)require(model.late_commands[i]==0 && !model.finished[i],"original cycles warmup");
 for(unsigned i=0;i<3;++i)require(model.total_misses[i]==0 && model.consecutive_misses[i]==0,"original monitor warmup");
 model.actuator_write=1;model.monitor_deadline=1;
 const auto started=std::chrono::steady_clock::now();
 const auto check=[&](std::uint64_t completed){
  const auto expected=static_cast<std::uint32_t>(std::min<std::uint64_t>(completed,0xffffffffULL));
  for(unsigned i=0;i<6;++i)require(model.late_commands[i]==expected && !model.finished[i],"real32bit late counter diverged");
  for(unsigned i=0;i<3;++i)require(model.total_misses[i]==expected && model.consecutive_misses[i]==expected && model.monitor_safe[i],"real32bit miss counters diverged");
  require(model.overflow_count==std::min<std::uint64_t>(static_cast<std::uint64_t>(overflow_baseline)+completed,0xffffffffULL),"real32bit overflow diverged");
  const auto seconds=std::chrono::duration<double>(std::chrono::steady_clock::now()-started).count();
  context.coveragep()->write((std::string(argv[2])+".at-"+std::to_string(completed)).c_str());
  std::cout<<"CHECK steps="<<completed<<" late="<<model.late_commands[0]<<" misses="<<model.total_misses[0]<<" overflow="<<model.overflow_count<<" seconds="<<seconds<<std::endl;
 };
 for(std::uint64_t i=1;i<=steps;++i){tick();if(i==0x7fffffffULL || i==0xfffffffeULL || i==0xffffffffULL || i==0x100000000ULL || i==steps)check(i);}
 const auto seconds=std::chrono::duration<double>(std::chrono::steady_clock::now()-started).count();
 const bool saturated=steps>0xffffffffULL;
 std::cout<<"PUBLIC32_PASS steps="<<steps<<" saturated="<<saturated<<" seconds="<<seconds<<" overflow_baseline="<<overflow_baseline<<std::endl;
 model.reset_n=0;tick();
 for(unsigned i=0;i<6;++i)require(model.late_commands[i]==0,"late reset");
 for(unsigned i=0;i<3;++i)require(model.total_misses[i]==0 && model.consecutive_misses[i]==0 && !model.monitor_safe[i],"miss reset");
 require(model.overflow_count==0 && !model.overflowed,"event reset");
 model.final();context.coveragep()->write(argv[2]);return 0;
}
