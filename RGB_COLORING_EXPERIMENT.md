# RGB Hex Coloring Experiment

**Branch:** `experiment/rgb-hex-coloring`
**Status:** Experimental - testing RGB-based coloring for hex bytes

## Concept

Instead of fixed colors for hex bytes (cyan, yellow, magenta), use the **MIDI bytes themselves as RGB color values** to create unique, meaningful colors for each message.

## Implementation

### Color Mapping
```
MIDI Message: B6 0D 40 (Control Change, Channel 6, CC 13, Value 64)

RGB Mapping:
- R = Status byte (0xB6 = 182) → Use as-is
- G = Data1 (0x0D = 13) → Multiply by 2 → 26
- B = Data2 (0x40 = 64) → Multiply by 2 → 128

Result: RGB(182, 26, 128) → Pinkish-magenta color
```

### Normalization
- **Status byte:** 0x80-0xBF range (128-191) → use as-is (already in RGB range)
- **Data bytes:** 0-127 range → multiply by 2 to get 0-254

### Visibility Boost
For very dark colors (low RGB sum), boost all components proportionally:
```python
min_brightness = 50
if total RGB < 50:
    boost_factor = 50 / total
    RGB *= boost_factor (clamped to 255)
```

This ensures messages like `B0 00 00` don't disappear in dark terminals.

## Examples

| MIDI Hex | Status | Data1 | Data2 | RGB Color | Visual Effect |
|----------|--------|-------|-------|-----------|---------------|
| `B0 00 00` | 176 | 0 | 0 | (176, 0, 0) | Dark red |
| `B6 0D 40` | 182 | 13 | 64 | (182, 26, 128) | Pinkish-magenta |
| `B6 2D 64` | 182 | 45 | 100 | (182, 90, 200) | Lighter magenta |
| `90 3C 7F` | 144 | 60 | 127 | (144, 120, 254) | Purple-blue |
| `91 7F 7F` | 145 | 127 | 127 | (145, 254, 254) | Cyan-blue |

## Observations

### Pattern Recognition
- **Similar messages** → **similar colors**
  - `B6 08 00`, `B6 08 20`, `B6 08 40` → Red with increasing blue
  - Shows value progression visually

- **Channel changes** → **subtle hue shifts**
  - `B0` (Ch 0) vs `B6` (Ch 6): Slight red component difference
  - `90` (Ch 0) vs `91` (Ch 1): Nearly identical

### Use Cases

**Good for:**
- **Quick visual pattern recognition** (same control = same color family)
- **Value progression** (gradual color shift as fader moves)
- **Channel grouping** (similar channels have similar base colors)
- **Aesthetic appeal** (unique color for each message)

**Not ideal for:**
- **Semantic meaning** (color doesn't indicate control type)
- **Color blindness** (hard to distinguish similar RGB values)
- **High contrast** (some combinations may be low-contrast)

## Testing

Run the test script to see RGB colors in action:
```bash
python3 test_rgb_colors.py
```

## Comparison with Original

### Original (Fixed Colors)
```
B6 08 40 → Magenta Status | Yellow Data1 | White Data2
```
- Semantic meaning (status, data1, data2 roles)
- High contrast
- Consistent across messages

### RGB Experiment
```
B6 08 40 → RGB(182, 16, 128) → All bytes in one color
```
- Unique color per message
- Visual pattern recognition
- Less semantic clarity

## Technical Implementation

### ANSI 24-bit RGB
```python
rgb_color = f"\033[38;2;{r};{g};{b}m"
colored = rgb_color + "B6 08 40" + "\033[0m"
```

### Changes
- `monitor.py`: Added `_midi_to_rgb()` method
- `monitor.py`: Modified `_format_hex_bytes()` to use RGB coloring
- All 3 hex bytes colored with single RGB value (based on the bytes themselves)

## Future Possibilities

1. **Hybrid approach**: RGB for hex bytes, semantic colors for function names
2. **Background coloring**: Use RGB as background instead of foreground
3. **Saturation adjustment**: Boost saturation for more vivid colors
4. **User preference**: CLI flag `--rgb-hex` to enable/disable

## Conclusion

This experiment demonstrates that **MIDI bytes can generate meaningful RGB colors** for visual pattern recognition. While it sacrifices semantic clarity (fixed color roles), it provides unique, aesthetically pleasing colors that help identify similar messages at a glance.

**Recommendation:** Keep as experimental feature. Could be useful for:
- Live performances (visual feedback)
- Pattern debugging (spot similar messages)
- Aesthetic preference (colorful terminal output)

Not recommended for production use where semantic clarity matters more than aesthetics.
