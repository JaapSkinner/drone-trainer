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

## Viewport Controls

The 3D viewport supports mouse-based camera controls:

### Mouse Controls
- **Left Click + Drag**: Orbit the camera around the center point (or locked object)
- **Scroll Wheel Up**: Zoom in (move camera closer)
- **Scroll Wheel Down**: Zoom out (move camera further away)

### Lock View to Object

You can lock the camera view to follow a specific object:

1. Open the **Settings Panel** from the navigation bar
2. Use the **Lock View To** dropdown to select an object
3. The camera will now orbit around and follow the selected object
4. Zoom and orbit controls continue to work while locked
5. Select "None (Origin)" to unlock and return to orbiting the scene origin

When locked to an object:
- The camera automatically follows the object as it moves
- Orbit controls rotate around the object instead of the origin
- Zoom controls adjust distance from the locked object

### Zoom Limits
- **Minimum distance**: 2 units (closest zoom)
- **Maximum distance**: 50 units (furthest zoom)

### Viewport Settings

To configure viewport controls:

1. Open the **Settings Panel** from the navigation bar
2. Use **Lock View To** to select an object to follow (or "None" for origin)
3. Adjust the **Zoom Sensitivity** slider (0.1x to 3.0x)
4. Click **Reset Camera** to return to the default camera position and unlock

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
