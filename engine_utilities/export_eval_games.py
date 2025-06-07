# export_eval_games.py
# this script compiles all evaluation game PGN files into a single file

import os
from datetime import datetime

def compile_eval_games_pgn():
    folder = 'games'
    # Create games directory if not exists
    os.makedirs(folder, exist_ok=True)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    export_filename = f'games/export_all_eval_games_{timestamp}.pgn'
    
    # Get matching files (case-sensitive)
    files_to_compile = [f for f in os.listdir(folder) 
                       if f.startswith('eval_game_') and f.endswith('.pgn')]
    
    # Write combined PGN
    with open(export_filename, 'w', encoding='utf-8') as outfile:
        for filename in files_to_compile:
            filepath = os.path.join(folder, filename)
            with open(filepath, 'r', encoding='utf-8') as infile:
                outfile.write(infile.read())
                outfile.write('\n\n')  # Add double newline between games
    
    print(f"Compiled {len(files_to_compile)} games into {export_filename}")
    return export_filename

# Execute the function
if __name__ == "__main__":
    compiled_file = compile_eval_games_pgn()
    print(f"Compiled PGN file created: {compiled_file}")