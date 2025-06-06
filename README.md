# V7P3R ChessBot - Streamlit Web Demo

A simple web demo of the V7P3R ChessBot engine, allowing you to play against the AI or evaluate any chess position using a FEN string. This version is designed for easy sharing and does **not** require a Python environment for your friends to try it out (when deployed on Streamlit Cloud).

---

## Features (Streamlit App)

- **Play vs AI:** Make moves as White or Black, and the AI will respond.
- **AI Configuration:** Choose AI type (lookahead, minimax, negamax, random) and search depth.
- **FEN Input:** Set up any position by pasting a FEN string.
- **Position Evaluation:** Instantly evaluate any position with a single click.
- **Human-Readable Moves:** Select moves in standard chess notation (SAN).
- **Move History:** See the full move list in readable notation.
- **Board Visualization:** Interactive chessboard updates after each move.
- **No Installation Needed:** Deployable on [Streamlit Cloud](https://streamlit.io/cloud) for instant sharing.

---

## Quick Start (Local)

1. **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

2. **Run the Streamlit app:**
    ```bash
    streamlit run streamlit_app.py
    ```

---

## How to Use

- **Set Position:** Paste a FEN string and click "Set Position from FEN" to load any chess position.
- **Play a Move:** Use the dropdown to select your move (in chess notation) and click "Play Move". The AI will respond automatically.
- **Evaluate:** Click "Evaluate Position" to see the engine's evaluation of the current board.
- **Configure AI:** Use the sidebar to change AI type and depth.
- **Refresh Board:** If the board does not update after the AI moves, click "Evaluate Position" or interact with the board.

---

## Deployment (Share with Friends)

You can deploy this app for free using [Streamlit Cloud](https://streamlit.io/cloud):

1. Push your code to GitHub.
2. Go to [streamlit.io/cloud](https://streamlit.io/cloud) and sign in.
3. Click "New app", select your repo, and deploy.
4. Share the link!

---

## File Overview

- `streamlit_app.py` — The Streamlit web app (all main features are here)
- `evaluation_engine.py` — Chess engine logic and evaluation
- `piece_square_tables.py` — Piece-square tables for evaluation
- `config.yaml` — Engine and AI configuration

---

## Limitations (Web Demo)

- No Lichess integration or UCI protocol in this demo.
- No Pygame GUI or advanced visualizations.
- Only single-game, human-vs-AI play (no AI vs AI or puzzle mode).
- Board may require manual refresh after AI moves (see sidebar instructions).

---

## Example Usage

- **Play a game:** Start from the default position and play as White or Black.
- **Test a position:** Paste a FEN (e.g., from a puzzle or analysis) and see what the engine thinks.
- **Experiment:** Try different AI types and depths to see how the engine responds.

---

## License

Open source — feel free to use and modify!
