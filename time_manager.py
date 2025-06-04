# time_manager.py
"""
Time Management System for Chess Engine
Handles time allocation for moves in different time controls

UNTESTED CODE
"""

import time
from typing import Optional, Dict, Any

class TimeManager:
    def __init__(self):
        self.start_time = None
        self.allocated_time = None
        self.max_time = None
        self.emergency_time = None

    def allocate_time(self, time_control: Dict[str, Any], board) -> float:
        """
        Allocate time for current move based on time control and position

        Args:
            time_control: Dictionary with time control parameters
            board: Current chess position

        Returns:
            Allocated time in seconds
        """
        # Handle fixed time per move
        if time_control.get('movetime'):
            return time_control['movetime'] / 1000.0

        # Handle infinite time
        if time_control.get('infinite'):
            return float('inf')

        # Handle depth-based search
        if time_control.get('depth'):
            return float('inf')  # No time limit for depth search

        # Get time remaining for current side
        if board.turn:  # White to move
            remaining_time = time_control.get('wtime', 60000)  # Default 1 minute
            increment = time_control.get('winc', 0)
        else:  # Black to move
            remaining_time = time_control.get('btime', 60000)
            increment = time_control.get('binc', 0)

        # Convert milliseconds to seconds
        remaining_time = remaining_time / 1000.0
        increment = increment / 1000.0

        # Get moves to go (default to 30 if not specified)
        moves_to_go = time_control.get('movestogo', 30)

        # Calculate base time allocation
        if moves_to_go:
            # Tournament time control with moves to go
            base_time = remaining_time / max(moves_to_go, 1)
        else:
            # Sudden death or increment-based
            # Use more conservative approach for sudden death
            base_time = remaining_time / 40  # Assume 40 moves left

        # Add increment (but not full increment to be safe)
        allocated_time = base_time + (increment * 0.8)

        # Apply position-based time modifiers
        time_multiplier = self.get_position_time_multiplier(board)
        allocated_time *= time_multiplier

        # Safety limits
        min_time = 0.1  # Minimum 100ms
        max_time = min(
            remaining_time * 0.1,  # Never use more than 10% of remaining time
            remaining_time - 1.0   # Always leave at least 1 second
        )

        allocated_time = max(min_time, min(allocated_time, max_time))

        # Emergency time handling
        if remaining_time < 10.0:  # Less than 10 seconds
            allocated_time = min(allocated_time, remaining_time * 0.05)

        return allocated_time

    def get_position_time_multiplier(self, board) -> float:
        """
        Adjust time allocation based on position characteristics

        Args:
            board: Current chess position

        Returns:
            Time multiplier (1.0 = normal, >1.0 = use more time, <1.0 = use less time)
        """
        multiplier = 1.0

        # Check if position is complex (many legal moves)
        legal_moves = len(list(board.legal_moves))
        if legal_moves > 35:
            multiplier *= 1.3  # Complex position, think longer
        elif legal_moves < 10:
            multiplier *= 0.7  # Simple position, think less

        # Check if in check
        if board.is_check():
            multiplier *= 1.4  # Critical position, think longer

        # Opening/middlegame/endgame considerations
        piece_count = len(board.piece_map())
        if piece_count > 20:  # Opening/early middlegame
            multiplier *= 0.8  # Don't overthink opening
        elif piece_count < 10:  # Endgame
            multiplier *= 1.2  # Endgame precision important

        # Limit multiplier range
        return max(0.3, min(multiplier, 2.5))

    def start_timer(self, allocated_time: float):
        """Start the timer for current move"""
        self.start_time = time.time()
        self.allocated_time = allocated_time
        self.max_time = allocated_time * 1.2  # 20% buffer for critical positions
        self.emergency_time = allocated_time * 0.1  # Emergency stop time

    def should_stop(self, depth: int = 0, nodes: int = 0) -> bool:
        """
        Check if search should stop based on time

        Args:
            depth: Current search depth
            nodes: Nodes searched so far

        Returns:
            True if search should stop
        """
        if self.start_time is None or self.allocated_time is None:
            return False

        elapsed = time.time() - self.start_time

        # Always stop if we exceed maximum time
        if elapsed >= self.max_time:
            return True

        # Stop if we've used allocated time
        if elapsed >= self.allocated_time:
            return True

        # Don't stop too early (minimum search time)
        if elapsed < 0.05:  # At least 50ms
            return False

        # Depth-based stopping
        if depth >= 1:  # If we have at least one complete iteration
            # If we're close to time limit, don't start new iteration
            if elapsed >= self.allocated_time * 0.8:
                return True

        return False

    def time_remaining(self) -> float:
        """Get remaining allocated time"""
        if self.start_time is None or self.allocated_time is None:
            return float('inf')

        elapsed = time.time() - self.start_time
        return max(0, self.allocated_time - elapsed)

    def time_elapsed(self) -> float:
        """Get time elapsed since search started"""
        if self.start_time is None:
            return 0.0
        return time.time() - self.start_time

    def get_time_info(self) -> Dict[str, float]:
        """Get timing information for UCI info output"""
        return {
            'elapsed': self.time_elapsed(),
            'remaining': self.time_remaining(),
            'allocated': self.allocated_time or 0.0
        }

# Example usage and testing
if __name__ == "__main__":
    import chess

    # Test time manager
    tm = TimeManager()
    board = chess.Board()

    # Test different time controls
    time_controls = [
        {'wtime': 300000, 'btime': 300000, 'winc': 3000, 'binc': 3000},  # 5+3 blitz
        {'wtime': 180000, 'btime': 180000, 'winc': 0, 'binc': 0},        # 3+0 blitz
        {'wtime': 900000, 'btime': 900000, 'winc': 10000, 'binc': 10000}, # 15+10 rapid
        {'movetime': 5000},  # 5 seconds per move
        {'depth': 10},       # Fixed depth
        {'infinite': True}   # Infinite time
    ]

    print("Time Manager Test Results:")
    print("-" * 40)

    for i, tc in enumerate(time_controls):
        allocated = tm.allocate_time(tc, board)
        print(f"Time Control {i+1}: {tc}")
        print(f"Allocated Time: {allocated:.3f} seconds")
        print()
