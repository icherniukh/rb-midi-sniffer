# Rekordbox MIDI Sniffer - Claude Context

## What This Is
CLI tool that monitors MIDI traffic from Pioneer DJ controllers and displays Rekordbox function names by parsing Rekordbox's bundled CSV mapping files.

## Key Files
- `sniffer.py` - Entry point (thin wrapper)
- `csv_parser.py` - CSV parsing (RekordboxCSVParser, CSV discovery)
- `monitor.py` - MIDI monitoring (RekordboxMIDISniffer, port scanning)
- `cli.py` - Click CLI commands
- `REKORDBOX-MIDI-CSV-SPEC.md` - Community CSV format specification (reverse-engineered)
- `docs/architecture.md` - System architecture diagram
- `references/` - Official docs and CSV examples:
  - `rekordbox7.0.5_midi_learn_operation_guide_EN.pdf` - Official AlphaTheta guide (UI/workflow, NOT CSV format)

## How It Works
1. Auto-detects connected MIDI controller (e.g., "DDJ-GRV6")
2. Finds matching CSV from `/Applications/rekordbox 7/.../MidiMappings/`
3. Parses CSV to build MIDI → function lookup table
4. Monitors MIDI port, displays function names in real-time

## CSV Format (Rekordbox MIDI Learn)
```
@file,1,DDJ-GRV6
#name,function,type,input,deck1,deck2,deck3,deck4,output,deck1,deck2,deck3,deck4,option,comment
PlayPause,PlayPause,Button,900B,0,1,2,3,900B,0,1,2,3,Fast,Play/Pause
```
- `input` column: base MIDI (e.g., `900B` = Note 0x0B on channel 0)
- `deck1-4` columns: channel offsets (0,1,2,3 → channels 0,1,2,3)
- Two patterns: (1) base + offsets, (2) empty input + full MIDI in deck columns

## Controller Family Detection
Built-in mappings for hardware controls (not in CSV) vary by family:
- DDJ controllers: Channel 6
  - CC 5: Mic Level
  - CC 8: Master Level
  - CC 9: Booth Level
  - CC 12: Cue/Master Mix
  - CC 13: Headphones Level
- XDJ all-in-ones: Channel 4, CC 24/25 (Master/Booth only)
- DJM mixers: Channel 0, CC 24/25 (Master/Booth only)

## Commands
```bash
python sniffer.py monitor      # Live monitoring
python sniffer.py replay X.log # Replay log file
python sniffer.py list-csv     # Show available CSVs
python sniffer.py list-ports   # Show MIDI ports
python sniffer.py show-headers # Show CSV column headers
python sniffer.py help         # Show help
```

## Pending Work
- [ ] See `tasks/120825_issue_audit/issue-analysis.md` for remaining issues from the 33 identified

## Completed
- [x] CSV format specification (REKORDBOX-MIDI-CSV-SPEC.md)
- [x] Verify/update imported skills - fixed stale file paths
- [x] Split into separate modules (parser.py, midi_sniffer.py, cli.py)
- [x] Change help to `sniffer.py help` convention
- [x] Add architecture diagram (docs/architecture.md)
- [x] Clarified OUT/IN behavior - DeckState/DeckSelect appear as IN because they ARE input messages from the controller reporting its state (marked with `RO` option in CSV). Added `[Status]` indicator for these read-only/feedback messages
- [x] Button press vs release indicators - now shows `PRESS` (green) or `release` (red/dim) for button events
- [x] Colorization improvements:
  - Hex bytes: status=cyan/magenta, data1=yellow, velocity=green(press)/red(release)
  - Function names colored by type: cyan=Button, magenta=Rotary/Knobs, yellow=Jog
  - Control type in blue, comments dimmed, Status indicator in bold yellow
- [x] Fixed critical log file handle leak (Issue #3)
- [x] Fixed negative speed validation in replay (Issue #5)
- [x] Regex case sensitivity already correct in refactored code (Issue #4)
- [x] Integrated official MIDI Learn Operation Guide - updated CSV spec with official control types, function categories, and constraints
- [x] Message grouping and bidirectional port support:
  - IOPort support with graceful fallback to input-only
  - Message grouping for jog wheels and repeated actions (throttled display at 250ms)
  - --no-grouping CLI flag to disable grouping
  - Proper Ctrl+C handling to flush groups on exit
  - Note: OUT monitoring (Rekordbox→controller LED feedback) requires virtual MIDI routing (see tasks/121925_bidirectional_research/)
- [x] Grouping improvements (tasks/231225_grouping_visibility/):
  - Fixed MSB/LSB grouping for hi-res controls (ChannelFader, CrossFader, etc.)
  - Value-based color gradient: green (0) → cyan → blue → magenta → red (127)
  - Clean display format: `(x502) val: 59` with gray counter, bold colored value
  - Discovered and mapped undocumented controls: MicLevel, HeadphonesLevel, CueMasterMix

## Dependencies
- `mido` - MIDI I/O
- `click` - CLI framework
