# viper_scoring_calculation.py

""" Viper Scoring Calculation Module
This module implements the scoring calculation for the Viper Chess Engine.
It provides various scoring functions for evaluation, quiescence, and move ordering
"""
import chess
import yaml
import random
import logging
import os
import threading # TODO enable parrallel score calculations via threading
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


class ViperScoringCalculation:
    def __init__(self, board: chess.Board = chess.Board(), player: chess.Color = chess.WHITE, ai_config=None):
        self.board = board
        self.current_player = player

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

        # Enable logging
        self.logging_enabled = self.config.get('debug', {}).get('enable_logging', False)
        self.show_thoughts = self.config.get('debug', {}).get('show_thinking', False)
        self.logger = evaluation_logger  # Use the module-level logger
        if self.logging_enabled:
            self.logger.debug("Logging enabled for Scoring Calculation")
        else:
            self.show_thoughts = False

        # Initialize piece-square tables
        self.pst = PieceSquareTables() # Initialize PST here
        # Bind the evaluation method to the instance
        import types
        self._piece_square_evaluation = types.MethodType(self._piece_square_table_evaluation_method, self) # Ensure this is properly bound

        # Strict draw prevention setting
        self.strict_draw_prevention = self.config.get('game_config', {}).get('strict_draw_prevention', False)

        # Endgame awareness setting
        self.game_phase_awareness = self.config.get('game_config', {}).get('game_phase_awareness', False)
        self.endgame_factor = 0.0 # Will be dynamically updated

    def _calculate_score(self, board, color, endgame_factor: float = 0.0):
        """IMPROVED scoring with piece-square tables and endgame awareness"""
        score = 0.0

        # Get piece-square table weight from ai_config or config
        self.pst_weight = self.ai_config.get('pst_weight', self.config.get('white_ai_config', {}).get('pst_weight', 1.0) if color == chess.WHITE else self.config.get('black_ai_config', {}).get('pst_weight', 1.0))
        
        # Get material weight from ai_config or config
        self.material_weight = self.ai_config.get(self.ruleset, {}).get('material_weight', 1.0)

        # Determine the game phase: opening, middlegame, or endgame, higher endgame_factor means more endgame criteria is met
        if self.game_phase_awareness:
            # Calculate the material game phase score based on material balance
            material_score = self._material_score(board, color)
            if abs(material_score) < 5:
                # If material score is low, it's likely an endgame
                endgame_factor = 1.0
            elif abs(material_score) < 15:
                # If material score is moderate, it's likely a middlegame
                endgame_factor = 0.5
            else:
                # If material score is high, it's likely an opening or early middlegame
                endgame_factor = 0.0
            # 
        # Rules included in scoring:
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
        
        # Pass endgame_factor to piece_square_evaluation
        if self.pst_enabled:
            score += self.scoring_modifier * self.pst_weight * (self.pst.evaluate_board_position(board, endgame_factor) or 0.0)
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
        # pawn_majority_score = self.scoring_modifier * (self._pawn_majority(board, color) or 0.0) # TODO
        # score += pawn_majority_score
        # if self.show_thoughts and self.logger:
        #     self.logger.debug(f"Pawn majority score: {pawn_majority_score:.3f} | FEN: {board.fen()}")
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
    
    # NOTE: These functions are from your original code. I've only added the 'endgame_factor' parameter
    #       to _calculate_score and ensured it's passed down to PST evaluation.
    #       No fundamental changes to their logic beyond that, as per your request.
    
    def _checkmate_threats(self, board):
        score = 0.0
        for move in board.legal_moves:
            board.push(move)
            if board.is_checkmate():
                score += self.ai_config.get(self.ruleset, {}).get('checkmate_bonus', 0)
                board.pop() # Pop before breaking
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
    
    # This method is now handled by directly calling self.pst.evaluate_board_position
    # It remains here to avoid breaking existing references, but will be removed in future refactors if not needed.
    def _piece_square_table_evaluation_method(self, board, color, endgame_factor=0.0):
        """Evaluate position using piece-square tables. This is the old binding. The direct PST call is used now. """
        # This method is effectively deprecated by the direct PST call in _calculate_score
        # It's kept for now to avoid breaking the dynamically bound method name from the original snippet.
        if not self.pst_enabled:
            return 0.0
        return self.pst.evaluate_board_position(board, endgame_factor) * self.pst_weight


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
        turn = board.turn # Directly use board.turn
        if not board.is_game_over(claim_draw=self._is_draw_condition(board)) and board.is_valid() and turn == color:
            return self.ai_config.get(self.ruleset, {}).get('tempo_bonus', 0.0)  # Small tempo bonus
        return 0.0

    def _is_attacked_by_pawn(self, board, square, by_color):
        """Helper function to check if a square is attacked by enemy pawns"""
        # chess.Board.attacks_with() is more robust for this check
        return bool(board.attacks_with(square, chess.PAWN) & board.pieces(chess.PAWN, by_color))

    def _center_control(self, board):
        """Simple center control"""
        score = 0.0
        center = [chess.D4, chess.D5, chess.E4, chess.E5]
        for square in center:
            piece = board.piece_at(square)
            if piece:
                # Check for piece color to attribute score correctly
                if piece.color == chess.WHITE:
                    score += self.ai_config.get(self.ruleset, {}).get('center_control_bonus', 0.0)
                else:
                    score -= self.ai_config.get(self.ruleset, {}).get('center_control_bonus', 0.0)
        return score

    def _piece_activity(self, board, color):
        """Mobility and attack patterns"""
        score = 0.0

        for square in board.pieces(chess.KNIGHT, color):
            score += len(list(board.attacks(square))) * self.ai_config.get(self.ruleset, {}).get('knight_activity_bonus', 0.0)

        for square in board.pieces(chess.BISHOP, color):
            score += len(list(board.attacks(square))) * self.ai_config.get(self.ruleset, {}).get('bishop_activity_bonus', 0.0)

        return score

    def _king_safety(self, board, color):
        score = 0.0
        king_square = board.king(color)
        if king_square is None:
            return score

        # Check for pawns directly in front of the king (king shield)
        king_file = chess.square_file(king_square)
        king_rank = chess.square_rank(king_square)

        # Define squares in front of the king for a pawn shield
        if color == chess.WHITE:
            shield_ranks = [king_rank + 1]
            # Consider pawns on ranks 2 and 3 if king is still on rank 1 (after castling)
            if king_rank == 0:
                shield_ranks.extend([1, 2])
        else: # Black
            shield_ranks = [king_rank - 1]
            # Consider pawns on ranks 6 and 7 if king is still on rank 8 (after castling)
            if king_rank == 7:
                shield_ranks.extend([6, 5])

        for rank_offset in shield_ranks:
            for file_offset in [-1, 0, 1]: # Check adjacent files too
                if 0 <= king_file + file_offset <= 7 and 0 <= rank_offset <= 7:
                    shield_square = chess.square(king_file + file_offset, rank_offset)
                    piece = board.piece_at(shield_square)
                    if piece and piece.piece_type == chess.PAWN and piece.color == color:
                        score += self.ai_config.get(self.ruleset, {}).get('king_safety_bonus', 0.0)
        
        return score

    def _king_threat(self, board):
        """
        Evaluate if the opponent's king is under threat (in check) in the current position.
        Adds a penalty/bonus if the opponent's king is in check.
        """
        score = 0.0
        # Check if the current player has the opponent's king in check
        if board.is_check():
            # If current player's turn and opponent is in check, it's a bonus for the current player
            # If opponent's turn and current player is in check, it's a penalty for the current player
            if board.turn == self.current_player: # Self is giving check
                score += self.ai_config.get(self.ruleset, {}).get('check_bonus', 0.0)
            else: # Self is in check
                score += self.ai_config.get(self.ruleset, {}).get('in_check_penalty', 0.0)
        return score

    def _undeveloped_pieces(self, board, color):
        score = 0.0
        undeveloped_count = 0.0

        starting_squares = {
            chess.WHITE: {chess.KNIGHT: [chess.B1, chess.G1], chess.BISHOP: [chess.C1, chess.F1]},
            chess.BLACK: {chess.KNIGHT: [chess.B8, chess.G8], chess.BISHOP: [chess.C8, chess.F8]}
        }

        for piece_type, squares in starting_squares[color].items():
            for square in squares:
                piece = board.piece_at(square)
                if piece and piece.color == color and piece.piece_type == piece_type:
                    undeveloped_count += 1

        # Apply penalty only if castling rights exist (implies early/middlegame)
        if undeveloped_count > 0 and (board.has_kingside_castling_rights(color) or board.has_queenside_castling_rights(color)):
            score = undeveloped_count * self.ai_config.get(self.ruleset, {}).get('undeveloped_penalty', 0.0)

        return score

    def _mobility_score(self, board, color):
        """Evaluate mobility of pieces"""
        score = 0.0
        
        # Iterate over all pieces of the given color
        for square in chess.SQUARES:
            piece = board.piece_at(square)
            if piece and piece.color == color and piece.piece_type != chess.KING: # Exclude king from general mobility
                score += len(list(board.attacks(square))) * self.ai_config.get(self.ruleset, {}).get('piece_mobility_bonus', 0.0)

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
        
        # Hanging pieces (undefended pieces that can be captured)
        # This needs to be evaluated from the perspective of the side whose turn it is
        # For simplicity, we can iterate all pieces and see if they are attacked by opponent
        # and not defended by own pieces.
        current_turn_color = board.turn
        opponent_color = not current_turn_color

        for square in chess.SQUARES:
            piece = board.piece_at(square)
            if piece and piece.color == current_turn_color: # Check own pieces
                if board.is_attacked_by(opponent_color, square) and not board.is_defended_by(current_turn_color, square):
                    score -= self.ai_config.get(self.ruleset, {}).get('undefended_piece_penalty', 0.0) # Penalty for having undefended piece
            elif piece and piece.color == opponent_color: # Check opponent pieces
                 if board.is_attacked_by(current_turn_color, square) and not board.is_defended_by(opponent_color, square):
                    score += self.ai_config.get(self.ruleset, {}).get('hanging_piece_bonus', 0.0) # Bonus for attacking hanging piece

        return score

    def _castling_evaluation(self, board, color):
        """Evaluate castling rights and opportunities"""
        score = 0.0

        # Check if castled - more robust check considering king's final position
        king_sq = board.king(color)
        if king_sq: # Ensure king exists
            if color == chess.WHITE:
                if king_sq == chess.G1: # Kingside castled
                    score += self.ai_config.get(self.ruleset, {}).get('castling_bonus', 0.0)
                elif king_sq == chess.C1: # Queenside castled
                    score += self.ai_config.get(self.ruleset, {}).get('castling_bonus', 0.0)
            else: # Black
                if king_sq == chess.G8: # Kingside castled
                    score += self.ai_config.get(self.ruleset, {}).get('castling_bonus', 0.0)
                elif king_sq == chess.C8: # Queenside castled
                    score += self.ai_config.get(self.ruleset, {}).get('castling_bonus', 0.0)

        # Penalty if castling rights lost and not yet castled (important catch: will not consider the castling action itself as losing castling rights)
        # This part should be careful not to penalize if castling *just occurred*
        initial_king_square = chess.E1 if color == chess.WHITE else chess.E8
        # Only penalize if king is still on initial square AND rights are lost
        if not board.has_castling_rights(color) and king_sq == initial_king_square:
            score += self.ai_config.get(self.ruleset, {}).get('castling_protection_penalty', 0.0)
        
        # Bonus if still has kingside or queenside castling rights
        if board.has_kingside_castling_rights(color) and board.has_queenside_castling_rights(color):
            score += self.ai_config.get(self.ruleset, {}).get('castling_protection_bonus', 0.0)
        elif board.has_kingside_castling_rights(color) or board.has_queenside_castling_rights(color):
            score += self.ai_config.get(self.ruleset, {}).get('castling_protection_bonus', 0.0) / 2
        
        return score

    def _piece_coordination(self, board, color):
        """Evaluate piece defense coordination for all pieces of the given color."""
        score = 0.0
        # For each piece of the given color
        for square in chess.SQUARES:
            piece = board.piece_at(square)
            if piece and piece.color == color:
                # If the piece is defended by another friendly piece
                if board.is_defended_by(color, square):
                    score += self.ai_config.get(self.ruleset, {}).get('piece_coordination_bonus', 0.0)
        return score
    
    def _pawn_structure(self, board, color):
        """Evaluate pawn structure"""
        score = 0.0
        
        # Count doubled pawns
        for file in range(8):
            pawns_on_file = [s for s in board.pieces(chess.PAWN, color) if chess.square_file(s) == file]
            if len(pawns_on_file) > 1:
                score += (len(pawns_on_file) - 1) * self.ai_config.get(self.ruleset, {}).get('doubled_pawn_penalty', 0.0)
        
        # Count isolated pawns
        for square in board.pieces(chess.PAWN, color):
            file = chess.square_file(square)
            is_isolated = True
            # Check left file
            if file > 0:
                if any(board.piece_at(chess.square(file - 1, r)) and board.piece_at(chess.square(file - 1, r)).piece_type == chess.PAWN and board.piece_at(chess.square(file - 1, r)).color == color for r in range(8)):
                    is_isolated = False
            # Check right file
            if file < 7:
                if any(board.piece_at(chess.square(file + 1, r)) and board.piece_at(chess.square(file + 1, r)).piece_type == chess.PAWN and board.piece_at(chess.square(file + 1, r)).color == color for r in range(8)):
                    is_isolated = False
            if is_isolated:
                score += self.ai_config.get(self.ruleset, {}).get('isolated_pawn_penalty', 0.0)
        
        if score > 0: # This check seems counter-intuitive if penalties are negative
            score += self.ai_config.get(self.ruleset, {}).get('pawn_structure_bonus', 0.0) # Bonus for *good* structure

        return score

    def _pawn_weaknesses(self, board, color):
        """Evaluate pawn weaknesses (e.g., backward pawns)"""
        score = 0.0
        
        # Count backward pawns
        # A pawn is backward if it cannot be defended by another pawn and is on an open or semi-open file
        # A simplified definition for a backward pawn: cannot advance and is attacked by an opponent pawn
        direction = 1 if color == chess.WHITE else -1
        for square in board.pieces(chess.PAWN, color):
            file = chess.square_file(square)
            rank = chess.square_rank(square)
            
            # Check if pawn can advance
            can_advance = False
            if color == chess.WHITE and rank < 7 and not board.piece_at(chess.square(file, rank + 1)):
                can_advance = True
            elif color == chess.BLACK and rank > 0 and not board.piece_at(chess.square(file, rank - 1)):
                can_advance = True
            
            if not can_advance:
                # Check if attacked by opponent pawn
                opponent_color = not color
                if self._is_attacked_by_pawn(board, square, opponent_color):
                    score += self.ai_config.get(self.ruleset, {}).get('backward_pawn_penalty', 0.0)
        
        return score

    def _pawn_majority(self, board, color):
        """Evaluate pawn majority on the queenside or kingside"""
        score = 0.0
        
        # Count pawns on each side
        white_pawns_kingside = len([p for p in board.pieces(chess.PAWN, chess.WHITE) if chess.square_file(p) >= 4])
        white_pawns_queenside = len([p for p in board.pieces(chess.PAWN, chess.WHITE) if chess.square_file(p) < 4])
        black_pawns_kingside = len([p for p in board.pieces(chess.PAWN, chess.BLACK) if chess.square_file(p) >= 4])
        black_pawns_queenside = len([p for p in board.pieces(chess.PAWN, chess.BLACK) if chess.square_file(p) < 4])
        
        if color == chess.WHITE:
            if white_pawns_kingside > black_pawns_kingside:
                score += self.ai_config.get(self.ruleset, {}).get('pawn_majority_bonus', 0.0) / 2 # Half bonus for kingside
            if white_pawns_queenside > black_pawns_queenside:
                score += self.ai_config.get(self.ruleset, {}).get('pawn_majority_bonus', 0.0) / 2 # Half bonus for queenside
        else: # Black
            if black_pawns_kingside > white_pawns_kingside:
                score += self.ai_config.get(self.ruleset, {}).get('pawn_majority_bonus', 0.0) / 2
            if black_pawns_queenside > white_pawns_queenside:
                score += self.ai_config.get(self.ruleset, {}).get('pawn_majority_bonus', 0.0) / 2
        
        return score

    def _passed_pawns(self, board, color):
        """Basic pawn structure evaluation for passed pawns"""
        score = 0.0
        
        for square in board.pieces(chess.PAWN, color):
            if board.is_passed(square, color): # Use the built-in is_passed method
                score += self.ai_config.get(self.ruleset, {}).get('passed_pawn_bonus', 0.0)
        return score

    def _knight_pair(self, board, color):
        """Evaluate knight pair bonus"""
        score = 0.0
        knights = board.pieces(chess.KNIGHT, color)
        if len(list(knights)) >= 2: # Ensure it's iterable and count
            score += len(list(knights)) * self.ai_config.get(self.ruleset, {}).get('knight_pair_bonus', 0.0)
        return score

    def _bishop_pair(self, board, color):
        """Evaluate bishop pair bonus"""
        score = 0.0
        bishops = board.pieces(chess.BISHOP, color)
        if len(list(bishops)) >= 2: # Ensure it's iterable and count
            score += self.ai_config.get(self.ruleset, {}).get('bishop_pair_bonus', 0.0)
        return score

    def _bishop_vision(self, board, color):
        """Evaluate bishop vision bonus"""
        score = 0.0
        for sq in board.pieces(chess.BISHOP, color):
            attacks = board.attacks(sq)
            # Bonus for having more attacked squares (i.e., good vision)
            if len(list(attacks)) > 5: # Bishops generally attack 7-13 squares, adjust threshold as needed
                score += self.ai_config.get(self.ruleset, {}).get('bishop_vision_bonus', 0.0)
        return score

    def _rook_coordination(self, board, color):
        """Calculate bonus for rook pairs on same file/rank"""
        score = 0.0
        rooks = list(board.pieces(chess.ROOK, color)) # Convert to list for iteration

        for i in range(len(rooks)):
            for j in range(i+1, len(rooks)):
                sq1, sq2 = rooks[i], rooks[j]
                if chess.square_file(sq1) == chess.square_file(sq2):
                    score += self.ai_config.get(self.ruleset, {}).get('stacked_rooks_bonus', 0.0)
                if chess.square_rank(sq1) == chess.square_rank(sq2):
                    score += self.ai_config.get(self.ruleset, {}).get('coordinated_rooks_bonus', 0.0)
                
                # Rook on 7th rank bonus (critical for attacking pawns)
                if (color == chess.WHITE and (chess.square_rank(sq1) == 6 or chess.square_rank(sq2) == 6)) or \
                   (color == chess.BLACK and (chess.square_rank(sq1) == 1 or chess.square_rank(sq2) == 1)):
                    score += self.ai_config.get(self.ruleset, {}).get('rook_position_bonus', 0.0)
        return score

    def _open_files(self, board, color):
        """Evaluate open files for rooks and king safety"""
        score = 0.0
        
        for file in range(8):
            is_open_file = True
            has_own_pawn = False
            has_opponent_pawn = False
            for rank in range(8):
                sq = chess.square(file, rank)
                piece = board.piece_at(sq)
                if piece and piece.piece_type == chess.PAWN:
                    is_open_file = False
                    if piece.color == color:
                        has_own_pawn = True
                    else:
                        has_opponent_pawn = True
            
            # Bonus for having an open file
            if is_open_file:
                score += self.ai_config.get(self.ruleset, {}).get('open_file_bonus', 0.0)
                # Bonus if a rook is on an open file
                if any(board.piece_at(chess.square(file, r)) == chess.Piece(chess.ROOK, color) for r in range(8)):
                    score += self.ai_config.get(self.ruleset, {}).get('file_control_bonus', 0.0)
            
            # Exposed king penalty if king is on an open file
            king_sq = board.king(color)
            if king_sq is not None and chess.square_file(king_sq) == file and is_open_file:
                score += self.ai_config.get(self.ruleset, {}).get('exposed_king_penalty', 0.0) # Penalty for exposed king

        return score
    
    def _stalemate(self, board: chess.Board):
        """Check if the position is a stalemate"""
        if board.is_stalemate():
            return self.ai_config.get(self.ruleset, {}).get('stalemate_penalty', 0.0)
        return 0.0
