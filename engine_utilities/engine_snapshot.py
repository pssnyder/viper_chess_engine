# engine_utilities/issue_dump.py
# This tool will immediately dump the contents of all log files, all console output, all active variables, all .yaml files on the project, and any other active and relevant problem solving data to generate an issue report to submit to github.

import os
import yaml
import json
import datetime
import glob

def dump_engine_snapshot(output_dir="project_management/issue_reports/error_dumps/"):
    """
    Dumps the last 1000 lines of all log files, console output, all .yaml config files, and active PGN data
    into a single JSON file with a timestamp for issue reporting and debugging.
    """
    os.makedirs(output_dir, exist_ok=True)
    snapshot = {}
    
    # Timestamp for filename and record
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    snapshot['timestamp'] = timestamp

    # Collect log files (last 1000 lines)
    log_data = {}
    for log_file in glob.glob("**/*.log", recursive=True):
        try:
            with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
                log_data[log_file] = ''.join(lines[-1000:])
        except Exception as e:
            log_data[log_file] = f"Error reading log: {e}"
    snapshot['logs'] = log_data

    # Collect console output if available (optional, placeholder)
    # If you have a mechanism to capture console output, insert it here
    # For now, just a placeholder
    snapshot['console_output'] = "(console output capture not implemented in this snapshot)"

    # Collect YAML config files
    yaml_data = {}
    for yaml_file in glob.glob("**/*.yaml", recursive=True):
        try:
            with open(yaml_file, 'r', encoding='utf-8', errors='ignore') as f:
                yaml_data[yaml_file] = yaml.safe_load(f)
        except Exception as e:
            yaml_data[yaml_file] = f"Error reading yaml: {e}"
    snapshot['yaml_configs'] = yaml_data

    # Collect active PGN data (e.g., logging/active_game.pgn)
    active_pgn_path = os.path.join('games', 'active_game.pgn')
    if os.path.exists(active_pgn_path):
        try:
            with open(active_pgn_path, 'r', encoding='utf-8', errors='ignore') as f:
                pgn_lines = f.readlines()
                snapshot['active_game_pgn'] = ''.join(pgn_lines[-1000:])
        except Exception as e:
            snapshot['active_game_pgn'] = f"Error reading PGN: {e}"
    else:
        snapshot['active_game_pgn'] = None

    # Add error info if available (placeholder for integration with error handling)
    # You could pass in error/exception info as an argument or capture from sys.exc_info()
    snapshot['error_info'] = None  # To be filled in by caller if needed

    # Add any other relevant metadata here
    snapshot['cwd'] = os.getcwd()
    snapshot['files_in_cwd'] = os.listdir('.')

    # Write to JSON file
    json_filename = f"engine_snapshot_{timestamp}.json"
    json_path = os.path.join(output_dir, json_filename)
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(snapshot, f, indent=2, default=str)

    print(f"Engine snapshot generated: {json_path}")

# Example usage
if __name__ == "__main__":
    dump_engine_snapshot()