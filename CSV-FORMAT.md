# Rekordbox MIDI Mapping CSV Format

Community-maintained specification based on observation and reverse engineering of Pioneer DJ controller CSV files bundled with Rekordbox 7.

**Status**: Draft
**Last Updated**: 2024-12
**Source Files Analyzed**: DDJ-FLX10.midi.csv, DDJ-GRV6.midi.csv

---

## File Structure

### Line 1: File Header
```csv
@file,1,DDJ-FLX10
```
| Position | Value | Notes |
|----------|-------|-------|
| 0 | `@file` | File type identifier |
| 1 | `1` | Version or format indicator (observed: always `1`) |
| 2 | Controller name | e.g., `DDJ-FLX10`, `DDJ-GRV6` |

### Line 2: Column Headers
```csv
#name,function,type,input,deck1,deck2,deck3,deck4,output,deck1,deck2,deck3,deck4,option,comment
```
15 columns total. Note: `deck1-4` appears twice (input and output).

### Subsequent Lines: Data Rows
Function mappings, section dividers, or empty rows.

---

## Column Definitions

| # | Header | Purpose | Examples |
|---|--------|---------|----------|
| 0 | `#name` | Internal identifier (purpose unclear) | `PlayPause`, `#CrossFader`, `#`, `# Browser` |
| 1 | `function` | **Rekordbox function being mapped** | `PlayPause`, `Browse+Press`, empty |
| 2 | `type` | Control type | `Button`, `Rotary`, `KnobSliderHiRes` |
| 3 | `input` | Base MIDI IN code (4-digit hex) | `900B`, `B640`, empty |
| 4-7 | `deck1-4` | Input deck channel data | `0,1,2,3` or `9646,9647,9648,9649` |
| 8 | `output` | Base MIDI OUT code (LED feedback) | `900B`, empty |
| 9-12 | `deck1-4` | Output deck channel data | Same patterns as input |
| 13 | `option` | Flags (semicolon-separated) | `Fast;Priority=50;Dual` |
| 14 | `comment` | Human-readable description | `Play/Pause` |

### Key Observation
**Column 1 (`function`) determines the actual mapping.** If empty, the row has no functional mapping (used as visual separator or placeholder).

---

## Row Types

### Functional Mapping
```csv
PlayPause,PlayPause,Button,900B,0,1,2,3,900B,0,1,2,3,Fast;Priority=50;Dual,Play/Pause
```
Column 1 contains a valid Rekordbox function name.

### Section Divider
```csv
# Browser,,,,,,,,,,,,,,
```
Column 0 contains text (often `# SectionName`), column 1 is empty. Visual organization only.

### Empty Row
```csv
,,,,,,,,,,,,,,
```
All columns empty. Visual spacing.

### Placeholder / Unassigned
```csv
#,Browse+Press+Shift,Button,,9669,966D,966E,966F,,,,,,,No function assigned here
```
Column 0 is `#`, column 1 has a function name, but comment indicates no assignment. Behavior unclear.

---

## MIDI Code Format

### 4-Digit Hex Structure
```
[Status Byte][Data Byte]
     90           0B
```

**Status Byte** = Message Type (upper nibble) + Channel (lower nibble)

| Hex | Message Type |
|-----|--------------|
| `8x` | Note Off |
| `9x` | Note On |
| `Bx` | Control Change (CC) |

**Examples**:
- `900B` = Note On, Channel 0, Note 11
- `B640` = CC, Channel 6, CC 64
- `BF49` = CC, Channel 15, CC 73

---

## Deck Assignment Patterns

### Pattern 1: Base + Channel Offsets
```csv
PlayPause,PlayPause,Button,900B,0,1,2,3,900B,0,1,2,3,...
```
- `input`: `900B` (base: Note On, Ch 0, Note 11)
- `deck1-4`: `0,1,2,3` (channel offsets)
- Result: Ch 0 = Deck 1, Ch 1 = Deck 2, Ch 2 = Deck 3, Ch 3 = Deck 4

### Pattern 2: Empty Base + Direct MIDI Codes
```csv
ForwardAndLoad,Browse+Press,Button,,9646,9647,9648,9649,...
```
- `input`: empty
- `deck1-4`: Complete MIDI codes per deck
- Result: Each deck has independent MIDI address

### Pattern 3: Global (No Deck Assignment)
```csv
Browse,Browse,Rotary,B640,,,,,,,,,,,Browse
```
- `input`: `B640` (CC, Channel 6)
- `deck1-4`: all empty
- Result: Single global control, not deck-specific

### Pattern 4: Non-Sequential Channels (Performance Pads)
```csv
PAD1_PadMode1,PAD1_PadMode1,Pad,9000,7,9,11,13,9000,7,9,11,13,...
```
- Channels 7, 9, 11, 13 for decks 1-4
- Used for performance pads where channel layout differs

---

## Control Types

### Input Controls
| Type | Description | Resolution |
|------|-------------|------------|
| `Button` | Momentary button | On/Off |
| `Pad` | Velocity-sensitive pad | 0-127 velocity |
| `Rotary` | Relative encoder | Centered at 64 |
| `Knob` | Absolute knob | 0-127 |
| `KnobSlider` | Fader | 0-127 |
| `KnobSliderHiRes` | High-resolution fader | 14-bit (0-16383) |
| `JogRotate` | Jog wheel rotation | Continuous |
| `JogTouch` | Jog wheel touch sensor | On/Off |
| `Difference` | Position difference | Search/seek |

### Output-Only Controls
| Type | Description |
|------|-------------|
| `Indicator` | LED or display feedback (no input) |
| `Value` | Bidirectional value/setting transfer |
| `Parameter` | Internal configuration (see below) |

---

## Options Field

Semicolon-separated flags in column 13.

| Option | Description |
|--------|-------------|
| `Fast` | High-priority processing |
| `Priority=N` | Priority level (0-100, default 50) |
| `Dual` | 4-deck controller dual-deck mode |
| `Blink=N` | LED blink rate in milliseconds |
| `RO` | Read-Only (output only, no input processing) |
| `Value=N` | Configuration value (used with `Parameter` type) |

---

## Special Sections

### `# State`
State synchronization between hardware and software.

```csv
VinylState,VinylState,Button,903A,0,1,2,3,,,,,,RO,LED State of the Vinyl buttons
DeckState,DeckState,Button,903C,0,1,2,3,,,,,,RO,LED State of the DECK
Permission_PadMode1,Permission_PadMode1,Indicator,,,,,,9021,0,1,2,3,RO,Permission flag
```

Observed uses:
- LED state reporting
- Deck state indicators
- Permission flags for mode changes

### `# illumination`
Hardware settings and LED control.

```csv
LoadedIndicator,LoadedIndicator,Indicator,,,,,,,9F00,9F01,9F02,9F03,RO;Priority=100,Load illumination
CrossFaderCurveSetting,CrossFaderCurveSetting,Value,BF49,,,,,BF49,,,,,RO;Priority=100,Cross Fader Curve
JogBrightnessSetting,JogBrightnessSetting,Value,BF46,,,,,BF46,,,,,RO;Priority=100,JOG RING brightness
```

Observed uses:
- Load/loop state indicators
- Hardware preferences (brightness, crossfader curve, talkover)
- Uses `9Fxx` and `BFxx` MIDI codes (channel 15)

### `# Parameter`
Internal timing and behavior configuration.

```csv
JogIndicatorInterval,JogIndicatorInterval,Parameter,FFF1,,,,,,,,,,Value=12,
MidiOutInterval,MidiOutInterval,Parameter,FFF3,,,,,,,,,,Value=2,
```

Observations:
- Uses `FFFx` codes (outside standard MIDI range)
- `Value=N` in options specifies the setting
- Likely internal to Rekordbox/hardware communication

---

## Unclear / Unverified Areas

### Column 0 (`#name`) Purpose
- Sometimes matches column 1 (`PlayPause,PlayPause,...`)
- Sometimes differs (`ForwardAndLoad,Browse+Press,...`)
- Purpose and processing rules unknown

### `#` Prefix in Column 0
Observed interpretations (unverified):
- May indicate "commented out" from processing
- May indicate hardware-defined (not user-assignable)
- Rows with `#` in col0 but valid function in col1 are ambiguous

### Function Name Modifiers
Syntax like `PlayPause+Shift`, `Browse+Press+LongPress` observed in column 1.
- Assumed to indicate modifier key combinations
- Not verified against official documentation

### `Parameter` Type and `FFFx` Codes
- Outside normal MIDI range (data byte > 127)
- Likely internal protocol, not standard MIDI
- Processing mechanism unknown

---

## References

- **Official**: Rekordbox MIDI Learn Guide v5.3.0 (PDF)
- **CSV Sources**: `/Applications/rekordbox 7/rekordbox.app/Contents/Resources/MidiMappings/`
- **Analyzed Files**: DDJ-FLX10.midi.csv (567 lines), DDJ-GRV6.midi.csv

---

## Contributing

This specification is maintained by the community. To contribute:
1. Document observed behaviors with evidence
2. Clearly mark assumptions vs. verified facts
3. Add unclear items to the "Unclear / Unverified Areas" section
