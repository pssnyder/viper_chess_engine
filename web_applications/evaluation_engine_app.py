# evaluation_engine_app.py
# A simplified Streamlit app to evaluate chess positions and suggest moves using the EvaluationEngine.
# This app allows users to set a position using FEN, view the board, make moves, and see AI evaluations.
# Search is performance limited to a depth of 4 plus quiescence and no move ordering.


import streamlit as st
import chess
import chess.svg 
from evaluation_engine import EvaluationEngine

# --- Sidebar: AI config ---
st.sidebar.title("AI Settings")
ai_type = st.sidebar.selectbox("AI Type", ["lookahead", "minimax", "negamax", "random"], index=0)
ai_depth = st.sidebar.slider("AI Depth", 1, 4, 2)
flip_board = st.sidebar.checkbox("Flip Board", value=False)
if st.sidebar.button("Reset Game"):
    st.session_state.board = chess.Board()
    st.session_state.engine = EvaluationEngine(st.session_state.board, st.session_state.board.turn)
    st.session_state.move_history = []
    st.experimental_set_query_params()
st.sidebar.info(
    "After the AI moves, if the board does not update automatically, "
    "please press 'Evaluate Position' or interact with the board to refresh the display."
)

# --- Session state for board ---
if "board" not in st.session_state:
    st.session_state.board = chess.Board()
if "engine" not in st.session_state:
    st.session_state.engine = EvaluationEngine(st.session_state.board, st.session_state.board.turn)
if "move_history" not in st.session_state:
    st.session_state.move_history = []

# --- FEN input and reset ---
fen = st.text_input("FEN", st.session_state.board.fen())
if st.button("Set Position from FEN"):
    try:
        st.session_state.board = chess.Board(fen)
        st.session_state.engine = EvaluationEngine(st.session_state.board, st.session_state.board.turn)
        st.session_state.move_history = []
        st.success("Position set.")
    except Exception as e:
        st.error(f"Invalid FEN: {e}")

# --- Show board ---
st.write("### Chess Board")
try:
    board_svg = chess.svg.board(st.session_state.board, size=400, flipped=flip_board)
    st.markdown(f'<div>{board_svg}</div>', unsafe_allow_html=True)
except Exception as e:
    st.warning("SVG board rendering failed. Showing text board instead.")
    st.text(str(st.session_state.board))

# --- Evaluation ---
if st.button("Evaluate Position"):
    score = st.session_state.engine.evaluate_position(st.session_state.board)
    st.write(f"Evaluation: {score:+.2f}")

# --- Human move input ---
st.write("### Make Your Move")
# Build a mapping from SAN to UCI for all legal moves
legal_moves = list(st.session_state.board.legal_moves)
san_to_uci = {}
san_moves = []
for move in legal_moves:
    san = st.session_state.board.san(move)
    san_to_uci[san] = move.uci()
    san_moves.append(san)
move_input_san = st.selectbox("Select your move", [""] + san_moves)
if st.button("Play Move") and move_input_san:
    move_uci = san_to_uci[move_input_san]
    move = chess.Move.from_uci(move_uci)
    if move in st.session_state.board.legal_moves:
        st.session_state.board.push(move)
        st.session_state.move_history.append(move.uci())
        # AI move
        ai_config = {
            "ai_type": ai_type,
            "depth": ai_depth,
            "max_depth": ai_depth,
            "move_ordering_enabled": False,
            "quiescence_enabled": True,
            "move_time_limit": 0,
            "pst_enabled": True,
            "pst_weight": 1.0,
            "engine": "viper",
            "ruleset": "default_evaluation"
        }
        ai_move = st.session_state.engine.search(
            st.session_state.board, st.session_state.board.turn, **ai_config
        )
        if isinstance(ai_move, chess.Move):
            ai_move_san = st.session_state.board.san(ai_move)  # Get SAN before pushing
            st.session_state.board.push(ai_move)
            st.session_state.move_history.append(ai_move.uci())
            st.success(f"AI played: {ai_move_san}")
        else:
            st.info("AI has no legal moves or search did not return a valid move.")
    else:
        st.error("Illegal move.")

# --- Move history ---
st.write("### Move History")
# Show move history in SAN for readability, with move numbers
board_tmp = chess.Board()
san_history = []
for idx, uci in enumerate(st.session_state.move_history):
    move = chess.Move.from_uci(uci)
    san = board_tmp.san(move)
    if board_tmp.turn == chess.WHITE:
        san_history.append(f"{(idx//2)+1}. {san}")
    else:
        san_history.append(san)
    board_tmp.push(move)
st.write(" ".join(san_history))

# --- Game over check ---
if st.session_state.board.is_game_over():
    st.write(f"**Game Over:** {st.session_state.board.result()}")