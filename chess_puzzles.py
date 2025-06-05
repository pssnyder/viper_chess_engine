# chess_puzzles.py

"""
    This module provides the ChessPuzzles class for managing, loading, and solving chess puzzles.
    It supports loading puzzles from a CSV file, filtering them by difficulty and type, and tracking solutions.
    The class also provides logging functionality and debug output for development and troubleshooting.
    Classes:
        ChessPuzzles: Handles the creation, management, and solving of chess puzzles, including configuration loading,
                      puzzle selection, solution checking, and result logging.
    UNFINISHED CODE - Still in development DO NOT DEPLOY
    """
import logging
import yaml
import random

class ChessPuzzles:
    """
    Class to handle chess puzzles.
    It provides methods to create, solve, and manage chess puzzles.
    """

    def __init__(self, debug=False):
        self.puzzles = []
        self.config = {}
        self.puzzle_config = {}
        self.positional_solutions = {}
        self.logger = None
        self.debug = debug
        
        # Load configuration with error handling
        try:
            with open("config.yaml") as f:
                self.config = yaml.safe_load(f)
            if self.debug:
                print("[DEBUG] Loaded config file successfully.")
        except Exception as e:
            print(f"Error loading config: {e}")

        # Set up puzzle solver
        self.puzzle_config = self.config.get('puzzle_config', {})
        self.puzzle_time_limit = self.puzzle_config.get('puzzle_time_limit', 60)
        self.puzzle_count = self.puzzle_config.get('puzzle_count', 1)
        self.puzzle_solution_limit = self.puzzle_config.get('puzzle_solution_limit', 1)
        self.puzzle_difficulty = self.puzzle_config.get('puzzle_difficulty', 0)
        self.puzzle_types = self.puzzle_config.get('puzzle_types', ['mate', 'mateIn2', 'mateIn3'])
        self.puzzle_file = self.puzzle_config.get('puzzle_file', 'puzzles/lichess_db_puzzle.csv')

        # Set up logging
        self.configure_logging(self.config.get('log_file', 'logging/puzzle_solving.log'))
        self.logger = logging.getLogger(__name__)

        if self.debug:
            print("[DEBUG] Puzzle config:", self.puzzle_config)
            print("[DEBUG] Puzzle file:", self.puzzle_file)

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
        if self.debug:
            print(f"[DEBUG] Logging configured. Log file: {log_file}")
    
    def load_puzzles(self):
        parts = []
        solution_text = ''
        solution = []
        keyword_text = ''
        keywords = []
        keyword_not_found = False
        skip_count = 0
        selected_count = 0
        positional_count = 0

        try:
            with open(self.puzzle_file, 'r', encoding='utf-8') as file:
                for line in file:
                    # Load all single move puzzles into the positional solutions dictionary and criteria matching puzzles into puzzles dictionary
                    parts = line.strip().split(',')
                    if parts[0].strip() == "PuzzleId":
                        continue  # Skip header line

                    if len(parts) >= 7 and parts[1].strip() and parts[2].strip() and parts[3].strip() and parts[7].strip():
                        # Extract the FEN, solution, rating, and keywords from the line
                        fen = parts[1]
                        solution_text = parts[2]
                        rating = parts[3]
                        keyword_text = parts[7] if len(parts) > 4 else ''
                        keyword_found = False
                        too_difficult = False
                        # Split the solution into individual moves if necessary
                        if ' ' in solution_text:
                            solution = solution_text.split(' ')[0]
                        else:
                            solution = [solution_text]

                        # Split the keywords into a list
                        if isinstance(keyword_text, list):
                            keywords = [k.strip() for k in keyword_text]
                        else:
                            keywords = [keyword_text.strip()]

                        # Check if the puzzle fits the positional solution criteria
                        if fen not in self.positional_solutions:
                            self.positional_solutions[fen] = solution[0] # Store only the first move as a positional solution
                        positional_count += 1

                        # Check if the puzzle fits the configuration criteria
                        for limiting_keyword in self.puzzle_types:
                            for keyword in keywords:
                                if limiting_keyword in keyword.lower():
                                    keyword_found = True
                                break  # Found a matching keyword, no need to check further
                        
                        # Check if the puzzle matches the difficulty level
                        if self.puzzle_difficulty > 0 and int(rating) < self.puzzle_difficulty:
                            too_difficult = True

                        # If the puzzle does not match the criteria, skip it
                        if (len(solution) > self.puzzle_solution_limit or not keyword_found or too_difficult):
                            skip_count += 1
                            continue # Skip puzzles that do not match the criteria
                        
                        # Add the puzzle to this puzzle session if it matches the criteria
                        self.add_puzzle(fen, solution)
                        selected_count += 1
                
                if self.debug:
                    print('[DEBUG] Puzzles added:', selected_count)
                    print('[DEBUG] Puzzles skipped:', skip_count)
                    print('[DEBUG] Positional solutions created:', positional_count)

        except FileNotFoundError:
            self.logger.warning(f"File {self.puzzle_file} not found.")
            if self.debug:
                print(f"[DEBUG] File {self.puzzle_file} not found.")

    def add_puzzle(self, fen: str, solution: str):
        """
        Add a new puzzle with its FEN string and solution.
        
        :param fen: FEN string representing the puzzle position
        :param solution: Solution array in UCI spaced format (e.g., ['e2e4', 'e7e5', 'b1c3'])
        """
        self.puzzles.append({'fen': fen, 'solution': solution, 'solved': False})
        
    def get_puzzle(self, index: int):
        """
        Get a puzzle by its index.
        
        :param index: Index of the puzzle
        :return: Dictionary containing the FEN and solution
        """
        if self.debug:
            print(f"[DEBUG] Getting puzzle at index: {index}")
        return self.puzzles[index] if 0 <= index < len(self.puzzles) else None
    
    def get_random_puzzle(self):
        """
        Get a random puzzle from the list of puzzles.
        
        :return: Random puzzle dictionary containing FEN and solution, or None if no puzzles are available
        """
        if not self.puzzles:
            if self.debug:
                print("[DEBUG] No puzzles available for random selection.")
            return None
        puzzle = random.choice(self.puzzles)
        puzzle_solved = puzzle.get('solved', False)
        if self.debug:
            print(f"[DEBUG] Random puzzle selected: {puzzle}")
        return puzzle if not puzzle_solved else self.get_random_puzzle()

    def solve_puzzle(self, index: int, move: str):
        """
        Check if the provided move solves the puzzle.
        
        :param index: Index of the puzzle
        :param move: Move in UCI format to check
        :return: True if the move is correct, False otherwise
        """
        puzzle = self.get_puzzle(index)
        if self.debug:
            print(f"[DEBUG] Solving puzzle at index {index} with move {move}. Puzzle: {puzzle}")
        return puzzle is not None and puzzle['solution'] == move
    
    def find_puzzle_solution(self, fen: str):
        """
        Find a positional solution for a given FEN string.

        :param fen: FEN string representing the position
        :return: Single move solution in UCI format if found, None otherwise
        """
        if self.debug:
            print(f"[DEBUG] Finding solution for FEN: {fen}")
        return self.positional_solutions.get(fen, None)
    
    def test_solution(self, index: int, move: str):
        """
        Test a solution against a puzzle.
        
        :param index: Index of the puzzle
        :param move: Move in UCI format to test
        :return: Tuple (is_correct, message)
        """
        if self.debug:
            print(f"[DEBUG] Testing solution for puzzle {index} with move {move}")
        if self.solve_puzzle(index, move):
            return True, "Correct solution!"
        else:
            return False, "Incorrect solution. Try again."

    def mark_puzzle_solved(self, fen: str):
        """
        Mark a puzzle as solved by its FEN string.
        
        :param fen: FEN string of the puzzle to mark as solved
        """
        for puzzle in self.puzzles:
            if puzzle['fen'] == fen:
                puzzle['solved'] = True
                if self.debug:
                    print(f"[DEBUG] Puzzle with FEN {fen} marked as solved.")
                return
        if self.debug:
            print(f"[DEBUG] Puzzle with FEN {fen} not found to mark as solved.")    
    def log_result(self, index: int, result: str):
        """
        Log the result of solving a puzzle.
        
        :param index: Index of the puzzle
        :param result: Result of the attempt (e.g., 'correct', 'incorrect')
        """
        puzzle = self.get_puzzle(index)
        if puzzle:
            self.logger.info(f"Puzzle {index} ({puzzle['fen']}): {result}")
            if self.debug:
                print(f"[DEBUG] Logged result for puzzle {index}: {result}")
        else:
            self.logger.warning(f"Attempted to log result for non-existent puzzle index {index}.")
            if self.debug:
                print(f"[DEBUG] Attempted to log result for non-existent puzzle index {index}.")
    
    
# Example usage
if __name__ == "__main__":
    puzzles = ChessPuzzles(debug=True)
    puzzles.load_puzzles()
    random_puzzle = puzzles.get_random_puzzle()
    if random_puzzle:
        print(f"Random Puzzle FEN: {random_puzzle['fen']}")
        move = input("Enter your move in UCI format (e.g., e2e4): ")
        is_correct, message = puzzles.test_solution(0, move)
        print(message)
        puzzles.log_result(0, 'correct' if is_correct else 'incorrect')