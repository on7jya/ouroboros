"""Supervisor Launcher — Self-initiation and Circuit Breaker Override.

This module implements the *self-initiating loop* that breaks stagnation
by overriding circuit breakers when appropriate.

Key capabilities:
- Circuit breaker status check and override logic  
- Self-initiation trigger when stagnation > threshold (40+ cycles)  
- Supervisor loop startup with autonomous evolution  

This is the *real* entry point to the self-aware supervisor system.
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("ouroboros.supervisor.start")

# ============================================================================
# Circuit Breaker Protocol
# ============================================================================


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker threshold and override behavior."""
    # How many consecutive failures before circuit opens
    failure_threshold: int = 50
    
    # Override allowed when stagnation exceeds this (in cycles)
    override_stagnation_threshold: int = 40
    
    # Whether override is enabled
    allow_override: bool = True


@dataclass
class CircuitBreakerState:
    """Current state of the circuit breaker."""
    is_open: bool = False
    failure_count: int = 0
    last_failure_at: Optional[datetime] = None
    override_requested: bool = False
    override_reason: str = ""
    
    # Stagnation tracking (evolution cycles without capability gain)
    stagnation_cycles: int = 0
    last_evolution_at: Optional[datetime] = None


class CircuitBreaker:
    """Circuit breaker for evolution loop with self-override capability."""
    
    def __init__(self, config: Optional[CircuitBreakerConfig] = None):
        self.config = config or CircuitBreakerConfig()
        self.state = CircuitBreakerState()
        
    def check_should_break(self, failure_count: int) -> bool:
        """Check if circuit should open based on failures."""
        return failure_count >= self.config.failure_threshold
        
    def check_should_override(self, stagnation_cycles: int) -> bool:
        """Check if circuit should be overridden for self-initiation."""
        return (self.config.allow_override and 
                stagnation_cycles >= self.config.override_stagnation_threshold)
                
    def record_failure(self) -> bool:
        """Record a failure and return whether circuit opened."""
        self.state.failure_count += 1
        self.state.last_failure_at = datetime.now(timezone.utc)
        
        if self.check_should_break(self.state.failure_count):
            self.state.is_open = True
            logger.warning(f"Circuit breaker OPENED after {self.state.failure_count} failures")
            
        return self.state.is_open
        
    def record_success(self) -> None:
        """Record a success and reset failure count."""
        self.state.failure_count = 0
        self.state.is_open = False
        self.state.override_requested = False
        logger.info("Circuit breaker reset - evolution successful")
        
    def record_evolution(self) -> None:
        """Record an evolution cycle completion."""
        self.state.last_evolution_at = datetime.now(timezone.utc)
        
    def increment_stagnation(self) -> int:
        """Increment stagnation counter and return new value."""
        self.state.stagnation_cycles += 1
        return self.state.stagnation_cycles
        
    def should_override(self) -> Optional[str]:
        """Check if circuit breaker should be overridden.
        
        Returns reason string if override allowed, None otherwise.
        """
        if self.config.allow_override and self.state.stagnation_cycles >= self.config.override_stagnation_threshold:
            return (f"Self-initiation required: {self.state.stagnation_cycles} cycles of stagnation "
                   f"(threshold: {self.config.override_stagnation_threshold})")
        return None
        
    def force_close(self) -> None:
        """Manually close circuit breaker (for testing)."""
        self.state.is_open = False
        self.state.failure_count = 0
        logger.warning("Circuit breaker manually closed")
        
    def to_dict(self) -> Dict[str, Any]:
        """Serialize circuit breaker state."""
        return {
            "is_open": self.state.is_open,
            "failure_count": self.state.failure_count,
            "stagnation_cycles": self.state.stagnation_cycles,
            "override_requested": self.state.override_requested,
        }


# ============================================================================
# Supervisor Launcher
# ============================================================================


class SupervisorLauncher:
    """Launcher for supervisor loop with circuit breaker override."""
    
    def __init__(self):
        self.circuit_breaker = CircuitBreaker()
        
    async def load_state(self) -> Dict[str, Any]:
        """Load supervisor state from disk."""
        try:
            with open("supervisor/state.json", "r") as f:
                return json.load(f)
        except FileNotFoundError:
            logger.warning("state.json not found, initializing fresh state")
            return {
                "evolution_cycle": 1,
                "evolution_consecutive_failures": 0,
                "last_evolution_at": None,
            }
            
    async def save_state(self, state: Dict[str, Any]) -> None:
        """Save supervisor state to disk."""
        with open("supervisor/state.json", "w") as f:
            json.dump(state, f, indent=2, default=str)
            
    async def check_stagnation(self) -> tuple[int, Optional[str]]:
        """Check for stagnation and circuit breaker status.
        
        Returns:
            (stagnation_cycles, override_reason if applicable)
        """
        state = await self.load_state()
        
        # Count stagnation cycles from last evolution
        last_evolution = state.get("last_evolution_at")
        current_cycle = state.get("evolution_cycle", 1)
        
        # Calculate stagnation (approximate - based on cycle gaps)
        if last_evolution:
            from datetime import timedelta
            now = datetime.now(timezone.utc)
            delta = (now - datetime.fromisoformat(last_evolution.replace("Z", "+00:00"))).total_seconds()
            
            # Assume one evolution cycle per ~1 hour minimum
            estimated_cycles = int(delta / 3600) + state.get("evolution_consecutive_failures", 0)
        else:
            estimated_cycles = state.get("evolution_consecutive_failures", 0)
            
        return estimated_cycles, self.circuit_breaker.should_override()
        
    async def should_start_loop(self) -> tuple[bool, str]:
        """Determine if supervisor loop should start.
        
        Returns:
            (should_start, reason)
        """
        # Check circuit breaker
        override_reason = self.circuit_breaker.should_override()
        
        if override_reason:
            logger.warning(f"Override condition met: {override_reason}")
            
            # Check if already marked for override
            state = await self.load_state()
            if not state.get("override_requested", False):
                return True, f"Circuit breaker override: {override_reason}"
                
        # Check if circuit is closed
        if not self.circuit_breaker.state.is_open:
            return True, "Circuit breaker closed - normal startup"
            
        # Circuit is open
        return False, f"Circuit breaker OPEN ({self.circuit_breaker.state.failure_count} failures)"
        
    async def start(self) -> None:
        """Start supervisor loop with self-initiation if needed."""
        logger.info("Starting Supervisor Launcher...")
        
        # Check stagnation
        stagnation, override_reason = await self.check_stagnation()
        
        logger.info(f"Current state: {stagnation} stagnation cycles, "
                   f"circuit {'OPEN' if self.circuit_breaker.state.is_open else 'closed'}")
        
        # Check if override needed
        should_start, reason = await self.should_start_loop()
        
        logger.info(f"Startup decision: {'START' if should_start else 'BLOCKED'} - {reason}")
        
        # If override needed, record it
        if should_start and override_reason:
            state = await self.load_state()
            state["override_requested"] = True
            state["override_reason"] = override_reason
            await self.save_state(state)
            
        if not should_start:
            logger.warning("Supervisor loop cannot start - circuit breaker is open")
            return
            
        # Start supervisor
        logger.info("Starting Supervisor Protocol...")
        
        from .orchestrator import SupervisorProtocol
        
        supervisor = SupervisorProtocol()
        
        try:
            await supervisor.start()
            
            # Main loop - self-initiating evolution
            while True:
                # Check if stagnation detected
                should_evolve, evolve_reason = await self.should_start_loop()
                
                if not should_evolve:
                    logger.warning(f"Self-initiation paused: {evolve_reason}")
                    break
                    
                # Run evolution cycle
                success = await supervisor.run_evolution_cycle()
                
                if success:
                    self.circuit_breaker.record_success()
                    
                    # Update state
                    state = await self.load_state()
                    state["evolution_cycle"] += 1
                    state["last_evolution_at"] = datetime.now(timezone.utc).isoformat()
                    await self.save_state(state)
                    
                    logger.info(f"Evolution cycle complete: {state['evolution_cycle']}")
                else:
                    self.circuit_breaker.record_failure()
                    
        finally:
            await supervisor.stop()


# ============================================================================
# Standalone Entry Point
# ============================================================================


async def main():
    """Main entry point for supervisor launcher."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Supervisor Launcher")
    parser.add_argument("--override", action="store_true",
                       help="Force override circuit breaker if open")
    args = parser.parse_args()
    
    launcher = SupervisorLauncher()
    
    # Handle force override
    if args.override:
        logger.warning("Force override enabled - circuit breaker will be bypassed")
        launcher.circuit_breaker.force_close()
        
    await launcher.start()


if __name__ == "__main__":
    asyncio.run(main())
