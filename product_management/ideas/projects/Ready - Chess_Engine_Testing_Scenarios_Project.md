# TODO Needs update by CoPilot
# Chess Engine Testing Scenarios

This document provides specific testing scenarios and positions to evaluate your chess engine's performance using the GUI or web interface.

## Quick Start Testing

- Use the GUI (`python chess_game.py`) or your web deployment to test positions.
- For web: add a FEN input box and evaluation display.

### 1. Basic Functionality Test

1. **Start a new game**: The engine should play as Black
2. **Make the move e4**: Click e2, then e4
3. **Observe engine response**: Engine should respond with a reasonable opening move
4. **Check evaluation**: Should show a small advantage for White (~0.2-0.5)

### 2. Engine Response Time Test

Observe how quickly your engine makes moves at different depths:
- Depth 1: Should be instant (< 0.1 seconds)
- Depth 2: Should be very fast (< 0.5 seconds)
- Depth 3: Should be reasonable (< 2 seconds)
- Depth 4+: May take longer depending on your evaluation complexity

## Specific Test Positions

### Tactical Positions

#### 1. Fork Detection
**Position**: `r1bqkb1r/pppp1ppp/2n2n2/1B2p3/4P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4`

**Test**: Your engine should find Bxf7+ (fork of king and rook)
**Expected**: Engine should heavily favor this move with high evaluation

#### 2. Pin Recognition
**Position**: `rnbqkbnr/ppp1pppp/8/3p4/4P3/8/PPPP1PPP/RNBQKBNR w KQkq d6 0 2`

**Test**: Play Bb5+ and observe if engine recognizes the pin
**Expected**: Engine should understand the pinned piece cannot move

#### 3. Discovery Attack
**Position**: `r1bqk2r/pppp1ppp/2n2n2/2b1p3/2B1P3/3P1N2/PPP2PPP/RNBQK2R w KQkq - 4 6`

**Test**: Look for discovered attacks with piece movement
**Expected**: Engine should recognize discovery potential

### Positional Test Positions

#### 1. Piece Development
**Position**: `rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1`

**Test**: Does the engine prioritize piece development?
**Expected**: Should develop knights and bishops before moving same piece twice

#### 2. King Safety
**Position**: `rnbqk2r/pppp1ppp/4pn2/8/1bPP4/2N2N2/PP2PPPP/R1BQKB1R w KQkq - 2 5`

**Test**: Does engine castle early for king safety?
**Expected**: Should prioritize castling over material gains

#### 3. Center Control
**Position**: `rnbqkbnr/ppp1pppp/8/3p4/4P3/8/PPPP1PPP/RNBQKBNR w KQkq d6 0 2`

**Test**: How does engine value center control?
**Expected**: Should prefer moves that control center squares

### Endgame Scenarios

#### 1. King and Pawn vs King
**Position**: `8/8/8/4k3/8/8/4P3/4K3 w - - 0 1`

**Test**: Can engine win this elementary endgame?
**Expected**: Should advance pawn with king support

#### 2. Queen vs Pawn Promotion
**Position**: `8/1P6/8/8/8/8/8/k6K w - - 0 1`

**Test**: Does engine find forced promotion?
**Expected**: Should recognize inevitable promotion and high evaluation

#### 3. Insufficient Material
**Position**: `8/8/8/8/8/5k2/8/5K2 w - - 0 1`

**Test**: Does engine recognize draw?
**Expected**: Should show evaluation near 0

## Web Testing

If you deploy the engine as a web app (see README), add a simple interface:
- FEN input box
- "Evaluate" button
- Display the evaluation score

You can copy-paste the FENs from the scenarios below to test the engine's output.

## Performance Benchmarks

### Evaluation Function Tests

Test these specific rules from your evaluation engine:

#### 1. Material Balance
```python
# Test positions with material imbalances
positions = [
    "rnbqkb1r/pppppppp/5n2/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 2 2",  # Missing knight
    "rnbqkbnr/ppp1pppp/8/8/8/8/PPPPPPPP/RNBQKB1R w KQkq - 0 3",     # Missing queen
    "rnbqkbnr/pppppp1p/6p1/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 2"   # Pawn down
]
```

#### 2. Center Control Evaluation
```python
# Positions emphasizing center control
center_positions = [
    "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1",
    "rnbqkbnr/ppp1pppp/8/3p4/3PP3/8/PPP2PPP/RNBQKBNR b KQkq e3 0 2",
    "rnbqkbnr/pp2pppp/8/2pp4/3PP3/8/PPP2PPP/RNBQKBNR w KQkq c6 0 3"
]
```

#### 3. King Safety Testing
```python
# Positions testing king safety evaluation
king_safety_positions = [
    "r1bqk2r/pppp1ppp/2n2n2/2b1p3/2B1P3/3P1N2/PPP2PPP/RNBQ1RK1 b kq - 0 6",  # Castled
    "r1bqk2r/pppp1ppp/2n2n2/2b1p3/2B1P3/3P1N2/PPP2PPP/RNBQK2R w KQkq - 0 6",   # Not castled
]
```

## Testing Methodology

### 1. Systematic Position Testing

Create a test suite file:

```python
# test_positions.py
test_suite = {
    "openings": [
        ("Italian Game", "r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R b KQkq - 3 3"),
        ("Queen's Gambit", "rnbqkbnr/ppp1pppp/8/3p4/2PP4/8/PP2PPPP/RNBQKBNR b KQkq c3 0 2"),
    ],
    "middlegame": [
        ("Complex Position", "r1bq1rk1/ppp2ppp/2np1n2/2b1p3/2B1P3/3P1N2/PPP1NPPP/R1BQ1RK1 w - - 0 8"),
    ],
    "endgame": [
        ("Rook Endgame", "8/8/8/8/8/8/1r6/K6k w - - 0 1"),
    ]
}
```

### 2. Comparative Analysis

Test your engine against different scenarios:

```python
# Compare evaluations at different depths
for position_name, fen in test_suite["openings"]:
    print(f"Testing: {position_name}")
    gui.import_fen(fen)
    
    for depth in range(1, 5):
        gui.engine.depth = depth
        eval_score = gui.engine.evaluate_position()
        print(f"  Depth {depth}: {eval_score:.3f}")
```

### 3. Move Consistency Testing

Test if your engine makes consistent moves:

```python
# Test move consistency
for i in range(10):
    gui.reset_game()
    gui.make_move(chess.Move.from_uci("e2e4"))  # 1.e4
    engine_response = gui.get_engine_move()
    print(f"Trial {i+1}: Engine played {engine_response}")
```

## GUI Features for Testing

### 1. Real-time Evaluation Display

The GUI shows the current position evaluation in real-time. Use this to:
- Verify evaluation changes make sense
- Identify positions where evaluation seems wrong
- Track evaluation consistency

### 2. Visual Move Indication

Green circles show legal moves, helping you:
- Verify move generation is correct
- Understand what moves the engine considers
- Check for missing or illegal moves

### 3. Check Detection

Red highlighting shows when the king is in check:
- Verify check detection works correctly
- Ensure engine responds appropriately to checks
- Test checkmate recognition

## Common Testing Pitfalls

### 1. Depth Dependency

**Issue**: Evaluations change dramatically with depth
**Solution**: Test at consistent depths and understand why evaluations change

### 2. Opening Book Dependency

**Issue**: Engine plays poorly in openings
**Solution**: Focus on middlegame positions for evaluation testing

### 3. Time Control Issues

**Issue**: Engine takes too long to move
**Solution**: 
- Reduce search depth
- Optimize evaluation function
- Add time management

### 4. Position Setup Errors

**Issue**: Testing with illegal positions
**Solution**: Validate FEN strings before testing

## Debugging Your Engine

### 1. Evaluation Breakdown

Add debug output to see which rules fire:

```python
def _calculate_score(self, color):
    score = 0
    material = self._material_score(color)
    print(f"Material: {material}")
    
    positional = self._positional_evaluation()
    print(f"Positional: {positional}")
    
    # Add more debug output for each rule
    return score
```

### 2. Move Scoring

Track why certain moves are preferred:

```python
def get_engine_move(self):
    move_scores = []
    for move in self.board.legal_moves:
        score = self.engine.evaluate_move(move)
        move_scores.append((move, score))
    
    # Sort and display top moves
    move_scores.sort(key=lambda x: x[1], reverse=True)
    for move, score in move_scores[:5]:
        print(f"{move}: {score:.3f}")
    
    return move_scores[0][0] if move_scores else None
```

## Advanced Testing Techniques

### 1. Perft Testing

Validate move generation with perft:

```python
def perft(board, depth):
    if depth == 0:
        return 1
    
    count = 0
    for move in board.legal_moves:
        board.push(move)
        count += perft(board, depth - 1)
        board.pop()
    
    return count

# Test known perft values
assert perft(chess.Board(), 3) == 8902
```

### 2. Engine vs Engine

Play your engine against itself:

```python
def engine_vs_engine_game():
    board = chess.Board()
    engine1 = EvaluationEngine(board, depth=3)
    engine2 = EvaluationEngine(board, depth=3)
    
    while not board.is_game_over():
        if board.turn:
            # White's turn
            move = engine1.get_best_move()
        else:
            # Black's turn  
            move = engine2.get_best_move()
        
        board.push(move)
        engine1.board = board.copy()
        engine2.board = board.copy()
    
    return board.result()
```

This comprehensive testing approach will help you identify strengths and weaknesses in your evaluation engine and guide further development.