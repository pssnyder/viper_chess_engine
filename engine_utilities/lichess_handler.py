# lichess_bot.py
# Lichess Bot Integration - Connects chess engine to Lichess via the Lichess Bot API
# TODO: Needs testing and validation. I need to be able to toggle the bot on and off easily if I need to make a patch or its behaving not as expected. It would also be nice to have a separate webapp page for controlling the lichess connection and bot settings.


import chess
import chess.engine
import requests
import json
import time
import threading
from typing import Dict, Optional, Any
from ..viper import ViperEvaluationEngine
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class LichessBot:
    def __init__(self, token: str, engine_name: str = "ChessBot"):
        self.token = token
        self.engine_name = engine_name
        self.engine = ViperEvaluationEngine()
        self.headers = {"Authorization": f"Bearer {token}"}
        self.base_url = "https://lichess.org/api"
        self.active_games = {}

        # Verify token and upgrade to bot account if needed
        self.verify_token()

    def verify_token(self):
        """Verify API token and upgrade to bot account"""
        try:
            # Check account status
            response = requests.get(f"{self.base_url}/account", headers=self.headers)
            response.raise_for_status()

            account_info = response.json()
            logger.info(f"Connected as: {account_info.get('username', 'Unknown')}")

            # Check if already a bot
            if account_info.get('title') != 'BOT':
                logger.info("Upgrading account to bot...")
                upgrade_response = requests.post(
                    f"{self.base_url}/bot/account/upgrade",
                    headers=self.headers
                )
                upgrade_response.raise_for_status()
                logger.info("Account upgraded to bot successfully!")
            else:
                logger.info("Account is already a bot")

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to verify token: {e}")
            raise

    def start(self):
        """Start the bot and listen for game events"""
        logger.info("Starting Lichess bot...")

        try:
            # Stream incoming events
            response = requests.get(
                f"{self.base_url}/stream/event",
                headers=self.headers,
                stream=True
            )
            response.raise_for_status()

            logger.info("Connected to Lichess event stream")

            for line in response.iter_lines():
                if line:
                    try:
                        event = json.loads(line.decode('utf-8'))
                        self.handle_event(event)
                    except json.JSONDecodeError:
                        logger.warning(f"Failed to parse event: {line}")

        except requests.exceptions.RequestException as e:
            logger.error(f"Stream connection failed: {e}")
        except KeyboardInterrupt:
            logger.info("Bot stopped by user")
        except Exception as e:
            logger.error(f"Unexpected error: {e}")

    def handle_event(self, event: Dict[str, Any]):
        """Handle incoming events from Lichess"""
        event_type = event.get('type')

        if event_type == 'challenge':
            self.handle_challenge(event['challenge'])
        elif event_type == 'gameStart':
            self.handle_game_start(event['game'])
        elif event_type == 'gameFinish':
            self.handle_game_finish(event['game'])
        else:
            logger.debug(f"Unhandled event type: {event_type}")

    def handle_challenge(self, challenge: Dict[str, Any]):
        """Handle incoming challenge"""
        challenge_id = challenge['id']
        challenger = challenge['challenger']['name']
        time_control = challenge['timeControl']
        variant = challenge.get('variant', {}).get('name', 'standard')

        logger.info(f"Challenge from {challenger}: {variant} {time_control}")

        # Accept or decline challenge based on criteria
        if self.should_accept_challenge(challenge):
            self.accept_challenge(challenge_id)
        else:
            self.decline_challenge(challenge_id)

    def should_accept_challenge(self, challenge: Dict[str, Any]) -> bool:
        """Determine whether to accept a challenge"""
        # Only accept standard chess variants
        variant = challenge.get('variant', {}).get('name', 'standard')
        if variant != 'standard':
            logger.info(f"Declining non-standard variant: {variant}")
            return False

        # Accept most time controls (avoid very fast games)
        time_control = challenge.get('timeControl', {})
        if time_control.get('type') == 'unlimited':
            return True

        initial_time = time_control.get('limit', 0)
        if initial_time < 30:  # Less than 30 seconds
            logger.info(f"Declining very fast game: {initial_time}s")
            return False

        # Check if challenger is not a known cheater (basic check)
        challenger = challenge.get('challenger', {})
        if challenger.get('title') == 'BOT':
            return True  # Accept bot challenges

        return True

    def accept_challenge(self, challenge_id: str):
        """Accept a challenge"""
        try:
            response = requests.post(
                f"{self.base_url}/challenge/{challenge_id}/accept",
                headers=self.headers
            )
            response.raise_for_status()
            logger.info(f"Accepted challenge {challenge_id}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to accept challenge {challenge_id}: {e}")

    def decline_challenge(self, challenge_id: str):
        """Decline a challenge"""
        try:
            response = requests.post(
                f"{self.base_url}/challenge/{challenge_id}/decline",
                headers=self.headers
            )
            response.raise_for_status()
            logger.info(f"Declined challenge {challenge_id}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to decline challenge {challenge_id}: {e}")

    def handle_game_start(self, game: Dict[str, Any]):
        """Handle game start event"""
        game_id = game['id']
        logger.info(f"Game started: {game_id}")

        # Start game handling in separate thread
        game_thread = threading.Thread(
            target=self.play_game,
            args=(game_id,),
            daemon=True
        )
        game_thread.start()

    def handle_game_finish(self, game: Dict[str, Any]):
        """Handle game finish event"""
        game_id = game['id']
        if game_id in self.active_games:
            del self.active_games[game_id]
        logger.info(f"Game finished: {game_id}")

    def play_game(self, game_id: str):
        """Play a game"""
        logger.info(f"Starting to play game {game_id}")

        try:
            # Stream game events
            response = requests.get(
                f"{self.base_url}/bot/game/stream/{game_id}",
                headers=self.headers,
                stream=True
            )
            response.raise_for_status()

            board = chess.Board()
            our_color = None

            for line in response.iter_lines():
                if line:
                    try:
                        event = json.loads(line.decode('utf-8'))

                        if event.get('type') == 'gameFull':
                            # Initial game state
                            our_color = self.get_our_color(event, game_id)
                            initial_fen = event.get('initialFen', 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1')
                            board = chess.Board(initial_fen)

                            # Apply existing moves
                            moves = event.get('state', {}).get('moves', '').split()
                            for move_uci in moves:
                                if move_uci:
                                    move = chess.Move.from_uci(move_uci)
                                    board.push(move)

                            # Make move if it's our turn
                            if board.turn == our_color:
                                self.make_move(game_id, board, event.get('state', {}))

                        elif event.get('type') == 'gameState':
                            # Game state update
                            moves = event.get('moves', '').split()

                            # Rebuild board from moves
                            board = chess.Board()
                            for move_uci in moves:
                                if move_uci:
                                    move = chess.Move.from_uci(move_uci)
                                    board.push(move)

                            # Make move if it's our turn and game is not over
                            if not board.is_game_over() and board.turn == our_color:
                                self.make_move(game_id, board, event)

                        elif event.get('type') == 'chatLine':
                            # Handle chat messages
                            self.handle_chat(game_id, event)

                    except json.JSONDecodeError:
                        logger.warning(f"Failed to parse game event: {line}")

        except requests.exceptions.RequestException as e:
            logger.error(f"Game stream failed for {game_id}: {e}")
        except Exception as e:
            logger.error(f"Error playing game {game_id}: {e}")
        finally:
            if game_id in self.active_games:
                del self.active_games[game_id]

    def get_our_color(self, game_full_event: Dict[str, Any], game_id: str) -> chess.Color:
        """Determine our color in the game"""
        white_player = game_full_event.get('white', {})
        black_player = game_full_event.get('black', {})

        # Get our username
        try:
            response = requests.get(f"{self.base_url}/account", headers=self.headers)
            response.raise_for_status()
            our_username = response.json().get('username', '')
        except:
            our_username = ''

        if white_player.get('name', '').lower() == our_username.lower():
            return chess.WHITE
        elif black_player.get('name', '').lower() == our_username.lower():
            return chess.BLACK
        else:
            # Fallback: assume we're white if we can't determine
            logger.warning(f"Could not determine color for game {game_id}, assuming white")
            return chess.WHITE

    def make_move(self, game_id: str, board: chess.Board, game_state: Dict[str, Any]):
        """Calculate and make a move"""
        if board.is_game_over():
            return

        logger.info(f"Thinking for game {game_id}...")

        # Convert Lichess time control to our format
        time_control = self.convert_time_control(game_state)

        try:
            # Get best move from engine
            best_move = self.engine.search(board, board.turn, time_control)

            if best_move:
                # Make the move
                if isinstance(best_move, chess.Move):
                    self.send_move(game_id, best_move)
                else:
                    logger.error(f"Invalid move type for game {game_id}: {type(best_move)}")
                if isinstance(best_move, chess.Move):
                    logger.info(f"Played {best_move.uci()} in game {game_id}")
                else:
                    logger.error(f"Invalid move type for game {game_id}: {type(best_move)}")
            else:
                logger.error(f"No move found for game {game_id}")

        except Exception as e:
            logger.error(f"Error calculating move for game {game_id}: {e}")

    def convert_time_control(self, game_state: Dict[str, Any]) -> Dict[str, Any]:
        """Convert Lichess time control to engine format"""
        wtime = game_state.get('wtime', 60000)  # White time in ms
        btime = game_state.get('btime', 60000)  # Black time in ms
        winc = game_state.get('winc', 0)        # White increment in ms
        binc = game_state.get('binc', 0)        # Black increment in ms

        return {
            'wtime': wtime,
            'btime': btime,
            'winc': winc,
            'binc': binc
        }

    def send_move(self, game_id: str, move: chess.Move):
        """Send move to Lichess"""
        try:
            response = requests.post(
                f"{self.base_url}/bot/game/{game_id}/move/{move.uci()}",
                headers=self.headers
            )
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to send move {move.uci()} for game {game_id}: {e}")

    def handle_chat(self, game_id: str, chat_event: Dict[str, Any]):
        """Handle chat messages"""
        username = chat_event.get('username', '')
        text = chat_event.get('text', '')
        room = chat_event.get('room', 'player')

        logger.info(f"Chat in {game_id} ({room}) {username}: {text}")

        # Respond to common chat messages
        if 'gg' in text.lower() or 'good game' in text.lower():
            self.send_chat(game_id, "Good game!", room)
        elif 'thanks' in text.lower() or 'thx' in text.lower():
            self.send_chat(game_id, "You're welcome!", room)

    def send_chat(self, game_id: str, message: str, room: str = 'player'):
        """Send chat message"""
        try:
            response = requests.post(
                f"{self.base_url}/bot/game/{game_id}/chat",
                headers=self.headers,
                data={'room': room, 'text': message}
            )
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to send chat message for game {game_id}: {e}")

    def resign_game(self, game_id: str):
        """Resign a game"""
        try:
            response = requests.post(
                f"{self.base_url}/bot/game/{game_id}/resign",
                headers=self.headers
            )
            response.raise_for_status()
            logger.info(f"Resigned game {game_id}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to resign game {game_id}: {e}")

# Main function to run the bot
def main():
    import os
    import sys

    # Get token from environment variable or command line
    token = os.getenv('LICHESS_TOKEN')

    if not token and len(sys.argv) > 1:
        token = sys.argv[1]

    if not token:
        print("Error: Lichess API token required!")
        print("Usage: python lichess_bot.py <token>")
        print("Or set LICHESS_TOKEN environment variable")
        sys.exit(1)

    # Create and start bot
    bot = LichessBot(token, "ChessBot")

    try:
        bot.start()
    except KeyboardInterrupt:
        print("\nBot stopped by user")
    except Exception as e:
        print(f"Bot error: {e}")

if __name__ == "__main__":
    main()
