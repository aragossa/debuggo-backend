"""
TestGenerationStateMachine: State machine for test generation workflow.

Manages the lifecycle of test generation with states:
- INIT: Initialize
- ANALYZE: Analyze requirements
- PLAN: Create execution plan
- GENERATE: Generate test step
- VALIDATE: Validate step
- EXECUTE: Run step and get feedback
- LEARN: Update patterns and confidence
- NEXT_STEP: Decide if more steps needed
- COMPLETE: Test generation complete

This ensures consistent, predictable test generation flow.
"""

import json
import logging
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class State(Enum):
    """Test generation states."""
    INIT = "INIT"
    ANALYZE = "ANALYZE"
    PLAN = "PLAN"
    GENERATE = "GENERATE"
    VALIDATE = "VALIDATE"
    EXECUTE = "EXECUTE"
    LEARN = "LEARN"
    NEXT_STEP = "NEXT_STEP"
    COMPLETE = "COMPLETE"
    ERROR = "ERROR"


class Event(Enum):
    """State transition events."""
    ANALYZE = "analyze"
    PLAN = "plan"
    GENERATE = "generate"
    VALIDATE = "validate"
    EXECUTE = "execute"
    LEARN = "learn"
    NEXT = "next"
    COMPLETE = "complete"
    REGENERATE = "regenerate"
    RETRY = "retry"
    ERROR = "error"


@dataclass
class StateContext:
    """Context maintained across state transitions."""
    test_case_id: int
    current_state: State
    previous_state: Optional[State]
    step_number: int
    total_steps: int
    confidence: float
    error_count: int
    retry_count: int
    context_data: Dict[str, Any]
    history: List[Dict[str, Any]]
    created_at: datetime = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()


class TestGenerationStateMachine:
    """State machine for test generation."""

    def __init__(self, test_case_id: int):
        self.test_case_id = test_case_id
        self.state = State.INIT
        self.context = StateContext(
            test_case_id=test_case_id,
            current_state=State.INIT,
            previous_state=None,
            step_number=0,
            total_steps=0,
            confidence=0.0,
            error_count=0,
            retry_count=0,
            context_data={},
            history=[]
        )
        self.logger = logging.getLogger(__name__)

        # State transition table
        self.transitions = {
            State.INIT: {
                Event.ANALYZE: State.ANALYZE,
            },
            State.ANALYZE: {
                Event.PLAN: State.PLAN,
                Event.ERROR: State.ERROR,
            },
            State.PLAN: {
                Event.GENERATE: State.GENERATE,
                Event.ERROR: State.ERROR,
            },
            # NEXT from the middle of a step: the step ended without LEARN (a duplicate that was
            # skipped, a step fixed by error recovery, a step that could not be made to pass)
            State.GENERATE: {
                Event.VALIDATE: State.VALIDATE,
                Event.NEXT: State.NEXT_STEP,
                Event.ERROR: State.ERROR,
            },
            State.VALIDATE: {
                Event.EXECUTE: State.EXECUTE,
                Event.REGENERATE: State.GENERATE,
                Event.NEXT: State.NEXT_STEP,
                Event.ERROR: State.ERROR,
            },
            State.EXECUTE: {
                Event.LEARN: State.LEARN,
                Event.NEXT: State.NEXT_STEP,
                Event.COMPLETE: State.COMPLETE,  # stop_test ends the test right after execution
                Event.ERROR: State.ERROR,
            },
            State.LEARN: {
                Event.NEXT: State.NEXT_STEP,
                Event.ERROR: State.ERROR,
            },
            State.NEXT_STEP: {
                Event.GENERATE: State.GENERATE,
                Event.COMPLETE: State.COMPLETE,
            },
            State.COMPLETE: {},
            State.ERROR: {
                Event.RETRY: State.ANALYZE,
                Event.COMPLETE: State.COMPLETE,
            }
        }

        # State handlers
        self.state_handlers: Dict[State, Callable] = {}

        self.logger.info(f"✓ Initialized state machine for test {test_case_id}")

    def transition(self, event) -> bool:
        """
        Attempt state transition.

        Args:
            event: Event triggering transition (can be Event enum or string)

        Returns:
            True if transition successful, False otherwise
        """
        # Convert string to Event enum if needed
        if isinstance(event, str):
            try:
                event = Event[event.upper()]
            except KeyError:
                self.logger.warning(f"Invalid event string: {event}")
                return False
        
        if self.state not in self.transitions:
            self.logger.error(f"No transitions defined for state {self.state}")
            return False

        if event not in self.transitions[self.state]:
            self.logger.warning(
                f"Invalid event {event.value} for state {self.state.value}"
            )
            return False

        # Record transition
        previous_state = self.state
        new_state = self.transitions[self.state][event]

        # Execute state exit handler
        self._execute_state_handler(self.state, 'exit')

        # Update context
        self.context.previous_state = previous_state
        self.context.current_state = new_state

        # Record in history
        self.context.history.append({
            'from_state': previous_state.value,
            'to_state': new_state.value,
            'event': event.value,
            'timestamp': datetime.now().isoformat(),
            'step_number': self.context.step_number,
            'confidence': self.context.confidence
        })

        # Update state
        self.state = new_state

        # Execute state entry handler
        self._execute_state_handler(new_state, 'enter')

        # Save to Redis for UI visualization
        self._save_to_redis()

        self.logger.info(
            f"✓ Transitioned: {previous_state.value} → {new_state.value} "
            f"(event: {event.value})"
        )

        return True

    def register_state_handler(self, state: State, phase: str,
                              handler: Callable) -> None:
        """
        Register handler for state entry/exit.

        Args:
            state: State
            phase: 'enter' or 'exit'
            handler: Callable to execute
        """
        key = f"{state.value}_{phase}"
        self.state_handlers[key] = handler
        self.logger.debug(f"✓ Registered handler for {key}")

    def get_state(self) -> State:
        """Get current state."""
        return self.state

    def get_context(self) -> StateContext:
        """Get current context."""
        return self.context

    def update_context(self, **kwargs) -> None:
        """Update context data."""
        for key, value in kwargs.items():
            if hasattr(self.context, key):
                setattr(self.context, key, value)
            else:
                self.context.context_data[key] = value

        self.logger.debug(f"✓ Updated context: {list(kwargs.keys())}")

    def increment_step(self) -> None:
        """Increment step number."""
        self.context.step_number += 1
        self.logger.debug(f"✓ Incremented step number to {self.context.step_number}")

    def increment_error_count(self) -> None:
        """Increment error count."""
        self.context.error_count += 1
        self.logger.warning(f"⚠ Error count: {self.context.error_count}")

    def increment_retry_count(self) -> None:
        """Increment retry count."""
        self.context.retry_count += 1
        self.logger.warning(f"⚠ Retry count: {self.context.retry_count}")

    def reset_retry_count(self) -> None:
        """Reset retry count."""
        self.context.retry_count = 0

    def set_confidence(self, confidence: float) -> None:
        """Set confidence score."""
        self.context.confidence = max(0.0, min(1.0, confidence))

    def get_history(self) -> List[Dict[str, Any]]:
        """Get state transition history."""
        return self.context.history

    def get_summary(self) -> Dict[str, Any]:
        """Get summary of state machine execution."""
        return {
            'test_case_id': self.test_case_id,
            'current_state': self.state.value,
            'step_number': self.context.step_number,
            'total_steps': self.context.total_steps,
            'confidence': self.context.confidence,
            'error_count': self.context.error_count,
            'retry_count': self.context.retry_count,
            'transition_count': len(self.context.history),
            'created_at': self.context.created_at.isoformat()
        }

    def is_complete(self) -> bool:
        """Check if state machine is complete."""
        return self.state == State.COMPLETE

    def is_error(self) -> bool:
        """Check if state machine is in error state."""
        return self.state == State.ERROR

    def can_retry(self) -> bool:
        """Check if can retry from error state."""
        return (
            self.state == State.ERROR and
            self.context.retry_count < 3
        )

    # Private methods

    def _execute_state_handler(self, state: State, phase: str) -> None:
        """Execute state handler if registered."""
        key = f"{state.value}_{phase}"
        if key in self.state_handlers:
            try:
                self.state_handlers[key](self.context)
                self.logger.debug(f"✓ Executed handler: {key}")
            except Exception as e:
                self.logger.error(f"Error executing handler {key}: {e}")

    def _save_to_redis(self) -> None:
        """Save state machine data to Redis for UI visualization."""
        try:
            import redis
            from auroqa.Utils.System import System
            
            system = System()
            redis_client = redis.Redis(
                host=system.redis_host,
                port=system.redis_port,
                decode_responses=True
            )
            
            # Save current state
            state_key = f"state_machine:{self.test_case_id}:current_state"
            redis_client.set(state_key, self.state.value, ex=3600)
            
            # Save context
            context_key = f"state_machine:{self.test_case_id}:context"
            context_data = {
                'previous_state': self.context.previous_state.value if self.context.previous_state else None,
                'step_number': self.context.step_number,
                'total_steps': self.context.total_steps,
                'confidence': self.context.confidence,
                'error_count': self.context.error_count,
                'retry_count': self.context.retry_count
            }
            redis_client.set(context_key, json.dumps(context_data), ex=3600)
            
            # Save history
            history_key = f"state_machine:{self.test_case_id}:history"
            redis_client.set(history_key, json.dumps(self.context.history), ex=3600)
            
        except Exception as e:
            self.logger.warning(f"Failed to save state machine data to Redis: {str(e)}")


class StateMachineBuilder:
    """Builder for configuring state machines."""

    def __init__(self, test_case_id: int):
        self.machine = TestGenerationStateMachine(test_case_id)

    def on_analyze(self, handler: Callable) -> 'StateMachineBuilder':
        """Register handler for ANALYZE state."""
        self.machine.register_state_handler(State.ANALYZE, 'enter', handler)
        return self

    def on_plan(self, handler: Callable) -> 'StateMachineBuilder':
        """Register handler for PLAN state."""
        self.machine.register_state_handler(State.PLAN, 'enter', handler)
        return self

    def on_generate(self, handler: Callable) -> 'StateMachineBuilder':
        """Register handler for GENERATE state."""
        self.machine.register_state_handler(State.GENERATE, 'enter', handler)
        return self

    def on_validate(self, handler: Callable) -> 'StateMachineBuilder':
        """Register handler for VALIDATE state."""
        self.machine.register_state_handler(State.VALIDATE, 'enter', handler)
        return self

    def on_execute(self, handler: Callable) -> 'StateMachineBuilder':
        """Register handler for EXECUTE state."""
        self.machine.register_state_handler(State.EXECUTE, 'enter', handler)
        return self

    def on_learn(self, handler: Callable) -> 'StateMachineBuilder':
        """Register handler for LEARN state."""
        self.machine.register_state_handler(State.LEARN, 'enter', handler)
        return self

    def build(self) -> TestGenerationStateMachine:
        """Build and return state machine."""
        return self.machine
