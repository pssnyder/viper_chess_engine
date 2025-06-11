# Chess GUI Setup Guide - Custom Image Integration

## Your Image Naming Convention
The updated chess GUI has been configured to work with your specific image naming convention:

### Directory Structure
```
your_project/
├── chess-gui-with-images.py
├── evaluation_engine.py
└── images/
    ├── wQ.png  # White Queen
    ├── wK.png  # White King
    ├── wR.png  # White Rook
    ├── wB.png  # White Bishop
    ├── wN.png  # White Knight
    ├── wp.png  # White Pawn
    ├── bQ.png  # Black Queen
    ├── bK.png  # Black King
    ├── bR.png  # Black Rook
    ├── bB.png  # Black Bishop
    ├── bN.png  # Black Knight
    └── bp.png  # Black Pawn
```

### Naming Convention Details
- **Colors**: `w` (white) or `b` (black)
- **Pieces**: 
  - `Q` - Queen (uppercase)
  - `K` - King (uppercase)
  - `R` - Rook (uppercase)
  - `B` - Bishop (uppercase)
  - `N` - Knight (uppercase)
  - `p` - Pawn (lowercase)

## Installation Requirements
```bash
pip install pygame python-chess
```

## Running the GUI
1. Ensure your `evaluation_engine.py` file is in the same directory
2. Create an `images/` folder with your piece images
3. Run the GUI:
```bash
python chess-gui-with-images.py
```

## Features
- **Automatic Image Loading**: The GUI will automatically detect and load your piece images
- **Fallback System**: If images are missing, it falls back to Unicode chess symbols
- **Image Status Display**: Shows how many images were successfully loaded (should be 12/12)
- **Real-time Evaluation**: Displays your engine's evaluation of the current position
- **Engine Integration**: Your bot plays as Black, you play as White

## Expected Console Output
When you run the GUI, you should see:
```
Chess Engine Testing Interface
==============================
Looking for piece images in 'images' directory...
Expected naming: wQ.png, bK.png, wp.png, etc.

Loaded: wQ.png
Loaded: wK.png
Loaded: wR.png
...
Successfully loaded 12 piece images
```

## Troubleshooting
- **Images not loading**: Check that your `images/` directory is in the same folder as the Python file
- **Wrong piece displayed**: Verify your image filenames match the exact convention (case-sensitive)
- **Engine errors**: Ensure your `evaluation_engine.py` has the required methods

## Key Code Changes Made
The updated GUI includes a specialized `load_piece_images()` function that:
1. Maps chess piece types to your naming convention
2. Looks for images in the `images/` directory
3. Scales images to fit the board squares
4. Provides detailed loading feedback
5. Gracefully handles missing images

Your custom naming convention is now fully integrated into the chess testing interface!