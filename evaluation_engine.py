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
        backupCount=3
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
        self.hash_size = self.config['performance']['hash_size']
        self.threads = self.config['performance']['thread_limit']

        # Reset engine for new game
        self.history_table.clear()
        self.transposition_table.clear()
        self.nodes_searched = 0

        # Enable logging
        self.logging_enabled = self.config['debug']['enable_logging']
        self.show_thoughts = self.config['debug']['show_thinking']
        self.logger = evaluation_logger  # Use the module-level logger
        if self.logging_enabled:
            self.logger.debug("Logging enabled for Evaluation Engine")
        else:
            self.show_thoughts = False

        # Use provided ai_config or fetch from config for this player
        if ai_config is None:
            # Use config file to get correct AI config for this color
            if player == chess.WHITE:
                self.ai_config = self._get_ai_config('white')
            else:
                self.ai_config = self._get_ai_config('black')
        else:
            self.ai_config = ai_config
            
        # Initialize Engine for this color AI
        self.configure_for_side(self.ai_config)
        
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
    
    def _get_ai_config(self, player_color):
        """Extract this bots AI configuration"""
        return {
            'ai_type': self.config[f'{player_color}_ai_config']['ai_type'],
            'ai_color': player_color,
            'depth': self.config[f'{player_color}_ai_config']['depth'],
            'max_depth': self.config['performance']['max_depth'],
            'solutions_enabled': self.config[f'{player_color}_ai_config']['use_solutions'],
            'pst_enabled': self.config[f'{player_color}_ai_config']['pst'],
            'pst_weight': self.config[f'{player_color}_ai_config']['pst_weight'],
            'move_ordering_enabled': self.config[f'{player_color}_ai_config']['move_ordering'],
            'quiescence_enabled': self.config[f'{player_color}_ai_config']['quiescence'],
            'move_time_limit': self.config[f'{player_color}_ai_config']['time_limit'],
            'engine': self.config[f'{player_color}_ai_config']['engine'],
            'ruleset': self.config[f'{player_color}_ai_config']['ruleset'],
            'scoring_modifier': self.config[f'{player_color}_ai_config']['scoring_modifier'],
        }
      
    def configure_for_side(self, ai_config: dict):
        """Configure evaluation engine with side-specific settings"""
        if ai_config is not None:
            self.ai_config = ai_config
        elif self.ai_config is None:
            # Fallback to default configuration
            self.ai_config = self._get_ai_config('white' if self.board.turn == chess.WHITE else 'black')

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
        # Ensure board.turn is a chess.Color
        assert self.board.turn in (chess.WHITE, chess.BLACK), f"reset: board.turn is not a chess.Color: {self.board.turn}"
        self.current_player = self.board.turn
        self.nodes_searched = 0
        self.transposition_table.clear()
        self.killer_moves = [[None, None] for _ in range(50)]
        self.history_table.clear()
        self.counter_moves.clear()
        if self.show_thoughts and self.logger:
            self.logger.debug(f"Evaluation engine for {self.ai_color} reset to initial state.")
        
        # Reconfigure for the current player
        self.configure_for_side(self.ai_config)
    
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

    def search(self, board: chess.Board, player: chess.Color, ai_config: dict = {}):
        """Searches for the best valid move using the AI's configured algorithm.
        NOTE: This engine instance is already configured for its color. Only update board state.
        """
        best_move = None
        self.board = board.copy()  # Ensure we work on a copy of the board
        # Ensure board.turn is a chess.Color
        assert self.board.turn in (chess.WHITE, chess.BLACK), f"search: board.turn is not a chess.Color: {self.board.turn}"
        self.current_player = self.board.turn if player not in (chess.WHITE, chess.BLACK) else player
        
        # Fallback setup, if AI config is not specified, use the configured AI type for that color
        if ai_config is None:
            ai_config = self._get_ai_config('white' if player == chess.WHITE else 'black')
            self.configure_for_side(ai_config)
        else:
            self.ai_config = ai_config

        # Start move evaluation
        if self.show_thoughts:
            self.logger.debug(f"== EVALUATION (Player: {'White' if player == chess.WHITE else 'Black'}) == | AI Type: {ai_config['ai_type']} | Depth: {ai_config['depth']} ==")

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
            best_move = self._deepsearch(self.board.copy(), self.depth, self.time_control, stop_callback=self.time_manager.should_stop)
        elif self.ai_type == 'minimax':
            # Use minimax algorithm with alpha-beta pruning
            if self.show_thoughts and self.logger:
                self.logger.debug("Using minimax algorithm with alpha-beta pruning")
            best_move = self._minimax(self.board.copy(), self.depth, -float('inf'), float('inf'), self.current_player == chess.WHITE, stop_callback=self.time_manager.should_stop)
        elif self.ai_type == 'negamax':
            # Use negamax algorithm with alpha-beta pruning
            if self.show_thoughts and self.logger:
                self.logger.debug("Using negamax algorithm with alpha-beta pruning")
            best_move = self._negamax(self.board.copy(), self.depth, -float('inf'), float('inf'), stop_callback=self.time_manager.should_stop)
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
            best_move = self._simple_search()
        elif self.ai_type == 'evaluation_only':
            # Use evaluation only with no special features (no depth, no quiescence, no move ordering)
            if self.show_thoughts and self.logger:
                self.logger.debug("Using evaluation only with no special features")
            best_move = self._evaluation_only()
        elif self.ai_type == 'random':
            # Select a random move from the available moves
            if self.show_thoughts and self.logger:
                self.logger.debug("Using random search selection")
            best_move = self._random_search()
        else: 
            # make a random move if no AI type is specified
            if self.show_thoughts and self.logger:
                self.logger.debug("No AI type specified, using random search selection")
            best_move = self._random_search()

        # save the best move to the transposition table
        if best_move:
            if isinstance(best_move, chess.Move) or best_move is None:
                self.update_transposition_table(self.board, self.depth, best_move, self.evaluate_position(self.board))
        # Enforce strict draw prevention before returning
        if self.strict_draw_prevention:
            best_move = self._enforce_strict_draw_prevention(self.board, best_move if isinstance(best_move, chess.Move) or best_move is None else None)
        return best_move if best_move else None

    # =================================
    # ===== EVALUATION FUNCTIONS ======

    def evaluate_position(self, board: chess.Board):
        """Calculate base position evaluation"""
        # Ensure board.turn is a chess.Color
        if board.turn not in (chess.WHITE, chess.BLACK):
            if self.logger:
                self.logger.error(f"evaluate_position: Invalid board.turn: {board.turn} | FEN: {board.fen()}")
            return 0.0
        score = 0.0
        white_score = 0.0
        black_score = 0.0
        try:
            white_score = self._calculate_score(board, chess.WHITE)
            black_score = self._calculate_score(board, chess.BLACK)
            score = white_score - black_score
            if self.logging_enabled and self.logger:
                self.logger.debug(f"Position evaluation: {score:.3f} | FEN: {board.fen()}")
        except Exception:
            # Fallback to simple material evaluation
            white_score = self._material_score(board, chess.WHITE)
            black_score = self._material_score(board, chess.BLACK)
            score = white_score - black_score
            if self.logging_enabled and self.logger:
                self.logger.error(f"Using fallback material evaluation: {score:.3f} | FEN: {board.fen()}")
        return score if score is not None else 0.0

    def evaluate_position_from_perspective(self, board: chess.Board, player: chess.Color):
        """Calculate position evaluation from specified player's perspective"""
        # Add assertion and logging for player
        if player not in (chess.WHITE, chess.BLACK):
            if self.logger:
                self.logger.error(f"Invalid player value: {player} | FEN: {board.fen()}")
            return 0.0
        score = 0.0
        try:
            white_score = self._calculate_score(board, chess.WHITE)
            black_score = self._calculate_score(board, chess.BLACK)
            score = float(white_score - black_score if player == chess.WHITE else black_score - white_score)
            if self.logging_enabled and self.logger:
                self.logger.debug(f"Position evaluation from {player} perspective: {score:.3f} | FEN: {board.fen()}")
            return score if score is not None else 0.0
        except Exception as e:
            if self.logging_enabled and self.logger:
                self.logger.error(f"Error evaluating position from perspective {player}: {e}")
            return 0.0  # Fallback to neutral score
    
    def evaluate_move(self, move: chess.Move = chess.Move.null()):
        """Quick evaluation of individual move on overall eval"""
        score = 0.0
        board = self.board.copy()
        if move not in board.legal_moves:  # Add validation check
            if self.logging_enabled and self.logger:
                self.logger.error(f"Attempted evaluation of an illegal move: {move} | FEN: {board.fen()}")
            return -9999999999 # never play illegal moves
        if move is not None:
            board.push(move)
            score = self.evaluate_position(board)
        if self.show_thoughts and self.logger:
            self.logger.debug("Exploring the move: %s | Evaluation: %.3f | FEN: %s", move, score, board.fen())
        board.pop()
        return score if score is not None else 0.0

    # ===================================
    # ======= HELPER FUNCTIONS ==========
    
    def order_moves(self, board: chess.Board, moves: list[chess.Move], hash_move: Optional[chess.Move] = None, depth: int = 0):
        """Order moves for better alpha-beta pruning efficiency"""
        # Store move scores for later sorting
        move_scores = []
        if moves is None or len(moves) == 0:
            moves =  list(board.legal_moves)  # Ensure we have legal moves to work with
        score = 0.0  # Initialize score to avoid unbound variable error
        for move in moves:
            # Checks and Mates
            if move not in board.legal_moves :  # Add validation check
                return [] # ensure illegal move is never played
            board.push(move)
            # Check if this move gives checkmate!
            if board.is_checkmate():
                board.pop()
                return [move for move in moves if move in board.legal_moves]
            # Calculate score for move
            score = self._order_move_score(board, move, hash_move, depth)
            if score is None:
                score = 0.0
            move_scores.append((move, score))
            board.pop()
            
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

        # Hash move or checkmate gets highest priority
        if hash_move and move == hash_move:
            return self.config.get('evaluation', {}).get('hash_move_bonus', 5000.0)

        # Captures scored by MVV-LVA (Most Valuable Victim - Least Valuable Aggressor)
        if board.is_capture(move):
            victim_piece = board.piece_at(move.to_square)
            aggressor_piece = board.piece_at(move.from_square)
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
        last_move = board.peek() if board.move_stack else None
        if last_move:
            counter_key = (last_move.from_square, last_move.to_square)
            if counter_key in self.counter_moves and self.counter_moves[counter_key] == move:
                return self.config.get('evaluation', {}).get('counter_move_bonus', 1000.0)

        # History heuristic (moves that have caused cutoffs in similar positions)
        piece = board.piece_at(move.from_square)
        if piece is None:
            return 0.0
        history_key = (piece.piece_type, move.from_square, move.to_square)
        history_score = self.history_table.get(history_key, 0)

        # Promotions (already handled in captures, but add for non-capture promotions)
        if move.promotion:
            score += float(self.config.get('evaluation', {}).get('promotion_move_bonus', 3000.0))

        # Checks and Mates
        if move not in board.legal_moves:  # Add validation check
            return -1000000.0 # ensure legal move is never played
        
        # prepare the evaluation by pushing the move
        board.push(move)
        
        # Check if this move gives checkmate!
        if board.is_checkmate():
            board.pop()
            return self.config.get('evaluation', {}).get('checkmate_move_bonus', 1000000.0) * 1000.0

        if board.is_check():
            score += float(self.config.get(self.ruleset, {}).get('check_move_bonus', 500.0))

        # Add move data to history table
        self.update_history_score(board, move, depth)

        return score if score is not None else 0.0
    
    def _quiescence_search(self, board: chess.Board, alpha: float, beta: float, depth: int = 0, stop_callback: Optional[Callable[[], bool]] = None):
        """Quiescence search to avoid horizon effect."""
        if stop_callback and stop_callback():
            return self.evaluate_position_from_perspective(board, board.turn)

        def mvv_lva_score(board: chess.Board, move: chess.Move):
            """Most Valuable Victim - Least Valuable Attacker score"""
            score = 0.0
            piece_values = self.piece_values
            victim_piece = board.piece_at(move.to_square)
            attacker_piece = board.piece_at(move.from_square)
            if victim_piece is None or attacker_piece is None:
                return 0
            victim_value = piece_values[victim_piece.piece_type]
            attacker_value = piece_values[attacker_piece.piece_type]

            score = victim_value * 100 - attacker_value
            return score if score is not None else 0.0

        if depth > 2:  # Limit quiescence depth
            return self.evaluate_position_from_perspective(board, board.turn)

        stand_pat = self.evaluate_position_from_perspective(board, board.turn)
        
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
            board.push(move)
            if board.is_checkmate() or board.is_capture(move):
                board.pop()
                quiescence_moves.append(move)
            board.pop()

        # Order captures by MVV-LVA
        quiescence_moves.sort(key=lambda m: mvv_lva_score(board, m), reverse=True)

        if self.move_ordering_enabled:
            quiescence_moves = self.order_moves(board, quiescence_moves, depth=depth)

        for move in quiescence_moves:
            if stop_callback and stop_callback():
                break
            if move not in board.legal_moves:
                continue
            board.push(move)
            score = self._checkmate_threats(board)
            if score is None:
                self.nodes_searched += 1
                score = -self._quiescence_search(board, -beta, -alpha, depth + 1, stop_callback)
            board.pop()
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
        if depth >= len(self.killer_moves):
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
        temp_board = board.copy()
        temp_board.push(move)
        if temp_board.is_stalemate() or temp_board.is_insufficient_material() or temp_board.is_fivefold_repetition() or temp_board.is_repetition(count=3):
            if self.show_thoughts and self.logger:
                self.logger.debug(f"Potential drawing move detected, enforcing strict draw prevention: {move} | FEN: {temp_board.fen()}")
            # Try to find a non-drawing move
            legal_moves = list(board.legal_moves)
            non_draw_moves = []
            for m in legal_moves:
                temp = board.copy()
                temp.push(m)
                if not (temp.is_stalemate() or temp.is_insufficient_material() or temp.is_fivefold_repetition() or temp.is_repetition(count=3)):
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
    
    def _random_search(self):
        legal_moves = list(self.board.legal_moves)
        move = random.choice(legal_moves) if legal_moves else None
        move = self._enforce_strict_draw_prevention(self.board, move)
        if self.show_thoughts and self.logger:
            self.logger.debug(f"Random search: {len(legal_moves)} legal moves available.")
        return move

    def _evaluation_only(self): 
        """Evaluate the current position without searching"""
        evaluation = self.evaluate_position(self.board)
        if self.show_thoughts and self.logger:
            self.logger.debug(f"Evaluating position: Score: {evaluation:.3f} FEN: {self.board.fen()}")
        return evaluation
    
    def _simple_search(self):
        """Simple search that evaluates all legal moves and picks the best one at 1/2 ply."""
        best_move = None
        best_score = -float('inf') if self.board.turn == chess.WHITE else float('inf')
        board = self.board.copy()
        if self.depth == 0 or board.is_game_over():
            return None
        
        # see if we have the best move in the transposition table
        depth = self.depth if self.depth > 0 else 1
        hash_move, hash_score = self.get_transposition_move(board, depth)
        if hash_move:
            if self.show_thoughts and self.logger:
                self.logger.debug(f"Using transposition move: {hash_move} at depth {depth} | Evaluation: {hash_score:.3f} | FEN: {board.fen()}")
            return hash_move, hash_score
        
        moves = list(board.legal_moves)
        if self.move_ordering_enabled:
            moves = self.order_moves(board, moves)
        for move in moves:
            score = 0.0
            if self.show_thoughts and self.logger:
                self.logger.debug(f"Evaluating move: {move} | Score: {score:.3f} | Best score: {best_score:.3f} | FEN: {board.fen()}")
            board.push(move)
            score = self.evaluate_position_from_perspective(board, chess.WHITE if board.turn else chess.BLACK)
            board.pop()
            if score > best_score:
                best_score = score
                best_move = move
            if self.show_thoughts and self.logger:
                self.logger.debug(f"Strongly considering: {best_move} | Best score: {best_score:.3f} | FEN: {board.fen()}")
        # Enforce strict draw prevention before returning best_move:
        best_move = self._enforce_strict_draw_prevention(self.board, best_move)
        return best_move

    def _lookahead_search(self, board: chess.Board, depth: int, alpha: float, beta: float, stop_callback: Optional[Callable[[], bool]] = None):
        if stop_callback is not None and stop_callback():
            return None
        if depth == 0 or board.is_game_over(claim_draw=self._is_draw_condition(board)):
            if self.quiescence_enabled:
                return self._quiescence_search(board, alpha, beta, depth, stop_callback)
            else:
                # PROBLEM AREA: player argument
                # The following line is likely the source of the bug:
                # score = self.evaluate_position_from_perspective(board, board.turn)
                # board.turn is a bool (True for white, False for black), but evaluate_position_from_perspective expects chess.WHITE or chess.BLACK.
                # However, in python-chess, chess.WHITE == True and chess.BLACK == False, so this is usually fine.
                # The bug can occur if somewhere a plain True/False is passed instead of chess.WHITE/chess.BLACK.
                # To be explicit and safe, always use chess.WHITE/chess.BLACK.
                score = self.evaluate_position_from_perspective(board, chess.WHITE if board.turn else chess.BLACK)
                if self.show_thoughts and self.logger:
                    if score is None:
                        self.logger.debug(f"Score is None at depth {depth} | FEN: {board.fen()}")
                    else:
                        self.logger.debug(f"Score at leaf: {score} | FEN: {board.fen()}")
                return score
        moves = list(board.legal_moves)
        if self.move_ordering_enabled:
            moves = self.order_moves(board, moves)
        best_move = None
        best_score = -float('inf') if board.turn == chess.WHITE else float('inf')
        best_move_board = None  # Track the board for logging
        for move in moves:
            new_board = board.copy()
            new_board.push(move)
            try:
                if depth - 1 == 0 or new_board.is_game_over(claim_draw=self._is_draw_condition(new_board)):
                    # PROBLEM AREA: player argument
                    # score = self.evaluate_position_from_perspective(board, board.turn)
                    score = self.evaluate_position_from_perspective(new_board, chess.WHITE if board.turn else chess.BLACK)
                else:
                    next_move = self._lookahead_search(new_board, depth - 1, alpha, beta, stop_callback)
                    if isinstance(next_move, chess.Move):
                        new_board.push(next_move)
                    # PROBLEM AREA: player argument
                    # score = self.evaluate_position_from_perspective(board, board.turn)
                    score = self.evaluate_position_from_perspective(new_board, chess.WHITE if board.turn else chess.BLACK)
            except Exception as e:
                if self.show_thoughts and self.logger:
                    self.logger.debug(f"Error during lookahead search: {e}")
                score = self.evaluate_position_from_perspective(new_board, chess.WHITE if board.turn else chess.BLACK)
            # Debug: log score value and if it's None
            if self.show_thoughts and self.logger:
                if score is None:
                    self.logger.debug(f"Score is None for move {move} at depth {depth} | FEN: {new_board.fen()}")
                else:
                    self.logger.debug(f"Score for move {move}: {score} at depth {depth} | FEN: {new_board.fen()}")
            if board.turn == chess.WHITE:
                if score > best_score:
                    best_score = score
                    best_move = move
                    best_move_board = new_board.copy()
            else:
                if score < best_score:
                    best_score = score
                    best_move = move
                    best_move_board = new_board.copy()
            if self.show_thoughts and self.logger:
                self.logger.debug(f"Evaluating move: {move} | Score: {score:.3f} | Depth: {self.depth - depth} | Best score: {best_score:.3f} | FEN: {new_board.fen()}")
        if self.show_thoughts and self.logger:
            # Use best_move_board if available, else board
            fen_to_log = best_move_board.fen() if best_move_board else board.fen()
            self.logger.debug(f"Strongly considering: {best_move} | Best score: {best_score:.3f} | FEN: {fen_to_log}")
        # Enforce strict draw prevention before returning best_move:
        best_move = self._enforce_strict_draw_prevention(board, best_move)
        return best_move

    def _minimax(self, board: chess.Board, depth: int, alpha: float, beta: float, maximizing_player: bool, stop_callback: Optional[Callable[[], bool]] = None):
        # Add base case to prevent infinite recursion
        if stop_callback is not None and stop_callback():
            return None
        if depth == 0 or board.is_game_over():
            # Use quiescence search if enabled, otherwise static evaluation
            if self.quiescence_enabled:
                return self._quiescence_search(board, alpha, beta, depth, stop_callback)
            else:
                # PROBLEM AREA: player argument
                # return self.evaluate_position_from_perspective(board, board.turn)
                return self.evaluate_position_from_perspective(board, chess.WHITE if board.turn else chess.BLACK)
        moves = list(board.legal_moves)
        if self.move_ordering_enabled:
            moves = self.order_moves(board, moves)
        best_move = None
        best_move_board = None  # Track the board for logging
        if maximizing_player:
            best_score = -float('inf')
            for move in moves:
                new_board = board.copy()
                new_board.push(move)
                if new_board.is_checkmate():
                    score = self.ai_config.get(self.ruleset, {}).get('checkmate_bonus', 1000000.0) - (self.depth - depth)
                elif new_board.is_stalemate() or new_board.is_insufficient_material():
                    score = 0.0
                else:
                    result = self._minimax(new_board, depth-1, alpha, beta, False, stop_callback)
                    if isinstance(result, (int, float)):
                        score = result
                    elif result is None:
                        score = self.evaluate_position_from_perspective(new_board, chess.WHITE if board.turn else chess.BLACK)
                    elif isinstance(result, chess.Move):
                        # Only push if result is a Move
                        new_board.push(result)
                        score = self.evaluate_position_from_perspective(new_board, chess.WHITE if board.turn else chess.BLACK)
                    else:
                        score = self.evaluate_position_from_perspective(new_board, chess.WHITE if board.turn else chess.BLACK)
                # Debug: log score value and if it's None
                if self.show_thoughts and self.logger:
                    if score is None:
                        self.logger.debug(f"Score is None for move {move} at depth {depth} | FEN: {new_board.fen()}")
                    else:
                        self.logger.debug(f"Score for move {move}: {score} at depth {depth} | FEN: {new_board.fen()}")
                if score > best_score:
                    best_score = score
                    best_move = move
                    best_move_board = new_board.copy()
                alpha = max(alpha, score)
                if beta <= alpha:
                    self.update_killer_move(move, depth)
                    break
                if self.show_thoughts and self.logger:
                    self.logger.debug(f"Evaluating move: {move} | Score: {score:.3f} | Depth: {self.depth - depth} | Best score: {best_score:.3f} | FEN: {new_board.fen()}")
            if self.show_thoughts and self.logger:
                fen_to_log = best_move_board.fen() if best_move_board else board.fen()
                self.logger.debug(f"Strongly considering: {best_move} | Best score: {best_score:.3f} | FEN: {fen_to_log}")
            if depth == self.depth:
                return best_move
            else:
                return best_score
        else:
            best_score = float('inf')
            for move in moves:
                new_board = board.copy()
                new_board.push(move)
                if new_board.is_checkmate():
                    score = -self.ai_config.get(self.ruleset, {}).get('checkmate_bonus', 1000000.0) + (self.depth - depth)
                elif new_board.is_stalemate() or new_board.is_insufficient_material():
                    score = 0.0
                else:
                    result = self._minimax(new_board, depth-1, alpha, beta, True, stop_callback)
                    if isinstance(result, (int, float)):
                        score = result
                    elif result is None:
                        score = self.evaluate_position_from_perspective(new_board, chess.WHITE if board.turn else chess.BLACK)
                    elif isinstance(result, chess.Move):
                        new_board.push(result)
                        score = self.evaluate_position_from_perspective(new_board, chess.WHITE if board.turn else chess.BLACK)
                    else:
                        score = self.evaluate_position_from_perspective(new_board, chess.WHITE if board.turn else chess.BLACK)
                if score < best_score:
                    best_score = score
                    best_move = move
                    best_move_board = new_board.copy()
                
                beta = min(beta, score)
                if beta <= alpha:
                    break
                if self.show_thoughts and self.logger:
                    self.logger.debug(f"Evaluating move tree for: {move} | Score: {score:.3f} | Best score: {best_score:.3f} | FEN: {new_board.fen()}")
            if self.show_thoughts and self.logger:
                fen_to_log = best_move_board.fen() if best_move_board else board.fen()
                self.logger.debug(f"Strongly considering: {best_move} | Best score: {best_score:.3f} | FEN: {fen_to_log}")
            if depth == self.depth:
                return best_move
            else:
                return best_score

    def _negamax(self, board: chess.Board, depth: int, alpha: float, beta: float, stop_callback: Optional[Callable[[], bool]] = None):
        if stop_callback is not None and stop_callback():
            return None
        if self.time_manager.should_stop(depth, self.nodes_searched):
            return None
        if depth == 0 or board.is_game_over():
            # Use quiescence search if enabled, otherwise static evaluation
            if self.quiescence_enabled:
                return self._quiescence_search(board, alpha, beta, depth, stop_callback)
            else:
                # PROBLEM AREA: player argument
                # return self.evaluate_position_from_perspective(board, board.turn)
                return self.evaluate_position_from_perspective(board, chess.WHITE if board.turn else chess.BLACK)
        moves = list(board.legal_moves)
        if self.move_ordering_enabled:
            moves = self.order_moves(board, moves)
        best_move = None
        best_score = -float('inf')
        best_move_board = None
        for move in moves:
            board.push(move)
            if board.is_checkmate():
                score = self.ai_config.get(self.ruleset, {}).get('checkmate_bonus', 1000000.0) - (self.depth - depth)
            elif board.is_stalemate() or board.is_insufficient_material():
                score = 0.0
            else:
                # For negamax, recursively call and negate the result
                result = self._negamax(board, depth-1, -beta, -alpha, stop_callback)
                score = -result if isinstance(result, (int, float)) else 0.0
            # Debug: log score value and if it's None
            if self.show_thoughts and self.logger:
                if score is None:
                    self.logger.debug(f"Score is None for move {move} at depth {depth} | FEN: {board.fen()}")
                else:
                    self.logger.debug(f"Score for move {move}: {score} at depth {depth} | FEN: {board.fen()}")
            board.pop()
            if score > best_score:
                best_score = score
                best_move = move
                best_move_board = board.copy()
            alpha = max(alpha, score)
            if alpha >= beta:
                break
            if self.show_thoughts and self.logger:
                self.logger.debug(f"Evaluating move: {move} | Score: {score:.3f} | Depth: {self.depth - depth} | Best score: {best_score:.3f} | FEN: {board.fen()}")
        if self.show_thoughts and self.logger:
            fen_to_log = best_move_board.fen() if best_move_board else board.fen()
            self.logger.debug(f"Strongly considering: {best_move} | Best score: {best_score:.3f} | FEN: {fen_to_log}")
        if depth == self.depth:
            return best_move
        else:
            return best_score

    def _negascout(self, board: chess.Board, depth: int, alpha: float, beta: float, stop_callback: Optional[Callable[[], bool]] = None):
        if stop_callback is not None and stop_callback():
            return None
        if self.time_manager.should_stop(depth, self.nodes_searched):
            return None
        if depth == 0 or board.is_game_over():
            if self.quiescence_enabled:
                return self._quiescence_search(board, alpha, beta, depth, stop_callback)
            else:
                # PROBLEM AREA: player argument
                # return self.evaluate_position_from_perspective(board, board.turn)
                return self.evaluate_position_from_perspective(board, chess.WHITE if board.turn else chess.BLACK)
        moves = list(board.legal_moves)
        if self.move_ordering_enabled:
            moves = self.order_moves(board, moves)
        best_move = None
        best_score = -float('inf')
        best_move_board = None
        first = True
        for move in moves:
            board.push(move)
            if board.is_checkmate():
                score = self.ai_config.get(self.ruleset, {}).get('checkmate_bonus', 1000000.0) - (self.depth - depth)
            elif board.is_stalemate() or board.is_insufficient_material():
                score = 0.0
            else:
                if first:
                    result = self._negascout(board, depth-1, -beta, -alpha, stop_callback)
                    score = -result if isinstance(result, (int, float)) else 0.0
                else:
                    result = self._negascout(board, depth-1, -alpha-1, -alpha, stop_callback)
                    score = -result if isinstance(result, (int, float)) else 0.0
                    # If score is in the window, do a full re-search
                    if alpha < score < beta:
                        result = self._negascout(board, depth-1, -beta, -score, stop_callback)
                        score = -result if isinstance(result, (int, float)) else 0.0
            # Debug: log score value and if it's None
            if self.show_thoughts and self.logger:
                if score is None:
                    self.logger.debug(f"Score is None for move {move} at depth {depth} | FEN: {board.fen()}")
                else:
                    self.logger.debug(f"Score for move {move}: {score} at depth {depth} | FEN: {board.fen()}")
            board.pop()
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
        if self.show_thoughts and self.logger:
            fen_to_log = best_move_board.fen() if best_move_board else board.fen()
            self.logger.debug(f"Negascout considering: {best_move} | Best score: {best_score:.3f} | FEN: {fen_to_log}")
        if depth == self.depth:
            return best_move
        else:
            return best_score
    
    def _deepsearch(self, board: chess.Board, depth: int, time_control: Dict[str, Any], stop_callback: Optional[Callable[[], bool]] = None):
        """
        Perform a search with iterative deepening, move ordering, quiescence search, and dynamic search depth.
        """
        self.nodes_searched = 0
        legal_moves = list(board.legal_moves)
        if not legal_moves:
            return None
        if len(legal_moves) == 1:
            return legal_moves[0]

        max_depth = self.max_depth
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
                dynamic_depth = self._get_dynamic_depth(board, d)
                if dynamic_depth is None:
                    dynamic_depth = d

                # Move ordering
                moves = list(board.legal_moves)
                if self.move_ordering_enabled:
                    moves = self.order_moves(board, moves)

                local_best_move = None
                local_best_score = -float('inf')

                for move in moves:
                    board.push(move)
                    # Use quiescence search at leaf nodes if enabled
                    if dynamic_depth - 1 == 0 or board.is_game_over():
                        if self.quiescence_enabled:
                            score = self._quiescence_search(board, -float('inf'), float('inf'), 0, stop_callback)
                        else:
                            score = self.evaluate_position_from_perspective(board, chess.WHITE if board.turn else chess.BLACK)
                    else:
                        # Recursively search deeper
                        result = self._deepsearch(board, dynamic_depth - 1, time_control, stop_callback)
                        if isinstance(result, chess.Move):
                            board.push(result)
                            score = self.evaluate_position_from_perspective(board, chess.WHITE if board.turn else chess.BLACK)
                            board.pop()
                        elif isinstance(result, (int, float)):
                            score = result
                        else:
                            score = self.evaluate_position_from_perspective(board, chess.WHITE if board.turn else chess.BLACK)
                    # Debug: log score value and if it's None
                    if self.show_thoughts and self.logger:
                        if score is None:
                            self.logger.debug(f"Score is None for move {move} at depth {d} | FEN: {board.fen()}")
                        else:
                            self.logger.debug(f"Score for move {move}: {score} at depth {d} | FEN: {board.fen()}")
                    board.pop()
                    if score > local_best_score:
                        local_best_score = score
                        local_best_move = move
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
                    self.logger.debug(f"Iterative deepening depth {d}: Best move: {best_move} | Score: {best_score:.3f}")

        except Exception as e:
            if self.logger:
                self.logger.debug(f"info string Search error: {e}")

        if self.show_thoughts and self.logger:
            self.logger.debug(f"Strongly considering: {best_move} | Best score: {best_score:.3f} | FEN: {board.fen()}")

        return best_move

    def _get_dynamic_search_depth(self, board: chess.Board, depth: int, stop_callback: Optional[Callable[[], bool]] = None):
        """Perform a search at a specific depth with dynamic evaluation."""
        if stop_callback is not None and stop_callback():
            return None, 0.0
        if self.time_manager.should_stop(depth, self.nodes_searched):
            return None, 0.0
        
        # Get the best move from transposition table if available
        hash_move = self.get_transposition_move(board, depth)
        if hash_move:
            if self.show_thoughts and self.logger:
                self.logger.debug(f"Using transposition move: {hash_move} at depth {depth}")
            return hash_move, self.evaluate_position_from_perspective(board, board.turn)

        # Determine the search depth dynamically
        dynamic_depth = self._get_dynamic_depth(board, depth)
        if dynamic_depth is None:
            return None, 0.0

        # Start a thread for each search type, storing their results for evaluation and selection for best move
        # For now, just return None, 0.0 as a stub
        return None, 0.0

    def _get_dynamic_depth(self, board: chess.Board, depth: int) -> int:
        """Stub for dynamic depth calculation. Returns the input depth."""
        # You can implement more advanced logic here if needed.
        return depth

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
        score += self.scoring_modifier * (self._piece_coordination(board, color) or 0.0)
        if self.show_thoughts and self.logger:
            self.logger.debug(f"Piece coordination score: {score:.3f} | FEN: {board.fen()}")
        score += self.scoring_modifier * (self._center_control(board) or 0.0)
        if self.show_thoughts and self.logger:
            self.logger.debug(f"Center control score: {score:.3f} | FEN: {board.fen()}")
        score += self.scoring_modifier * (self._pawn_structure(board, color) or 0.0)
        if self.show_thoughts and self.logger:
            self.logger.debug(f"Pawn structure score: {score:.3f} | FEN: {board.fen()}")
        score += self.scoring_modifier * (self._pawn_weaknesses(board, color) or 0.0)
        if self.show_thoughts and self.logger:
            self.logger.debug(f"Pawn weaknesses score: {score:.3f} | FEN: {board.fen()}")
        score += self.scoring_modifier * (self._passed_pawns(board, color) or 0.0)
        if self.show_thoughts and self.logger:
            self.logger.debug(f"Passed pawns score: {score:.3f} | FEN: {board.fen()}")
        score += self.scoring_modifier * (self._pawn_majority(board, color) or 0.0) # TODO
        if self.show_thoughts and self.logger:
            self.logger.debug(f"Pawn majority score: {score:.3f} | FEN: {board.fen()}")
        score += self.scoring_modifier * (self._bishop_pair(board, color) or 0.0)
        if self.show_thoughts and self.logger:
            self.logger.debug(f"Bishop pair score: {score:.3f} | FEN: {board.fen()}")
        score += self.scoring_modifier * (self._knight_pair(board, color) or 0.0)
        if self.show_thoughts and self.logger:
            self.logger.debug(f"Knight pair score: {score:.3f} | FEN: {board.fen()}")
        score += self.scoring_modifier * (self._bishop_vision(board, color) or 0.0)
        if self.show_thoughts and self.logger:
            self.logger.debug(f"Bishop vision score: {score:.3f} | FEN: {board.fen()}")
        score += self.scoring_modifier * (self._rook_coordination(board, color) or 0.0)
        if self.show_thoughts and self.logger:
            self.logger.debug(f"Rook coordination score: {score:.3f} | FEN: {board.fen()}")
        score += self.scoring_modifier * (self._castling_evaluation(board, color) or 0.0)
        if self.show_thoughts and self.logger:
            self.logger.debug(f"Castling evaluation score: {score:.3f} | FEN: {board.fen()}")
        
        # Piece development and mobility
        score += self.scoring_modifier * (self._piece_activity(board, color) or 0.0)
        if self.show_thoughts and self.logger:
            self.logger.debug(f"Piece activity score: {score:.3f} | FEN: {board.fen()}")
        score += self.scoring_modifier * (self._improved_minor_piece_activity(board, color) or 0.0)
        if self.show_thoughts and self.logger:
            self.logger.debug(f"Improved minor piece activity score: {score:.3f} | FEN: {board.fen()}")
        score += self.scoring_modifier * (self._mobility_score(board, color) or 0.0)
        if self.show_thoughts and self.logger:
            self.logger.debug(f"Mobility score: {score:.3f} | FEN: {board.fen()}")
        score += self.scoring_modifier * (self._undeveloped_pieces(board, color) or 0.0)
        if self.show_thoughts and self.logger:
            self.logger.debug(f"Undeveloped pieces score: {score:.3f} | FEN: {board.fen()}")
        
        # Tactical and strategic considerations
        score += self.scoring_modifier * (self._tactical_evaluation(board) or 0.0)
        if self.show_thoughts and self.logger:
            self.logger.debug(f"Tactical evaluation score: {score:.3f} | FEN: {board.fen()}")
        score += self.scoring_modifier * (self._tempo_bonus(board, color) or 0.0)
        if self.show_thoughts and self.logger:
            self.logger.debug(f"Tempo bonus score: {score:.3f} | FEN: {board.fen()}")
        score += self.scoring_modifier * (self._special_moves(board) or 0.0)
        if self.show_thoughts and self.logger:
            self.logger.debug(f"Special moves score: {score:.3f} | FEN: {board.fen()}")
        score += self.scoring_modifier * (self._open_files(board, color) or 0.0)
        if self.show_thoughts and self.logger:
            self.logger.debug(f"Open files score: {score:.3f} | FEN: {board.fen()}")

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
        if not board.is_game_over() and board.turn == color:
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
            if board.piece_at(square) and board.piece_at(square).color == board.turn:
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

        direction = 1 if color == board.turn else -1
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
        engine = EvaluationEngine(board, board.turn)
        score = engine.evaluate_position(board)
        if score is not None:
            print(f"Current Evaluation: {score}")
        else:
            print("Unable to evaluate position")
    except Exception as e:
        print(f"Error running evaluation: {e}")

