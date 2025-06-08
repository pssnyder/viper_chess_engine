# evaluation_engine.py

""" Viper Evaluation Engine
This module implements the evaluation engine for the Viper chess AI.
It provides various search algorithms, evaluation functions, and move ordering
"""
import chess
import yaml
import random
import logging
import os
import threading
from typing import Optional, Callable, Dict, Any
from engine_utilities.piece_square_tables import PieceSquareTables
from engine_utilities.time_manager import TimeManager
from engine_utilities.opening_book import OpeningBook
from collections import OrderedDict

# At module level, define a single logger for this file
evaluation_logger = logging.getLogger("evaluation_engine")
evaluation_logger.setLevel(logging.DEBUG)
if not evaluation_logger.handlers:
    if not os.path.exists('logging'):
        os.makedirs('logging', exist_ok=True)
    from logging.handlers import RotatingFileHandler
    log_file_path = "logging/evaluation_engine.log"
    file_handler = RotatingFileHandler(
        log_file_path,
        maxBytes=10*1024*1024,
        backupCount=3,
        delay=True
    )
    formatter = logging.Formatter(
        '%(asctime)s | %(funcName)-15s | %(message)s',
        datefmt='%H:%M:%S'
    )
    file_handler.setFormatter(formatter)
    evaluation_logger.addHandler(file_handler)
    evaluation_logger.propagate = False

class LimitedSizeDict(OrderedDict):
    def __init__(self, *args, maxlen=100000, **kwargs):
        self.maxlen = maxlen
        super().__init__(*args, **kwargs)
    def __setitem__(self, key, value):
        if key in self:
            self.move_to_end(key)
        super().__setitem__(key, value)
        if len(self) > self.maxlen:
            oldest = next(iter(self))
            del self[oldest]

class EvaluationEngine:
    def __init__(self, board: chess.Board = chess.Board(), player: chess.Color = chess.WHITE, ai_config=None):
        self.board = board
        self.current_player = player
        self.time_manager = TimeManager()
        self.opening_book = OpeningBook()

        # Variable init
        self.nodes_searched = 0
        self.transposition_table = LimitedSizeDict(maxlen=100000)  # Limit size to avoid memory leak
        self.killer_moves = [[None, None] for _ in range(50)]
        self.history_table = {}
        self.counter_moves = {}

        # Default piece values
        self.piece_values = {
            chess.KING: 0.0,
            chess.QUEEN: 9.0,
            chess.ROOK: 5.0,
            chess.BISHOP: 3.25,
            chess.KNIGHT: 3.0,
            chess.PAWN: 1.0
        }

        # Load configuration with error handling
        try:
            with open("config.yaml") as f:
                self.config = yaml.safe_load(f)
        except Exception as e:
            print(f"Error loading config: {e}")

        # Performance settings
        self.hash_size = self.config.get('performance', {}).get('hash_size', 1024)
        self.threads = self.config.get('performance', {}).get('thread_limit', 1)

        # Reset engine for new game
        self.history_table.clear()
        self.transposition_table.clear()
        self.nodes_searched = 0

        # Enable logging
        self.logging_enabled = self.config.get('debug', {}).get('enable_logging', False)
        self.show_thoughts = self.config.get('debug', {}).get('show_thinking', False)
        self.logger = evaluation_logger  # Use the module-level logger
        if self.logging_enabled:
            self.logger.debug("Logging enabled for Evaluation Engine")
        else:
            self.show_thoughts = False

        # Use provided ai_config or fetch from config for this player
        self.ai_config = self._ensure_ai_config(ai_config, player)

        # Initialize Engine for this color AI
        self.configure_for_side(self.board, self.ai_config)

        # Initialize piece-square tables
        if self.pst_enabled:
            try:
                self.pst = PieceSquareTables()
            except Exception as e:
                print(f"Warning: Could not initialize PST: {e}")
                self.pst = None

        # Strict draw prevention setting
        self.strict_draw_prevention = self.config.get('game_config', {}).get('strict_draw_prevention', False)

    # =================================
    # ==== EVALUATOR CONFIGURATION ====   

    def _ensure_ai_config(self, ai_config, player):
        """Ensure ai_config is a dict with required keys and defaults."""
        if ai_config is None or not isinstance(ai_config, dict):
            ai_config = self._get_ai_config('white_ai_config' if player == chess.WHITE else 'black_ai_config')
        # Defensive: ensure required keys exist
        if 'ai_type' not in ai_config:
            ai_config['ai_type'] = 'random'
        if 'depth' not in ai_config:
            ai_config['depth'] = 1
        if 'max_depth' not in ai_config:
            ai_config['max_depth'] = ai_config['depth'] + 1
        return ai_config

    def _get_ai_config(self, player_config: str):
        """Extract this bots AI configuration"""
        if player_config not in ['white_ai_config', 'black_ai_config']:
            raise ValueError("player_color for config retrieval must be 'white' or 'black'")
        if (f'{player_config}_ai_config' not in self.config):
            raise KeyError(f"AI configuration for {player_config} not found in config")
        if self.config[f'{player_config}_ai_config'] is None:
            raise ValueError(f"AI configuration for {player_config} is None, please check your config file")
        return {
            'exclude_from_metrics': self.config.get(f'{player_config}_ai_config', {}).get('exclude_from_metrics', False),
            'ai_type': self.config.get(f'{player_config}_ai_config', {}).get('ai_type', 'random'),
            'ai_color': player_config,
            'depth': self.config.get(f'{player_config}_ai_config', {}).get('depth', 1),
            'max_depth': self.config.get('performance', {}).get('max_depth', 2),
            'solutions_enabled': self.config.get(f'{player_config}_ai_config', {}).get('use_solutions', False),
            'pst_enabled': self.config.get(f'{player_config}_ai_config', {}).get('pst', False),
            'pst_weight': self.config.get(f'{player_config}_ai_config', {}).get('pst_weight', 1.0),
            'move_ordering_enabled': self.config.get(f'{player_config}_ai_config', {}).get('move_ordering', False),
            'quiescence_enabled': self.config.get(f'{player_config}_ai_config', {}).get('quiescence', False),
            'move_time_limit': self.config.get(f'{player_config}_ai_config', {}).get('time_limit', 0),
            'engine': self.config.get(f'{player_config}_ai_config', {}).get('engine', 'viper'),
            'ruleset': self.config.get(f'{player_config}_ai_config', {}).get('ruleset', 'default_evaluation'),
            'scoring_modifier': self.config.get(f'{player_config}_ai_config', {}).get('scoring_modifier', 1.0)
        }

    def configure_for_side(self, board: chess.Board, ai_config: dict):
        """Configure evaluation engine with side-specific settings"""
        configuration_board = board # Point the local working board to the board passed in
        if ai_config is not None:
            self.ai_config = ai_config
        elif self.ai_config is None:
            # Fallback to default configuration
            self.ai_config = self._get_ai_config('white_ai_config' if configuration_board.turn == chess.WHITE else 'black_ai_config')

        # Update AI configuration for this bot
        self.ai_type = self.ai_config.get('ai_type','random')
        self.ai_color = self.ai_config.get('ai_color', 'white')
        self.depth = self.ai_config.get('depth', 1)
        self.max_depth = self.ai_config.get('max_depth', 2)
        self.solutions_enabled = self.ai_config.get('solutions_enabled', False)
        self.move_ordering_enabled = self.ai_config.get('move_ordering_enabled', False)
        self.quiescence_enabled = self.ai_config.get('quiescence_enabled', False)
        self.move_time_limit = self.ai_config.get('move_time_limit', 0)
        self.pst_enabled = self.ai_config.get('pst_enabled', False)
        self.pst_weight = self.ai_config.get('pst_weight', 1.0)
        self.eval_engine = self.ai_config.get('engine','viper')
        self.ruleset = self.ai_config.get('ruleset','default_evaluation')
        self.scoring_modifier = self.ai_config.get('scoring_modifier',1.0)
        if self.logging_enabled and self.logger:
            self.logger.debug(f"Configuring AI for {self.ai_color} with type={self.ai_type}, depth={self.depth}/{self.max_depth}, solutions={self.solutions_enabled}, move_ordering={self.move_ordering_enabled}, "
                             f"quiescence={self.quiescence_enabled}, move_time={self.move_time_limit}, pst_enabled={self.pst_enabled}, pst_weight={self.pst_weight}, engine={self.eval_engine}, scoring_mod={self.scoring_modifier}, ruleset={self.ruleset}")
        if self.move_time_limit == 0:
            self.time_control = {"infinite": True}
        else:
            self.time_control = {"movetime": self.move_time_limit}
        # Update piece-square table settings
        if hasattr(self, 'pst') and self.pst:
            self.pst_weight = self.ai_config.get('pst_weight', 1.0)
            self.pst_enabled = self.ai_config.get('pst_enabled', True)
        self.eval_engine = self.ai_config.get('engine','None')
        self.ruleset = self.ai_config.get('ruleset','None')

        # Debug output for configuration changes
        if self.show_thoughts and self.logger:
            self.logger.debug(f"AI configured for {'White' if self.ai_color == 'white' else 'Black'}: type={self.ai_type} depth={self.depth}, ordering={self.move_ordering_enabled}, "
                             f"quiescence={self.quiescence_enabled}, pst_enabled={self.pst_enabled} pst_weight={self.pst_weight}")

    def reset(self, board: chess.Board):
        """Reset the evaluation engine to its initial state"""
        self.board = board.copy()
        self.current_player = chess.WHITE if board.turn else chess.BLACK
        self.nodes_searched = 0
        self.transposition_table.clear()
        self.killer_moves = [[None, None] for _ in range(50)]
        self.history_table.clear()
        self.counter_moves.clear()
        if self.show_thoughts and self.logger:
            self.logger.debug(f"Evaluation engine for {self.ai_color} reset to initial state.")
        
        # Reconfigure for the current player
        self.configure_for_side(self.board, self.ai_config)

    def _is_draw_condition(self, board):
        """Check if the current board position is a draw condition"""
        # Check for threefold repetition
        if board.can_claim_threefold_repetition():
            return True
        # Check for fifty-move rule
        if board.can_claim_fifty_moves():
            return True
        # Check for seventy-five move rule (since July 2014 rules)
        if board.is_seventyfive_moves():
            return True
        return False
    
    # =================================
    # ===== MOVE SEARCH HANDLER =======

    def sync_with_game_board(self, game_board: chess.Board):
        """Synchronize the evaluation engine's board with the game board."""
        if not isinstance(game_board, chess.Board) or not game_board.is_valid():
            if self.logger:
                self.logger.error(f"Invalid game board state detected during sync! | FEN: {getattr(game_board, 'fen', lambda: 'N/A')()}")
            return False
        self.board = game_board.copy()
        self.game_board = game_board.copy()
        return True

    def has_game_board_changed(self):
        """Check if the game board has changed since last sync."""
        if self.game_board is None:
            return False
        return self.board.fen() != self.game_board.fen()

    def search(self, board: chess.Board, player: chess.Color, ai_config: dict = {}, stop_callback=None):
        """Searches for the best valid move using the AI's configured algorithm.
        NOTE: This engine instance is already configured for its color. Only update board state.
        """
        self.sync_with_game_board(board)  # Ensure synchronization before starting search
        best_move = None
        self.board = board.copy()  # Ensure we work on a copy of the board
        self.current_player = chess.WHITE if player == chess.WHITE else chess.BLACK

        # Always use self.ai_config, but allow override if a valid dict is passed
        self.ai_config = self._ensure_ai_config(ai_config, player)
        self.ai_type = self.ai_config.get('ai_type', 'random')
        self.depth = self.ai_config.get('depth', 1)
        self.max_depth = self.ai_config.get('max_depth', 2)

        # Start move evaluation
        if self.show_thoughts:
            self.logger.debug(f"== EVALUATION (Player: {'White' if player == chess.WHITE else 'Black'}) == | AI Type: {self.ai_config['ai_type']} | Depth: {self.ai_config['depth']} ==")

        # Check if the position is already in our transposition table
        trans_move, _ = self.get_transposition_move(board, self.depth)
        if trans_move:
            if self.show_thoughts and self.logger:
                self.logger.debug(f"Transposition table hit: {trans_move} | FEN: {board.fen()}")
            return trans_move
        # AI Search Type Selection
        elif self.ai_type == 'deepsearch':
            # Use deep search with iterative deepening time control
            if self.show_thoughts and self.logger:
                self.logger.debug("Using deep search with iterative deepening time control")
            best_move = self._deep_search(self.board.copy(), self.depth, self.time_control, stop_callback=self.time_manager.should_stop)
        elif self.ai_type == 'minimax':
            # Use minimax algorithm with alpha-beta pruning
            if self.show_thoughts and self.logger:
                self.logger.debug("Using minimax algorithm with alpha-beta pruning")
            best_move = self._minimax_search(self.board.copy(), self.depth, -float('inf'), float('inf'), self.current_player == chess.WHITE, stop_callback=self.time_manager.should_stop)
        elif self.ai_type == 'negamax':
            # Use negamax algorithm with alpha-beta pruning
            if self.show_thoughts and self.logger:
                self.logger.debug("Using negamax algorithm with alpha-beta pruning")
            best_move = self._negamax_search(self.board.copy(), self.depth, -float('inf'), float('inf'), stop_callback=self.time_manager.should_stop)
        elif self.ai_type == 'negascout':
            # Use negascout algorithm with alpha-beta pruning
            if self.show_thoughts and self.logger:
                self.logger.debug("Using negascout algorithm with alpha-beta pruning")
            best_move = self._negascout(self.board.copy(), self.depth, -float('inf'), float('inf'), stop_callback=self.time_manager.should_stop)
        elif self.ai_type == 'lookahead':
            # Use lookahead search with static depth
            if self.show_thoughts and self.logger:
                self.logger.debug("Using lookahead search with static depth")
            best_move = self._lookahead_search(self.board.copy(), self.depth, -float('inf'), float('inf'), stop_callback=self.time_manager.should_stop)
        elif self.ai_type == 'simple_search':
            # Use simple 1-ply search algorithm with special features available
            if self.show_thoughts and self.logger:
                self.logger.debug("Using simple search algorithm with special features")
            best_move = self._simple_search(self.board.copy())
        elif self.ai_type == 'evaluation_only':
            # Use evaluation only with no special features (no depth, no quiescence, no move ordering)
            if self.show_thoughts and self.logger:
                self.logger.debug("Using evaluation only with no special features")
            best_move = self._evaluation_only(self.board.copy())
        elif self.ai_type == 'random':
            # Select a random move from the available moves
            if self.show_thoughts and self.logger:
                self.logger.debug("Using random search selection")
            best_move = self._random_search(self.board.copy(), self.current_player)
        else: 
            # make a random move if no AI type is specified
            if self.show_thoughts and self.logger:
                self.logger.debug("No AI type specified, using random search selection")
            best_move = self._random_search(self.board.copy(), self.current_player)

        # save the best move to the transposition table
        if best_move:
            if isinstance(best_move, chess.Move) or best_move is None:
                self.update_transposition_table(self.board, self.depth, best_move, self.evaluate_position(self.board))
        # Enforce strict draw prevention before returning
        if self.strict_draw_prevention:
            best_move = self._enforce_strict_draw_prevention(self.board, best_move if isinstance(best_move, chess.Move) or best_move is None else None)
        
        # Validate the move before returning
        if isinstance(best_move, chess.Move) and best_move not in self.board.legal_moves:
            if self.logger:
                self.logger.error(f"Invalid move generated: {best_move} | FEN: {self.board.fen()}")
            return None

        return best_move if best_move else None

    # =================================
    # ===== EVALUATION FUNCTIONS ======

    def evaluate_position(self, board: chess.Board):
        """Calculate base position evaluation"""
        positional_evaluation_board = board.copy()  # Work on a copy of the board
        if not isinstance(positional_evaluation_board, chess.Board):
            if self.logger:
                self.logger.error(f"Invalid board type when evaluating position: {type(positional_evaluation_board)} | Expected chess.Board | FEN: {positional_evaluation_board.fen() if hasattr(positional_evaluation_board, 'fen') else 'N/A'}")
            return 0.0
        if not positional_evaluation_board.is_valid():
            if self.logger:
                self.logger.error(f"evaluate_position: Invalid board state for: {chess.WHITE if positional_evaluation_board.turn else chess.BLACK} | FEN: {positional_evaluation_board.fen()}")
            return 0.0
        score = 0.0
        white_score = 0.0
        black_score = 0.0
        try:
            white_score = self._calculate_score(positional_evaluation_board, chess.WHITE)
            black_score = self._calculate_score(positional_evaluation_board, chess.BLACK)
            score = white_score - black_score
            if self.logging_enabled and self.logger:
                self.logger.debug(f"Position evaluation: {score:.3f} | FEN: {positional_evaluation_board.fen()}")
        except Exception:
            # Fallback to simple material evaluation
            white_score = self._material_score(positional_evaluation_board, chess.WHITE)
            black_score = self._material_score(positional_evaluation_board, chess.BLACK)
            score = white_score - black_score
            if self.logging_enabled and self.logger:
                self.logger.error(f"Using fallback material evaluation: {score:.3f} | FEN: {positional_evaluation_board.fen()}")
        return score if score is not None else 0.0

    def evaluate_position_from_perspective(self, board: chess.Board, player: chess.Color):
        """Calculate position evaluation from specified player's perspective"""
        # Add assertion and logging for player
        perspective_evaluation_board = board.copy()  # Work on a copy of the board
        if not isinstance(player, chess.Color):
            if self.logger:
                self.logger.error(f"Invalid player type when evaluating from perspective: {type(player)} | Expected chess.Color | FEN: {perspective_evaluation_board.fen() if hasattr(perspective_evaluation_board, 'fen') else 'N/A'}")
            return 0.0
        if not isinstance(perspective_evaluation_board, chess.Board):
            if self.logger:
                self.logger.error(f"Invalid board type when evaluating from perspective: {type(perspective_evaluation_board)} | Expected chess.Board | FEN: {perspective_evaluation_board.fen() if hasattr(perspective_evaluation_board, 'fen') else 'N/A'}")
            return 0.0
        if perspective_evaluation_board.turn != player:
            if self.logger:
                self.logger.warning(f"Board turn does not match player when evaluating from perspective (may be negating for algorithm): {perspective_evaluation_board.turn} vs {player} | FEN: {perspective_evaluation_board.fen()}")
        if not perspective_evaluation_board.is_valid():
            if self.logger:
                self.logger.error(f"Invalid board state, cannot evaluate from perspective: {chess.WHITE if perspective_evaluation_board.turn else chess.BLACK} | FEN: {perspective_evaluation_board.fen()}")
            return 0.0
        if player not in (chess.WHITE, chess.BLACK):
            if self.logger:
                self.logger.error(f"Invalid player value when evaluating from perspective: {player} | FEN: {perspective_evaluation_board.fen()}")
            return 0.0

        score = 0.0
        player_color = 'white' if player == chess.WHITE else 'black'
        try:
            white_score = self._calculate_score(perspective_evaluation_board, chess.WHITE)
            black_score = self._calculate_score(perspective_evaluation_board, chess.BLACK)
            white_perspective_score = white_score - black_score
            black_perspective_score = black_score - white_score
            score = float(white_perspective_score if perspective_evaluation_board.turn else black_perspective_score)
            if self.logging_enabled and self.logger:
                self.logger.debug(f"Position evaluation from {player_color} perspective: {score:.3f} | FEN: {perspective_evaluation_board.fen()}")
            return score if score is not None else 0.0
        except Exception as e:
            if self.logging_enabled and self.logger:
                self.logger.error(f"Error evaluating position from perspective {player_color}: {e}")
            return 0.0  # Fallback to neutral score

    def evaluate_move(self, board: chess.Board, move: chess.Move = chess.Move.null()):
        """Quick evaluation of individual move on overall eval"""
        score = 0.0
        move_evaluation_board = board.copy()  # Work on a copy of the board
        if move not in board.legal_moves:  # Add validation check
            if self.logging_enabled and self.logger:
                self.logger.error(f"Attempted evaluation of an illegal move: {move} | FEN: {board.fen()}")
            return -9999999999 # never play illegal moves
        if move is not None:
            move_evaluation_board.push(move)
            score = self.evaluate_position(move_evaluation_board)
        if self.show_thoughts and self.logger:
            self.logger.debug("Exploring the move: %s | Evaluation: %.3f | FEN: %s", move, score, board.fen())
        move_evaluation_board.pop()
        return score if score is not None else 0.0

    # ===================================
    # ======= HELPER FUNCTIONS ==========
    
    def order_moves(self, board: chess.Board, moves, hash_move: Optional[chess.Move] = None, depth: int = 0):
        """Order moves for better alpha-beta pruning efficiency"""
        # Ensure moves is a list, not a single Move
        if isinstance(moves, chess.Move):
            moves = [moves]
        move_scores = []
        move_ordering_board = board.copy()
        if not isinstance(move_ordering_board, chess.Board):
            if self.logger:
                self.logger.error(f"Invalid board type when ordering moves: {type(move_ordering_board)} | Expected chess.Board | FEN: {move_ordering_board.fen() if hasattr(move_ordering_board, 'fen') else 'N/A'}")
            return []
        if not isinstance(moves, list) or moves is None or len(moves) == 0:
            moves = list(board.legal_moves)  # Ensure we have legal moves to work with
        score = 0.0  # Initialize score to avoid unbound variable error
        for move in moves:
            # Checks and Mates
            if move not in move_ordering_board.legal_moves :  # Add validation check
                return [] # ensure illegal move is never played
            move_ordering_board.push(move)
            # Check if this move gives checkmate!
            if move_ordering_board.is_checkmate():
                move_ordering_board.pop()
                return [move for move in moves if move in move_ordering_board.legal_moves]
            # Calculate score for move
            score = self._order_move_score(move_ordering_board, move, hash_move, depth)
            if score is None:
                score = 0.0
            move_scores.append((move, score))
            move_ordering_board.pop()
        if self.show_thoughts and self.logger:
            self.logger.debug(f"Ordered moves at depth {depth}: {[f'{move} ({score:.2f})' for move, score in move_scores]} | FEN: {move_ordering_board.fen()}")
        # Sort moves by score in descending order
        move_scores.sort(key=lambda x: x[1], reverse=True)
        
        if self.logging_enabled and self.logger:
            self.logger.debug(f"Ordered moves at depth {depth}: {[f'{move} ({score:.2f})' for move, score in move_scores]}")
        
        # Return just the moves, not the scores
        return [move for move, _ in move_scores]

    def _order_move_score(self, board: chess.Board, move: chess.Move, hash_move: Optional[chess.Move], depth: int):
        """Score a move for ordering"""
        # Base score
        score = 0.0
        order_move_score_board = board.copy()  # Work on a copy of the board
        if not isinstance(order_move_score_board, chess.Board):
            if self.logger:
                self.logger.error(f"Invalid board type when scoring move: {type(order_move_score_board)} | Expected chess.Board | FEN: {order_move_score_board.fen() if hasattr(order_move_score_board, 'fen') else 'N/A'}")
            return 0.0
        # Hash move or checkmate gets highest priority
        if hash_move and move == hash_move:
            return self.config.get('evaluation', {}).get('hash_move_bonus', 5000.0)

        # Captures scored by MVV-LVA (Most Valuable Victim - Least Valuable Aggressor)
        if order_move_score_board.is_capture(move):
            victim_piece = order_move_score_board.piece_at(move.to_square)
            aggressor_piece = order_move_score_board.piece_at(move.from_square)
            if victim_piece is None or aggressor_piece is None:
                return 0.0
            # Most valuable victim (queen=9, rook=5, etc.) minus least valuable aggressor
            victim_value = self.piece_values.get(victim_piece.piece_type, 0)
            aggressor_value = self.piece_values.get(aggressor_piece.piece_type, 0)

            # MVV-LVA formula: 10 * victim_value - aggressor_value
            score += self.config.get('evaluation', {}).get('capture_move_bonus', 4000.0) + 10 * victim_value - aggressor_value

            # Bonus for promotions
            if move.promotion:
                score += float(self.config.get('evaluation', {}).get('promotion_move_bonus', 3000.0)) + 100  # High score for promotion captures

            return score if score is not None else 0.0

        # Killer moves (non-capture moves that caused a beta cutoff)
        if depth in self.killer_moves and move in self.killer_moves[depth]:
            return self.config.get('evaluation', {}).get('killer_move_bonus', 2000.0)

        # Counter moves (moves that are good responses to the previous move)
        last_move = order_move_score_board.peek() if order_move_score_board.move_stack else None
        if last_move:
            counter_key = (last_move.from_square, last_move.to_square)
            if counter_key in self.counter_moves and self.counter_moves[counter_key] == move:
                return self.config.get('evaluation', {}).get('counter_move_bonus', 1000.0)

        # History heuristic (moves that have caused cutoffs in similar positions)
        piece = order_move_score_board.piece_at(move.from_square)
        if piece is None:
            return 0.0
        history_key = (piece.piece_type, move.from_square, move.to_square)
        history_score = self.history_table.get(history_key, 0)

        # Promotions (already handled in captures, but add for non-capture promotions)
        if move.promotion:
            score += float(self.config.get('evaluation', {}).get('promotion_move_bonus', 3000.0))

        # Checks and Mates
        if move not in order_move_score_board.legal_moves:  # Add validation check
            return -1000000.0 # ensure legal move is never played
        
        # prepare the evaluation by pushing the move
        order_move_score_board.push(move)

        # Check if this move gives checkmate!
        if order_move_score_board.is_checkmate():
            order_move_score_board.pop()
            return self.config.get('evaluation', {}).get('checkmate_move_bonus', 1000000.0) * 1000.0

        if order_move_score_board.is_check():
            score += float(self.config.get(self.ruleset, {}).get('check_move_bonus', 500.0))

        # Add move data to history table
        self.update_history_score(order_move_score_board, move, depth)

        return score if score is not None else 0.0
    
    def _quiescence_search(self, board: chess.Board, alpha: float, beta: float, depth: int = 0, stop_callback: Optional[Callable[[], bool]] = None):
        """Quiescence search to avoid horizon effect."""
        if stop_callback and stop_callback():
            return self.evaluate_position_from_perspective(board, chess.WHITE if board.turn else chess.BLACK)
        quiescence_board = board.copy()  # Work on a copy of the board
        if not isinstance(quiescence_board, chess.Board):   
            if self.logger:
                self.logger.error(f"Invalid board type when performing quiescence search: {type(quiescence_board)} | Expected chess.Board | FEN: {quiescence_board.fen() if hasattr(quiescence_board, 'fen') else 'N/A'}")
            return 0.0
        def mvv_lva_score(board: chess.Board, move: chess.Move):
            """Most Valuable Victim - Least Valuable Attacker score"""
            score = 0.0
            mvv_lva_board = board.copy()  # Work on a copy of the board
            if not isinstance(mvv_lva_board, chess.Board):
                if self.logger:
                    self.logger.error(f"Invalid board type when calculating MVV-LVA score: {type(mvv_lva_board)} | Expected chess.Board | FEN: {mvv_lva_board.fen() if hasattr(mvv_lva_board, 'fen') else 'N/A'}")
                return 0.0
            piece_values = self.piece_values
            victim_piece = mvv_lva_board.piece_at(move.to_square)
            attacker_piece = mvv_lva_board.piece_at(move.from_square)
            if victim_piece is None or attacker_piece is None:
                return 0
            victim_value = piece_values[victim_piece.piece_type]
            attacker_value = piece_values[attacker_piece.piece_type]

            score = victim_value * 100 - attacker_value
            return score if score is not None else 0.0

        if depth > 2:  # Limit quiescence depth
            return self.evaluate_position_from_perspective(board, chess.WHITE if board.turn else chess.BLACK)

        stand_pat = self.evaluate_position_from_perspective(board, chess.WHITE if board.turn else chess.BLACK)
        
        if stand_pat >= beta:
            return beta
        if stand_pat > alpha:
            alpha = stand_pat

        # Only search captures and checks in quiescence
        captures = list(board.legal_moves)
        quiescence_moves = []
        for move in captures:
            if not board.is_legal(move):
                continue
            quiescence_board.push(move)
            if quiescence_board.is_checkmate() or quiescence_board.is_capture(move):
                quiescence_board.pop()
                quiescence_moves.append(move)
            quiescence_board.pop()

        # Order captures by MVV-LVA
        quiescence_moves.sort(key=lambda m: mvv_lva_score(quiescence_board, m), reverse=True)

        if self.move_ordering_enabled:
            quiescence_moves = self.order_moves(quiescence_board, quiescence_moves, depth=depth)

        for move in quiescence_moves:
            if stop_callback and stop_callback():
                break
            if move not in quiescence_board.legal_moves:
                continue
            quiescence_board.push(move)
            score = self._checkmate_threats(quiescence_board)
            if score is None:
                self.nodes_searched += 1
                score = -self._quiescence_search(quiescence_board, -beta, -alpha, depth + 1, stop_callback)
            quiescence_board.pop()
            if score >= beta:
                self.update_killer_move(move, depth)
                return beta
            if score > alpha:
                alpha = score
        
        if self.logging_enabled and self.logger:
            self.logger.debug(f"Quiescence search at depth {depth} | Alpha: {alpha} Beta: {beta} | Nodes searched: {self.nodes_searched}")
        
        return alpha
    
    def get_transposition_move(self, board: chess.Board, depth: int):
        """Get the best move from the transposition table for the current position"""
        key = board.fen()
        if key in self.transposition_table:
            entry = self.transposition_table[key]
            if entry['depth'] >= depth:
                return entry['best_move'], entry['score']
        return None, 0.0
    
    def update_transposition_table(self, board: chess.Board, depth: int, best_move: Optional[chess.Move], score: float):
        """Update the transposition table with the best move and score for the current position"""
        key = board.fen()
        if best_move is not None:
            self.transposition_table[key] = {
                'best_move': best_move,
                'depth': depth,
                'score': score
            }

    def update_killer_move(self, move, depth):
        """Update killer move table with a move that caused a beta cutoff"""
        if isinstance(self.killer_moves, list) and depth >= len(self.killer_moves):
            return
        if move not in self.killer_moves[depth]:
            self.killer_moves[depth][1] = self.killer_moves[depth][0]
            self.killer_moves[depth][0] = move

    def update_history_score(self, board, move, depth):
        """Update history heuristic score for a move that caused a beta cutoff"""
        piece = board.piece_at(move.from_square)
        if piece is None:
            return
        history_key = (piece.piece_type, move.from_square, move.to_square)

        # Update history score using depth-squared bonus
        self.history_table[history_key] = self.history_table.get(history_key, 0) + depth * depth

    def update_counter_move(self, last_move, current_move):
        """Update counter move table"""
        if last_move:
            counter_key = (last_move.from_square, last_move.to_square)
            self.counter_moves[counter_key] = current_move

    def _enforce_strict_draw_prevention(self, board: chess.Board, move: Optional[chess.Move]):
        """Enforce strict draw prevention rules to block moves that would lead to stalemate, insufficient material, or threefold repetition."""
        move = move if isinstance(move, chess.Move) else None  # Ensure move is a chess.Move object
        if not self.strict_draw_prevention or move is None:
            return move
        draw_prevention_board = board.copy()
        draw_prevention_board.push(move)
        if draw_prevention_board.is_stalemate() or draw_prevention_board.is_insufficient_material() or draw_prevention_board.is_fivefold_repetition() or draw_prevention_board.is_repetition(count=3):
            if self.show_thoughts and self.logger:
                self.logger.debug(f"Potential drawing move detected, enforcing strict draw prevention: {move} | FEN: {draw_prevention_board.fen()}")
            # Try to find a non-drawing move
            legal_moves = list(board.legal_moves)
            non_draw_moves = []
            for m in legal_moves:
                non_draw_board = board.copy()
                non_draw_board.push(m)
                if not (non_draw_board.is_stalemate() or non_draw_board.is_insufficient_material() or non_draw_board.is_fivefold_repetition() or non_draw_board.is_repetition(count=3)):
                    non_draw_moves.append(m)
            if non_draw_moves:
                chosen = random.choice(non_draw_moves)
                if self.logger:
                    self.logger.info(f"Strict draw prevention: Move {move} would result in a draw, replaced with {chosen}")
                move = chosen
            else:
                # If all moves lead to a draw, just use the original move
                move = move
                if self.logger:
                    self.logger.info(f"Strict draw prevention: All moves result in draw, playing {move}")
        return move

    # =======================================
    # ======= MAIN SEARCH ALGORITHMS ========
    
    def _random_search(self, board: chess.Board, player: chess.Color):
        """Select a random legal move from the board."""
        legal_moves = list(board.legal_moves)
        if not legal_moves:
            if self.show_thoughts and self.logger:
                self.logger.debug(f"No legal moves available for {player} | FEN: {board.fen()}")
            return None
        move = random.choice(legal_moves)
        if self.show_thoughts and self.logger:
            self.logger.debug(f"Randomly selected move: {move} | FEN: {board.fen()}")
        return move

    def _evaluation_only(self, board: chess.Board): 
        """Evaluate the current position without searching"""
        evaluation = 0.0
        evaluation_only_board = board.copy()  # Work on a copy of the board
        try:
            evaluation = self.evaluate_position(evaluation_only_board)
            if self.show_thoughts and self.logger:
                self.logger.debug(f"Evaluation only for position: {evaluation_only_board.fen()} score: {evaluation:.3f} ")
        except Exception as e:
            if self.show_thoughts and self.logger:
                self.logger.error(f"Error during evaluation only for position: {evaluation_only_board.fen()} | Error: {e}")
        return evaluation

    def _simple_search(self, board: chess.Board):
        """Simple search that evaluates all legal moves and picks the best one at 1/2 ply."""
        best_move = None
        best_score = -float('inf') if board.turn else float('inf')
        simple_search_board = board.copy()  # Work on a copy of the board
        best_move = chess.Move.null()
        best_score = -float('inf') if simple_search_board.turn else float('inf')

        # If depth is 0 or game is over, return None
        if self.depth == 0 or simple_search_board.is_game_over(claim_draw=self._is_draw_condition(simple_search_board)) and self.board.is_valid():
            return None
            
        # see if we have the best move in the transposition table
        depth = self.depth if self.depth > 0 else 1
        hash_move, hash_score = self.get_transposition_move(simple_search_board, depth)
        if hash_move:
            if self.show_thoughts and self.logger:
                self.logger.debug(f"Using transposition move: {hash_move} at depth {depth} | Evaluation: {hash_score:.3f} | FEN: {simple_search_board.fen()}")
            return hash_move, hash_score

        legal_moves = list(simple_search_board.legal_moves)
        if self.move_ordering_enabled:
            legal_moves = self.order_moves(simple_search_board, legal_moves)
        for move in legal_moves:
            score = 0.0
            if self.show_thoughts and self.logger:
                self.logger.debug(f"Simple search is evaluating move: {move} | Score: {score:.3f} | Best score: {best_score:.3f} | FEN: {simple_search_board.fen()}")
            simple_search_board.push(move)
            score = self.evaluate_position_from_perspective(simple_search_board, chess.WHITE if simple_search_board.turn else chess.BLACK)
            simple_search_board.pop()
            if score > best_score:
                best_score = score
                best_move = move
            simple_search_board.pop()  # Ensure we revert the board state after each move evaluation
            if self.show_thoughts and self.logger:
                self.logger.debug(f"Simple search is strongly considering: {best_move} | Best score: {best_score:.3f} | FEN: {simple_search_board.fen()}")
        # Enforce strict draw prevention before returning best_move:
        best_move = self._enforce_strict_draw_prevention(self.board, best_move)
        
        return best_move

    def _lookahead_search(self, board: chess.Board, depth: int, alpha: float, beta: float, stop_callback: Optional[Callable[[], bool]] = None):
        try:
            if stop_callback is not None and stop_callback():
                return None
            lookahead_board = board.copy()  # Work on a copy of the board
            if not isinstance(lookahead_board, chess.Board):    
                if self.logger:
                    self.logger.error(f"Invalid board type when performing lookahead search: {type(lookahead_board)} | Expected chess.Board | FEN: {lookahead_board.fen() if hasattr(lookahead_board, 'fen') else 'N/A'}")
                return None
            if depth == 0 or lookahead_board.is_game_over(claim_draw=self._is_draw_condition(lookahead_board)):
                if self.quiescence_enabled:
                    return self._quiescence_search(lookahead_board, alpha, beta, depth, stop_callback)
                else:
                    score = self.evaluate_position_from_perspective(lookahead_board, chess.WHITE if lookahead_board.turn else chess.BLACK)
                    if self.show_thoughts and self.logger:
                        if score is None:
                            self.logger.debug(f"Lookahead score is None at depth {depth} | FEN: {lookahead_board.fen()}")
                        else:
                            self.logger.debug(f"Lookahead score at leaf: {score} | FEN: {lookahead_board.fen()}")
                    return score
            player = chess.WHITE if lookahead_board.turn else chess.BLACK
            legal_moves = list(lookahead_board.legal_moves)
            if self.move_ordering_enabled:
                legal_moves = self.order_moves(lookahead_board, legal_moves)
            best_move = None
            best_score = -float('inf') if lookahead_board.turn else float('inf')
            best_move_board = None  # Track the board for logging
            for move in legal_moves:
                lookahead_board = board.copy()
                lookahead_board.push(move)
                try:
                    if depth - 1 == 0 or lookahead_board.is_game_over(claim_draw=self._is_draw_condition(lookahead_board)):
                        score = self.evaluate_position_from_perspective(lookahead_board, chess.WHITE if lookahead_board.turn else chess.BLACK)
                    else:
                        next_move = self._lookahead_search(lookahead_board, depth - 1, alpha, beta, stop_callback)
                        if isinstance(next_move, chess.Move):
                            lookahead_board.push(next_move)
                        score = self.evaluate_position_from_perspective(lookahead_board, chess.WHITE if lookahead_board.turn else chess.BLACK)
                except Exception as e:
                    if self.show_thoughts and self.logger:
                        self.logger.debug(f"Error during lookahead search: {e}")
                    score = self.evaluate_position_from_perspective(lookahead_board, chess.WHITE if lookahead_board.turn else chess.BLACK)
                if self.show_thoughts and self.logger:
                    if score is None:
                        self.logger.debug(f"Lookahead score is None for move {move} at depth {depth} | FEN: {lookahead_board.fen()}")
                    else:
                        self.logger.debug(f"Lookahead score for move {move}: {score} at depth {depth} | FEN: {lookahead_board.fen()}")
                if lookahead_board.turn:
                    if score > best_score:
                        best_score = score
                        best_move = move
                        best_move_board = lookahead_board.copy()
                else:
                    if score < best_score:
                        best_score = score
                        best_move = move
                        best_move_board = lookahead_board.copy()
                lookahead_board.pop()  # Ensure we revert the board state after each move evaluation
                if self.show_thoughts and self.logger:
                    self.logger.debug(f"Lookahead evaluating move: {move} | Score: {score:.3f} | Depth: {self.depth - depth} | Best score: {best_score:.3f} | FEN: {lookahead_board.fen()}")
            if self.show_thoughts and self.logger:
                # Use best_move_board if available, else board
                fen_to_log = best_move_board.fen() if best_move_board else board.fen()
                self.logger.debug(f"Lookahead is strongly considering: {best_move} | Best score: {best_score:.3f} | FEN: {fen_to_log}")
            # Enforce strict draw prevention before returning best_move:
            best_move = self._enforce_strict_draw_prevention(board, best_move)
            # Make sure the move is legal for a specific player
            if isinstance(legal_moves, chess.Move):
                legal_moves = [legal_moves]
            if player == chess.WHITE:
                legal_moves = [m for m in legal_moves if board.color_at(m.from_square) == chess.WHITE]
            else:
                legal_moves = [m for m in legal_moves if board.color_at(m.from_square) == chess.BLACK]
            if best_move is None or best_move not in legal_moves:
                if self.show_thoughts and self.logger:
                    self.logger.debug(f"Simple search found no legal moves available for {player} | FEN: {board.fen()}")
                return None
        except Exception as e:
            if self.show_thoughts and self.logger:
                self.logger.error(f"Error during lookahead search: {e} | FEN: {board.fen()}")
            return None
        
        return best_move

    def _minimax_search(self, board: chess.Board, depth: int, alpha: float, beta: float, maximizing_player: bool, stop_callback: Optional[Callable[[], bool]] = None):
        # Add base case to prevent infinite recursion
        if stop_callback is not None and stop_callback():
            return None
        minimax_board = board.copy()  # Work on a copy of the board
        if not isinstance(minimax_board, chess.Board):
            if self.logger:
                self.logger.error(f"Invalid board type when performing minimax: {type(minimax_board)} | Expected chess.Board | FEN: {minimax_board.fen() if hasattr(minimax_board, 'fen') else 'N/A'}")
            return None
        if depth == 0 or minimax_board.is_game_over(claim_draw=self._is_draw_condition(minimax_board)):
            # Use quiescence search if enabled, otherwise static evaluation
            if self.quiescence_enabled:
                return self._quiescence_search(minimax_board, alpha, beta, depth, stop_callback)
            else:
                return self.evaluate_position_from_perspective(minimax_board, chess.WHITE if minimax_board.turn else chess.BLACK)
        player = chess.WHITE if minimax_board.turn else chess.BLACK
        legal_moves = list(minimax_board.legal_moves)
        if self.move_ordering_enabled:
            legal_moves = self.order_moves(minimax_board, legal_moves)
        best_move = None
        best_move_board = None  # Track the board for logging
        if maximizing_player:
            best_score = -float('inf')
            for move in legal_moves:
                minimax_board = board.copy()
                minimax_board.push(move)
                if minimax_board.is_checkmate():
                    score = self.ai_config.get(self.ruleset, {}).get('checkmate_bonus', 1000000.0) - (self.depth - depth)
                elif minimax_board.is_stalemate() or minimax_board.is_insufficient_material():
                    score = 0.0
                else:
                    result = self._minimax_search(minimax_board, depth-1, alpha, beta, False, stop_callback)
                    if isinstance(result, (int, float)):
                        score = result
                    elif result is None:
                        score = self.evaluate_position_from_perspective(minimax_board, chess.WHITE if board.turn else chess.BLACK)
                    elif isinstance(result, chess.Move):
                        # Only push if result is a Move
                        minimax_board.push(result)
                        score = self.evaluate_position_from_perspective(minimax_board, chess.WHITE if board.turn else chess.BLACK)
                    else:
                        score = self.evaluate_position_from_perspective(minimax_board, chess.WHITE if board.turn else chess.BLACK)
                if self.show_thoughts and self.logger:
                    if score is None:
                        self.logger.debug(f"Minimax core is None for move {move} at depth {depth} | FEN: {minimax_board.fen()}")
                    else:
                        self.logger.debug(f"Minimax score for move {move}: {score} at depth {depth} | FEN: {minimax_board.fen()}")
                if score > best_score:
                    best_score = score
                    best_move = move
                    best_move_board = minimax_board.copy()
                alpha = max(alpha, score)
                if beta <= alpha:
                    self.update_killer_move(move, depth)
                    break
                minimax_board.pop()  # Ensure we revert the board state after each move evaluation
                if self.show_thoughts and self.logger:
                    self.logger.debug(f"Minimax evaluating move: {move} | Score: {score:.3f} | Depth: {self.depth - depth} | Best score: {best_score:.3f} | FEN: {minimax_board.fen()}")
            if self.show_thoughts and self.logger:
                fen_to_log = best_move_board.fen() if best_move_board else board.fen()
                self.logger.debug(f"Minimax strongly considering: {best_move} | Best score: {best_score:.3f} | FEN: {fen_to_log}")
            if depth == self.depth:
                # Enforce strict draw prevention before returning best_move:
                best_move = self._enforce_strict_draw_prevention(board, best_move)
                # Make sure the move is legal for a specific player
                if isinstance(legal_moves, chess.Move):
                    legal_moves = [legal_moves]
                if player == chess.WHITE:
                    legal_moves = [m for m in legal_moves if board.color_at(m.from_square) == chess.WHITE]
                else:
                    legal_moves = [m for m in legal_moves if board.color_at(m.from_square) == chess.BLACK]
                if best_move is None or best_move not in legal_moves:
                    if self.show_thoughts and self.logger:
                        self.logger.debug(f"Minimax found no legal moves available for {player} | FEN: {board.fen()}")
                    return None
                return best_move
            else:
                return best_score
        else:
            # Minimizing player 
            best_score = float('inf')
            for move in legal_moves:
                minimax_board = board.copy()
                minimax_board.push(move)
                if minimax_board.is_checkmate():
                    score = -self.ai_config.get(self.ruleset, {}).get('checkmate_bonus', 1000000.0) + (self.depth - depth)
                elif minimax_board.is_stalemate() or minimax_board.is_insufficient_material():
                    score = 0.0
                else:
                    result = self._minimax_search(minimax_board, depth-1, alpha, beta, True, stop_callback)
                    if isinstance(result, (int, float)):
                        score = result
                    elif result is None:
                        score = self.evaluate_position_from_perspective(minimax_board, chess.WHITE if board.turn else chess.BLACK)
                    elif isinstance(result, chess.Move):
                        minimax_board.push(result)
                        score = self.evaluate_position_from_perspective(minimax_board, chess.WHITE if board.turn else chess.BLACK)
                    else:
                        score = self.evaluate_position_from_perspective(minimax_board, chess.WHITE if board.turn else chess.BLACK)
                if score < best_score:
                    best_score = score
                    best_move = move
                    best_move_board = minimax_board.copy()
                beta = min(beta, score)
                if beta <= alpha:
                    break
                minimax_board.pop()  # Ensure we revert the board state after each move evaluation
                if self.show_thoughts and self.logger:
                    self.logger.debug(f"Minimax evaluating move tree for: {move} | Score: {score:.3f} | Best score: {best_score:.3f} | FEN: {minimax_board.fen()}")
            if self.show_thoughts and self.logger:
                fen_to_log = best_move_board.fen() if best_move_board else board.fen()
                self.logger.debug(f"Minimax is strongly considering: {best_move} | Best score: {best_score:.3f} | FEN: {fen_to_log}")
            if depth == self.depth:
                # Enforce strict draw prevention before returning best_move:
                best_move = self._enforce_strict_draw_prevention(board, best_move)
                # Make sure the move is legal for a specific player
                if isinstance(legal_moves, chess.Move):
                    legal_moves = [legal_moves]
                if player == chess.WHITE:
                    legal_moves = [m for m in legal_moves if board.color_at(m.from_square) == chess.WHITE]
                else:
                    legal_moves = [m for m in legal_moves if board.color_at(m.from_square) == chess.BLACK]
                if best_move is None or best_move not in legal_moves:
                    if self.show_thoughts and self.logger:
                        self.logger.debug(f"Minimax found no legal moves available for {player} | FEN: {board.fen()}")
                    return None
                return best_move
            else:
                return best_score

    def _negamax_search(self, board: chess.Board, depth: int, alpha: float, beta: float, stop_callback: Optional[Callable[[], bool]] = None):
        if stop_callback is not None and stop_callback():
            return None
        if self.time_manager.should_stop(depth, self.nodes_searched):
            return None
        negamax_board = board.copy()  # Work on a copy of the board
        if not isinstance(negamax_board, chess.Board):
            if self.logger:
                self.logger.error(f"Invalid board type when performing negamax: {type(negamax_board)} | Expected chess.Board | FEN: {negamax_board.fen() if hasattr(negamax_board, 'fen') else 'N/A'}")
            return None
        if depth == 0 or negamax_board.is_game_over(claim_draw=self._is_draw_condition(negamax_board)):
            # Use quiescence search if enabled, otherwise static evaluation
            if self.quiescence_enabled:
                return self._quiescence_search(negamax_board, alpha, beta, depth, stop_callback)
            else:
                return self.evaluate_position_from_perspective(negamax_board, chess.WHITE if negamax_board.turn else chess.BLACK)
        player = chess.WHITE if negamax_board.turn else chess.BLACK
        legal_moves = list(negamax_board.legal_moves)
        if self.move_ordering_enabled:
            legal_moves = self.order_moves(negamax_board, legal_moves)
        best_move = None
        best_score = -float('inf')
        for move in legal_moves:
            negamax_board = board.copy()
            negamax_board.push(move)
            if negamax_board.is_checkmate():
                score = self.ai_config.get(self.ruleset, {}).get('checkmate_bonus', 1000000.0) - (self.depth - depth)
            elif negamax_board.is_stalemate() or negamax_board.is_insufficient_material():
                score = 0.0
            else:
                # For negamax, recursively call and negate the result
                result = self._negamax_search(negamax_board, depth-1, -beta, -alpha, stop_callback)
                score = -result if isinstance(result, (int, float)) else 0.0
            if self.show_thoughts and self.logger:
                if score is None:
                    self.logger.debug(f"Negamax score is None for move {move} at depth {depth} | FEN: {negamax_board.fen()}")
                else:
                    self.logger.debug(f"Negamax score for move {move}: {score} at depth {depth} | FEN: {negamax_board.fen()}")
            negamax_board.pop()
            if score > best_score:
                best_score = score
                best_move = move
            alpha = max(alpha, score)
            if alpha >= beta:
                break
            negamax_board.pop()  # Ensure we revert the board state after each move evaluation
            if self.show_thoughts and self.logger:
                self.logger.debug(f"Negamax evaluating move: {move} | Score: {score:.3f} | Depth: {self.depth - depth} | Best score: {best_score:.3f} | FEN: {negamax_board.fen()}")
        if self.show_thoughts and self.logger:
            fen_to_log = negamax_board.fen() if negamax_board else board.fen()
            self.logger.debug(f"Negamax is strongly considering: {best_move} | Best score: {best_score:.3f} | FEN: {fen_to_log}")
        if depth == self.depth:
            # Enforce strict draw prevention before returning best_move:
            best_move = self._enforce_strict_draw_prevention(board, best_move)
            # Make sure the move is legal for a specific player
            if isinstance(legal_moves, chess.Move):
                legal_moves = [legal_moves]
            if player == chess.WHITE:
                legal_moves = [m for m in legal_moves if board.color_at(m.from_square) == chess.WHITE]
            else:
                legal_moves = [m for m in legal_moves if board.color_at(m.from_square) == chess.BLACK]
            if best_move is None or best_move not in legal_moves:
                if self.show_thoughts and self.logger:
                    self.logger.debug(f"Negamax found no legal moves available for {player} | FEN: {board.fen()}")
                return None
            return best_move
        else:
            return best_score

    def _negascout(self, board: chess.Board, depth: int, alpha: float, beta: float, stop_callback: Optional[Callable[[], bool]] = None):
        if stop_callback is not None and stop_callback():
            return None
        if self.time_manager.should_stop(depth, self.nodes_searched):
            return None
        negascout_board = board.copy()  # Work on a copy of the board
        if not isinstance(negascout_board, chess.Board):
            if self.logger:
                self.logger.error(f"Invalid board type when performing negascout: {type(negascout_board)} | Expected chess.Board | FEN: {negascout_board.fen() if hasattr(negascout_board, 'fen') else 'N/A'}")
            return None
        if depth == 0 or negascout_board.is_game_over(claim_draw=self._is_draw_condition(negascout_board)):
            # Use quiescence search if enabled, otherwise static evaluation
            if self.quiescence_enabled:
                return self._quiescence_search(negascout_board, alpha, beta, depth, stop_callback)
            else:
                return self.evaluate_position_from_perspective(negascout_board, chess.WHITE if negascout_board.turn else chess.BLACK)
        player = chess.WHITE if negascout_board.turn else chess.BLACK
        legal_moves = list(negascout_board.legal_moves)
        if self.move_ordering_enabled:
            legal_moves = self.order_moves(negascout_board, legal_moves)
        best_move = None
        best_score = -float('inf')
        first = True
        for move in legal_moves:
            negascout_board = board.copy()
            negascout_board.push(move)
            if negascout_board.is_checkmate():
                score = self.ai_config.get(self.ruleset, {}).get('checkmate_bonus', 1000000.0) - (self.depth - depth)
            elif negascout_board.is_stalemate() or negascout_board.is_insufficient_material():
                score = 0.0
            else:
                if first:
                    result = self._negascout(negascout_board, depth-1, -beta, -alpha, stop_callback)
                    score = -result if isinstance(result, (int, float)) else 0.0
                else:
                    result = self._negascout(negascout_board, depth-1, -alpha-1, -alpha, stop_callback)
                    score = -result if isinstance(result, (int, float)) else 0.0
                    # If score is in the window, do a full re-search
                    if alpha < score < beta:
                        result = self._negascout(negascout_board, depth-1, -beta, -score, stop_callback)
                        score = -result if isinstance(result, (int, float)) else 0.0
            if self.show_thoughts and self.logger:
                if score is None:
                    self.logger.debug(f"Score is None for move {move} at depth {depth} | FEN: {board.fen()}")
                else:
                    self.logger.debug(f"Score for move {move}: {score} at depth {depth} | FEN: {board.fen()}")
            negascout_board.pop()
            if score > best_score:
                best_score = score
                best_move = move
                best_move_board = board.copy()
            if score > alpha:
                alpha = score
            if alpha >= beta:
                break
            first = False
            if self.show_thoughts and self.logger:
                self.logger.debug(f"Negascout move: {move} | Score: {score:.3f} | Depth: {self.depth - depth} | Best: {best_score:.3f} | FEN: {board.fen()}")
            negascout_board.pop()  # Ensure we revert the board state after each move evaluation
        if self.show_thoughts and self.logger:
            fen_to_log = best_move_board.fen() if best_move_board else board.fen()
            self.logger.debug(f"Negascout considering: {best_move} | Best score: {best_score:.3f} | FEN: {fen_to_log}")
        if depth == self.depth:
            # Enforce strict draw prevention before returning best_move:
            best_move = self._enforce_strict_draw_prevention(board, best_move)
            # Make sure the move is legal for a specific player
            if isinstance(legal_moves, chess.Move):
                legal_moves = [legal_moves]
            if player == chess.WHITE:
                legal_moves = [m for m in legal_moves if board.color_at(m.from_square) == chess.WHITE]
            else:
                legal_moves = [m for m in legal_moves if board.color_at(m.from_square) == chess.BLACK]
            if best_move is None or best_move not in legal_moves:
                if self.show_thoughts and self.logger:
                    self.logger.debug(f"Simple search found no legal moves available for {player} | FEN: {board.fen()}")
                return None
            return best_move
        else:
            return best_score
    
    def _deep_search(self, board: chess.Board, depth: int, time_control: Dict[str, Any], stop_callback: Optional[Callable[[], bool]] = None):
        """
        Perform a search with iterative deepening, move ordering, quiescence search, and dynamic search depth.
        """
        deepsearch_board = board.copy()  # Work on a copy of the board
        dynamic_depth = self.max_depth
        current_depth = depth if depth > 0 else 1
        if stop_callback is not None and stop_callback():
            return None
        if not isinstance(deepsearch_board, chess.Board):
            if self.logger:
                self.logger.error(f"Invalid board type when performing deepsearch: {type(deepsearch_board)} | Expected chess.Board | FEN: {deepsearch_board.fen() if hasattr(deepsearch_board, 'fen') else 'N/A'}")
            return None
        self.nodes_searched = 0
        player = chess.WHITE if deepsearch_board.turn else chess.BLACK
        legal_moves = list(deepsearch_board.legal_moves)
        if not legal_moves:
            return None
        if isinstance(legal_moves, list) and len(legal_moves) == 1:
            return legal_moves[0]
        
        if time_control.get('depth'):
            max_depth = time_control['depth']
        best_move = None
        best_score = -float('inf')
        try:
            for d in range(1, max_depth + 1):
                if stop_callback is not None and stop_callback():
                    break
                if self.time_manager.should_stop(d, self.nodes_searched):
                    break
                # Dynamic search depth
                dynamic_depth = d
                new_max_depth = self.time_manager.get_dynamic_depth(d, self.max_depth, time_control, self.nodes_searched)
                if new_max_depth is None:
                    new_max_depth = d
                # Use move ordering if enabled
                if self.move_ordering_enabled:
                    legal_moves = list(deepsearch_board.legal_moves)
                    deepsearch_moves = self.order_moves(deepsearch_board, legal_moves)
                else:
                    deepsearch_moves = legal_moves
                local_best_move = None
                local_best_score = -float('inf')
                for move in deepsearch_moves:
                    deepsearch_board = board.copy()
                    deepsearch_board.push(move)
                    # Use quiescence search at leaf nodes if enabled
                    if dynamic_depth - 1 == 0 or deepsearch_board.is_game_over(claim_draw=self._is_draw_condition(deepsearch_board)):
                        # If quiescence search is enabled, perform it
                        if self.quiescence_enabled:
                            score = self._quiescence_search(deepsearch_board, -float('inf'), float('inf'), 0, stop_callback)
                        else:
                            score = self.evaluate_position_from_perspective(deepsearch_board, chess.WHITE if board.turn else chess.BLACK)
                    else:
                        # Recursively search deeper
                        result = self._deep_search(deepsearch_board, dynamic_depth - 1, time_control, stop_callback)
                        if isinstance(result, chess.Move):
                            deepsearch_board.push(result)
                            score = self.evaluate_position_from_perspective(deepsearch_board, chess.WHITE if board.turn else chess.BLACK)
                            deepsearch_board.pop()
                        elif isinstance(result, (int, float)):
                            score = result
                        else:
                            score = self.evaluate_position_from_perspective(board, chess.WHITE if board.turn else chess.BLACK)
                    if self.show_thoughts and self.logger:
                        if score is None:
                            self.logger.debug(f"Deepsearch score is None for move {move} at depth {d} | FEN: {board.fen()}")
                        else:
                            self.logger.debug(f"Deepsearch score for move {move}: {score} at depth {d} | FEN: {board.fen()}")
                    if score > local_best_score:
                        local_best_score = score
                        local_best_move = move
                    deepsearch_board.pop() # Ensure we revert the board state after each move evaluation
                    if self.show_thoughts and self.logger:
                        self.logger.debug(f"Deepsearch move: {move} | Score: {score:.3f} | Depth: {d} | Local best: {local_best_score:.3f} | FEN: {board.fen()}")
                # After searching all moves at this depth, update global best if improved
                if local_best_move is not None and (best_move is None or local_best_score > best_score):
                    best_move = local_best_move
                    best_score = local_best_score

                # Early exit if mate found
                if isinstance(best_score, (int, float)) and abs(best_score) > 9000:
                    break

                if self.show_thoughts and self.logger:
                    self.logger.debug(f"Deepsearch is at iterative deepening depth {d}: Best move: {best_move} | Score: {best_score:.3f}")

        except Exception as e:
            if self.logger:
                self.logger.debug(f"info string Search error: {e}")

        if self.show_thoughts and self.logger:
            self.logger.debug(f"Deepsearch is strongly considering: {best_move} | Best score: {best_score:.3f} | FEN: {board.fen()}")
        # Enforce strict draw prevention before returning best_move:
        best_move = self._enforce_strict_draw_prevention(board, best_move)
        # Make sure the move is legal for a specific player
        if player == chess.WHITE:
            if isinstance(legal_moves, chess.Move):
                legal_moves = [legal_moves]
            legal_moves = [m for m in legal_moves if board.color_at(m.from_square) == chess.WHITE]
        else:
            if isinstance(legal_moves, chess.Move):
                legal_moves = [legal_moves]
            legal_moves = [m for m in legal_moves if board.color_at(m.from_square) == chess.BLACK]
        if best_move is None or best_move not in legal_moves:
            if self.show_thoughts and self.logger:
                self.logger.debug(f"Simple search found no legal moves available for {player} | FEN: {board.fen()}")
            return None
        return best_move

    def _get_dynamic_depth(self, board: chess.Board, depth: int, time_control: Dict[str, Any], stop_callback: Optional[Callable[[], bool]] = None):
        """
        Determine the dynamic depth based on time control and current board state.
        """
        if stop_callback is not None and stop_callback():
            return None
        if self.time_manager.should_stop(depth, self.nodes_searched):
            return None
        dynamic_depth = depth
        dynamic_depth = self.time_manager.get_dynamic_depth(depth, self.max_depth, time_control, self.nodes_searched)
        if dynamic_depth is None:
            dynamic_depth = depth
        return dynamic_depth
    
    # ==================================
    # ====== RULE SCORING HANDLER ======
    
    def _calculate_score(self, board, color):
        """IMPROVED scoring with piece-square tables"""
        score = 0.0

        # Update the evaluator with the provided board and color before scoring
        self.board = board
        self.current_player = color

        # Get piece-square table weight from ai_config or config
        pst_weight = self.ai_config.get('pst_weight', self.config.get('white_ai_config', {}).get('pst_weight', 1.0) if color == chess.WHITE else self.config.get('black_ai_config', {}).get('pst_weight', 1.0))
        
        # Get material weight from ai_config or config
        material_weight = self.ai_config.get(self.ruleset, {}).get('material_weight', 1.0)

        # Rules included in scoring

        # Critical scoring components
        score += self.scoring_modifier * (self._checkmate_threats(board) or 0.0)
        if self.show_thoughts and self.logger:
            self.logger.debug(f"Checkmate threats score: {score:.3f} | FEN: {board.fen()}")
        score += self.scoring_modifier * (self._king_safety(board, color) or 0.0)
        if self.show_thoughts and self.logger:
            self.logger.debug(f"King safety score: {score:.3f} | FEN: {board.fen()}")
        score += self.scoring_modifier * (self._king_threat(board) or 0.0)
        if self.show_thoughts and self.logger:
            self.logger.debug(f"King threat score: {score:.3f} | FEN: {board.fen()}")
        score += self.scoring_modifier * (self._draw_scenarios(board) or 0.0)
        if self.show_thoughts and self.logger:
            self.logger.debug(f"Draw scenarios score: {score:.3f} | FEN: {board.fen()}")

        # Material and piece-square table evaluation
        score += self.scoring_modifier * material_weight * (self._material_score(board, color) or 0.0)
        if self.show_thoughts and self.logger:
            self.logger.debug(f"Material score: {score:.3f} | FEN: {board.fen()}")
        score += self.scoring_modifier * pst_weight * (self._piece_square_table_evaluation(color) or 0.0)
        if self.show_thoughts and self.logger:
            self.logger.debug(f"PST score: {score:.3f} | FEN: {board.fen()}")

        # Piece coordination and control
        piece_coordination_score = self.scoring_modifier * (self._piece_coordination(board, color) or 0.0)
        score += piece_coordination_score
        if self.show_thoughts and self.logger:
            self.logger.debug(f"Piece coordination score: {piece_coordination_score:.3f} | FEN: {board.fen()}")
        center_control_score = self.scoring_modifier * (self._center_control(board) or 0.0)
        score += center_control_score
        if self.show_thoughts and self.logger:
            self.logger.debug(f"Center control score: {center_control_score:.3f} | FEN: {board.fen()}")
        pawn_structure_score = self.scoring_modifier * (self._pawn_structure(board, color) or 0.0)
        score += pawn_structure_score
        if self.show_thoughts and self.logger:
            self.logger.debug(f"Pawn structure score: {pawn_structure_score:.3f} | FEN: {board.fen()}")
        pawn_weaknesses_score = self.scoring_modifier * (self._pawn_weaknesses(board, color) or 0.0)
        score += pawn_weaknesses_score
        if self.show_thoughts and self.logger:
            self.logger.debug(f"Pawn weaknesses score: {pawn_weaknesses_score:.3f} | FEN: {board.fen()}")
        passed_pawns_score = self.scoring_modifier * (self._passed_pawns(board, color) or 0.0)
        score += passed_pawns_score
        if self.show_thoughts and self.logger:
            self.logger.debug(f"Passed pawns score: {passed_pawns_score:.3f} | FEN: {board.fen()}")
        pawn_majority_score = self.scoring_modifier * (self._pawn_majority(board, color) or 0.0) # TODO
        score += pawn_majority_score
        if self.show_thoughts and self.logger:
            self.logger.debug(f"Pawn majority score: {pawn_majority_score:.3f} | FEN: {board.fen()}")
        bishop_pair_score = self.scoring_modifier * (self._bishop_pair(board, color) or 0.0)
        score += bishop_pair_score
        if self.show_thoughts and self.logger:
            self.logger.debug(f"Bishop pair score: {bishop_pair_score:.3f} | FEN: {board.fen()}")
        knight_pair_score = self.scoring_modifier * (self._knight_pair(board, color) or 0.0)
        score += knight_pair_score
        if self.show_thoughts and self.logger:
            self.logger.debug(f"Knight pair score: {knight_pair_score:.3f} | FEN: {board.fen()}")
        bishop_vision_score = self.scoring_modifier * (self._bishop_vision(board, color) or 0.0)
        score += bishop_vision_score
        if self.show_thoughts and self.logger:
            self.logger.debug(f"Bishop vision score: {bishop_vision_score:.3f} | FEN: {board.fen()}")
        rook_coordination_score = self.scoring_modifier * (self._rook_coordination(board, color) or 0.0)
        score += rook_coordination_score
        if self.show_thoughts and self.logger:
            self.logger.debug(f"Rook coordination score: {rook_coordination_score:.3f} | FEN: {board.fen()}")
        castling_evaluation_score = self.scoring_modifier * (self._castling_evaluation(board, color) or 0.0)
        if self.show_thoughts and self.logger:
            self.logger.debug(f"Castling evaluation score: {castling_evaluation_score:.3f} | FEN: {board.fen()}")

        # Piece development and mobility
        piece_activity_score = self.scoring_modifier * (self._piece_activity(board, color) or 0.0)
        score += piece_activity_score
        if self.show_thoughts and self.logger:
            self.logger.debug(f"Piece activity score: {piece_activity_score:.3f} | FEN: {board.fen()}")
        improved_minor_piece_activity_score = self.scoring_modifier * (self._improved_minor_piece_activity(board, color) or 0.0)
        score += improved_minor_piece_activity_score
        if self.show_thoughts and self.logger:
            self.logger.debug(f"Improved minor piece activity score: {improved_minor_piece_activity_score:.3f} | FEN: {board.fen()}")
        mobility_score = self.scoring_modifier * (self._mobility_score(board, color) or 0.0)
        score += mobility_score
        if self.show_thoughts and self.logger:
            self.logger.debug(f"Mobility score: {mobility_score:.3f} | FEN: {board.fen()}")
        undeveloped_pieces_score = self.scoring_modifier * (self._undeveloped_pieces(board, color) or 0.0)
        score += undeveloped_pieces_score
        if self.show_thoughts and self.logger:
            self.logger.debug(f"Undeveloped pieces score: {undeveloped_pieces_score:.3f} | FEN: {board.fen()}")

        # Tactical and strategic considerations
        tactical_evaluation_score = self.scoring_modifier * (self._tactical_evaluation(board) or 0.0)
        score += tactical_evaluation_score
        if self.show_thoughts and self.logger:
            self.logger.debug(f"Tactical evaluation score: {tactical_evaluation_score:.3f} | FEN: {board.fen()}")
        tempo_bonus_score = self.scoring_modifier * (self._tempo_bonus(board, color) or 0.0)
        score += tempo_bonus_score
        if self.show_thoughts and self.logger:
            self.logger.debug(f"Tempo bonus score: {tempo_bonus_score:.3f} | FEN: {board.fen()}")
        special_moves_score = self.scoring_modifier * (self._special_moves(board) or 0.0)
        score += special_moves_score
        if self.show_thoughts and self.logger:
            self.logger.debug(f"Special moves score: {special_moves_score:.3f} | FEN: {board.fen()}")
        open_files_score = self.scoring_modifier * (self._open_files(board, color) or 0.0)
        score += open_files_score
        if self.show_thoughts and self.logger:
            self.logger.debug(f"Open files score: {open_files_score:.3f} | FEN: {board.fen()}")

        return score

    # ==========================================
    # ========= RULE SCORING FUNCTIONS =========

    def _checkmate_threats(self, board):
        score = 0.0
        for move in board.legal_moves:
            board.push(move)
            if board.is_checkmate():
                score += self.ai_config.get(self.ruleset, {}).get('checkmate_bonus', 0)
                break
            board.pop()
        return score
    
    def _draw_scenarios(self, board):
        score = 0.0
        if board.is_stalemate() or board.is_insufficient_material() or board.is_fivefold_repetition() or board.is_repetition(count=2):
            score += self.ai_config.get(self.ruleset, {}).get('draw_penalty', -9999999999.0)
        return score

    def _material_score(self, board, color):
        """Simple material count for given color"""
        score = 0.0
        for piece_type, value in self.piece_values.items():
            score += len(board.pieces(piece_type, color)) * value
        return score
    
    def _piece_square_table_evaluation(self, color):
        pst_score = 0.0
        if not self.pst:
            return 0.0
        for square in chess.SQUARES:
            piece = self.board.piece_at(square)
            if piece and piece.color == color:
                # Get piece-square table value for this piece on this square
                pst_value = self.pst.get_piece_value(piece, square, color)
                pst_score += pst_value / 100.0  # Convert centipawns to pawn units

        # Use correct pst_weight from ai_config or config
        pst_weight = self.ai_config.get('pst_weight', self.config.get('white_ai_config', {}).get('pst_weight', 1.0) if color == chess.WHITE else self.config.get('black_ai_config', {}).get('pst_weight', 1.0))
        return pst_score * pst_weight

    def _improved_minor_piece_activity(self, board, color):
        """
        Mobility calculation with safe squares
        """
        score = 0.0

        for square in board.pieces(chess.KNIGHT, color):
            # Count safe moves (not attacked by enemy pawns)
            safe_moves = 0
            for target in board.attacks(square):
                if not self._is_attacked_by_pawn(board, target, not color):
                    safe_moves += 1
            score += safe_moves * self.ai_config.get(self.ruleset, {}).get('knight_activity_bonus', 0.0)

        for square in board.pieces(chess.BISHOP, color):
            safe_moves = 0
            for target in board.attacks(square):
                if not self._is_attacked_by_pawn(board, target, not color):
                    safe_moves += 1
            score += safe_moves * self.ai_config.get(self.ruleset, {}).get('bishop_activity_bonus', 0.0)

        return score

    def _tempo_bonus(self, board, color):
        """If it's the player's turn and the game is still ongoing, give a small tempo bonus"""
        turn = chess.WHITE if board.turn else chess.BLACK
        if not board.is_game_over(claim_draw=self._is_draw_condition(board)) and self.board.is_valid() and turn == color:
            return self.ai_config.get(self.ruleset, {}).get('tempo_bonus', 0.0)  # Small tempo bonus
        return 0.0

    def _is_attacked_by_pawn(self, board, square, by_color):
        """Helper function to check if a square is attacked by enemy pawns"""
        if by_color == chess.WHITE:
            # White pawns attack diagonally upward
            pawn_attacks = [square - 7, square - 9]
        else:
            # Black pawns attack diagonally downward
            pawn_attacks = [square + 7, square + 9]

        for attack_square in pawn_attacks:
            if 0 <= attack_square < 64:
                piece = board.piece_at(attack_square)
                if piece and piece.piece_type == chess.PAWN and piece.color == by_color:
                    return True
        return False

    def _center_control(self, board):
        """Simple center control"""
        score = 0.0
        center = [chess.D4, chess.D5, chess.E4, chess.E5]
        for square in center:
            if board.piece_at(square) and board.piece_at(square).color == (chess.WHITE if board.turn else chess.BLACK):
                score += self.ai_config.get(self.ruleset, {}).get('center_control_bonus', 0.0)
        return score

    def _piece_activity(self, board, color):
        """Mobility and attack patterns"""
        score = 0.0

        for square in board.pieces(chess.KNIGHT, color):
            score += len(board.attacks(square)) * self.ai_config.get(self.ruleset, {}).get('knight_activity_bonus', 0.0)

        for square in board.pieces(chess.BISHOP, color):
            score += len(board.attacks(square)) * self.ai_config.get(self.ruleset, {}).get('bishop_activity_bonus', 0.0)

        return score

    def _king_safety(self, board, color):
        score = 0.0
        king = board.king(color)
        if king is None:
            return score

        direction = 1 if color == (chess.WHITE if board.turn else chess.BLACK) else -1
        shield_squares = [
            king + 8 * direction + delta
            for delta in [-1, 0, 1]
            if 0 <= king + 8 * direction + delta < 64
        ]

        for shield in shield_squares:
            if shield in chess.SQUARES:
                piece = board.piece_at(shield)
                if piece and piece.piece_type == chess.PAWN and piece.color == color:
                    score += self.ai_config.get(self.ruleset, {}).get('king_safety_bonus', 0.0)

        return score

    def _king_threat(self, board):
        """
        Evaluate if the opponent's king is under threat (in check) in the current position.
        Adds a penalty/bonus if the opponent's king is in check.
        """
        score = 0.0
        # Check if the opponent's king is in check in the current position
        if board.is_check():
            score += self.ai_config.get(self.ruleset, {}).get('king_threat_penalty', 0.0)
        return score

    def _undeveloped_pieces(self, board, color):
        score = 0.0
        undeveloped = 0.0

        starting_squares = {
            chess.WHITE: [chess.B1, chess.G1, chess.C1, chess.F1],
            chess.BLACK: [chess.B8, chess.G8, chess.C8, chess.F8]
        }

        for square in starting_squares[color]:
            piece = board.piece_at(square)
            if piece and piece.color == color and piece.piece_type in [chess.KNIGHT, chess.BISHOP]:
                undeveloped += 1

        if undeveloped > 0 and board.has_castling_rights(color):
            score = undeveloped * self.ai_config.get(self.ruleset, {}).get('undeveloped_penalty', 0.0)

        return score

    def _mobility_score(self, board, color):
        """Evaluate mobility of pieces"""
        score = 0.0
        
        # Count legal moves for each piece type
        for piece_type in [chess.PAWN, chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN]:
            for square in board.pieces(piece_type, color):
                score += len(board.attacks(square)) * self.ai_config.get(self.ruleset, {}).get('piece_mobility_bonus', 0.0)

        return score
    
    def _special_moves(self, board):
        """Evaluate special moves and opportunities"""
        score = 0.0
        
        # En passant
        if board.ep_square:
            score += self.ai_config.get(self.ruleset, {}).get('en_passant_bonus', 0.0)
        
        # Promotion opportunities
        for move in board.legal_moves:
            if move.promotion:
                score += self.ai_config.get(self.ruleset, {}).get('pawn_promotion_bonus', 0.0)
        
        return score

    def _tactical_evaluation(self, board):
        """Evaluate tactical elements"""
        score = 0.0
        
        # Captures
        for move in board.legal_moves:
            if board.is_capture(move):
                score += self.ai_config.get(self.ruleset, {}).get('capture_bonus', 0.0)
        
        # Checks
        for move in board.legal_moves:
            board.push(move)
            if board.is_check():
                score += self.ai_config.get(self.ruleset, {}).get('check_bonus', 0.0)
            board.pop()
        
        return score

    def _castling_evaluation(self, board, color):
        """Evaluate castling rights and opportunities"""
        score = 0.0

        # Helper to detect if the king has castled (king not on starting square and not just moved away)
        def has_castled(board, color):
            king_start = chess.E1 if color == chess.WHITE else chess.E8
            king_sq = board.king(color)
            # King must have moved from starting square and be on g1/g8 or c1/c8
            if color == chess.WHITE:
                return king_sq in [chess.G1, chess.C1]
            else:
                return king_sq in [chess.G8, chess.C8]

        # Bonus if has already castled
        if has_castled(board, color):
            score += self.ai_config.get(self.ruleset, {}).get('castling_bonus', 0.0)

        # Penalty if castling rights lost (important catch: will not consider the castling action itself as losing castling rights)
        if not board.has_castling_rights(color) and not has_castled(board, color):
            score += self.ai_config.get(self.ruleset, {}).get('castling_protection_penalty', 0.0)
        
        # Bonus if still has kingside or queenside castling rights
        if board.has_kingside_castling_rights(color) and board.has_queenside_castling_rights(color):
            # Full bonus if both kingside and queenside castling rights are available
            score += self.ai_config.get(self.ruleset, {}).get('castling_protection_bonus', 0.0)
        elif board.has_kingside_castling_rights(color):
            # grant a half bonus if only king side is available
            score += self.ai_config.get(self.ruleset, {}).get('castling_protection_bonus', 0.0) / 2
        elif board.has_queenside_castling_rights(color):
            # grant a half bonus if only queen side is available
            score += self.ai_config.get(self.ruleset, {}).get('castling_protection_bonus', 0.0) / 2
        return score

    def _piece_coordination(self, board, color):
        """Evaluate piece defense coordination for all pieces of the given color."""
        score = 0.0
        # For each piece of the given color
        for square in chess.SQUARES:
            piece = board.piece_at(square)
            if piece and piece.color == color:
                # For each square this piece attacks
                for target in board.attacks(square):
                    target_piece = board.piece_at(target)
                    # If the attacked square is occupied by a friendly piece, count as coordination
                    if target_piece and target_piece.color == color:
                        score += self.ai_config.get(self.ruleset, {}).get('piece_coordination_bonus', 0.0)
        return score
    
    def _pawn_structure(self, board, color):
        """Evaluate pawn structure"""
        score = 0.0
        
        # Count doubled pawns
        for square in board.pieces(chess.PAWN, color):
            file = chess.square_file(square)
            rank = chess.square_rank(square)
            if board.piece_at(chess.square(file, rank + 1)) and board.piece_at(chess.square(file, rank + 1)).piece_type == chess.PAWN:
                score -= self.ai_config.get(self.ruleset, {}).get('doubled_pawn_penalty', 0.0)
        
        # Count isolated pawns
        for square in board.pieces(chess.PAWN, color):
            file = chess.square_file(square)
            left = file - 1
            right = file + 1
            has_left = left >= 0 and any(board.piece_at(chess.square(left, r)) and board.piece_at(chess.square(left, r)).piece_type == chess.PAWN and board.piece_at(chess.square(left, r)).color == color for r in range(8))
            has_right = right < 8 and any(board.piece_at(chess.square(right, r)) and board.piece_at(chess.square(right, r)).piece_type == chess.PAWN and board.piece_at(chess.square(right, r)).color == color for r in range(8))
            if not has_left and not has_right:
                score -= self.ai_config.get(self.ruleset, {}).get('isolated_pawn_penalty', 0.0)
        
        if score > 0:
            score += self.ai_config.get(self.ruleset, {}).get('pawn_structure_bonus', 0.0)

        return score

    def _pawn_weaknesses(self, board, color):
        """Evaluate pawn weaknesses"""
        score = 0.0
        
        # Count backward pawns
        for square in board.pieces(chess.PAWN, color):
            file = chess.square_file(square)
            rank = chess.square_rank(square)
            if rank < 7 and not board.piece_at(chess.square(file, rank + 1)):
                score -= self.ai_config.get(self.ruleset, {}).get('backward_pawn_penalty', 0.0)
        
        return score

    def _pawn_majority(self, board, color):
        """Evaluate pawn majority on the queenside or kingside"""
        score = 0.0
        
        # Count pawns on each side
        white_pawns = len(board.pieces(chess.PAWN, chess.WHITE))
        black_pawns = len(board.pieces(chess.PAWN, chess.BLACK))
        
        if color == chess.WHITE:
            if white_pawns > black_pawns:
                score += self.ai_config.get(self.ruleset, {}).get('pawn_majority_bonus', 0.0)
            elif white_pawns < black_pawns:
                score -= self.ai_config.get(self.ruleset, {}).get('pawn_minority_penalty', 0.0)
        else:
            if black_pawns > white_pawns:
                score += self.ai_config.get(self.ruleset, {}).get('pawn_majority_bonus', 0.0)
            elif black_pawns < white_pawns:
                score -= self.ai_config.get(self.ruleset, {}).get('pawn_minority_penalty', 0.0)
        
        return score

    def _passed_pawns(self, board, color):
        """Basic pawn structure evaluation"""
        score = 0.0
        
        # Check for passed pawns
        for square in board.pieces(chess.PAWN, color):
            file = chess.square_file(square)
            rank = chess.square_rank(square)
            is_passed = True
            direction = 1 if color == chess.WHITE else -1
            for check_rank in range(rank + direction, 8 if color == chess.WHITE else -1, direction):
                if 0 <= check_rank < 8:
                    for check_file in [file - 1, file, file + 1]:
                        if 0 <= check_file < 8:
                            check_square = chess.square(check_file, check_rank)
                            piece = board.piece_at(check_square)
                            if piece and piece.piece_type == chess.PAWN and piece.color != color:
                                is_passed = False
                                break
                if not is_passed:
                    break
            if is_passed:
                passed_bonus = self.ai_config.get(self.ruleset, {}).get('passed_pawn_bonus', 0.0)
                score += passed_bonus if color == chess.WHITE else -passed_bonus

        return score

    def _knight_pair(self, board, color):
        """Evaluate knight pair bonus"""
        score = 0.0
        knights = [sq for sq in chess.SQUARES
                   if (piece := board.piece_at(sq)) and piece.color == color and piece.piece_type == chess.KNIGHT]
        if len(knights) >= 2:
            score += len(knights) * self.ai_config.get(self.ruleset, {}).get('knight_pair_bonus', 0.0)
        return score

    def _bishop_pair(self, board, color):
        """Evaluate bishop pair bonus"""
        score = 0.0
        bishops = [sq for sq in chess.SQUARES
                   if (piece := board.piece_at(sq)) and piece.color == color and piece.piece_type == chess.BISHOP]
        if len(bishops) >= 2:
            score += len(bishops) * self.ai_config.get(self.ruleset, {}).get('bishop_pair_bonus', 0.0)
        return score

    def _bishop_vision(self, board, color):
        """Evaluate bishop vision bonus"""
        score = 0.0
        for sq in chess.SQUARES:
            piece = board.piece_at(sq)
            if piece and piece.color == color and piece.piece_type == chess.BISHOP:
                attacks = board.attacks(sq)
                if hasattr(attacks, '__len__') and len(attacks) > 3:
                    score += self.ai_config.get(self.ruleset, {}).get('bishop_vision_bonus', 0.0)
        return score

    def _rook_coordination(self, board, color):
        """Calculate bonus for rook pairs on same file/rank"""
        score = 0.0
        rooks = [sq for sq in chess.SQUARES
                 if board.piece_at(sq) == chess.Piece(chess.ROOK, color)]
        for i in range(len(rooks)):
            for j in range(i+1, len(rooks)):
                sq1, sq2 = rooks[i], rooks[j]
                if chess.square_file(sq1) == chess.square_file(sq2):
                    score += self.ai_config.get(self.ruleset, {}).get('stacked_rooks_bonus', 0.0)
                if chess.square_rank(sq1) == chess.square_rank(sq2):
                    score += self.ai_config.get(self.ruleset, {}).get('coordinated_rooks_bonus', 0.0)
                if chess.square_rank(sq1) == 6 or chess.square_rank(sq2) == 6:
                    score += self.ai_config.get(self.ruleset, {}).get('rook_position_bonus', 0.0)
        return score

    def _open_files(self, board, color):
        """Evaluate open files for rooks"""
        score = 0.0
        # count empty files
        empty_file_count = sum(
            1 for file in range(8)
            if all(board.piece_at(chess.square(file, r)) is None for r in range(8))
        )
        score += empty_file_count * self.ai_config.get(self.ruleset, {}).get('open_file_bonus', 0.0)

        # file control by rooks
        for sq in board.pieces(chess.ROOK, color):
            file = chess.square_file(sq)
            if all(board.piece_at(chess.square(file, r)) is None for r in range(8)):
                score += self.ai_config.get(self.ruleset, {}).get('file_control_bonus', 0.0)

        # exposed king penalty
        king_sq = board.king(color)
        if king_sq is not None:
            kfile = chess.square_file(king_sq)
            if all(board.piece_at(chess.square(kfile, r)) is None for r in range(8)):
                score -= self.ai_config.get(self.ruleset, {}).get('exposed_king_penalty', 0.0)
        return score
    
    def _stalemate(self, board: chess.Board):
        """Check if the position is a stalemate"""
        if board.is_stalemate():
            return self.ai_config.get(self.ruleset, {}).get('stalemate_penalty', 0.0)
        return 0.0

    # ================================
    # ======= DEBUG AND TESTING =======""
    
    def debug_evaluate_position(self, fen_position):
        """Debugging function to evaluate a position given in FEN"""
        try:
            board = chess.Board(fen_position)
            return self.evaluate_position(board)
        except Exception as e:
            if self.logger:
                self.logger.debug(f"Error in debug_evaluate_position: {e}")
            return None

    def debug_order_moves(self, fen_position, moves):
        """Debugging function to order moves in a given position"""        # Run an evaluation on a sample position

    
# Example usage and testing
if __name__ == "__main__":
    import logging
    import logging.handlers
    import random
    from typing import Callable, Dict, Any, Optional, Tuple

    try:
        # Run an evaluation on a sample position
        fen_position = input("Enter FEN position: ")
        if not fen_position:
            fen_position = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
        board = chess.Board(fen_position)
        engine = EvaluationEngine(board, chess.WHITE if board.turn else chess.BLACK)
        score = engine.evaluate_position(board)
        if score is not None:
            print(f"Current Evaluation: {score}")
        else:
            print("Unable to evaluate position")
    except Exception as e:
        print(f"Error running evaluation: {e}")


