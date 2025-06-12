# Viper Chess Engine - Product README

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

## Quick Start

### Web Demo (Streamlit)

1. Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```
2. Run the web app:
    ```bash
    streamlit run streamlit_app.py
    ```

### Local Metrics Dashboard

1. Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```
2. Run the dashboard:
    ```bash
    python metrics/chess_metrics.py
    ```

---

## Significant File Overview

- `chess_game.py` — Core chess game logic and rules
- `viper_scoring_calculation.py` — AI scoring and evaluation logic
- `chess_metrics.py` — Engine performance metrics dashboard
- `metrics_store.py` — Metrics database and logic
- `viper.py` — Core chess engine logic
- `piece_square_tables.py` — Piece-square evaluation tables

- `config.yaml` — Engine and AI configuration
- `testing/` — Unit and integration tests for each module
- `games/` — Saved games, configs, and logs (for local/dev use)

---

## Testing

- Each main `.py` file has a corresponding `[module]_testing.py` in `testing/`.
- Run individual tests:
    ```bash
    python testing/metrics_store_testing.py
    ```
- Or run a suite (see `testing/launch_testing_suite.py` and `testing/testing.yaml`).

---

## Deployment

- **Web:** Deploy `streamlit_app.py` to [Streamlit Cloud](https://streamlit.io/cloud).
- **Local:** Run any module directly for advanced features and metrics.

---

## Limitations

- No Lichess/UCI integration in the web demo.
- Local metrics dashboard requires Python environment.
- AI vs AI and distributed/cloud database support are in development.

---

## Example Usage

- Play a game or analyze a position in the web app.
- Tune engine parameters and visualize results in the dashboard.
- Run tests to verify engine and metrics correctness.

---

## License

Open source — feel free to use and modify!
