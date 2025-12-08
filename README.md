# Rekordbox MIDI Sniffer

Real-time MIDI monitor for Pioneer DJ controllers. Displays Rekordbox function names by parsing Rekordbox's bundled CSV mapping files.

## Install

```bash
pip install mido click python-rtmidi
```

## Usage

```bash
# Monitor connected controller (auto-detects CSV)
python sniffer.py monitor

# Replay a captured log
python sniffer.py replay session.log

# Show specific columns
python sniffer.py monitor -c "function,type,comment"

# List available commands
python sniffer.py --help
```

## Features

- Auto-detects controller and matches CSV from Rekordbox installation
- Parses 68+ Pioneer DJ controller mappings
- Shows function names, control types, deck assignments
- Logs sessions for later replay
- Supports DDJ, XDJ, and DJM controller families

## Requirements

- macOS with Rekordbox 7 installed (for CSV files)
- Pioneer DJ controller connected via USB
