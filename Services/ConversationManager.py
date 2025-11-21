"""
ConversationManager: Implements ReAct pattern for multi-turn reasoning.

Implements the Reasoning + Acting pattern:
- Thought: AI reasons about what to do
- Action: AI takes an action (generate step, use tool, etc.)
- Observation: System provides feedback on the action
- Repeat until complete

This enables more sophisticated test generation with better reasoning.
"""

import json
import logging
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional, Any
from datetime import datetime
from enum import Enum
from auroqa.Utils.System import System
from auroqa.Utils.Connectors.db_utils import get_db_connection_context

logger = logging.getLogger(__name__)


class TurnType(Enum):
    """Types of conversation turns."""
    THOUGHT = "thought"
    ACTION = "action"
    OBSERVATION = "observation"
    REFLECTION = "reflection"


@dataclass
class ConversationTurn:
    """Represents a single turn in the ReAct conversation."""
    turn_number: int
    thought: str  # AI's reasoning
    action: str  # What the AI decided to do
    observation: str  # Result of the action
    tool_used: Optional[str] = None
    tool_params: Optional[Dict] = None
    tool_result: Optional[Dict] = None
    confidence: float = 0.0
    created_at: datetime = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()


@dataclass
class Conversation:
    """Represents a multi-turn conversation for test generation."""
    id: Optional[int]
    test_case_id: int
    status: str  # 'active', 'completed', 'failed'
    turns: List[ConversationTurn]
    overall_strategy: Optional[str] = None
    created_at: datetime = None
    completed_at: Optional[datetime] = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()


class ConversationManager:
    """Manages multi-turn conversations for test generation."""

    def __init__(self):
        self.system = System()
        self.logger = logging.getLogger(__name__)

    def start_conversation(self, test_case_id: int,
                          overall_strategy: str = None) -> Conversation:
        """
        Start a new conversation for test generation.

        Args:
            test_case_id: ID of the test case
            overall_strategy: Optional strategy description

        Returns:
            Conversation object
        """
        try:
            with get_db_connection_context() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO conversations
                        (test_case_id, status, overall_strategy)
                        VALUES (%s, %s, %s)
                        RETURNING id, created_at
                    """, (test_case_id, 'active', overall_strategy))

                    conversation_id, created_at = cur.fetchone()
                    conn.commit()

                    conversation = Conversation(
                        id=conversation_id,
                        test_case_id=test_case_id,
                        status='active',
                        turns=[],
                        overall_strategy=overall_strategy,
                        created_at=created_at
                    )

                    self.logger.info(
                        f"✓ Started conversation {conversation_id} for test {test_case_id}"
                    )

                    return conversation

        except Exception as e:
            self.logger.error(f"Error starting conversation: {e}")
            raise

    def add_turn(self, conversation: Conversation, turn: ConversationTurn) -> None:
        """
        Add a turn to the conversation.

        Args:
            conversation: Conversation object
            turn: ConversationTurn object
        """
        try:
            with get_db_connection_context() as conn:
                with conn.cursor() as cur:
                    # Set turn number
                    turn.turn_number = len(conversation.turns) + 1

                    cur.execute("""
                        INSERT INTO conversation_turns
                        (conversation_id, turn_number, thought, action, observation,
                         tool_used, tool_params, tool_result)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING id
                    """, (
                        conversation.id,
                        turn.turn_number,
                        turn.thought,
                        turn.action,
                        turn.observation,
                        turn.tool_used,
                        json.dumps(turn.tool_params) if turn.tool_params else None,
                        json.dumps(turn.tool_result) if turn.tool_result else None
                    ))

                    turn_id = cur.fetchone()[0]
                    conn.commit()

                    conversation.turns.append(turn)

                    self.logger.debug(
                        f"✓ Added turn {turn.turn_number} to conversation {conversation.id}"
                    )

        except Exception as e:
            self.logger.error(f"Error adding turn: {e}")
            raise

    def get_conversation_history(self, test_case_id: int) -> List[ConversationTurn]:
        """
        Get conversation history for a test case.

        Args:
            test_case_id: ID of the test case

        Returns:
            List of ConversationTurn objects
        """
        try:
            with get_db_connection_context() as conn:
                with conn.cursor() as cur:
                    # Get latest conversation for test case
                    cur.execute("""
                        SELECT id FROM conversations
                        WHERE test_case_id = %s
                        ORDER BY created_at DESC
                        LIMIT 1
                    """, (test_case_id,))

                    result = cur.fetchone()
                    if not result:
                        return []

                    conversation_id = result[0]

                    # Get all turns
                    cur.execute("""
                        SELECT turn_number, thought, action, observation,
                               tool_used, tool_params, tool_result, created_at
                        FROM conversation_turns
                        WHERE conversation_id = %s
                        ORDER BY turn_number
                    """, (conversation_id,))

                    turns = []
                    for row in cur.fetchall():
                        turn_num, thought, action, observation, tool_used, \
                            tool_params, tool_result, created_at = row

                        turn = ConversationTurn(
                            turn_number=turn_num,
                            thought=thought,
                            action=action,
                            observation=observation,
                            tool_used=tool_used,
                            tool_params=json.loads(tool_params) if tool_params else None,
                            tool_result=json.loads(tool_result) if tool_result else None,
                            created_at=created_at
                        )
                        turns.append(turn)

                    self.logger.info(
                        f"✓ Retrieved {len(turns)} turns from conversation history"
                    )

                    return turns

        except Exception as e:
            self.logger.error(f"Error retrieving conversation history: {e}")
            return []

    def extract_context(self, conversation: Conversation) -> Dict[str, Any]:
        """
        Extract context from conversation for next turn.

        Args:
            conversation: Conversation object

        Returns:
            Dictionary with extracted context
        """
        context = {
            'test_case_id': conversation.test_case_id,
            'turn_count': len(conversation.turns),
            'overall_strategy': conversation.overall_strategy,
            'recent_actions': [],
            'recent_observations': [],
            'tools_used': [],
            'confidence_trend': []
        }

        # Extract recent turns (last 3)
        for turn in conversation.turns[-3:]:
            context['recent_actions'].append(turn.action)
            context['recent_observations'].append(turn.observation)
            if turn.tool_used:
                context['tools_used'].append(turn.tool_used)
            context['confidence_trend'].append(turn.confidence)

        # Calculate average confidence
        if context['confidence_trend']:
            context['average_confidence'] = sum(context['confidence_trend']) / len(
                context['confidence_trend']
            )
        else:
            context['average_confidence'] = 0.0

        self.logger.debug(
            f"✓ Extracted context: {len(context['recent_actions'])} recent actions, "
            f"avg_confidence={context['average_confidence']:.2f}"
        )

        return context

    def generate_reasoning_trace(self, conversation: Conversation) -> str:
        """
        Generate a reasoning trace from conversation.

        Args:
            conversation: Conversation object

        Returns:
            Formatted reasoning trace
        """
        trace = f"=== Reasoning Trace for Test {conversation.test_case_id} ===\n"
        trace += f"Strategy: {conversation.overall_strategy}\n"
        trace += f"Total Turns: {len(conversation.turns)}\n\n"

        for turn in conversation.turns:
            trace += f"--- Turn {turn.turn_number} ---\n"
            trace += f"Thought: {turn.thought}\n"
            trace += f"Action: {turn.action}\n"
            trace += f"Observation: {turn.observation}\n"

            if turn.tool_used:
                trace += f"Tool: {turn.tool_used}\n"
                if turn.tool_params:
                    trace += f"Params: {json.dumps(turn.tool_params, indent=2)}\n"
                if turn.tool_result:
                    trace += f"Result: {json.dumps(turn.tool_result, indent=2)}\n"

            trace += f"Confidence: {turn.confidence:.2f}\n\n"

        return trace

    def complete_conversation(self, conversation: Conversation,
                             status: str = 'completed') -> None:
        """
        Mark conversation as complete.

        Args:
            conversation: Conversation object
            status: Final status ('completed', 'failed', 'cancelled')
        """
        try:
            with get_db_connection_context() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE conversations
                        SET status = %s, completed_at = CURRENT_TIMESTAMP
                        WHERE id = %s
                    """, (status, conversation.id))

                    conn.commit()

                    conversation.status = status
                    conversation.completed_at = datetime.now()

                    self.logger.info(
                        f"✓ Completed conversation {conversation.id} with status: {status}"
                    )

        except Exception as e:
            self.logger.error(f"Error completing conversation: {e}")
            raise

    def get_conversation(self, conversation_id: int) -> Optional[Conversation]:
        """
        Retrieve a conversation by ID.

        Args:
            conversation_id: ID of the conversation

        Returns:
            Conversation object or None
        """
        try:
            with get_db_connection_context() as conn:
                with conn.cursor() as cur:
                    # Get conversation
                    cur.execute("""
                        SELECT id, test_case_id, status, overall_strategy,
                               created_at, completed_at
                        FROM conversations
                        WHERE id = %s
                    """, (conversation_id,))

                    result = cur.fetchone()
                    if not result:
                        return None

                    conv_id, test_case_id, status, strategy, created_at, completed_at = result

                    # Get turns
                    cur.execute("""
                        SELECT turn_number, thought, action, observation,
                               tool_used, tool_params, tool_result, created_at
                        FROM conversation_turns
                        WHERE conversation_id = %s
                        ORDER BY turn_number
                    """, (conversation_id,))

                    turns = []
                    for row in cur.fetchall():
                        turn_num, thought, action, observation, tool_used, \
                            tool_params, tool_result, turn_created_at = row

                        turn = ConversationTurn(
                            turn_number=turn_num,
                            thought=thought,
                            action=action,
                            observation=observation,
                            tool_used=tool_used,
                            tool_params=json.loads(tool_params) if tool_params else None,
                            tool_result=json.loads(tool_result) if tool_result else None,
                            created_at=turn_created_at
                        )
                        turns.append(turn)

                    conversation = Conversation(
                        id=conv_id,
                        test_case_id=test_case_id,
                        status=status,
                        turns=turns,
                        overall_strategy=strategy,
                        created_at=created_at,
                        completed_at=completed_at
                    )

                    return conversation

        except Exception as e:
            self.logger.error(f"Error retrieving conversation: {e}")
            return None

    def list_conversations(self, test_case_id: int, limit: int = 10) -> List[Conversation]:
        """
        List conversations for a test case.

        Args:
            test_case_id: ID of the test case
            limit: Maximum number of conversations to return

        Returns:
            List of Conversation objects
        """
        try:
            with get_db_connection_context() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT id, test_case_id, status, overall_strategy,
                               created_at, completed_at
                        FROM conversations
                        WHERE test_case_id = %s
                        ORDER BY created_at DESC
                        LIMIT %s
                    """, (test_case_id, limit))

                    conversations = []
                    for row in cur.fetchall():
                        conv_id, tc_id, status, strategy, created_at, completed_at = row

                        conversation = Conversation(
                            id=conv_id,
                            test_case_id=tc_id,
                            status=status,
                            turns=[],  # Don't load turns for list view
                            overall_strategy=strategy,
                            created_at=created_at,
                            completed_at=completed_at
                        )
                        conversations.append(conversation)

                    return conversations

        except Exception as e:
            self.logger.error(f"Error listing conversations: {e}")
            return []
