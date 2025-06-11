# Chess GUI Implementation for Engine Testing

This document provides a complete implementation of a chess GUI that integrates with your existing evaluation engine for easy testing and performance analysis.

## Installation Requirements (requirements.txt)

```
pygame>=2.1.0
python-chess>=1.999
numpy>=1.21.0
```

## Setup Instructions

1. **Install Dependencies**:
   ```bash
   pip install pygame python-chess numpy
   ```

2. **Save the Code**: Save the above code as `chess_gui.py` in the same directory as your `evaluation_engine.py`

3. **Run the GUI**:
   ```bash
   python chess_gui.py
   ```

## Features

### Visual Interface
- **Professional Chess Board**: Traditional brown and beige squares with coordinate labels
- **Unicode Chess Pieces**: High-quality Unicode symbols for all pieces
- **Visual Feedback**: Highlighted squares for selection and legal moves
- **Check Indication**: Red highlighting when king is in check

### Game Controls
- **Left Click**: Select pieces and make moves
- **R Key**: Reset game to starting position
- **ESC Key**: Quit the application
- **Drag and Drop**: Click source square, then destination square

### Engine Integration
- **Real-time Evaluation**: Shows current position evaluation
- **Automatic Engine Moves**: Engine plays black automatically
- **Configurable Depth**: Adjust engine search depth
- **Error Handling**: Graceful fallback if engine fails

### Game Features
- **Legal Move Validation**: Only allows legal chess moves
- **Game State Detection**: Detects checkmate, stalemate, and draws
- **Move History**: Tracks game progression
- **Turn Indication**: Clear indication of whose turn it is

## Customization Options

### Engine Configuration
```python
# Change engine depth
gui.setup_engine(depth=4)

# Use different engine class
gui.setup_engine(MyCustomEngine, depth=3)

# Switch human color
gui.human_color = chess.BLACK  # Human plays black
```

### Visual Customization
```python
# Change board colors
self.LIGHT_BROWN = (255, 248, 220)  # Lighter squares
self.DARK_BROWN = (139, 69, 19)     # Darker squares

# Adjust board size
gui = ChessGUI(width=1000, height=800)
```

## Testing Your Engine

This GUI provides several ways to test your engine performance:

1. **Interactive Testing**: Play against your engine to test move quality
2. **Position Evaluation**: Real-time evaluation display shows engine assessment
3. **Performance Monitoring**: Observe engine thinking time and move selection
4. **Edge Case Testing**: Test unusual positions, endgames, and tactical scenarios

## Troubleshooting

### Common Issues

1. **Import Error**: Ensure `evaluation_engine.py` is in the same directory
2. **Pygame Issues**: Install pygame with `pip install pygame`
3. **Unicode Display**: Some systems may not display chess symbols correctly
4. **Performance**: Reduce engine depth if moves are too slow

### Debug Mode
Add debug prints to monitor engine behavior:

```python
def get_engine_move(self):
    print(f"Engine thinking... (depth {self.engine_depth})")
    move = self.engine.get_best_move()
    print(f"Engine selected: {move}")
    return move
```