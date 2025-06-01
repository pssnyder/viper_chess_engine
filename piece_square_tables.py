# piece_square_tables.py
# Advanced piece-square table implementation for chess engine evaluation

import chess

class PieceSquareTables:
    """
    Piece-Square Tables for chess position evaluation.
    These tables assign values to pieces based on their square location.
    Values are in centipawns (1/100th of a pawn).
    """
    
    def __init__(self):
        # Initialize piece-square tables
        self.tables = self._create_tables()
        
    def _create_tables(self):
        """Create all piece-square tables"""
        
        # Pawn table - encourages advancement and center control
        self.PAWN_TABLE = [
            [  0,  0,  0,  0,  0,  0,  0,  0],  # 8th rank (promotion)
            [ 50, 50, 50, 50, 50, 50, 50, 50],  # 7th rank 
            [ 10, 10, 20, 30, 30, 20, 10, 10],  # 6th rank
            [  5,  5, 10, 25, 25, 10,  5,  5],  # 5th rank
            [  0,  0,  0, 20, 20,  0,  0,  0],  # 4th rank
            [  5, -5,-10,  0,  0,-10, -5,  5],  # 3rd rank
            [  5, 10, 10,-20,-20, 10, 10,  5],  # 2nd rank
            [  0,  0,  0,  0,  0,  0,  0,  0]   # 1st rank
        ]
        
        # Knight table - heavily penalizes rim placement
        self.KNIGHT_TABLE = [
            [-50,-40,-30,-30,-30,-30,-40,-50],
            [-40,-20,  0,  0,  0,  0,-20,-40],
            [-30,  0, 10, 15, 15, 10,  0,-30],
            [-30,  5, 15, 20, 20, 15,  5,-30],
            [-30,  0, 15, 20, 20, 15,  0,-30],
            [-30,  5, 10, 15, 15, 10,  5,-30],
            [-40,-20,  0,  5,  5,  0,-20,-40],
            [-50,-40,-30,-30,-30,-30,-40,-50]
        ]
        
        # Bishop table - encourages long diagonals
        self.BISHOP_TABLE = [
            [-20,-10,-10,-10,-10,-10,-10,-20],
            [-10,  0,  0,  0,  0,  0,  0,-10],
            [-10,  0,  5, 10, 10,  5,  0,-10],
            [-10,  5,  5, 10, 10,  5,  5,-10],
            [-10,  0, 10, 10, 10, 10,  0,-10],
            [-10, 10, 10, 10, 10, 10, 10,-10],
            [-10,  5,  0,  0,  0,  0,  5,-10],
            [-20,-10,-10,-10,-10,-10,-10,-20]
        ]
        
        # Rook table - encourages 7th rank and center files
        self.ROOK_TABLE = [
            [  0,  0,  0,  0,  0,  0,  0,  0],
            [  5, 10, 10, 10, 10, 10, 10,  5],
            [ -5,  0,  0,  0,  0,  0,  0, -5],
            [ -5,  0,  0,  0,  0,  0,  0, -5],
            [ -5,  0,  0,  0,  0,  0,  0, -5],
            [ -5,  0,  0,  0,  0,  0,  0, -5],
            [ -5,  0,  0,  0,  0,  0,  0, -5],
            [  0,  0,  0,  5,  5,  0,  0,  0]
        ]
        
        # Queen table - discourages early development
        self.QUEEN_TABLE = [
            [-20,-10,-10, -5, -5,-10,-10,-20],
            [-10,  0,  0,  0,  0,  0,  0,-10],
            [-10,  0,  5,  5,  5,  5,  0,-10],
            [ -5,  0,  5,  5,  5,  5,  0, -5],
            [  0,  0,  5,  5,  5,  5,  0, -5],
            [-10,  5,  5,  5,  5,  5,  0,-10],
            [-10,  0,  5,  0,  0,  0,  0,-10],
            [-20,-10,-10, -5, -5,-10,-10,-20]
        ]
        
        # King table - encourages castling and safety
        self.KING_TABLE = [
            [-30,-40,-40,-50,-50,-40,-40,-30],
            [-30,-40,-40,-50,-50,-40,-40,-30],
            [-30,-40,-40,-50,-50,-40,-40,-30],
            [-30,-40,-40,-50,-50,-40,-40,-30],
            [-20,-30,-30,-40,-40,-30,-30,-20],
            [-10,-20,-20,-20,-20,-20,-20,-10],
            [ 20, 20,  0,  0,  0,  0, 20, 20],
            [ 20, 30, 10,  0,  0, 10, 30, 20]
        ]
        
        self.KING_MG_TABLE = [
            [-30, -40, -40, -50, -50, -40, -40, -30],
            [-30, -40, -40, -50, -50, -40, -40, -30],
            [-30, -40, -40, -50, -50, -40, -40, -30],
            [-30, -40, -40, -50, -50, -40, -40, -30],
            [-20, -30, -30, -40, -40, -30, -30, -20],
            [-10, -20, -20, -20, -20, -20, -20, -10],
            [ 20,  20,   0,   0,   0,   0,  20,  20],
            [ 20,  30,  10,   0,   0,  10,  30,  20]
        ]

        # King endgame table (encourages activity)
        self.KING_EG_TABLE = [
            [-50, -40, -30, -20, -20, -30, -40, -50],
            [-30, -20, -10,   0,   0, -10, -20, -30],
            [-30, -10,  20,  30,  30,  20, -10, -30],
            [-30, -10,  30,  40,  40,  30, -10, -30],
            [-30, -10,  30,  40,  40,  30, -10, -30],
            [-30, -10,  20,  30,  30,  20, -10, -30],
            [-30, -30,   0,   0,   0,   0, -30, -30],
            [-50, -30, -30, -30, -30, -30, -30, -50]
        ]
    
    def get_piece_value(self, piece, square, color, endgame_factor=0.0):
        """
        Get the piece-square table value for a piece on a specific square.
        
        Args:
            piece_type: chess.PAWN, chess.KNIGHT, etc.
            square: chess square (0-63)
            color: chess.WHITE or chess.BLACK
            
        Returns:
            Value in centipawns (positive is good for the piece's color)
        """

        file = chess.square_file(square)  # 0-7 (a-h)
        rank = chess.square_rank(square)  # 0-7 (1-8)
        
        # For black pieces, flip the rank (black's perspective)
        if color == chess.BLACK:
            rank = 7 - rank
        
        if piece.piece_type == chess.PAWN:
            return self.PAWN_TABLE[rank][file]
        elif piece.piece_type == chess.KNIGHT:
            return self.KNIGHT_TABLE[rank][file]
        elif piece.piece_type == chess.BISHOP:
            return self.BISHOP_TABLE[rank][file]
        elif piece.piece_type == chess.ROOK:
            return self.ROOK_TABLE[rank][file]
        elif piece.piece_type == chess.QUEEN:
            return self.QUEEN_TABLE[rank][file]
        elif piece.piece_type == chess.KING:
            return self.KING_TABLE[rank][file]
            # Interpolate between middle game and endgame tables
            #mg_value = self.KING_MG_TABLE[rank][file]
            #eg_value = self.KING_EG_TABLE[rank][file]
            #return mg_value * (1 - endgame_factor) + eg_value * endgame_factor
        else:
            return 0
    
    def evaluate_board_position(self, board):
        """
        Evaluate the entire board using piece-square tables.
        
        Args:
            board: chess.Board object
            
        Returns:
            Total piece-square table score (positive favors white)
        """
        total_score = 0
        
        for square in chess.SQUARES:
            piece = board.piece_at(square)
            if piece:
                value = self.get_piece_value(piece.piece_type, square, piece.color)
                if piece.color == chess.WHITE:
                    total_score += value
                else:
                    total_score -= value
                    
        return total_score / 100.0  # Convert centipawns to pawn units


# Integration function for your existing evaluation engine
def add_piece_square_evaluation(evaluation_engine_instance):
    """
    Add piece-square table evaluation to your existing EvaluationEngine class.
    Call this function in your EvaluationEngine.__init__() method.
    """
    evaluation_engine_instance.pst = PieceSquareTables()
    
    # Add new evaluation method
    def _piece_square_evaluation(self):
        """Evaluate position using piece-square tables"""
        return self.pst.evaluate_board_position(self.board) * 1.2  # Weight factor
    
    # Bind the method to the instance
    import types
    evaluation_engine_instance._piece_square_evaluation = types.MethodType(_piece_square_evaluation, evaluation_engine_instance)


# Example usage and testing
if __name__ == "__main__":
    # Test the piece-square tables
    pst = PieceSquareTables()
    board = chess.Board()
    
    print("Initial position PST evaluation:", pst.evaluate_board_position(board))
    
    # Test specific squares
    print(f"Knight on h3 value: {pst.get_piece_value(chess.KNIGHT, chess.H3, chess.WHITE)}")
    print(f"Knight on e4 value: {pst.get_piece_value(chess.KNIGHT, chess.E4, chess.WHITE)}")
    print(f"Difference: {pst.get_piece_value(chess.KNIGHT, chess.E4, chess.WHITE) - pst.get_piece_value(chess.KNIGHT, chess.H3, chess.WHITE)} centipawns")