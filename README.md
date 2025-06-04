# ChessBot - Python Chess Engine

A complete chess engine with UCI interface and Lichess bot integration, built around custom evaluation functions.

## Features

🎯 **Custom Evaluation Engine**
- 25+ evaluation rules and heuristics
- Minimax, Negamax, iterative deepening, alpha-beta pruning
- Position-aware scoring system

🔍 **Advanced Search**
- Move ordering, killer moves, quiescence search
- Transposition table (optional)

⏱️ **Time Management**
- Adaptive time allocation
- Position-complexity aware

🌐 **Lichess Integration**
- Automatic challenge handling
- Real-time play and chat

🖥️ **UCI Compatible**
- Works with Arena, ChessBase, etc.
- Standard UCI protocol

## Quick Start

### 1. Setup
```bash
pip install -r requirements.txt
python setup.py
```

### 2. Test UCI Engine
```bash
python uci_interface.py
```

### 3. Run Lichess Bot
```bash
export LICHESS_TOKEN=your_token_here
python lichess_bot.py
```

### 4. Run the GUI
```bash
python chess_game.py
```

### 5. Package as Executable
```bash
python package_exe.py
```

## Configuration

Edit `config.yaml` to customize:
- Engine strength and search depth
- Lichess bot behavior
- Time management
- Evaluation parameters

## Files Overview

- `evaluation_engine.py` - Core evaluation and search logic
- `main_engine.py` - Main engine controller
- `uci_interface.py` - UCI protocol implementation
- `time_manager.py` - Time control
- `lichess_bot.py` - Lichess API integration
- `chess_game.py` - Pygame GUI
- `config.yaml` - Configuration
- `piece_square_tables.py` - Piece-square tables
- `testing-scenarios.md` - Testing scenarios and methodology

## Lichess Setup

1. Create a Lichess account (no games played)
2. Go to https://lichess.org/account/oauth/token and create a token with "Bot Play" scope
3. Upgrade to bot account:
   ```bash
   curl -d "" https://lichess.org/api/bot/account/upgrade \
        -H "Authorization: Bearer YOUR_TOKEN"
   ```

## Testing

See [`testing-scenarios.md`](./testing-scenarios.md) for a comprehensive set of test positions and evaluation methodology.

## Deployment: Simple Web Solution

You can deploy this chess engine as a web app so others can try it without a Python environment. Here are two low-cost, simple options:

### 1. Streamlit Cloud (Recommended for Prototyping)

- [Streamlit](https://streamlit.io/) lets you build Python web apps easily.
- Create a `streamlit_app.py` that wraps your engine and provides a simple UI.
- Push your repo to GitHub.
- Sign up at [streamlit.io/cloud](https://streamlit.io/cloud), connect your repo, and deploy for free (with some usage limits).

### 2. Railway or Render (Flask/FastAPI)

- Wrap your engine in a Flask or FastAPI app (see below).
- Push to GitHub.
- Deploy on [Railway](https://railway.app/) or [Render](https://render.com/) for free/low cost.

#### Example: Minimal Flask Wrapper

```python
# app.py
from flask import Flask, request, jsonify
import chess
from evaluation_engine import EvaluationEngine

app = Flask(__name__)

@app.route('/evaluate', methods=['POST'])
def evaluate():
    fen = request.json.get('fen')
    board = chess.Board(fen)
    engine = EvaluationEngine(board, board.turn)
    score = engine.evaluate_position(board)
    return jsonify({'score': score})

if __name__ == '__main__':
    app.run()
```

- Add a `requirements.txt` with `flask`, `python-chess`, and your dependencies.
- Deploy to Railway/Render (both have GitHub integration and simple deploy buttons).

### 3. (Optional) Gradio

- [Gradio](https://gradio.app/) is another Python tool for quick web UIs.
- Similar to Streamlit, but more focused on ML demos.

## Usage Examples

### UCI Engine in Arena
1. Open Arena Chess GUI
2. Install new engine
3. Select `ChessBot_UCI.exe`
4. Start playing!

### Lichess Bot
```bash
python lichess_bot.py your_token
# or
export LICHESS_TOKEN=your_token
python lichess_bot.py
```

## Troubleshooting

- See `testing-scenarios.md` for debugging and test positions.
- Check Python version (3.8+), dependencies, and config.

## Contributing

Pull requests welcome! Ideas:
- Opening book
- Endgame tablebases
- Neural network eval
- Multi-threading

## License

Open source - feel free to use and modify!
