# Rekordbox MIDI Sniffer - Claude Context

## What This Is
CLI tool that monitors MIDI traffic from Pioneer DJ controllers and displays Rekordbox function names by parsing Rekordbox's bundled CSV mapping files.

## Key Files
- `sniffer.py` - Main tool (single file, ~1100 lines)
- `REKORDBOX-MIDI-CSV-SPEC.md` - Community CSV format specification (reverse-engineered)
- `references/` - CSV examples and Rekordbox MIDI Learn Guide PDF

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
Built-in mappings for Master/Booth Level vary by family:
- DDJ controllers: Channel 6, CC 8/9
- XDJ all-in-ones: Channel 4, CC 24/25
- DJM mixers: Channel 0, CC 24/25

## Commands
```bash
python sniffer.py monitor      # Live monitoring
python sniffer.py replay X.log # Replay log file
python sniffer.py list-csv     # Show available CSVs
python sniffer.py list-ports   # Show MIDI ports
```

## Pending Work
- [ ] Split into separate modules (parser, sniffer, cli)
- [ ] Change help to `sniffer.py help` convention
- [ ] Add architecture diagram

## Completed
- [x] CSV format specification (REKORDBOX-MIDI-CSV-SPEC.md)
- [x] Verify/update imported skills - fixed stale file paths

## Dependencies
- `mido` - MIDI I/O
- `click` - CLI framework
