# ChessBot - Python Chess Engine

A complete chess engine with UCI interface and Lichess bot integration, built around your custom evaluation functions.

## Features

🎯 **Your Custom Evaluation Engine**
- 25+ evaluation rules and heuristics
- Minimax with alpha-beta pruning
- Position-aware scoring system

🔍 **Advanced Search**
- Iterative deepening
- Transposition table
- Move ordering and killer moves
- Quiescence search

⏱️ **Smart Time Management**
- Adaptive time allocation
- Position-complexity aware
- Emergency time handling

🌐 **Lichess Integration**
- Automatic challenge handling
- Real-time game playing
- Chat integration

🖥️ **UCI Compatible**
- Works with Arena, ChessBase, etc.
- Standard UCI protocol
- Configurable engine options

## Quick Start

### 1. Setup
```bash
python setup.py
```

### 2. Test UCI Engine
```bash
python uci_interface.py
```

### 3. Run Lichess Bot
```bash
# Set your token
export LICHESS_TOKEN=your_token_here

# Run the bot
python lichess_bot.py
```

### 4. Package as Executable
```bash
python package_exe.py
```

## Configuration

Edit `config.py` to customize:
- Engine strength and search depth
- Lichess bot behavior
- Time management settings
- Evaluation parameters

## Files Overview

- `evaluation_engine.py` - Your custom evaluation functions
- `main_engine.py` - Main engine controller with search
- `uci_interface.py` - UCI protocol implementation
- `time_manager.py` - Time control management
- `lichess_bot.py` - Lichess API integration
- `config.py` - Configuration settings

## Lichess Setup

1. Create Lichess account (don't play any games)
2. Go to https://lichess.org/account/oauth/token
3. Create token with "Bot Play" scope
4. Upgrade to bot account:
   ```bash
   curl -d "" https://lichess.org/api/bot/account/upgrade \
        -H "Authorization: Bearer YOUR_TOKEN"
   ```

## Deployment Options

### Desktop Application
- Use PyInstaller to create .exe files
- Package with `python package_exe.py`
- Distribute executables to users

### Cloud Hosting
- Deploy on Heroku, Railway, or DigitalOcean
- Use environment variables for tokens
- Run 24/7 for continuous bot operation

### Local Testing
- Test with Arena or other UCI GUIs
- Challenge your bot on Lichess
- Analyze games to improve evaluation

## Usage Examples

### UCI Engine in Arena
1. Open Arena Chess GUI
2. Install new engine
3. Select `ChessBot_UCI.exe`
4. Start playing!

### Lichess Bot
```bash
# Direct token
python lichess_bot.py your_token

# Environment variable
export LICHESS_TOKEN=your_token
python lichess_bot.py
```

### Custom Time Control
```python
time_control = {
    'wtime': 300000,  # 5 minutes
    'btime': 300000,
    'winc': 3000,     # 3 second increment
    'binc': 3000
}
```

## Troubleshooting

**Engine not responding?**
- Check Python version (3.8+ required)
- Verify all dependencies installed
- Test with `python uci_interface.py`

**Lichess bot not connecting?**
- Verify API token is correct
- Check account is upgraded to bot
- Ensure no firewall blocking connections

**Packaging issues?**
- Install latest PyInstaller
- Check all files are present
- Use spec file for complex builds

## Contributing

Feel free to improve the evaluation functions or add new features:
- Opening book integration
- Endgame tablebase support
- Neural network evaluation
- Multi-threading search
- Advanced pruning techniques

## License

Open source - feel free to use and modify!
