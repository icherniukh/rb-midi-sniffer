# Rekordbox MIDI Development Guide

This guide helps developers create enhanced DJ workflows and custom controls for Rekordbox via MIDI commands using the MIDI Learn CSV format.

## Table of Contents

1. [Quick Start](#quick-start)
2. [Understanding MIDI Learn](#understanding-midi-learn)
3. [CSV Format Reference](#csv-format-reference)
4. [Creating Custom Mappings](#creating-custom-mappings)
5. [Uploading Your CSV](#uploading-your-csv)
6. [Control Types & Behaviors](#control-types--behaviors)
7. [Common MIDI Mappings](#common-midi-mappings)
8. [Workflow Examples](#workflow-examples)
9. [Troubleshooting](#troubleshooting)
10. [Reference Tools](#reference-tools)

---

## Quick Start

1. **Monitor existing MIDI**: Use `sniffer.py` to see what your controller sends
2. **Export a CSV**: Use an existing mapping as a template
3. **Edit the CSV**: Add/modify entries for your custom workflow
4. **Import to Rekordbox**: MIDI Learn → Load CSV
5. **Test**: Your mappings should now trigger Rekordbox functions

```bash
# Start monitoring
python sniffer.py monitor

# See what's available
python sniffer.py list-csv
python sniffer.py show-headers --csv DDJ-GRV6.midi.csv
```

---

## Understanding MIDI Learn

Rekordbox MIDI Learn allows you to map MIDI messages from any controller to Rekordbox functions. The mapping is defined by a CSV file that specifies which MIDI addresses trigger which functions.

### How It Works

```
Controller sends MIDI message → Rekordbox looks up CSV → Triggers function
```

**Example**: When you press button `0x900B` (Note On, Channel 0, Note 11), Rekordbox:
1. Receives the MIDI message
2. Looks up `900B` in the CSV
3. Finds `PlayPause` function
4. Triggers play/pause

### Two-Way Communication

- **IN (Input)**: Controller → Rekordbox (button presses, knob turns)
- **OUT (Output)**: Rekordbox → Controller (LED feedback, status indicators)

---

## CSV Format Reference

### File Structure

```csv
@file,1,DDJ-GRV6
#name,function,type,input,deck1,deck2,deck3,deck4,output,deck1,deck2,deck3,deck4,option,comment
PlayPause,PlayPause,Button,900B,0,1,2,3,900B,0,1,2,3,Fast,Play/Pause
```

### Columns

| Column | Name | Description | Example |
|--------|------|-------------|---------|
| 0 | `#name` | Internal name (unique identifier) | `PlayPause` |
| 1 | `function` | Rekordbox function name to execute | `PlayPause` |
| 2 | `type` | Control type (determines behavior) | `Button`, `Rotary`, `KnobSliderHiRes` |
| 3 | `input` | Base MIDI address (hex) | `900B`, `B640` |
| 4-7 | `deck1-4` | Channel offsets for each deck | `0,1,2,3` |
| 8 | `output` | MIDI address for LED feedback | `900B` |
| 9-12 | `deck1-4` (out) | Channel offsets for feedback | `0,1,2,3` |
| 13 | `option` | Semicolon-separated options | `Fast;Priority=50` |
| 14 | `comment` | Human-readable description | `Play/Pause` |

### MIDI Address Format

The MIDI address is a 4-character hex string:

```
┌─────────┬─────────┬─────────┐
│ Status  │ Data1   │ Data2   │
│ (2 hex) │ (1 hex) │ (1 hex) │
└─────────┴─────────┴─────────┘
```

**Status byte breakdown**:
- `9` = Note On, `8` = Note Off, `B` = Control Change
- Last hex digit = MIDI channel (0-F)

| Address | Type | Channel | Data1 | Meaning |
|---------|------|---------|-------|---------|
| `900B` | Note On | 0 | 0x0B (11) | Note 11 on Channel 0 |
| `B640` | Control Change | 6 | 0x40 (64) | CC 64 on Channel 6 |
| `B61F` | Control Change | 6 | 0x1F (31) | CC 31 on Channel 6 |

---

## Creating Custom Mappings

### Step 1: Find Your MIDI Address

Use the sniffer to see what messages your controller sends:

```bash
python sniffer.py monitor
```

Press a button or move a knob - you'll see output like:
```
[12:34:56.789] | IN  | B6 08 40 | ChannelFader [KnobSliderHiRes] (x502) val: 8192
```

The `B6 08 40` is your MIDI address:
- `B6` = Control Change, Channel 6
- `08` = CC number (8)
- `40` = Value (64)

### Step 2: Choose Your Function

Available functions depend on your Rekordbox version. Common ones:

| Function | Description |
|----------|-------------|
| `PlayPause` | Play/Pause |
| `Cue` | Cue button |
| `Sync` | Sync beatgrid |
| `TempoSlider` | Tempo fader (14-bit) |
| `HotCue1` - `HotCue16` | Hot Cue triggers |
| `FX1_1_On` - `FX1_3_On` | FX enable |
| `FilterHigh` | High EQ |
| `FilterMid` | Mid EQ |
| `FilterLow` | Low EQ |

### Step 3: Pick Your Control Type

| Type | Description | MIDI Behavior |
|------|-------------|---------------|
| `Button` | Momentary button | Note On/Off |
| `Rotary` | Endless knob | Control Change |
| `KnobSlider` | 7-bit fader/knob | CC, value 0-127 |
| `KnobSliderHiRes` | 14-bit fader/knob | MSB+LSB CC pair, value 0-16383 |
| `Jog` | Jog wheel | Note On with pitch value |
| `Pad` | Performance pad | Note On/Off |

### Step 4: Write Your CSV Entry

```csv
#name,function,type,input,deck1,deck2,deck3,deck4,output,deck1,deck2,deck3,deck4,option,comment
MyCustomButton,PlayPause,Button,B001,0,1,2,3,B001,0,1,2,3,Fast,Custom Play Button
```

### Step 5: Handle Multi-Deck Mappings

For 4-deck support, the `deck1-4` columns specify channel offsets:

```csv
# With offsets 0,1,2,3, the same control works for all decks:
# Deck 1: Channel 0 (0+0)
# Deck 2: Channel 1 (0+1)
# Deck 3: Channel 2 (0+2)
# Deck 4: Channel 3 (0+3)

TempoSlider,TempoSlider,KnobSliderHiRes,B000,0,1,2,3,,,,,Fast,Tempo Control
```

---

## Uploading Your CSV

### Method 1: Via Rekordbox GUI

1. Open Rekordbox
2. Go to **Preferences** → **Controller**
3. Select your controller
4. Click **MIDI Learn**
5. Click **Load** → Select your CSV file
6. Click **OK** to save

### Method 2: Manual File Placement

Place your CSV in:
```
/Applications/rekordbox 7/rekordbox.app/Contents/Resources/MidiMappings/
```

Naming convention: `<ControllerName>.midi.csv`

### CSV Location Tips

- macOS: `/Applications/rekordbox 7/rekordbox.app/Contents/Resources/MidiMappings/`
- Windows: `C:\Program Files\rekordbox 7\...\MidiMappings\`
- Always backup the original CSV before modifying

---

## Control Types & Behaviors

### Button

Simple on/off or momentary action.

```csv
PlayPause,PlayPause,Button,900B,0,1,2,3,900B,0,1,2,3,Fast,Play/Pause
```

- **Velocity > 0**: Press (ON)
- **Velocity = 0**: Release (OFF)

### Rotary

Endless encoder (no absolute position).

```csv
Browse,Browse,Rotary,B602,0,0,0,0,,,,,Fast,Browse knob
```

- Sends CC messages while turning
- Direction depends on value increase/decrease

### KnobSlider

7-bit absolute fader or knob.

```csv
Gain,Gain,KnobSlider,B004,0,1,2,3,,,,,Fast,Gain knob
```

- Single CC, value 0-127
- Position reflects current value

### KnobSliderHiRes

14-bit high-resolution fader (16384 steps).

```csv
TempoSlider,TempoSlider,KnobSliderHiRes,B000,0,1,2,3,,,,,Fast,Tempo fader
```

- Uses **two CCs**: MSB (0-31) + LSB (32-63)
- Combined value: `msb * 128 + lsb` = 0-16383
- Example: CC 0 (MSB) + CC 32 (LSB) for same control

### Jog

Jog wheel for scratch/search.

```csv
JogWheel,Jog,Jog,D001,0,1,2,3,,,,,Fast,Jog wheel
```

- Sends Note On with velocity = jog speed/direction
- Positive velocity = forward, Negative = backward (signed byte)

---

## Common MIDI Mappings

### Transport Controls

| Function | Type | MIDI Example |
|----------|------|--------------|
| Play/Pause | Button | `900B` Note On Ch0 |
| Cue | Button | `900C` Note On Ch0 |
| Play/Cue (pair) | Button | `900D` Note On Ch0 |
| Sync | Button | `900E` Note On Ch0 |

### Tempo Control

| Function | Type | MSB | LSB | Range |
|----------|------|-----|-----|-------|
| Tempo Slider | KnobSliderHiRes | `B000` | `B020` | 0-16383 |
| Tempo Bend | Rotary | `B001` | - | - |

### EQ / Isolator

| Function | Type | Channel | CC | Deck Offsets |
|----------|------|---------|-----|--------------|
| High EQ | KnobSliderHiRes | 6 | 7 | 0,1,2,3 |
| Mid EQ | KnobSliderHiRes | 6 | 11 | 0,1,2,3 |
| Low EQ | KnobSliderHiRes | 6 | 15 | 0,1,2,3 |

### Channel Fader

| Function | Type | Channel | MSB | LSB |
|----------|------|---------|-----|-----|
| Channel Fader | KnobSliderHiRes | 6 | 19 (0x13) | 51 (0x33) |

### Crossfader

| Function | Type | Channel | MSB | LSB |
|----------|------|---------|-----|-----|
| Crossfader | KnobSliderHiRes | 6 | 31 (0x1F) | 63 (0x3F) |

### FX Control

| Function | Type | Channel | CC |
|----------|------|---------|-----|
| FX 1 On | Button | 6 | 40-43 (per deck) |
| FX 1 Depth | KnobSliderHiRes | 6 | 23 (MSB) |
| FX 2 On | Button | 6 | 44-47 |

### Hot Cues

| Function | Type | Note | Deck Offset |
|----------|------|------|-------------|
| Hot Cue 1-16 | Button | 0x10-0x1F | Ch+deck |
| Hot Cue Delete | Button | 0x30 | Ch+deck |

---

## Workflow Examples

### Example 1: Single-Button Loop Trigger

Create a button that sets a 4-beat loop and activates it:

```csv
#name,function,type,input,deck1-4,output,deck1-4,option,comment
Loop4,Loop4On,Button,9020,0,1,2,3,9020,0,1,2,3,Fast,4 Beat Loop
```

### Example 2: Shift-Modified Behavior

Use shift to change button behavior:

```csv
# Normal mode: Play/Pause
PlayPause,PlayPause,Button,900B,0,0,0,0,,,,,Fast,Play

# Shift mode: Delete Hot Cue
DeleteHotCue,HotCueDelete,Button,900B,0,0,0,0,,,,,Fast;Shift,Delete Cue
```

The `;Shift` option means this mapping only activates when Shift is held.

### Example 3: Layered FX Control

Assign multiple FX to one knob with layering:

```csv
#name,function,type,input,deck1-4,output,deck1-4,option,comment
FX1Depth,FX1_1_Depth,KnobSliderHiRes,B610,0,0,0,0,,,,,Fast,FX1 Depth
FX2Depth,FX2_1_Depth,KnobSliderHiRes,B610,0,0,0,0,,,,,Fast;Shift,FX2 Depth
```

### Example 4: Performance Pad Layout

Create a 4x4 pad grid for Hot Cues:

```csv
# Row 1: Hot Cues 1-4
HotCue1,HotCue1,Button,9010,0,0,0,0,9010,0,0,0,0,Fast,Hot Cue 1
HotCue2,HotCue2,Button,9011,0,0,0,0,9011,0,0,0,0,Fast,Hot Cue 2
HotCue3,HotCue3,Button,9012,0,0,0,0,9012,0,0,0,0,Fast,Hot Cue 3
HotCue4,HotCue4,Button,9013,0,0,0,0,9013,0,0,0,0,Fast,Hot Cue 4

# Row 2: Hot Cues 5-8
HotCue5,HotCue5,Button,9014,0,0,0,0,9014,0,0,0,0,Fast,Hot Cue 5
# ... etc
```

### Example 5: Smart Fader Start

Automatically start playback when fader moves up:

```csv
#name,function,type,input,deck1-4,output,deck1-4,option,comment
FaderStart,Play,Button,XXXX,0,0,0,0,,,,,FaderStart,Auto Start on Fader Up
```

The `;FaderStart` option enables special fader-start behavior.

---

## Troubleshooting

### Mapping Not Working?

1. **Check the MIDI address** - Use `sniffer.py` to verify the exact message
2. **Verify the function name** - Some functions are version-specific
3. **Check channel offsets** - Ensure deck offsets match your controller
4. **Confirm CSV format** - No extra spaces, correct hex format

### Wrong Function Triggered?

- **Duplicate addresses**: Check if two entries use the same MIDI address
- **Priority conflicts**: Use `Priority=XX` option to set order

### No LED Feedback?

1. Check the `output` column is filled
2. Verify output channel offsets match
3. Some functions don't support feedback (check `RO` option)

### Hi-Res Controls Jumpy?

- Verify both MSB and LS
- B CCs are mapped
- Check that `type` is `KnobSliderHiRes`
- MSB should be CC 0-31, LSB should be CC 32-63

---

## Reference Tools

### sniffer.py Commands

```bash
# Live monitoring with RGB hex coloring (default)
python sniffer.py monitor

# Disable RGB coloring for traditional output
python sniffer.py monitor --no-rgbmidi

# List available controllers
python sniffer.py list-ports

# List discovered CSV files
python sniffer.py list-csv

# Show CSV headers (for column mapping)
python sniffer.py show-headers

# Replay a log file
python sniffer.py replay session.log

# Replay with specific CSV
python sniffer.py replay session.log --csv custom.csv
```

### Related Documentation

- `REKORDBOX-MIDI-CSV-SPEC.md` - Complete CSV format specification
- `RGB_COLORING_EXPERIMENT.md` - RGB hex coloring experiment details
- `docs/architecture.md` - System architecture

### Controller-Specific Notes

| Controller | Notes |
|------------|-------|
| DDJ-FLX10 | Built-in hi-res faders on Ch 6 |
| DDJ-GRV6 | Channel 6 for mixer controls |
| XDJ-RX2/3 | Channel 4 for master/booth |
| DJM mixers | Channel 0 for master/booth |

---

## Tips for Advanced Workflows

1. **Use Shift Layers**: Double your control surface with shift modifiers
2. **Color-Code Pads**: Assign different pad colors for different functions
3. **Macro Buttons**: Map complex sequences to single buttons
4. **Velocity Sensitivity**: Use note velocity for parameter scaling
5. **LED Feedback**: Always include output mapping for visual confirmation
6. **Test Incrementally**: Add a few mappings at a time, test, then continue
7. **Backup Often**: Keep copies of working CSV versions

---

## Further Resources

- **Rekordbox MIDI Learn Operation Guide**: Official AlphaTheta documentation
- **MIDI Specification**: Standard MIDI messages and protocols
- **Community Mappings**: Share and discover mappings at DJ forums

---

*Generated for rb-midi-sniffer project*
