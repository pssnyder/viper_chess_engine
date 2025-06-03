# chess_puzzles.py

import chess
import chess.pgn
import logging
import yaml

class ChessPuzzles:
    """
    Class to handle chess puzzles.
    It provides methods to create, solve, and manage chess puzzles.
    """

    def __init__(self):
        self.puzzles = []
        self.config = {}
        self.puzzle_config = {}
        self.positional_solutions = {}
        self.logger = None
        puzzles = ChessPuzzles()
        
        # Load configuration with error handling
        try:
            with open("config.yaml") as f:
                self.config = yaml.safe_load(f)
        except Exception as e:
            print(f"Error loading config: {e}")

        # Set up puzzle solver
        self.puzzle_config = self.config.get('puzzle_config', {})
        if not self.puzzle_config:
            raise ValueError("Puzzle configuration not found in config file.")
        self.puzzle_count = self.puzzle_config.get('puzzle_count', 1)
        self.puzzle_solution_length = self.puzzle_config.get('puzzle_solution_length', 1)
        self.puzzle_difficulty = self.puzzle_config.get('puzzle_difficulty', 'easy')
        self.puzzle_types = self.puzzle_config.get('puzzle_types', ['mate', 'mateIn2', 'mateIn3'])
        self.puzzle_file = self.puzzle_config.get('puzzle_file', 'puzzles/lichess_db_puzzle.csv')

        # Set up logging
        self.configure_logging(self.config.get('log_file', 'logging/puzzle_solving.log'))
        self.logger = logging.getLogger(__name__)


        # Load puzzles from the puzzle file that match the configuration criteria
        self.load_puzzles()
    
    def configure_logging(self, log_file: str):
        """
        Configure logging for the class.
        
        :param log_file: Path to the log file
        """
        logging.basicConfig(filename=log_file, level=logging.INFO,
                            format='%(asctime)s - %(levelname)s - %(message)s')
        self.logger = logging.getLogger(__name__)
    
    def load_puzzles(self):
        parts = []
        solution_text = ''
        solution = []
        keyword_text = ''
        keywords = []
        keyword_not_found = False

        try:
            with open(self.puzzle_file, 'r', encoding='utf-8') as file:
                for line in file:
                    # Load all single move puzzles into the positional solutions dictionary and criteria matching puzzles into puzzles dictionary
                    parts = line.strip().split(',')
                    if len(parts) >= 3 and parts[1].strip() and parts[2].strip():
                        fen = parts[1]
                        solution_text = parts[2]
                        keyword_text = parts[3:] if len(parts) > 3 else []

                        # Split the solution into individual moves if necessary
                        if ' ' in solution_text:
                            solution = solution_text.split(' ')[0]

                        # Split the keywords into a list
                        if ' ' in keyword_text:
                            keywords = keyword_text.split(' ')[0]

                        for keyword in self.puzzle_types:
                            if keyword.lower() not in keywords:
                                keyword_not_found = True

                        for difficulty in self.puzzle_difficulty:
                            if difficulty.lower() not in keywords:
                                keyword_not_found = True
                        
                        # Check if the puzzle fits the positional solution criteria
                        if fen not in self.positional_solutions and solution.__len__() == 1:
                            self.positional_solutions[fen] = solution_text

                        # Check if the puzzle fits the configuration criteria
                        if (solution.__len__() > self.puzzle_solution_length or keyword_not_found):
                            continue # Skip puzzles that do not match the criteria
                        
                        # Add the puzzle to this puzzle session if it matches the criteria
                        self.add_puzzle(fen, solution_text)

        except FileNotFoundError:
            self.logger.warning(f"File {self.puzzle_file} not found.")

    def add_puzzle(self, fen: str, solution: str):
        """
        Add a new puzzle with its FEN string and solution.
        
        :param fen: FEN string representing the puzzle position
        :param solution: Solution in UCI format (e.g., 'e2e4')
        """
        self.puzzles.append({'fen': fen, 'solution': solution})

    def get_puzzle(self, index: int):
        """
        Get a puzzle by its index.
        
        :param index: Index of the puzzle
        :return: Dictionary containing the FEN and solution
        """
        return self.puzzles[index] if 0 <= index < len(self.puzzles) else None
    
    def get_random_puzzle(self):
        """
        Get a random puzzle from the list of puzzles.

        :return: Random puzzle dictionary containing FEN and solution
        """
        import random
        if not self.puzzles:
            return None
        return random.choice(self.puzzles)

    def solve_puzzle(self, index: int, move: str):
        """
        Check if the provided move solves the puzzle.
        
        :param index: Index of the puzzle
        :param move: Move in UCI format to check
        :return: True if the move is correct, False otherwise
        """
        puzzle = self.get_puzzle(index)
        return puzzle is not None and puzzle['solution'] == move
    
    def find_puzzle_solution(self, fen: str):
        """
        Find a positional solution for a given FEN string.

        :param fen: FEN string representing the position
        :return: Single move solution in UCI format if found, None otherwise
        """
        return self.positional_solutions.get(fen, None)
    
    def test_solution(self, index: int, move: str):
        """
        Test a solution against a puzzle.
        
        :param index: Index of the puzzle
        :param move: Move in UCI format to test
        :return: Tuple (is_correct, message)
        """
        if self.solve_puzzle(index, move):
            return True, "Correct solution!"
        else:
            return False, "Incorrect solution. Try again."
        
    def log_result(self, index: int, result: str):
        """
        Log the result of solving a puzzle.
        
        :param index: Index of the puzzle
        :param result: Result of the attempt (e.g., 'correct', 'incorrect')
        """
        puzzle = self.get_puzzle(index)
        if puzzle:
            self.logger.info(f"Puzzle {index} ({puzzle['fen']}): {result}")
        else:
            self.logger.warning(f"Attempted to log result for non-existent puzzle index {index}.")
    
    
# Example usage
if __name__ == "__main__":
    puzzles = ChessPuzzles()
    puzzles.load_puzzles()
    random_puzzle = puzzles.get_random_puzzle()
    if random_puzzle:
        print(f"Random Puzzle FEN: {random_puzzle['fen']}")
        move = input("Enter your move in UCI format (e.g., e2e4): ")
        is_correct, message = puzzles.test_solution(0, move)
        print(message)
        puzzles.log_result(0, 'correct' if is_correct else 'incorrect')
    else:
        print("No puzzles available.")