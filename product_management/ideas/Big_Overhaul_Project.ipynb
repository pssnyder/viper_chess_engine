{
 "cells": [
  {
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "# Viper Chess Engine Big Overhaul Project: Primary Update Documentation\n",
    "\n",
    "This document outlines the progress and key updates for the Viper Chess Engine overhaul project. It will serve as the primary documentation for each phase, including progress tracking, unit tests, and visualizations where applicable."
   ]
  },
  {
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "## Project Outline\n",
    "\n",
    "The project is divided into three main phases, each with specific goals and deliverables."
   ]
  },
  {
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "### Phase 1: Core Engine Functionality & Data Collection\n",
    "\n",
    "**Objective**: Establish robust core engine functionality and ensure accurate data collection for game analysis.\n",
    "\n",
    "#### Steps:\n",
    "\n",
    "1.  **Update Configuration File Handling**: Modify the codebase to correctly load settings from the new YAML file structure (`viper.yaml`, `chess_game.yaml`, `stockfish_handler.yaml`).\n",
    "2.  **Ensure Automated Game Play**: Verify that `chess_game.py` can run an AI vs. AI game (e.g., Viper vs. Stockfish) using the updated configurations and save game data (PGN, config, logs).\n",
    "3.  **Basic Metrics Collection**: Confirm that essential game metrics (result, players, length, configurations) are being saved."
   ]
  },
  {
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "### Phase 2: Configuration GUI\n",
    "\n",
    "**Objective**: Develop a user-friendly graphical interface for managing engine and game configurations.\n",
    "\n",
    "#### Steps:\n",
    "\n",
    "1.  **Design Configuration Data Structure**: Determine how configurations will be stored and managed (e.g., a JSON file or a simple database) to allow for saving, loading, and creating new named configurations.\n",
    "2.  **Implement GUI for Viper Settings**: Build out `viper_gui.app.py` (likely using Flask or Streamlit) to:\n",
    "    * Load existing configurations.\n",
    "    * Display current settings from `viper.yaml`.\n",
    "    * Allow users to modify these settings.\n",
    "    * Save changes back to `viper.yaml` or a new named configuration.\n",
    "    * Allow users to select which named configuration is \"active\" for the engine.\n",
    "3.  **Implement GUI for Game Settings**: Extend the GUI to manage settings in `chess_game.yaml`.\n",
    "4.  **Implement GUI for Stockfish Settings**: Extend the GUI to manage settings in `stockfish_handler.yaml`."
   ]
  },
  {
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "### Phase 3: Engine Monitor and TODOs\n",
    "\n",
    "**Objective**: Refine the engine monitoring dashboard and address outstanding code tasks.\n",
    "\n",
    "#### Steps:\n",
    "\n",
    "1.  **Update `engine_monitor.app.py`**: Refactor the Streamlit dashboard based on TODO notes, focusing on historical analysis and removing real-time/log-based features not relevant to its new scope.\n",
    "2.  **Address Code TODOs**: Systematically go through the codebase, identify all TODO comments, and implement them.\n",
    "3.  **Adaptive ELO (Stretch Goal)**: If time permits and core functionality is stable, begin planning/implementing the adaptive ELO for opponent AI in `chess_game.py`."
   ]
  },
  {
   "cell_type": "markdown",
   "metadata": {},
   "source": [
    "## Phase 1 Progress: Core Engine Functionality & Data Collection\n",
    "\n",
    "### Step 1: Update Configuration File Handling\n",
    "\n",
    "**Status: In Progress**\n",
    "\n",
    "**Details:**\n",
    "*   **`chess_game.py`**: \n",
    "    *   Modified `ChessGame.__init__` to load `chess_game.yaml` (into `self.game_config_data`), `viper.yaml` (into `self.viper_config_data`), and `engine_utilities/stockfish_handler.yaml` (into `self.stockfish_config_data`).\n",
    "    *   Updated various methods (`_initialize_ai_engines`, `set_headers`, etc.) to access settings from these new configuration attributes.\n",
    "    *   `save_game_data` now includes a `game_specific_config` dictionary containing all three loaded config data structures, plus the resolved `white_actual_config` and `black_actual_config` used for the game.\n",
    "*   **`viper.py`**: \n",
    "    *   Corrected `reportUndefinedVariable` for `legal_moves` in `ViperEvaluationEngine._deep_search`.\n",
    "    *   `ViperEvaluationEngine.__init__` now loads `viper.yaml` into `self.viper_config_data` and `chess_game.yaml` into `self.game_settings_config_data`.\n",
    "    *   `ViperEvaluationEngine._ensure_ai_config` has been significantly refactored to correctly merge configurations in the order: `viper.yaml` (base) -> `chess_game.yaml` (player-specific overrides like `white_ai_config` or `black_ai_config`) -> runtime `ai_config` (highest precedence). This method now performs a deep merge for nested dictionary settings.\n",
    "    *   `ViperEvaluationEngine.configure_for_side` updated to use the fully resolved configuration from `_ensure_ai_config` to set all engine parameters (search algorithm, ruleset, depth, scoring modifier, hash size, TT settings, move ordering, quiescence, PSTs, time limits, etc.).\n",
    "    *   `ViperEvaluationEngine.search` now calls `_ensure_ai_config` at the beginning of each search to get the most up-to-date resolved configuration for the current player and then calls `configure_for_side`.\n",
    "    *   Methods like `order_moves`, `_order_move_score`, and `_quiescence_search` updated to pull parameters (e.g., bonuses, max depths) from the resolved `self.ai_config`.\n",
    "*   **`engine_utilities/viper_scoring_calculation.py`**: \n",
    "    *   `ViperScoringCalculation.__init__` modified to accept `viper_yaml_config` (the parsed `viper.yaml` data, specifically the `viper` key and its sub-keys) and the resolved `ai_config` for the current context.\n",
    "    *   It now loads all ruleset definitions from `viper_yaml_config.get('rulesets', {})`.\n",
    "    *   The active `ruleset_name`, `scoring_modifier`, `pst_enabled`, and `pst_weight` are now determined from the passed `ai_config` (which itself is a result of merging `viper.yaml`, `chess_game.yaml` player specifics, and runtime overrides).\n",
    "    *   The main scoring method, `calculate_score` (renamed from `_calculate_score`), re-synchronizes its internal state (current ruleset, modifier, PST settings) with the `ai_config` at the start of each call. This ensures that if the `ai_config` changes (e.g., for a different player or a re-configuration), the scoring calculator uses the correct, up-to-date parameters.\n",
    "    *   `_get_rule_value` updated to fetch values from the `current_ruleset`, with a fallback to `viper_yaml_config.get('default_evaluation', {})` for common rule defaults, and then to a hardcoded default if not found.\n",
    "    *   PST score application in `calculate_score` made perspective-aware (adjusts score if `color` is `chess.BLACK` and PST scores are White-centric).\n",
    "    *   `_special_moves` method now accepts a `color` parameter and its logic was refined for en passant and promotion opportunities for that specific color.\n",
    "\n",
    "**Next Steps for Step 1:**\n",
    "1.  Thoroughly test the configuration loading and merging logic in `chess_game.py` and `viper.py`.\n",
    "2.  Verify that `ViperScoringCalculation` correctly uses the rulesets and parameters from `viper.yaml` as intended, especially with different player AI configurations in `chess_game.yaml`."
   ]
  },
  {
   "cell_type": "code",
   "execution_count": null,
   "metadata": {},
   "outputs": [],
   "source": [
    "# Code Snippet: Configuration Loading (Initial Implementation/Changes)\n",
    "# This section will contain the actual code modifications related to loading YAML files.\n",
    "# For example:\n",
    "# import yaml\n",
    "\n",
    "# def load_config(filepath):\n",
    "#     with open(filepath, 'r') as file:\n",
    "#         return yaml.safe_load(file)\n",
    "\n",
    "# chess_game_config = load_config('chess_game.yaml')\n",
    "# stockfish_config = load_config('stockfish_handler.yaml')\n",
    "# viper_config = load_config('viper.yaml')\n",
    "\n",
    "# print(\"Chess Game Config:\", chess_game_config)\n",
    "# print(\"Stockfish Config:\", stockfish_config)\n",
    "# print(\"Viper Config:\", viper_config)"
   ]
  },
  {
   "cell_type": "markdown",
   "id": "f95f43b3",
   "metadata": {},
   "source": [
    "### Phase 1: Core Engine Functionality & Data Collection\n",
    "\n",
    "**Objective**: Establish robust core engine functionality and ensure accurate data collection for game analysis.\n",
    "\n",
    "#### Steps:\n",
    "\n",
    "1.  **Update Configuration File Handling**: **COMPLETED** (as detailed above, pending testing).\n",
    "2.  **Ensure Automated Game Play**: Verify that `chess_game.py` can run an AI vs. AI game (e.g., Viper vs. Stockfish) using the updated configurations and save game data (PGN, config, logs).\n",
    "    *   **Next Action**: Run a test game between Viper and Stockfish using `chess_game.py`.\n",
    "    *   **Verification**: Check that the game completes, a PGN file is saved, a combined configuration file is saved, and logs are generated without errors related to config access.\n",
    "3.  **Basic Metrics Collection**: Confirm that essential game metrics (result, players, length, configurations) are being saved correctly in the output files.\n",
    "    *   **Next Action**: After a successful test game, inspect the saved PGN headers and the combined configuration file.\n",
    "    *   **Verification**: Ensure all expected data points are present and accurate."
   ]
  }
 ],
 "metadata": {
  "language_info": {
   "name": "python"
  }
 },
 "nbformat": 4,
 "nbformat_minor": 5
}
