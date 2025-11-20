# Input Controls

The drone trainer now supports multiple input methods for controlling objects in the 3D environment.

## Supported Input Types

### 1. Controller/Gamepad
- **Left Stick**: Move forward/backward and strafe left/right (X/Z plane)
- **Right Stick**: Rotate around axes
- **LB/RB Buttons**: Move up/down (Y axis)
- **LT/RT Triggers**: Rotate around Z-axis

### 2. WASD Keyboard
- **W/S**: Move forward/backward
- **A/D**: Strafe left/right
- **Q/E**: Move up/down
- **R/F**: Rotate

### 3. Arrow Keys Keyboard
- **Up/Down**: Move forward/backward
- **Left/Right**: Strafe left/right
- **Page Up/Down**: Move up/down
- **Home/End**: Rotate

## Configuration

To change input settings:

1. Open the **Configuration Panel** from the navigation bar
2. Select your preferred **Input Type** from the dropdown
3. Adjust the **Sensitivity** slider to your liking (0.1x to 5.0x)
4. View the input mapping information in the panel

## Sensitivity

The sensitivity setting applies a multiplier to all input movements:
- **0.1x**: Very slow and precise movements
- **1.0x**: Default speed (recommended)
- **5.0x**: Very fast movements

## Status Panel

The status panel (top-right corner) shows:
- Current input device type
- Connection status (for controllers)
- Active input method (Controller/WASD/Arrow Keys)

## Notes

- Movement is relative to the camera angle
- Press and hold keys for continuous movement
- Only one input type is active at a time
- Keyboard input requires the 3D viewport to have focus (click on it first)
