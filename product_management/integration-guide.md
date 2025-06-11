# Chess Engine GUI Implementation Guide

This guide explains how to use and customize the Chess GUI we've built to thoroughly test your chess evaluation engine.

## Table of Contents
1. [Getting Started](#getting-started)
2. [Integration with Your Evaluation Engine](#integration-with-your-evaluation-engine)
3. [Customization Options](#customization-options)
4. [Testing Strategies](#testing-strategies)
5. [Troubleshooting](#troubleshooting)

## Getting Started

### Prerequisites
- Python 3.7 or higher
- Your `evaluation_engine.py` file
- Required packages: `pygame`, `python-chess`, `numpy`

### Installation

1. Install dependencies:
   ```bash
   pip install pygame python-chess numpy
   ```

2. Place `chess_gui.py` in the same directory as your `evaluation_engine.py` file.

3. Run the GUI:
   ```bash
   python chess_gui.py
   ```

## Integration with Your Evaluation Engine

The chess GUI automatically integrates with your `evaluation_engine.py` through its `EvaluationEngine` class. Here's how the integration works:

### Automatic Integration

1. The GUI imports your `EvaluationEngine` class from `evaluation_engine.py`
2. It creates an instance of the class, passing a chess board and depth parameter
3. When moves are made, the GUI updates the engine's board state
4. The GUI uses your engine's evaluation methods to:
   - Get the best move for the engine player
   - Display the current position evaluation

### Required Interface

Your `EvaluationEngine` class must implement these methods:

```python
class EvaluationEngine:
    def __init__(self, board, depth=3):
        self.board = board
        self.depth = depth
        
    def evaluate_position(self):
        """Return numerical evaluation of current position"""
        # Implementation here
        return score  # Positive values favor white, negative favor black
    
    def evaluate_move(self, move):
        """Evaluate a specific move"""
        # Implementation here
        return score  # Higher is better
```

## Customization Options

You can customize the chess GUI to fit your specific testing needs.

### Engine Settings

Modify these lines in `chess_gui.py` to change engine settings:

```python
# In the main() function:
gui.setup_engine(depth=3)  # Change depth for deeper search
gui.human_color = chess.BLACK  # Play as black instead
```

### Visual Customization

```python
# In the ChessGUI.__init__ method:
# Change board colors
self.LIGHT_BROWN = (240, 217, 181)  # Light squares
self.DARK_BROWN = (181, 136, 99)    # Dark squares
self.HIGHLIGHT_COLOR = (255, 255, 0, 128)  # Selected square

# Change board size
# In the main() function:
gui = ChessGUI(width=1000, height=900)
```

### Adding Features

Here are some useful features you might want to add:

#### Position Import/Export

```python
def import_fen(self, fen_string):
    """Import a position from FEN notation"""
    try:
        self.board = chess.Board(fen_string)
        if self.engine:
            self.engine.board = self.board.copy()
        self.selected_square = None
        self.legal_moves = []
        self.game_over = self.board.is_game_over()
        return True
    except ValueError:
        return False
        
def export_fen(self):
    """Export current position as FEN string"""
    return self.board.fen()
```

#### Move History

```python
# Add to ChessGUI.__init__
self.move_history = []

# Add to make_move method
self.move_history.append(move)

# Add method to draw move history
def draw_move_history(self):
    history_x = self.width - 200
    history_y = 50
    
    history_surface = self.font.render("Move History", True, self.BLACK)
    self.screen.blit(history_surface, (history_x, history_y))
    
    for i, move in enumerate(self.move_history[-10:]):  # Show last 10 moves
        move_text = f"{i+1}. {move}"
        move_surface = self.small_font.render(move_text, True, self.BLACK)
        self.screen.blit(move_surface, (history_x, history_y + 40 + i*20))
```

## Testing Strategies

Here are effective strategies for testing your chess engine:

### 1. Baseline Testing

Compare your engine against known positions with established evaluations:

```python
test_positions = [
    ("Starting position", "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"),
    ("Queen's Gambit", "rnbqkbnr/ppp1pppp/8/3p4/2PP4/8/PP2PPPP/RNBQKBNR b KQkq - 0 2"),
    # Add more test positions
]

for name, fen in test_positions:
    print(f"Testing: {name}")
    gui.import_fen(fen)
    eval_score = gui.engine.evaluate_position()
    print(f"Evaluation: {eval_score}")
```

### 2. Depth Analysis

Test how evaluation changes with search depth:

```python
for depth in range(1, 6):
    gui.engine.depth = depth
    best_move = gui.get_engine_move()
    eval_score = gui.engine.evaluate_position()
    print(f"Depth {depth}: Best move {best_move}, Eval: {eval_score}")
```

### 3. Move Consistency Testing

Test if your engine consistently finds the same best move:

```python
results = {}
for _ in range(5):  # Run multiple times
    best_move = gui.get_engine_move()
    if best_move in results:
        results[best_move] += 1
    else:
        results[best_move] = 1

for move, count in results.items():
    print(f"Move {move}: {count} times")
```

### 4. Visual Testing

Observe the engine's behavior in these specific scenarios:

- **Checkmate Detection**: Set up positions where checkmate is possible in 1-2 moves
- **Material Evaluation**: Test positions with various material imbalances
- **Positional Understanding**: Test classic positional concepts like pawn structure, piece activity
- **Tactical Awareness**: Test positions with tactical opportunities (forks, pins, skewers)

## Troubleshooting

### Common Issues

1. **Import Error**:
   ```
   ImportError: No module named 'evaluation_engine'
   ```
   - Make sure `evaluation_engine.py` is in the same directory as `chess_gui.py`

2. **Pygame Installation**:
   ```
   ModuleNotFoundError: No module named 'pygame'
   ```
   - Install pygame: `pip install pygame`

3. **Engine Errors**:
   ```
   Engine error: 'EvaluationEngine' object has no attribute 'evaluate_position'
   ```
   - Check your `EvaluationEngine` class implements the required methods

4. **Performance Issues**:
   - If moves are too slow, reduce engine depth
   - Add timeout mechanism to engine evaluation
   ```python
   import signal
   
   def timeout_handler(signum, frame):
       raise TimeoutError("Engine evaluation timed out")
   
   signal.signal(signal.SIGALRM, timeout_handler)
   signal.alarm(5)  # 5 second timeout
   try:
       # Perform evaluation
       signal.alarm(0)  # Reset alarm
   except TimeoutError:
       # Handle timeout
   ```

### Debug Mode

Add this code to enable debug mode in your chess GUI:

```python
# Add to ChessGUI.__init__
self.debug_mode = True

# Add to get_engine_move
if self.debug_mode:
    print(f"Engine thinking at depth {self.engine_depth}...")
    print(f"Current position evaluation: {self.engine.evaluate_position()}")
    print(f"Legal moves: {list(self.board.legal_moves)}")
```

## Conclusion

This chess GUI provides a powerful way to test and refine your evaluation engine. By using the visual interface, you can:

1. Quickly identify strengths and weaknesses in your engine
2. Compare different evaluation functions side by side
3. Develop a stronger understanding of your engine's decision-making process
4. Save time in development by rapid testing of changes

With the customization options available, you can adapt the GUI to focus on specific aspects of your engine that need improvement.