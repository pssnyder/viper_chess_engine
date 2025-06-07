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
        self.engine = self.ai_config.get('engine','viper')
        self.ruleset = self.ai_config.get('ruleset','evaluation')
        self.scoring_modifier = self.ai_config.get('scoring_modifier',1.0)
        if self.move_time_limit == 0:
            self.time_control = {"infinite": True}
        else:
            self.time_control = {"movetime": self.move_time_limit}
        # Update piece-square table settings
        if hasattr(self, 'pst') and self.pst:
            self.pst_weight = self.ai_config.get('pst_weight', 1.0)
            self.pst_enabled = self.ai_config.get('pst_enabled', True)
        self.engine = self.ai_config.get('engine','None')
        self.ruleset = self.ai_config.get('ruleset','None')

        # Debug output for configuration changes
        if self.show_thoughts and self.logger:
            self.logger.debug(f"AI configured for {'White' if self.ai_color == 'white' else 'Black'}: type={self.ai_type} depth={self.depth}, ordering={self.move_ordering_enabled}, "
                             f"quiescence={self.quiescence_enabled}, pst_enabled={self.pst_enabled} pst_weight={self.pst_weight}")

    def reset(self, board: chess.Board):
        """Reset the evaluation engine to its initial state"""
        self.board = board.copy()
        self.nodes_searched = 0
        self.transposition_table.clear()
        self.killer_moves = [[None, None] for _ in range(50)]
        self.history_table.clear()
        self.counter_moves.clear()
        if self.show_thoughts and self.logger:
            self.logger.debug(f"Evaluation engine for {self.ai_color} reset to initial state.")
        
        # Reconfigure for the current player
        self.configure_for_side(self.ai_config)
    
    # =================================
    # ===== MOVE SEARCH HANDLER =======

    def search(self, board: chess.Board, player: chess.Color, ai_config: dict = {}):
        """Searches for the best valid move using the AI's configured algorithm.
        NOTE: This engine instance is already configured for its color. Only update board state.
        """
        best_move = None
        self.board = board.copy()  # Ensure we work on a copy of the board
        self.current_player = player
        
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
        return best_move if best_move else None
    
    # =================================
    # ===== EVALUATION FUNCTIONS ======
        
    def evaluate_position(self, board: chess.Board):
        """Calculate base position evaluation"""
        score = 0.0
        white_score = 0.0
        black_score = 0.0
        try:
            white_score = self._calculate_score(board, chess.WHITE)
            black_score = self._calculate_score(board, chess.BLACK)
            score = white_score - black_score
        except Exception:
            # Fallback to simple material evaluation
            white_score = self._material_score(board, chess.WHITE)
            black_score = self._material_score(board, chess.BLACK)
            score = white_score - black_score            
        return score if score is not None else 0.0

    def evaluate_position_from_perspective(self, board: chess.Board, player: chess.Color):
        """Calculate position evaluation from specified player's perspective"""
        score = 0.0
        try:
            white_score = self._calculate_score(board, chess.WHITE)
            black_score = self._calculate_score(board, chess.BLACK)
            score = float(white_score - black_score if player == chess.WHITE else black_score - white_score)
            return score if score is not None else 0.0
        except Exception as e:
            return 0.0  # Fallback to neutral score
    
    def evaluate_move(self, move: chess.Move):
        """Quick evaluation of individual move on overall eval"""
        score = 0.0
        board = self.board.copy()
        if move not in board.legal_moves:  # Add validation check
            return -9999999999 # never play illegal moves
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
            score += float(self.config['evaluation']['check_move_bonus'])

        # Add move data to history table
        self.update_history_score(board, move, depth)

        return score if score is not None else 0.0
    
    def _quiescence_search(self, board: chess.Board, alpha: float, beta: float, depth: int = 0, stop_callback: Optional[Callable[[], bool]] = None):
        """Quiescence search to avoid horizon effect."""
        if stop_callback and stop_callback():
            return self.evaluate_position_from_perspective(board, board.turn)

        if depth > 2:  # Limit quiescence depth
            return self.evaluate_position_from_perspective(board, board.turn)

        stand_pat = self.evaluate_position_from_perspective(board, board.turn)
        if stand_pat >= beta:
            return beta
        if stand_pat > alpha:
            alpha = stand_pat

        # Only search captures and checks in quiescence
        captures = [m for m in board.legal_moves if board.is_capture(m) or board.gives_check(m)]
        # Order captures by MVV-LVA
        captures.sort(key=lambda m: self.mvv_lva_score(board, m), reverse=True)
        if self.move_ordering_enabled:
            captures = self.order_moves(board, captures)

        for m in captures:
            if stop_callback and stop_callback():
                break
            if m not in board.legal_moves:
                continue
            board.push(m)
            if board.is_checkmate():
                score = self.config['evaluation']['checkmate_bonus']
            else:
                self.nodes_searched += 1
                score = -self._quiescence_search(board, -beta, -alpha, depth + 1, stop_callback)
            board.pop()
            if score >= beta:
                self.update_killer_move(m, depth)
                return beta
            if score > alpha:
                alpha = score
        
        if self.logging_enabled and self.logger:
            self.logger.debug(f"Quiescence search at depth {depth} | Alpha: {alpha} Beta: {beta} | Nodes searched: {self.nodes_searched}")
        
        return alpha
    
    def mvv_lva_score(self, board: chess.Board, move: chess.Move):
        """Most Valuable Victim - Least Valuable Attacker score"""
        score = 0.0
        piece_values = [0, 1, 3, 3, 5, 9, 10]  # None, P, N, B, R, Q, K
        victim_piece = board.piece_at(move.to_square)
        attacker_piece = board.piece_at(move.from_square)
        if victim_piece is None or attacker_piece is None:
            return 0
        victim_value = piece_values[victim_piece.piece_type]
        attacker_value = piece_values[attacker_piece.piece_type]

        score = victim_value * 100 - attacker_value
        return score if score is not None else 0.0
    
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

    # =======================================
    # ======= MAIN SEARCH ALGORITHMS ========
    
    def _random_search(self):
        legal_moves = list(self.board.legal_moves)
        if self.show_thoughts and self.logger:
            self.logger.debug(f"Random search: {len(legal_moves)} legal moves available.")
        return random.choice(legal_moves) if legal_moves else None
    
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
            score = self.evaluate_position_from_perspective(board, board.turn)
            board.pop()
            if score > best_score:
                best_score = score
                best_move = move
            if self.show_thoughts and self.logger:
                self.logger.debug(f"Strongly considering: {best_move} | Best score: {best_score:.3f} | FEN: {board.fen()}")
        return best_move

    def _lookahead_search(self, board: chess.Board, depth: int, alpha: float, beta: float, stop_callback: Optional[Callable[[], bool]] = None):
        if stop_callback is not None and stop_callback():
            return None
        if depth == 0 or board.is_game_over(claim_draw=True):
            if self.quiescence_enabled:
                return self._quiescence_search(board, alpha, beta, depth, stop_callback)
            else:
                return self.evaluate_position_from_perspective(board, board.turn)
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
                if depth - 1 == 0 or new_board.is_game_over(claim_draw=True):
                    score = self.evaluate_position_from_perspective(new_board, board.turn)
                else:
                    next_move = self._lookahead_search(new_board, depth - 1, alpha, beta, stop_callback)
                    # Only push if next_move is a chess.Move
                    if isinstance(next_move, chess.Move):
                        new_board.push(next_move)
                    score = self.evaluate_position_from_perspective(new_board, board.turn)
            except Exception as e:
                if self.show_thoughts and self.logger:
                    self.logger.debug(f"Error during lookahead search: {e}")
                score = self.evaluate_position_from_perspective(new_board, board.turn)
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
                return self.evaluate_position_from_perspective(board, board.turn)
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
                    score = self.config['evaluation']['checkmate_bonus'] - (self.depth - depth)
                elif new_board.is_stalemate() or new_board.is_insufficient_material():
                    score = 0.0
                else:
                    result = self._minimax(new_board, depth-1, alpha, beta, False, stop_callback)
                    if isinstance(result, (int, float)):
                        score = result
                    elif result is None:
                        score = self.evaluate_position_from_perspective(new_board, board.turn)
                    elif isinstance(result, chess.Move):
                        # Only push if result is a Move
                        new_board.push(result)
                        score = self.evaluate_position_from_perspective(new_board, board.turn)
                    else:
                        score = self.evaluate_position_from_perspective(new_board, board.turn)
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
                    score = -self.config['evaluation']['checkmate_bonus'] + (self.depth - depth)
                elif new_board.is_stalemate() or new_board.is_insufficient_material():
                    score = 0.0
                else:
                    result = self._minimax(new_board, depth-1, alpha, beta, True, stop_callback)
                    if isinstance(result, (int, float)):
                        score = result
                    elif result is None:
                        score = self.evaluate_position_from_perspective(new_board, board.turn)
                    elif isinstance(result, chess.Move):
                        new_board.push(result)
                        score = self.evaluate_position_from_perspective(new_board, board.turn)
                    else:
                        score = self.evaluate_position_from_perspective(new_board, board.turn)
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
                return self.evaluate_position_from_perspective(board, board.turn)
        moves = list(board.legal_moves)
        if self.move_ordering_enabled:
            moves = self.order_moves(board, moves)
        best_move = None
        best_score = -float('inf')
        best_move_board = None
        for move in moves:
            board.push(move)
            if board.is_checkmate():
                score = self.config['evaluation']['checkmate_bonus'] - (self.depth - depth)
            elif board.is_stalemate() or board.is_insufficient_material():
                score = 0.0
            else:
                # For negamax, recursively call and negate the result
                result = self._negamax(board, depth-1, -beta, -alpha, stop_callback)
                score = -result if isinstance(result, (int, float)) else 0.0
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
        # If at root, return best move; otherwise, return best_score
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
                return self.evaluate_position_from_perspective(board, board.turn)
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
                score = self.config['evaluation']['checkmate_bonus'] - (self.depth - depth)
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
                            score = self.evaluate_position_from_perspective(board, board.turn)
                    else:
                        # Recursively search deeper
                        result = self._deepsearch(board, dynamic_depth - 1, time_control, stop_callback)
                        if isinstance(result, chess.Move):
                            board.push(result)
                            score = self.evaluate_position_from_perspective(board, board.turn)
                            board.pop()
                        elif isinstance(result, (int, float)):
                            score = result
                        else:
                            score = self.evaluate_position_from_perspective(board, board.turn)
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
        material_weight = self.config['evaluation'].get('material_weight', 1.0)

        # Rules included in scoring

        # Critical scoring components
        score += self.scoring_modifier * (self._checkmate_threats(board) or 0.0)
        score += self.scoring_modifier * (self._king_safety(board, color) or 0.0)
        score += self.scoring_modifier * (self._king_threat(board) or 0.0)
        score += self.scoring_modifier * (self._draw_scenarios(board) or 0.0)

        # Material and piece-square table evaluation
        score += self.scoring_modifier * material_weight * (self._material_score(board, color) or 0.0)
        score += self.scoring_modifier * pst_weight * (self._piece_square_table_evaluation(color) or 0.0)

        # Piece coordination and control
        score += self.scoring_modifier * (self._piece_coordination(board, color) or 0.0)
        score += self.scoring_modifier * (self._center_control(board) or 0.0)
        score += self.scoring_modifier * (self._pawn_structure(board, color) or 0.0)
        score += self.scoring_modifier * (self._pawn_weaknesses(board, color) or 0.0)
        score += self.scoring_modifier * (self._passed_pawns(board, color) or 0.0)
        score += self.scoring_modifier * (self._pawn_majority(board, color) or 0.0) # TODO
        score += self.scoring_modifier * (self._bishop_pair(board, color) or 0.0)
        score += self.scoring_modifier * (self._knight_pair(board, color) or 0.0)
        score += self.scoring_modifier * (self._bishop_vision(board, color) or 0.0)
        score += self.scoring_modifier * (self._rook_coordination(board, color) or 0.0)
        score += self.scoring_modifier * (self._castling_evaluation(board, color) or 0.0)
        
        # Piece development and mobility
        score += self.scoring_modifier * (self._piece_activity(board, color) or 0.0)
        score += self.scoring_modifier * (self._improved_minor_piece_activity(board, color) or 0.0)
        score += self.scoring_modifier * (self._mobility_score(board, color) or 0.0)
        score += self.scoring_modifier * (self._undeveloped_pieces(board, color) or 0.0)
        
        # Tactical and strategic considerations
        score += self.scoring_modifier * (self._tactical_evaluation(board) or 0.0)
        score += self.scoring_modifier * (self._tempo_bonus(board, color) or 0.0)
        score += self.scoring_modifier * (self._special_moves(board) or 0.0)
        score += self.scoring_modifier * (self._open_files(board, color) or 0.0)

        return score

    # ==========================================
    # ========= RULE SCORING FUNCTIONS =========

    def _checkmate_threats(self, board):
        score = 0.0
        for move in board.legal_moves:
            board.push(move)
            if board.is_checkmate():
                score += self.config['evaluation']['checkmate_bonus']
                break
            board.pop()
        return score
    
    def _draw_scenarios(self, board):
        score = 0.0
        if board.is_stalemate() or board.is_insufficient_material() or board.is_fivefold_repetition() or board.is_repetition(count=2):
            score += self.config['evaluation']['draw_penalty']
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
            score += safe_moves * self.config['evaluation']['knight_activity_bonus']

        for square in board.pieces(chess.BISHOP, color):
            safe_moves = 0
            for target in board.attacks(square):
                if not self._is_attacked_by_pawn(board, target, not color):
                    safe_moves += 1
            score += safe_moves * self.config['evaluation']['bishop_activity_bonus']

        return score

    def _tempo_bonus(self, board, color):
        """If it's the player's turn and the game is still ongoing, give a small tempo bonus"""
        if not board.is_game_over() and board.turn == color:
            return self.config['evaluation']['tempo_bonus']  # Small tempo bonus
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
                score += self.config['evaluation']['center_control_bonus']
        return score

    def _piece_activity(self, board, color):
        """Mobility and attack patterns"""
        score = 0.0

        for square in board.pieces(chess.KNIGHT, color):
            score += len(board.attacks(square)) * self.config['evaluation']['knight_activity_bonus']

        for square in board.pieces(chess.BISHOP, color):
            score += len(board.attacks(square)) * self.config['evaluation']['bishop_activity_bonus']

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
                    score += self.config['evaluation']['king_safety_bonus']

        return score

    def _king_threat(self, board):
        """
        Evaluate if the opponent's king is under threat (in check) in the current position.
        Adds a penalty/bonus if the opponent's king is in check.
        """
        score = 0.0
        # Check if the opponent's king is in check in the current position
        if board.is_check():
            score += self.config['evaluation']['king_threat_penalty']
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
            score = undeveloped * self.config['evaluation']['undeveloped_penalty']

        return score

    def _mobility_score(self, board, color):
        """Evaluate mobility of pieces"""
        score = 0.0
        
        # Count legal moves for each piece type
        for piece_type in [chess.PAWN, chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN]:
            for square in board.pieces(piece_type, color):
                score += len(board.attacks(square)) * self.config['evaluation']['piece_mobility_bonus']

        return score
    
    def _special_moves(self, board):
        """Evaluate special moves and opportunities"""
        score = 0.0
        
        # En passant
        if board.ep_square:
            score += self.config['evaluation']['en_passant_bonus']
        
        # Promotion opportunities
        for move in board.legal_moves:
            if move.promotion:
                score += self.config['evaluation']['pawn_promotion_bonus']
        
        return score

    def _tactical_evaluation(self, board):
        """Evaluate tactical elements"""
        score = 0.0
        
        # Captures
        for move in board.legal_moves:
            if board.is_capture(move):
                score += self.config['evaluation']['capture_bonus']
        
        # Checks
        for move in board.legal_moves:
            board.push(move)
            if board.is_check():
                score += self.config['evaluation']['check_bonus']
            board.pop()
        
        return score

    def _castling_evaluation(self, board, color):
        """Evaluate castling rights and opportunities"""
        score = 0.0
        if board.has_castling_rights(color):
            score += self.config['evaluation']['castling_protection_bonus']
        
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
                        score += self.config['evaluation']['piece_coordination_bonus']
        return score
    
    def _pawn_structure(self, board, color):
        """Evaluate pawn structure"""
        score = 0.0
        
        # Count doubled pawns
        for square in board.pieces(chess.PAWN, color):
            file = chess.square_file(square)
            rank = chess.square_rank(square)
            if board.piece_at(chess.square(file, rank + 1)) and board.piece_at(chess.square(file, rank + 1)).piece_type == chess.PAWN:
                score -= self.config['evaluation']['doubled_pawn_penalty']
        
        # Count isolated pawns
        for square in board.pieces(chess.PAWN, color):
            file = chess.square_file(square)
            if not (board.piece_at(chess.square(file - 1, chess.square_rank(square))) or board.piece_at(chess.square(file + 1, chess.square_rank(square)))):
                score -= self.config['evaluation']['isolated_pawn_penalty']
        
        if score > 0:
            score += self.config['evaluation']['pawn_structure_bonus']

        return score
    
    def _pawn_weaknesses(self, board, color):
        """Evaluate pawn weaknesses"""
        score = 0.0
        
        # Count backward pawns
        for square in board.pieces(chess.PAWN, color):
            file = chess.square_file(square)
            rank = chess.square_rank(square)
            if rank < 7 and not board.piece_at(chess.square(file, rank + 1)):
                score -= self.config['evaluation']['backward_pawn_penalty']
        
        return score
    
    def _pawn_majority(self, board, color):
        """Evaluate pawn majority on the queenside or kingside"""
        score = 0.0
        
        # Count pawns on each side
        white_pawns = len(board.pieces(chess.PAWN, chess.WHITE))
        black_pawns = len(board.pieces(chess.PAWN, chess.BLACK))
        
        if color == chess.WHITE:
            if white_pawns > black_pawns:
                score += self.config['evaluation']['pawn_majority_bonus']
            elif white_pawns < black_pawns:
                score -= self.config['evaluation']['pawn_minority_penalty']
        else:
            if black_pawns > white_pawns:
                score += self.config['evaluation']['pawn_majority_bonus']
            elif black_pawns < white_pawns:
                score -= self.config['evaluation']['pawn_minority_penalty']
        
        return score
    
    def _passed_pawns(self, board, color):
        """Basic pawn structure evaluation"""
        score = 0.0
        
        # Check for passed pawns
        for color in [chess.WHITE, chess.BLACK]:
            for square in board.pieces(chess.PAWN, color):
                file = chess.square_file(square)
                rank = chess.square_rank(square)
                
                # Simple passed pawn detection
                is_passed = True
                direction = 1 if color == chess.WHITE else -1
                
                # Check if there are opponent pawns blocking or attacking
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
                    passed_bonus = self.config['evaluation']['passed_pawn_bonus']
                    if color == chess.WHITE:
                        score += passed_bonus
                    else:
                        score -= passed_bonus
        
        return score
    
    def _knight_pair(self, board, color):
        """Evaluate knight pair bonus"""
        score = 0.0
        knights = []
        for square in chess.SQUARES:
            piece = board.piece_at(square)
            if piece and piece.color == color:
                if piece.piece_type == chess.KNIGHT:
                    knights.append(square)
                    
        if len(knights) >= 2:
            score += len(knights) * self.config['evaluation']['knight_pair_bonus']
        return score

    def _bishop_pair(self, board, color):
        """Evaluate bishop pair bonus"""
        score = 0.0
        bishops = []
        for square in chess.SQUARES:
            piece = board.piece_at(square)
            if piece and piece.color == color:
                if piece.piece_type == chess.BISHOP:
                    bishops.append(square)

        if len(bishops) >= 2:
            score += len(bishops) * self.config['evaluation']['bishop_pair_bonus']
        return score

    def _bishop_vision(self, board, color):
        score = 0.0
        for square in chess.SQUARES:
            piece = board.piece_at(square)
            if piece and piece.color == color:
                if piece.piece_type == chess.BISHOP:
                    if len(board.attacks(square)) > 3:
                        score += self.config['evaluation']['bishop_vision_bonus']
        return score
    
    def _rook_coordination(self, board, color):
        """Calculate bonus for rook pairs on same file/rank"""
        score = 0.0
        rooks = [sq for sq in chess.SQUARES 
                if board.piece_at(sq) == chess.Piece(chess.ROOK, color)]
        
        # Check all unique rook pairs
        if rooks:  # Ensure rooks is not None
            for i in range(len(rooks)):
                for j in range(i+1, len(rooks)):
                    sq1, sq2 = rooks[i], rooks[j]
                    
                    # Same file bonus (15 centipawns)
                    if chess.square_file(sq1) == chess.square_file(sq2):
                        score += self.config['evaluation']['stacked_rooks_bonus']
                        
                    # Same rank bonus (10 centipawns)
                    if chess.square_rank(sq1) == chess.square_rank(sq2):
                        score += self.config['evaluation']['coordinated_rooks_bonus']
                    
                    # If rooks are on the 7th rank, give a bonus
                    if chess.square_rank(sq1) == 6 or chess.square_rank(sq2) == 6:
                        score += self.config['evaluation']['rook_positioning_bonus']
        
        return score
    
    def _open_files(self, board, color):
        """Evaluate open files for rooks"""
        score = 0.0
        open_files = 0
        
        # Count open files for the given color
        for file in range(8):
            if all(board.piece_at(chess.square(file, rank)) is None for rank in range(8)):
                open_files += 1
        
        # Bonus for each open file
        score += open_files * self.config['evaluation']['open_file_bonus']

        # If the player has rooks on open files, give a bonus
        for square in board.pieces(chess.ROOK, color):
            if chess.square_file(square) in range(8) and all(board.piece_at(chess.square(chess.square_file(square), rank)) is None for rank in range(8)):
                score += self.config['evaluation']['file_control_bonus']
        
        # If the king is on an open file, give an exposed king penalty
        if board.king(color) in range(8):
            score -= self.config['evaluation']['exposed_king_penalty']

        return score
    
    def _stalemate(self, board: chess.Board):
        """Check if the position is a stalemate"""
        if board.is_stalemate():
            return self.config['evaluation']['stalemate_penalty']
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

