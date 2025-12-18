# Rekordbox MIDI Sniffer Architecture

## Overview

The Rekordbox MIDI Sniffer is a CLI tool that monitors MIDI traffic from Pioneer DJ controllers and displays Rekordbox function names by parsing Rekordbox's bundled CSV mapping files.

## Module Structure

```
rb-midi-sniffer/
├── sniffer.py          # Entry point (thin wrapper)
├── csv_parser.py       # CSV parsing and lookup
├── monitor.py          # MIDI monitoring and formatting
├── cli.py              # Click CLI commands
└── docs/
    └── architecture.md # This file
```

## Component Diagram

```mermaid
flowchart TD
    subgraph Entry["Entry Point"]
        MAIN[sniffer.py]
    end

    subgraph CLI["CLI Layer (cli.py)"]
        CMD[Click Commands]
        MON_CMD[monitor]
        REPLAY_CMD[replay]
        LIST_CMD[list-ports/list-csv]
        SHOW_CMD[show-headers]
        HELP_CMD[help]

        CMD --> MON_CMD
        CMD --> REPLAY_CMD
        CMD --> LIST_CMD
        CMD --> SHOW_CMD
        CMD --> HELP_CMD
    end

    subgraph Parser["Parser Layer (csv_parser.py)"]
        CSV_PARSER[RekordboxCSVParser]
        CSV_DISCOVER[find_rekordbox_csv_files]
        CSV_MATCH[auto_match_port_to_csv]
        COL_PARSE[parse_columns]
    end

    subgraph Sniffer["Sniffer Layer (monitor.py)"]
        MIDI_SNIFFER[RekordboxMIDISniffer]
        PORT_SCAN[scan_midi_ports]
        HEX_PARSE[parse_hex_to_midi]
    end

    subgraph External["External"]
        CSV_FILE[(CSV Files)]
        MIDI_PORT[MIDI Controller]
        LOG_FILE[(Log Files)]
        TERMINAL[Terminal]
    end

    MAIN --> CMD

    MON_CMD --> CSV_PARSER
    MON_CMD --> MIDI_SNIFFER
    MON_CMD --> PORT_SCAN
    MON_CMD --> CSV_DISCOVER
    MON_CMD --> CSV_MATCH

    REPLAY_CMD --> CSV_PARSER
    REPLAY_CMD --> MIDI_SNIFFER
    REPLAY_CMD --> HEX_PARSE

    SHOW_CMD --> CSV_PARSER
    LIST_CMD --> PORT_SCAN
    LIST_CMD --> CSV_DISCOVER

    CSV_PARSER --> CSV_FILE
    MIDI_SNIFFER --> MIDI_PORT
    MIDI_SNIFFER --> LOG_FILE
    MIDI_SNIFFER --> TERMINAL
```

## Data Flow

```mermaid
sequenceDiagram
    participant User
    participant CLI as cli.py
    participant Parser as csv_parser.py
    participant Sniffer as monitor.py
    participant CSV as CSV File
    participant MIDI as MIDI Port
    participant Term as Terminal

    User->>CLI: python sniffer.py monitor
    CLI->>Sniffer: scan_midi_ports()
    Sniffer-->>CLI: [port names]
    CLI->>Parser: find_rekordbox_csv_files()
    Parser-->>CLI: [csv paths]
    CLI->>Parser: auto_match_port_to_csv()
    Parser-->>CLI: matched_csv
    CLI->>Parser: RekordboxCSVParser(csv)
    Parser->>CSV: read
    CSV-->>Parser: rows
    Parser-->>CLI: parser (with lookup table)
    CLI->>Sniffer: RekordboxMIDISniffer(parser)

    loop Monitor Loop
        MIDI->>Sniffer: MIDI message
        Sniffer->>Parser: lookup_function(msg)
        Parser-->>Sniffer: function info
        Sniffer->>Term: formatted output
    end
```

## Module Responsibilities

### sniffer.py (Entry Point)
- Thin wrapper that imports and runs the CLI
- Contains module docstring with usage examples

### csv_parser.py (CSV Parsing)
- `RekordboxCSVParser`: Parse Rekordbox CSV files, build MIDI→function lookup table
- `find_rekordbox_csv_files()`: Discover CSV files in standard locations
- `auto_match_port_to_csv()`: Match MIDI port name to CSV file
- `parse_columns()`: Parse user column specifications

### monitor.py (MIDI Handling)
- `RekordboxMIDISniffer`: Monitor MIDI ports, format and display messages
- `scan_midi_ports()`: List available MIDI input/output ports
- `parse_hex_to_midi()`: Convert hex string to mido Message (for replay)

### cli.py (CLI Commands)
- `monitor`: Real-time MIDI monitoring
- `replay`: Replay captured log files
- `list-ports`: Show available MIDI ports
- `list-csv`: Show discovered CSV files
- `show-headers`: Display CSV column headers
- `help`: Show help information

## CSV Lookup Table

The parser builds a lookup table mapping MIDI messages to Rekordbox functions:

```
Key Format: "{msg_type}:{channel}:{data1}"

Examples:
  "note_on:0:11"      → PlayPause (Deck 1)
  "control_change:6:8" → MasterLevel
```

## Dependencies

- **mido**: MIDI I/O library
- **click**: CLI framework
- **pathlib**: File path handling (stdlib)
- **csv**: CSV parsing (stdlib)
