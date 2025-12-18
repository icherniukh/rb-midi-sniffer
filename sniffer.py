#!/usr/bin/env python3
"""
Rekordbox MIDI Sniffer

Real-time MIDI monitor for DDJ controller ↔ Rekordbox communication.
Displays MIDI messages with Rekordbox function names parsed from CSV files.

Features:
- Auto-scan MIDI ports (detect DDJ controllers and Rekordbox ports)
- Auto-discover Rekordbox CSV files from Rekordbox.app folder
- Parse CSV to map MIDI → Rekordbox functions
- Display bidirectional MIDI with hex bytes and function names
- Customizable column display
- Write timestamped log files

Usage:
    python sniffer.py monitor      # Live monitoring
    python sniffer.py replay X.log # Replay log file
    python sniffer.py list-csv     # Show available CSVs
    python sniffer.py list-ports   # Show MIDI ports
    python sniffer.py help         # Show help
"""

from cli import cli

if __name__ == '__main__':
    cli()
