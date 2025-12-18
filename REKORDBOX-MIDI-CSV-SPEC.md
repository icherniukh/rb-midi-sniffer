# Rekordbox MIDI Mapping CSV Specification

Reverse-engineered specification of Rekordbox's MIDI controller mapping CSV format. The official AlphaTheta documentation covers the MIDI Learn UI and workflow, but not the underlying CSV file structure—this spec fills that gap.

**Status**: Draft v1.2
**Last Updated**: 2024-12-15
**Sources**: DDJ-FLX10.midi.csv (567 lines), DDJ-GRV6.midi.csv (339 lines), rekordbox7.0.5 MIDI Learn Operation Guide

---

## Quick Reference

| Aspect | Value |
|--------|-------|
| Format | CSV, 15 columns |
| Header | Line 1: `@file,1,ControllerName` |
| Columns | Line 2: `#name,function,type,input,deck1-4,output,deck1-4,option,comment` |
| MIDI codes | 4-digit hex: `SSDD` (status byte + data byte) |
| Key column | Column 1 (`function`) - determines mapped Rekordbox function |

---

## Column Definitions

| Col | Header | Purpose | Required |
|-----|--------|---------|----------|
| 0 | `#name` | Internal identifier (see [Column 0 Patterns](#column-0-name-patterns)) | No |
| 1 | `function` | **Rekordbox function to map** | Yes (if functional row) |
| 2 | `type` | Control type (Button, Rotary, etc.) | Usually |
| 3 | `input` | Base MIDI IN code (4-digit hex) | Conditional |
| 4-7 | `deck1-4` | Input deck assignments | Conditional |
| 8 | `output` | Base MIDI OUT code (LED feedback) | No |
| 9-12 | `deck1-4` | Output deck assignments | No |
| 13 | `option` | Flags (semicolon-separated) | No |
| 14 | `comment` | Human description | No |

### Column 0 (`#name`) Patterns

Three observed patterns (purpose not officially documented):

| Pattern | Example | Observation |
|---------|---------|-------------|
| Matches col 1 | `PlayPause,PlayPause,...` | Most common |
| Differs from col 1 | `ForwardAndLoad,Browse+Press,...` | Function aliasing? |
| Hash only | `#,Browse+Press+Shift,...` | Placeholder row |

### Column 1 (`function`) - The Key Column

This column determines what Rekordbox function is mapped. Syntax includes modifiers:

```
FunctionName
FunctionName+Shift
FunctionName+LongPress
FunctionName+Press
FunctionName+Shift+LongPress
```

**If column 1 is empty, the row has no functional mapping** (used as visual separator).

---

## File Structure

### Line 1: File Header
```csv
@file,1,DDJ-FLX10
```
- Position 0: `@file` (file type marker)
- Position 1: `1` (format version - always observed as `1`)
- Position 2: Controller name

### Line 2: Column Headers
```csv
#name,function,type,input,deck1,deck2,deck3,deck4,output,deck1,deck2,deck3,deck4,option,comment
```

### Subsequent Lines: Data Rows

See [Row Types](#row-types).

---

## MIDI Code Format

Codes are 4-digit hexadecimal: `SSDD`
- `SS` = Status byte (message type + channel)
- `DD` = Data byte (note number or CC number)

**Status byte**: Upper nibble = message type, lower nibble = channel (0-15)

| Upper Nibble | Message Type |
|--------------|--------------|
| `8` | Note Off |
| `9` | Note On |
| `B` | Control Change |

**Example**: `900B`
- `90` = Note On, Channel 0
- `0B` = Note 11

See [MIDI 1.0 Specification](https://www.midi.org/specifications) for full reference.

---

## Deck Assignment Patterns

### Pattern 1: Base Code + Channel Offsets
```csv
PlayPause,PlayPause,Button,900B,0,1,2,3,900B,0,1,2,3,...
```
*(DDJ-FLX10.midi.csv:16)*

- `input`: `900B` (base code, Channel 0)
- `deck1-4`: `0,1,2,3` (channel offsets added to base)
- Result: Deck 1 = Ch 0, Deck 2 = Ch 1, Deck 3 = Ch 2, Deck 4 = Ch 3

### Pattern 2: Empty Base + Direct MIDI Codes
```csv
ForwardAndLoad,Browse+Press,Button,,9646,9647,9648,9649,...
```
*(DDJ-FLX10.midi.csv:7)*

- `input`: empty
- `deck1-4`: Complete MIDI codes per deck

### Pattern 3: Global Control (No Deck Assignment)
```csv
Browse,Browse,Rotary,B640,,,,,,,,,,,Browse
```
*(DDJ-FLX10.midi.csv:5)*

- `input`: `B640` (Channel 6 = global)
- `deck1-4`: all empty

### Pattern 4: Non-Sequential Channels
```csv
PAD1_PadMode1,PAD1_PadMode1,Pad,9000,7,9,11,13,...
```
*(DDJ-FLX10.midi.csv:220)*

- Channels 7, 9, 11, 13 for decks 1-4 (not sequential)

### Pattern 5: Multi-Row Per Function
```csv
FXPartSelectVocalOn,,Button,9714,,,,,9714,,,,,,FX PART SELECT VOCAL
FXPartSelectVocalOn,,Button,9914,,,,,9914,,,,,,FX PART SELECT VOCAL
FXPartSelectVocalOn,,Button,9B14,,,,,9B14,,,,,,FX PART SELECT VOCAL
FXPartSelectVocalOn,,Button,9D14,,,,,9D14,,,,,,FX PART SELECT VOCAL
```
*(DDJ-GRV6.midi.csv:223-226)*

- Same function repeated on multiple rows
- Each row has different MIDI code (channels 7, 9, 11, 13)
- Deck columns empty; channel embedded in MIDI code

---

## Row Types

### Functional Row
Column 1 contains a valid function name.
```csv
PlayPause,PlayPause,Button,900B,0,1,2,3,900B,0,1,2,3,Fast;Priority=50;Dual,Play/Pause
```

### Section Header
Column 0 contains section name, column 1 empty.
```csv
# Browser,,,,,,,,,,,,,,
# Deck,,,,,,,,,,,,,,
```

### Empty Row (Separator)
```csv
,,,,,,,,,,,,,,
```

### Prefixed Rows (`#` in Column 0)
Rows where column 0 starts with `#` but column 1 has content:
```csv
#CrossFader,CrossFader,KnobSliderHiRes,B61F,,,,,,,,,,Fast,Crossfader
#,Browse+Press+Shift,Button,,9669,966D,966E,966F,,,,,,,No function assigned
```

**Observed behavior**: These rows appear functional but may be excluded from MIDI Learn UI assignment. Requires further testing.

---

## Control Types

### Official Types (from MIDI Learn UI)

These are the types shown in Rekordbox's MIDI setting window:

| UI Name | CSV Name | Description |
|---------|----------|-------------|
| `Button` | `Button` | Momentary button, Note On/Off |
| `Button(for Pad)` | `Button` | Button mode for pad hardware |
| `Pad` | `Pad` | Velocity-sensitive pad, Note On with velocity |
| `Knob/Slider (0h-7Fh)` | `Knob`, `KnobSlider` | 128-step (7-bit) knob/fader |
| `Knob/Slider (0h-3FFFh)` | `KnobSliderHiRes` | 16384-step (14-bit) high-resolution fader |
| `Rotary` | `Rotary` | Relative encoder |
| `Indicator` | `Indicator` | Output-only LED feedback (cannot learn from input) |
| `Value` | `Value` | Special type for Needle Search and Velocity Sampler |

### CSV-Only Types (observed in mapping files)

| Type | Description | Notes |
|------|-------------|-------|
| `JogRotate` | Jog wheel rotation | Continuous |
| `JogTouch` | Jog wheel touch | On/Off |
| `JogIndicator` | Jog display feedback | Output only |
| `Difference` | Position difference | For search/seek |
| `Parameter` | Internal config | Uses special `FFFx` codes |

### Value Type Details

Per official documentation, the `Value` type serves two purposes:

1. **Needle Search**: Set by sliding finger along ribbon controller
2. **Velocity Sampler**: For pads that send both Note On and CC simultaneously
   - MIDI IN format: `Bnxx` where `n` = channel (0-F), `xx` = Data 1 (00-FF)
   - Cannot be learned by pressing pads; must enter MIDI code directly

### Indicator Type Behavior

The `Indicator` type is output-only:
- Illumination information sent TO equipment
- Cannot assign functions by operating equipment
- Must directly enter MIDI OUT code in the UI

---

## Options Field

Semicolon-separated flags in column 13.

| Option | Description | Example |
|--------|-------------|---------|
| `Fast` | Priority processing | Time-critical controls |
| `Priority=N` | Priority level (0-100) | `Priority=50` |
| `Dual` | 4-deck mode support | DDJ-FLX10 |
| `Blink=N` | LED blink rate (ms) | `Blink=600` |
| `RO` | Read-only | See note below |
| `Value=N` | Config value | Used with `Parameter` type |
| `Min=N` | Minimum value | `Min=1` |
| `Max=N` | Maximum value | `Max=72` |

**Note on `RO`**: Defined as "read-only / output only" but some rows have both input MIDI codes and `RO` flag (e.g., JogScratch). Exact semantics unclear.

---

## Function Categories

Rekordbox organizes MIDI-assignable functions into these tabs (per official MIDI Learn UI):

| Tab | Functions |
|-----|-----------|
| **DECK** | PlayPause, Cue, Sync, Loop, Tempo, etc. |
| **PAD** | Hot Cue, Pad Mode, Performance Pads |
| **FX** | Effect select, Effect parameters |
| **SAMPLER** | Sampler triggers, volume |
| **MIXER** | Faders, EQ, filters |
| **BROWSE** | Library navigation, Load |
| **OTHER** | Miscellaneous functions |
| **VIDEO** | Video mode controls |
| **LIGHTING** | Lighting mode controls |
| **MIXPOINTLINK** | MixPointLink features |

When using ADD in MIDI Learn, available functions are filtered to the selected tab's category.

---

## Special Sections

### `# State` Section
State synchronization messages.
```csv
VinylState,VinylState,Button,903A,0,1,2,3,,,,,,RO,LED State of Vinyl buttons
DeckState,DeckState,Button,903C,0,1,2,3,,,,,,RO,LED State of DECK
```

### `# illumination` Section
Hardware settings and LED control. Uses `9Fxx` and `BFxx` codes (Channel 15).
```csv
LoadedIndicator,LoadedIndicator,Indicator,,,,,,,9F00,9F01,9F02,9F03,RO;Priority=100,Load illumination
JogBrightnessSetting,JogBrightnessSetting,Value,BF46,,,,,BF46,,,,,RO;Priority=100,JOG RING brightness
```

### `# Parameter` Section
Internal timing configuration. Uses `FFFx` codes (outside standard MIDI range).
```csv
JogIndicatorInterval,JogIndicatorInterval,Parameter,FFF1,,,,,,,,,,Value=12,
MidiOutInterval,MidiOutInterval,Parameter,FFF3,,,,,,,,,,Value=2,
```

---

## Worked Example

Row from DDJ-FLX10.midi.csv:16:
```csv
PlayPause,PlayPause,Button,900B,0,1,2,3,900B,0,1,2,3,Fast;Priority=50;Dual,Play/Pause
```

| Column | Value | Meaning |
|--------|-------|---------|
| 0 `#name` | `PlayPause` | Internal identifier |
| 1 `function` | `PlayPause` | Maps to Rekordbox PlayPause function |
| 2 `type` | `Button` | Momentary button control |
| 3 `input` | `900B` | Base: Note On (0x90), Channel 0, Note 11 |
| 4-7 `deck1-4` | `0,1,2,3` | Channel offsets → Ch 0,1,2,3 for decks 1-4 |
| 8 `output` | `900B` | Same as input (LED mirrors button state) |
| 9-12 `deck1-4` | `0,1,2,3` | Output channels match input |
| 13 `option` | `Fast;Priority=50;Dual` | High priority, 4-deck support |
| 14 `comment` | `Play/Pause` | Human description |

**Resulting MIDI mappings**:
- `900B` (Ch 0, Note 11) → PlayPause Deck 1
- `910B` (Ch 1, Note 11) → PlayPause Deck 2
- `920B` (Ch 2, Note 11) → PlayPause Deck 3
- `930B` (Ch 3, Note 11) → PlayPause Deck 4

---

## Lookup Algorithm

To find a Rekordbox function from a MIDI message:

```
1. Receive MIDI message (e.g., 0x910B = Note On, Ch 1, Note 11)
2. Extract: type=note_on, channel=1, note=11

3. Search rows for match:
   a. Check if input column base + deck offset matches
      - Base 900B + offset 1 = 910B ✓
   b. Check if deck column contains full MIDI code
      - deck2 column = "910B" ✓
   c. Check multi-row patterns (same function, different MIDI)

4. Return function from column 1
```

Reference implementation: `sniffer.py` class `RekordboxCSVParser`

---

## Unknown / Needs Verification

| Item | Status | Notes |
|------|--------|-------|
| Column 0 purpose | Unknown | Three patterns observed, no documentation |
| `#` prefix meaning | Unknown | May exclude from MIDI Learn UI |
| `RO` with input codes | Unclear | Contradicts "output only" definition |
| `FFFx` codes | Unknown | Internal protocol, not standard MIDI |
| Format changes across versions | Untested | Rekordbox 6 vs 7 differences unknown |

### Official Constraints (from MIDI Learn Guide)

- **One MIDI code per function**: The same MIDI code cannot be assigned to multiple functions
- **MIDI OUT auto-populates**: For functions with indicators (LEDs), MIDI OUT is automatically set to match MIDI IN
- **Auto-save**: Settings are automatically saved when MIDI setting window is closed

---

## Undocumented Controls Found in Practice

The following controls have been observed in actual hardware use but are **not present** in the official Rekordbox CSV mapping files. These may be:
- Hardware-specific features not yet documented by manufacturer
- Firmware updates adding new functionality
- Undocumented modifier combinations

### DDJ-GRV6: Shift+Jog Rotation (CC 41)

**MIDI Code**: `B0 29` (Control Change 41 on Channel 0) + deck offsets
**Observed Behavior**: When Shift is held and jog wheel is rotated
**Function**: Fast track search/scan (faster than regular jog pitch bend)

**Details**:
- Generates high-frequency messages (~2-4ms intervals)
- Value range: 59-71 (0x3B-0x47), center at 64 (0x40)
- Values appear to encode rotation speed/direction
- Not present in DDJ-GRV6.midi.csv despite related controls being documented:
  - `JogScratch` (B022 / CC 34) ✓ Present
  - `JogPitchBend` (B023 / CC 35) ✓ Present
  - `JogTouch+Shift` (9067 / Note 0x67) ✓ Present
  - `Shift+Jog Rotation` (B029 / CC 41) ✗ Missing

**Test Data**: See `tasks/121825_test_findings/analysis.md` for full analysis (5,007 instances in 81K-line log)

**Suggested CSV Entry**:
```csv
JogFastSearch,JogFastSearch+Shift,JogRotate,B029,0,1,2,3,,,,,,RO,Fast Track Search (Shift+Jog)
```

### DDJ-GRV6: Unknown Channel 6 (Mixer) Controls

Several unrecognized CC messages on Channel 6 (mixer channel):
- CC 5: 12 instances (various values)
- CC 12: 12 instances (various values)
- CC 13: 18 instances (various values)
- CC 37: 23 instances (various values)
- CC 44: 13 instances (various values)
- CC 45: 32 instances (various values)

**Status**: Function unknown - may be effect controls, sampler, or mixer-specific features not in CSV

---

## References

- **Source CSVs**: `/Applications/rekordbox 7/rekordbox.app/Contents/Resources/MidiMappings/`
- **Parser implementation**: `parser.py` (RekordboxCSVParser)
- **Official guide**: `references/rekordbox7.0.5_midi_learn_operation_guide_EN.pdf` - AlphaTheta MIDI Learn Operation Guide
  - Documents MIDI setting UI, control types, and LEARN workflow
  - Does NOT document CSV file format (which we reverse-engineered)
- **MIDI 1.0 Spec**: https://www.midi.org/specifications

---

## Contributing

Found a pattern we missed? Tested a theory? Please contribute:

1. **Cite your source**: Include CSV filename and line number
2. **Show your test**: "Pressed X, observed MIDI Y, Rekordbox did Z"
3. **Mark unknowns**: If guessing, say so clearly
4. **Add test files**: New controller CSVs welcome in `references/`

We especially need:
- Testers with XDJ/DJM gear (different MIDI channel conventions)
- Verification of `#` prefix behavior in MIDI Learn UI
- Rekordbox 6 CSV comparisons

---

*This specification aids interoperability and community tool development. We encourage users to support official Pioneer DJ hardware and Rekordbox software.*
