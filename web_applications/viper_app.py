# viper.app.py
# A simplified Streamlit app that converts the pygam version into a portable lightweight web app
# run with: streamlit run "s:/Maker Stuff/Programming/AI and Machine Learning/ViperChessEngine/viper_chess_engine/web_applications/viper_app.py"
# TODO How to modify to match chess_game but can be served in a browser with a different game mechanic than pygames infinite loop.


import streamlit as st
import yaml
import chess
import chess.svg
import random  # Using random move selection for low engine power
# Use st.components.v1 as the correct components API
import streamlit.components.v1 as components

def load_config(config_path="web_applications/viper_app.yaml"):
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

# Load configuration
config = load_config()
st.set_page_config(
    page_title=config["streamlit"]["title"],
    page_icon=config["streamlit"].get("page_icon", "♟️"),
    layout=config["streamlit"].get("layout", "wide")
)
st.title(config["streamlit"]["title"])

# Initialize board in session state if not exists
if 'board' not in st.session_state:
    st.session_state.board = chess.Board()

# Sidebar options for (limited) engine configuration
st.sidebar.header("AI Options")
# Lower engine power settings for the browser; only allow shallow depth or random moves.
search_depth = st.sidebar.slider("Engine Search Depth", min_value=1, max_value=4, value=2)
# (For now, we support a minimal AI based on random moves.)
st.sidebar.info("For web use, engine power is intentionally limited.")

# Function to render board using chess.svg and Streamlit's HTML component
def render_board(board):
    board_svg = chess.svg.board(board, size=400)
    # Use the correct Streamlit components API
    components.html(board_svg, height=420, scrolling=False)

st.subheader("Current Board")
render_board(st.session_state.board)

# Section for human move input
st.subheader("Your Move (UCI format)")
player_move = st.text_input("Enter your move", value="")
if st.button("Play Move"):
    # Attempt to parse and play the human move if legal
    try:
        move = chess.Move.from_uci(player_move.strip())
        if move in st.session_state.board.legal_moves:
            st.session_state.board.push(move)
            st.success(f"Player move {player_move} played.")
            # AI move using a minimal strategy (random legal move)
            legal_moves = list(st.session_state.board.legal_moves)
            if legal_moves:
                # For web, we limit AI power; deeper searches are disabled.
                ai_move = random.choice(legal_moves)
                st.session_state.board.push(ai_move)
                st.success(f"AI responds with: {ai_move.uci()}")
            else:
                st.warning("No legal moves left for making an AI move.")
        else:
            st.error("Illegal move. Please try again.")
    except Exception as e:
        st.error(f"Error processing move: {e}")
    render_board(st.session_state.board)

# Section for FEN input to set a custom position
st.subheader("Set Position via FEN")
fen_input = st.text_input("Enter FEN string", value="startpos")
if st.button("Set Position"):
    try:
        # If "startpos", initiate standard starting position.
        if fen_input.strip().lower() == "startpos":
            st.session_state.board = chess.Board()
        else:
            st.session_state.board = chess.Board(fen_input)
        st.success("Board updated successfully.")
    except Exception as e:
        st.error(f"Invalid FEN: {e}")
    render_board(st.session_state.board)

# Section to evaluate the current position (placeholder for deeper evaluation)
st.subheader("Evaluate Position")
if st.button("Evaluate"):
    # Placeholder: In production, call a proper evaluation function with limited depth.
    # Here, we simply compute a naive score (material balance) as an example.
    board = st.session_state.board
    score = sum([piece.piece_type for piece in board.piece_map().values()])
    st.write(f"Evaluation Score: {score:.1f}")
