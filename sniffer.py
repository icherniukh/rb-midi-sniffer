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
"""

import sys
import mido
import csv
import click
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List, Tuple
from collections import defaultdict


class RekordboxCSVParser:
    """Parse Rekordbox MIDI Learn CSV files"""

    def __init__(self, csv_path: Path):
        self.csv_path = csv_path
        self.midi_to_function: Dict[str, Dict] = {}
        self.midi_to_csv_row: Dict[str, Dict] = {}  # Store full CSV rows
        self.controller_name = "Unknown"
        self.csv_headers: List[str] = []
        self._parse_csv()
        self._add_builtin_mappings()

    def _parse_csv(self):
        """
        Parse Rekordbox CSV format

        Format: #name,function,type,input,deck1,deck2,deck3,deck4,output,deck1,deck2,deck3,deck4,option,comment
        Column indices:
          0:#name, 1:function, 2:type, 3:input, 4-7:input_deck1-4, 8:output, 9-12:output_deck1-4, 13:option, 14:comment
        Example: PlayPause,PlayPause,Button,900B,0,1,2,3,900B,0,1,2,3,Fast;Priority=50;Dual,Play/Pause
        """
        with open(self.csv_path, 'r', encoding='utf-8') as f:
            # Extract controller name from first line (@file,1,DDJ-FLX10)
            f.seek(0)
            first_line = f.readline().strip()
            if first_line.startswith('@file'):
                parts = first_line.split(',')
                if len(parts) >= 3:
                    self.controller_name = parts[2]

            # Reset to read CSV properly
            f.seek(0)
            # Skip @file line
            f.readline()

            # Read header line to store headers
            header_line = f.readline().strip()
            self.csv_headers = header_line.split(',')

            # Read data rows using csv.reader (not DictReader) to handle duplicate column names
            reader = csv.reader(f)

            for cols in reader:
                if len(cols) < 15:
                    continue

                # Column indices: 0:#name, 1:function, 2:type, 3:input, 4-7:deck1-4, 8:output, 9-12:deck1-4, 13:option, 14:comment
                name = cols[0].strip()
                function_name = cols[1].strip()
                control_type = cols[2].strip()
                input_midi = cols[3].strip()
                input_deck_offsets = [cols[4].strip(), cols[5].strip(), cols[6].strip(), cols[7].strip()]
                output_midi = cols[8].strip()
                output_deck_offsets = [cols[9].strip(), cols[10].strip(), cols[11].strip(), cols[12].strip()]
                comment = cols[14].strip() if len(cols) > 14 else ''

                # Build row dict for CSV row storage
                row = dict(zip(self.csv_headers, cols))

                # Skip empty rows, section headers (lines starting with '# '), and comment lines
                if not name or name.startswith('# ') or name.startswith('#'):
                    continue

                # Use #name as fallback if function is empty
                if not function_name:
                    function_name = name

                # Parse input MIDI - two patterns:
                # 1. input has base MIDI + deck columns have channel offsets (e.g., B007 with 0,1,2,3)
                # 2. input is empty + deck columns have full MIDI bytes (e.g., empty with 9646,9647,9648,9649)
                if input_midi and not input_midi.startswith('#'):
                    self._add_midi_mapping(input_midi, function_name, control_type, comment, 'input', row, input_deck_offsets)
                elif not input_midi and any(input_deck_offsets):
                    # Deck columns contain full MIDI bytes, not offsets
                    for i, deck_midi in enumerate(input_deck_offsets):
                        if deck_midi and not deck_midi.startswith('#'):
                            self._add_midi_mapping_direct(deck_midi, function_name, control_type, comment, 'input', row, i + 1)

                # Parse output MIDI (LED feedback) - same two patterns
                if output_midi and not output_midi.startswith('#'):
                    self._add_midi_mapping(output_midi, function_name, control_type, comment, 'output', row, output_deck_offsets)
                elif not output_midi and any(output_deck_offsets):
                    # Deck columns contain full MIDI bytes, not offsets
                    for i, deck_midi in enumerate(output_deck_offsets):
                        if deck_midi and not deck_midi.startswith('#'):
                            self._add_midi_mapping_direct(deck_midi, function_name, control_type, comment, 'output', row, i + 1)

    def _add_midi_mapping(self, midi_str: str, function: str, control_type: str, comment: str, direction: str, csv_row: Dict, deck_offsets: List[str] = None):
        """
        Add MIDI mapping from CSV string

        Format examples:
        - Button: "900B" → status=0x90, data1=0x0B, channel=0
        - CC: "B640" → status=0xB6, data1=0x40, channel=6
        - Rotary: "B640" (similar to CC)

        Deck offsets (0,1,2,3) are added to the base channel to create
        mappings for all 4 decks.
        """
        if len(midi_str) < 4:
            return

        # Parse hex string (e.g., "900B" or "B640")
        try:
            status_byte = int(midi_str[:2], 16)
            data1_byte = int(midi_str[2:4], 16)

            # Extract message type and channel
            msg_type_nibble = (status_byte & 0xF0) >> 4
            base_channel = status_byte & 0x0F

            # Map to mido message types
            type_map = {
                0x8: 'note_off',
                0x9: 'note_on',
                0xB: 'control_change',
            }

            msg_type = type_map.get(msg_type_nibble)
            if not msg_type:
                return

            # Determine which channels to create mappings for
            channels_to_map = []
            if deck_offsets and any(deck_offsets):
                # Use deck offsets to create channel variants
                for i, offset_str in enumerate(deck_offsets):
                    if offset_str:
                        try:
                            offset = int(offset_str)
                            channels_to_map.append((base_channel + offset, i + 1))  # (channel, deck_num)
                        except ValueError:
                            pass
            else:
                # No deck offsets, just use base channel
                channels_to_map.append((base_channel, None))

            # Create mappings for each channel variant
            for channel, deck_num in channels_to_map:
                # Create key for lookup
                if msg_type in ['note_on', 'note_off']:
                    key = f"{msg_type}:{channel}:{data1_byte}"
                elif msg_type == 'control_change':
                    key = f"control_change:{channel}:{data1_byte}"
                else:
                    continue

                # Build comment with deck info
                full_comment = comment
                if deck_num:
                    full_comment = f"{comment} [Deck {deck_num}]" if comment else f"Deck {deck_num}"

                self.midi_to_function[key] = {
                    'function': function,
                    'type': control_type,
                    'comment': full_comment,
                    'direction': direction,
                    'channel': channel,
                    'data1': data1_byte,
                    'deck': deck_num,
                }

                # Store full CSV row
                self.midi_to_csv_row[key] = dict(csv_row)

        except (ValueError, IndexError):
            pass

    def _add_midi_mapping_direct(self, midi_str: str, function: str, control_type: str, comment: str, direction: str, csv_row: Dict, deck_num: int):
        """
        Add MIDI mapping from full MIDI hex string (no offsets)

        Used when deck columns contain complete MIDI addresses like "9646"
        instead of channel offsets like "0", "1", "2", "3".
        """
        if len(midi_str) < 4:
            return

        try:
            status_byte = int(midi_str[:2], 16)
            data1_byte = int(midi_str[2:4], 16)

            # Extract message type and channel
            msg_type_nibble = (status_byte & 0xF0) >> 4
            channel = status_byte & 0x0F

            # Map to mido message types
            type_map = {
                0x8: 'note_off',
                0x9: 'note_on',
                0xB: 'control_change',
            }

            msg_type = type_map.get(msg_type_nibble)
            if not msg_type:
                return

            # Create key for lookup
            if msg_type in ['note_on', 'note_off']:
                key = f"{msg_type}:{channel}:{data1_byte}"
            elif msg_type == 'control_change':
                key = f"control_change:{channel}:{data1_byte}"
            else:
                return

            # Build comment with deck info
            full_comment = f"{comment} [Deck {deck_num}]" if comment else f"Deck {deck_num}"

            self.midi_to_function[key] = {
                'function': function,
                'type': control_type,
                'comment': full_comment,
                'direction': direction,
                'channel': channel,
                'data1': data1_byte,
                'deck': deck_num,
            }

            # Store full CSV row
            self.midi_to_csv_row[key] = dict(csv_row)

        except (ValueError, IndexError):
            pass

    def _add_builtin_mappings(self):
        """
        Add built-in mappings for common controls not in CSV

        Some controllers don't include Master Level and Booth Level in their
        MIDI mapping CSV, but these controls do send MIDI and work in Rekordbox.

        Controller families use different channels/CCs:
        - DDJ controllers (GRV6, FLX10, 1000, 800, etc.): Channel 6, CC 8/9
        - XDJ all-in-ones (RX2, RX3, RR): Channel 4, CC 24/25
        - DJM mixers (A9, 900NXS2, etc.): Channel 0, CC 24/25
        """
        # Detect controller family from name
        name_upper = self.controller_name.upper()

        # XDJ all-in-one units use Channel 4
        if 'XDJ-RX' in name_upper or 'XDJ-RR' in name_upper or 'XDJ-XZ' in name_upper:
            builtin_controls = [
                (4, 24, 'MasterLevel', 'Master Level (built-in, XDJ)'),
                (4, 25, 'BoothLevel', 'Booth Level (built-in, XDJ)'),
            ]
        # DJM mixers use Channel 0
        elif 'DJM-' in name_upper or 'DJM ' in name_upper:
            builtin_controls = [
                (0, 24, 'MasterLevel', 'Master Level (built-in, DJM)'),
                (0, 25, 'BoothLevel', 'Booth Level (built-in, DJM)'),
            ]
        # DDJ controllers (default) use Channel 6
        else:
            builtin_controls = [
                (6, 8, 'MasterLevel', 'Master Level (built-in)'),
                (6, 9, 'BoothLevel', 'Booth Level (built-in)'),
            ]

        for channel, cc, function_name, comment in builtin_controls:
            key = f"control_change:{channel}:{cc}"
            # Only add if not already mapped by CSV
            if key not in self.midi_to_function:
                self.midi_to_function[key] = {
                    'function': function_name,
                    'type': 'KnobSliderHiRes',
                    'comment': comment,
                    'direction': 'input',
                    'channel': channel,
                    'data1': cc,
                    'deck': None,
                    'builtin': True,  # Flag to indicate built-in mapping
                }

    def lookup_function(self, msg: mido.Message) -> Optional[Dict]:
        """Look up Rekordbox function for MIDI message"""
        if msg.type in ['note_on', 'note_off']:
            key = f"{msg.type}:{msg.channel}:{msg.note}"
        elif msg.type == 'control_change':
            key = f"control_change:{msg.channel}:{msg.control}"
        else:
            return None

        result = self.midi_to_function.get(key)
        if result:
            return result

        # Check if this is an LSB for a 14-bit hi-res CC (CC 32-63 are LSBs for CC 0-31)
        if msg.type == 'control_change' and 32 <= msg.control <= 63:
            msb_cc = msg.control - 32
            msb_key = f"control_change:{msg.channel}:{msb_cc}"
            msb_info = self.midi_to_function.get(msb_key)
            if msb_info:
                # Return a modified copy indicating this is the LSB
                return {
                    **msb_info,
                    'comment': f"{msb_info.get('comment', '')} (LSB)".strip(),
                    'is_lsb': True,
                    'msb_cc': msb_cc,
                }

        return None

    def lookup_csv_row(self, msg: mido.Message) -> Optional[Dict]:
        """Look up full CSV row for MIDI message"""
        if msg.type in ['note_on', 'note_off']:
            key = f"{msg.type}:{msg.channel}:{msg.note}"
        elif msg.type == 'control_change':
            key = f"control_change:{msg.channel}:{msg.control}"
        else:
            return None

        return self.midi_to_csv_row.get(key)

    def get_headers(self) -> List[str]:
        """Get CSV headers"""
        return self.csv_headers


class RekordboxMIDISniffer:
    """Real-time MIDI sniffer for Rekordbox"""

    def __init__(
        self,
        csv_parser: Optional[RekordboxCSVParser] = None,
        log_file: Optional[Path] = None,
        show_hex: bool = True,
        show_timestamp: bool = True,
        full_row: bool = False,
        columns: Optional[List[str]] = None,
        use_colors: bool = True
    ):
        self.csv_parser = csv_parser
        self.log_file = log_file
        self.show_hex = show_hex
        self.show_timestamp = show_timestamp
        self.full_row = full_row
        self.columns = columns
        self.use_colors = use_colors
        self.log_handle = None
        self.header_printed = False

        if log_file:
            self.log_handle = open(log_file, 'w', encoding='utf-8')
            self._write_log_header()

    def _write_log_header(self):
        """Write log file header"""
        if not self.log_handle:
            return

        self.log_handle.write(f"Rekordbox MIDI Sniffer Log\n")
        self.log_handle.write(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        if self.csv_parser:
            self.log_handle.write(f"Controller: {self.csv_parser.controller_name}\n")
            self.log_handle.write(f"CSV: {self.csv_parser.csv_path}\n")
        self.log_handle.write(f"{'='*80}\n\n")
        self.log_handle.flush()

    def format_message(self, msg: mido.Message, direction: str = "IN") -> Tuple[str, str]:
        """
        Format MIDI message with hex bytes and function name

        Returns:
            Tuple of (colored_output, plain_output)
        """
        parts_colored = []
        parts_plain = []

        # Timestamp
        if self.show_timestamp:
            timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            ts_str = f"[{timestamp}]"
            parts_colored.append(click.style(ts_str, fg='white', dim=True) if self.use_colors else ts_str)
            parts_plain.append(ts_str)

        # Direction (IN/OUT)
        dir_str = f"{direction:3s}"
        if self.use_colors:
            color = 'green' if direction == 'IN' else 'yellow'
            parts_colored.append(click.style(dir_str, fg=color, bold=True))
        else:
            parts_colored.append(dir_str)
        parts_plain.append(dir_str)

        # Hex bytes with rainbow colors
        if self.show_hex:
            hex_colored, hex_plain = self._format_hex_bytes(msg)
            hex_str_colored = f"{hex_colored:12s}" if not self.use_colors else hex_colored
            hex_str_plain = f"{hex_plain:12s}"
            parts_colored.append(hex_str_colored)
            parts_plain.append(hex_str_plain)

        # Rekordbox function or CSV row
        if self.full_row and self.csv_parser:
            csv_row = self.csv_parser.lookup_csv_row(msg)
            if csv_row:
                func_str_colored, func_str_plain = self._format_csv_values(csv_row)
            else:
                raw = self._format_raw_message(msg)
                func_str_colored = click.style(raw, fg='white', dim=True) if self.use_colors else raw
                func_str_plain = raw
        else:
            func_str_colored, func_str_plain = self._format_function(msg)

        parts_colored.append(func_str_colored)
        parts_plain.append(func_str_plain)

        return " | ".join(parts_colored), " | ".join(parts_plain)

    def _format_hex_bytes(self, msg: mido.Message) -> Tuple[str, str]:
        """Format MIDI message as hex bytes"""
        if msg.type in ['note_on', 'note_off']:
            status = (0x90 if msg.type == 'note_on' else 0x80) | msg.channel
            bytes_list = [f"{status:02X}", f"{msg.note:02X}", f"{msg.velocity:02X}"]
        elif msg.type == 'control_change':
            status = 0xB0 | msg.channel
            bytes_list = [f"{status:02X}", f"{msg.control:02X}", f"{msg.value:02X}"]
        else:
            plain = str(msg)
            return (click.style(plain, fg='bright_white', bold=True) if self.use_colors else plain), plain

        plain = " ".join(bytes_list)
        colored = click.style(plain, fg='bright_white', bold=True) if self.use_colors else plain
        return colored, plain

    def _format_function(self, msg: mido.Message) -> Tuple[str, str]:
        """Format Rekordbox function name with details"""
        if not self.csv_parser:
            raw = self._format_raw_message(msg)
            return (click.style(raw, fg='white', dim=True) if self.use_colors else raw), raw

        func_info = self.csv_parser.lookup_function(msg)

        if not func_info:
            raw = self._format_raw_message(msg)
            return (click.style(raw, fg='white', dim=True) if self.use_colors else raw), raw

        # Build function string
        parts = [func_info['function']]

        # Add comment if available
        if func_info.get('comment'):
            parts.append(f"({func_info['comment']})")

        # Add control type
        if func_info.get('type'):
            parts.append(f"[{func_info['type']}]")

        # Add value for CC messages
        if msg.type == 'control_change':
            parts.append(f"val={msg.value}")

        plain = " ".join(parts)
        colored = click.style(plain, fg='bright_white', bold=True) if self.use_colors else plain

        return colored, plain

    def _format_csv_values(self, csv_row: Dict) -> Tuple[str, str]:
        """Format CSV row values with rainbow colors"""
        colors = ['red', 'yellow', 'green', 'cyan', 'blue', 'magenta', 'bright_red', 'bright_yellow',
                  'bright_green', 'bright_cyan', 'bright_blue', 'bright_magenta']
        if self.columns:
            display_cols = self.columns
        else:
            display_cols = self.csv_parser.get_headers() if self.csv_parser else []

        values_colored = []
        values_plain = []
        for i, col in enumerate(display_cols):
            value = csv_row.get(col, '')
            value_str = value if value else ''
            values_plain.append(value_str)
            if self.use_colors:
                values_colored.append(click.style(value_str, fg=colors[i % len(colors)]))
            else:
                values_colored.append(value_str)

        plain = ",".join(values_plain)
        colored = ",".join(values_colored)
        return colored, plain

    def _format_csv_header(self) -> Tuple[str, str]:
        """Format CSV header line (printed once at start)"""
        parts_colored = []
        parts_plain = []

        # Timestamp placeholder
        if self.show_timestamp:
            placeholder = "------------"
            parts_colored.append(click.style(placeholder, fg='white', dim=True) if self.use_colors else placeholder)
            parts_plain.append(placeholder)

        # Direction placeholder
        placeholder = "---"
        parts_colored.append(click.style(placeholder, fg='white', dim=True) if self.use_colors else placeholder)
        parts_plain.append(placeholder)

        # Hex bytes placeholder
        if self.show_hex:
            placeholder = "------------"
            parts_colored.append(click.style(placeholder, fg='white', dim=True) if self.use_colors else placeholder)
            parts_plain.append(placeholder)

        # CSV column headers (comma-separated)
        if self.columns:
            headers = self.columns
        else:
            headers = self.csv_parser.get_headers() if self.csv_parser else []

        headers_str = ",".join(headers)
        headers_colored = click.style(headers_str, fg='cyan', bold=True) if self.use_colors else headers_str

        parts_colored.append(headers_colored)
        parts_plain.append(headers_str)

        return " | ".join(parts_colored), " | ".join(parts_plain)

    def _format_raw_message(self, msg: mido.Message) -> str:
        """Format raw MIDI message (no CSV mapping)"""
        if msg.type in ['note_on', 'note_off']:
            return f"{msg.type.upper()} Ch:{msg.channel+1} Note:{msg.note} Vel:{msg.velocity}"
        elif msg.type == 'control_change':
            return f"CC Ch:{msg.channel+1} CC:{msg.control} Val:{msg.value}"
        else:
            return str(msg)

    def print_message(self, msg: mido.Message, direction: str = "IN"):
        """Print formatted message to console and log"""
        # Print CSV header once if in full_row mode
        if self.full_row and not self.header_printed and self.csv_parser:
            header_colored, header_plain = self._format_csv_header()
            print(header_colored)
            if self.log_handle:
                self.log_handle.write(header_plain + "\n")
                self.log_handle.flush()
            self.header_printed = True

        colored, plain = self.format_message(msg, direction)
        print(colored)

        if self.log_handle:
            self.log_handle.write(plain + "\n")
            self.log_handle.flush()

    def monitor(self, input_port: mido.ports.BaseInput, direction: str = "IN"):
        """Monitor MIDI port in real-time"""
        try:
            for msg in input_port:
                self.print_message(msg, direction)
        except KeyboardInterrupt:
            pass

    def close(self):
        """Close log file"""
        if self.log_handle:
            self.log_handle.close()


def scan_midi_ports() -> Tuple[List[str], List[str]]:
    """Scan and list all MIDI ports"""
    inputs = mido.get_input_names()
    outputs = mido.get_output_names()
    return inputs, outputs


def find_rekordbox_csv_files() -> List[Path]:
    """
    Find Rekordbox CSV files in common locations

    Search paths:
    - /Applications/rekordbox 7/rekordbox.app/Contents/Resources/MidiMappings/
    - ~/Library/Pioneer/rekordbox/
    - Current project docs/references/
    """
    search_paths = [
        Path("/Applications/rekordbox 7/rekordbox.app/Contents/Resources/MidiMappings"),
        Path.home() / "Library" / "Pioneer" / "rekordbox",
        Path(__file__).parent.parent / "docs" / "references",
    ]

    csv_files = []
    for search_path in search_paths:
        if search_path.exists():
            csv_files.extend(search_path.glob("**/*.csv"))

    return csv_files


def auto_match_port_to_csv(port_name: str, csv_files: List[Path]) -> Optional[Path]:
    """
    Auto-match MIDI port name to CSV file

    Matches port name like "DDJ-GRV6" to CSV file "DDJ-GRV6.midi.csv"
    Also handles variations like "PIONEER DDJ-GRV6" or "DDJ-GRV6 MIDI"

    Returns:
        Path to matched CSV file, or None if no match found
    """
    # Extract controller model from port name (remove common prefixes/suffixes)
    controller_model = port_name.upper()
    for prefix in ["PIONEER ", "PIONEER DJ ", "DJ "]:
        if controller_model.startswith(prefix):
            controller_model = controller_model[len(prefix):]
    for suffix in [" MIDI", " 2IN2OUT", " AUDIO"]:
        if controller_model.endswith(suffix):
            controller_model = controller_model[:-len(suffix)]

    controller_model = controller_model.strip()

    # Try to find exact match first
    for csv_file in csv_files:
        csv_name = csv_file.stem.upper()  # filename without extension

        # Remove .midi from double extension (.midi.csv)
        if csv_name.endswith('.MIDI'):
            csv_name = csv_name[:-5]

        # Try exact match
        if csv_name == controller_model:
            return csv_file

        # Try with common variations removed
        csv_model = csv_name
        for prefix in ["PIONEER ", "PIONEER DJ ", "DJ "]:
            if csv_model.startswith(prefix):
                csv_model = csv_model[len(prefix):]
        for suffix in [" MIDI", " 2IN2OUT"]:
            if csv_model.endswith(suffix):
                csv_model = csv_model[:-len(suffix)]

        if csv_model.strip() == controller_model:
            return csv_file

    # Try partial match (controller model is substring of CSV name)
    for csv_file in csv_files:
        csv_name = csv_file.stem.upper()
        if controller_model in csv_name or csv_name.replace(" MIDI", "").replace("PIONEER ", "") == controller_model:
            return csv_file

    return None


def parse_columns(columns_str: str, csv_parser: RekordboxCSVParser) -> List[str]:
    """
    Parse column specification (names or numbers)

    Examples:
        "1,2,3" -> first 3 columns by index
        "#name,function,type" -> columns by name
        "0,function,5" -> mix of index and name
    """
    if not columns_str:
        return []

    headers = csv_parser.get_headers()
    result = []

    for col_spec in columns_str.split(','):
        col_spec = col_spec.strip()

        # Try to parse as number (0-indexed)
        try:
            index = int(col_spec)
            if 0 <= index < len(headers):
                result.append(headers[index])
            else:
                click.echo(f"⚠️  Column index {index} out of range (0-{len(headers)-1})")
        except ValueError:
            # It's a column name
            if col_spec in headers:
                result.append(col_spec)
            else:
                click.echo(f"⚠️  Column '{col_spec}' not found in CSV")

    return result


# Click CLI
@click.group()
@click.version_option(version='1.0.0', prog_name='Rekordbox MIDI Sniffer')
def cli():
    """
    Rekordbox MIDI Sniffer

    Monitor MIDI communication between DDJ controllers and Rekordbox.
    Parse Rekordbox CSV files to display function names alongside MIDI messages.
    """
    pass


@cli.command()
@click.option('--csv', 'csv_path', type=click.Path(exists=True), help='Path to Rekordbox CSV file')
@click.option('-i', '--input', 'input_port', help='MIDI input port name')
@click.option('--output', 'output_port', help='MIDI output port name')
@click.option('-n', '--no-log', 'no_log', is_flag=True, help='Disable log file')
@click.option('-l', '--log-filename', 'log_filename', help='Custom log filename')
@click.option('--direction', type=click.Choice(['in', 'out', 'both']), default='in', help='Monitor direction (out/both not yet implemented)')
@click.option('-f', '--full-row', is_flag=True, help='Show full CSV row (all columns)')
@click.option('-c', '--columns', 'columns_str', help='Show specific columns (e.g., "function,type" or "0,1,14")')
@click.option('--no-colors', is_flag=True, help='Disable colors')
def monitor(csv_path, input_port, output_port, no_log, log_filename, direction, full_row, columns_str, no_colors):
    """
    Monitor MIDI messages in real-time

    Examples:

        # Auto-detect controller and CSV
        rekordbox-sniffer monitor

        # Specify port (-i/--input)
        rekordbox-sniffer monitor -i "DDJ-GRV6"

        # Show full CSV rows (-f/--full-row)
        rekordbox-sniffer monitor -f

        # Show specific columns (-c/--columns)
        rekordbox-sniffer monitor -c "function,type,comment"
        rekordbox-sniffer monitor -c "0,1,14"

        # Disable logging (-n/--no-log)
        rekordbox-sniffer monitor -n

        # Custom log file (-l/--log-filename)
        rekordbox-sniffer monitor -l "my_session.log"

        # Disable colors
        rekordbox-sniffer monitor --no-colors
    """
    # Check for mutually exclusive options
    if full_row and columns_str:
        click.echo(click.style("❌ --full-row and --columns are mutually exclusive. Use one or the other.", fg='red'))
        sys.exit(1)

    # Warn about unimplemented direction options
    if direction in ['out', 'both']:
        click.echo(click.style(f"⚠️  --direction={direction} is not yet implemented.", fg='yellow'))
        click.echo(click.style("   Output monitoring requires virtual MIDI routing.", fg='yellow'))
        click.echo(click.style("   Falling back to input-only monitoring.\n", fg='yellow'))
        direction = 'in'

    # Auto-detect MIDI port if not specified
    if not input_port:
        inputs, outputs = scan_midi_ports()
        if not inputs:
            click.echo(click.style("❌ No MIDI input ports found. Connect a controller and try again.", fg='red'))
            sys.exit(1)
        elif len(inputs) == 1:
            input_port = inputs[0]
            click.echo(click.style(f"🔍 Auto-detected controller: ", fg='cyan') + click.style(input_port, fg='bright_white', bold=True))
        else:
            click.echo(click.style("❌ Multiple MIDI ports found. Please specify one with --input:", fg='red'))
            for i, name in enumerate(inputs):
                click.echo(f"   [{i}] {name}")
            sys.exit(1)

    # Find all available CSV files
    csv_files = find_rekordbox_csv_files()

    # Parse CSV
    csv_parser = None
    if csv_path:
        # User specified CSV manually
        csv_parser = RekordboxCSVParser(Path(csv_path))
        click.echo(click.style("✅ Loaded CSV: ", fg='green') + click.style(csv_parser.controller_name, fg='bright_white', bold=True))
        click.echo(f"   Functions mapped: {len(csv_parser.midi_to_function)}")
    else:
        # Try to auto-match port to CSV
        if csv_files:
            matched_csv = auto_match_port_to_csv(input_port, csv_files)
            if matched_csv:
                csv_parser = RekordboxCSVParser(matched_csv)
                click.echo(click.style("✅ Auto-matched CSV: ", fg='green') + click.style(csv_parser.controller_name, fg='bright_white', bold=True))
                click.echo(f"   CSV: {matched_csv.name}")
                click.echo(f"   Functions mapped: {len(csv_parser.midi_to_function)}")
            else:
                click.echo(click.style(f"⚠️  No matching CSV found for '{input_port}'", fg='yellow'))
                click.echo(f"   Found {len(csv_files)} CSV files (use 'list-csv' command to see them)")
                click.echo(f"   Monitoring without function names\n")
        else:
            click.echo(click.style("⚠️  No CSV files found. Monitoring without function names", fg='yellow'))

    # Parse columns if specified
    columns = None
    if columns_str and csv_parser:
        columns = parse_columns(columns_str, csv_parser)
        if columns:
            click.echo(f"   Showing columns: {', '.join(columns)}")

    # Create log file
    log_file = None
    if not no_log:
        if log_filename:
            log_file = Path(log_filename)
        else:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            controller_name = input_port.replace(" ", "_").replace("/", "_")
            log_file = Path(f"rekordbox_midi_{controller_name}_{timestamp}.log")
        click.echo(f"📝 Logging to: {log_file}\n")

    # Create sniffer
    sniffer = RekordboxMIDISniffer(
        csv_parser=csv_parser,
        log_file=log_file,
        show_hex=True,
        show_timestamp=True,
        full_row=full_row,
        columns=columns,
        use_colors=not no_colors
    )

    try:
        click.echo(click.style(f"🎛️  Monitoring: ", fg='cyan') + click.style(input_port, fg='bright_white', bold=True))
        click.echo(click.style(f"   Press Ctrl+C to stop\n", fg='white', dim=True))
        click.echo("=" * 80)

        with mido.open_input(input_port) as port:
            sniffer.monitor(port, direction="IN")

    except KeyboardInterrupt:
        click.echo(click.style("\n\n✅ Stopped", fg='green'))
    except Exception as e:
        click.echo(click.style(f"\n❌ Error: {e}", fg='red'))
        sys.exit(1)
    finally:
        sniffer.close()


@cli.command(name='list-ports')
def list_ports():
    """List available MIDI ports"""
    inputs, outputs = scan_midi_ports()
    click.echo(click.style("\n=== MIDI Input Ports ===", fg='cyan', bold=True))
    if inputs:
        for i, name in enumerate(inputs):
            click.echo(f"  [{i}] {name}")
    else:
        click.echo(click.style("  (none)", fg='white', dim=True))

    click.echo(click.style("\n=== MIDI Output Ports ===", fg='cyan', bold=True))
    if outputs:
        for i, name in enumerate(outputs):
            click.echo(f"  [{i}] {name}")
    else:
        click.echo(click.style("  (none)", fg='white', dim=True))
    click.echo()


@cli.command(name='list-csv')
def list_csv():
    """List discovered Rekordbox CSV files"""
    csv_files = find_rekordbox_csv_files()
    click.echo(click.style("\n=== Discovered Rekordbox CSV Files ===", fg='cyan', bold=True))
    if csv_files:
        for csv_file in csv_files:
            click.echo(f"  {csv_file}")
    else:
        click.echo(click.style("  (none)", fg='white', dim=True))
    click.echo()


@cli.command(name='show-headers')
@click.option('--csv', 'csv_path', type=click.Path(exists=True), help='Path to Rekordbox CSV file')
@click.option('--input', 'input_port', help='MIDI input port name (for auto-matching CSV)')
def show_headers(csv_path, input_port):
    """
    Show CSV headers with assigned numbers

    Display all available column headers from the Rekordbox CSV file.
    Headers can be referenced by name or number when using --columns option.

    Examples:
        # Auto-detect CSV from connected controller
        rekordbox-sniffer show-headers

        # Show headers from specific CSV
        rekordbox-sniffer show-headers --csv /path/to/DDJ-GRV6.midi.csv
    """
    csv_parser = None

    if csv_path:
        # User specified CSV manually
        csv_parser = RekordboxCSVParser(Path(csv_path))
    else:
        # Try to auto-detect
        if not input_port:
            inputs, outputs = scan_midi_ports()
            if inputs and len(inputs) == 1:
                input_port = inputs[0]
            elif inputs:
                click.echo(click.style("❌ Multiple MIDI ports found. Please specify one with --input:", fg='red'))
                for i, name in enumerate(inputs):
                    click.echo(f"   [{i}] {name}")
                sys.exit(1)
            else:
                click.echo(click.style("❌ No MIDI ports found. Please specify CSV with --csv", fg='red'))
                sys.exit(1)

        # Auto-match CSV
        csv_files = find_rekordbox_csv_files()
        if csv_files:
            matched_csv = auto_match_port_to_csv(input_port, csv_files)
            if matched_csv:
                csv_parser = RekordboxCSVParser(matched_csv)
            else:
                click.echo(click.style(f"❌ No matching CSV found for '{input_port}'", fg='red'))
                sys.exit(1)
        else:
            click.echo(click.style("❌ No CSV files found", fg='red'))
            sys.exit(1)

    if not csv_parser:
        click.echo(click.style("❌ Could not load CSV file", fg='red'))
        sys.exit(1)

    # Display headers
    headers = csv_parser.get_headers()
    click.echo(click.style(f"\n=== CSV Headers for {csv_parser.controller_name} ===", fg='cyan', bold=True))
    click.echo(click.style(f"CSV: {csv_parser.csv_path}", fg='white', dim=True))
    click.echo()

    for i, header in enumerate(headers):
        # Highlight special columns
        if header in ['#name', 'function', 'type', 'input', 'output', 'comment']:
            header_display = click.style(f"[{i}]", fg='cyan') + " " + click.style(header, fg='bright_white', bold=True)
        else:
            header_display = click.style(f"[{i}]", fg='cyan') + f" {header}"
        click.echo(f"  {header_display}")

    click.echo(click.style(f"\nTotal: {len(headers)} columns", fg='white', dim=True))
    click.echo(click.style("\nUsage:", fg='yellow'))
    click.echo("  rekordbox-sniffer monitor --columns \"0,1,function,type\"")
    click.echo("  rekordbox-sniffer monitor --columns \"#name,function,comment\"")
    click.echo()


def parse_hex_to_midi(hex_str: str) -> Optional[mido.Message]:
    """
    Parse hex bytes string to mido Message

    Format: "B6 08 33" -> control_change channel=6 control=8 value=51
    """
    try:
        # Split hex string and convert to bytes
        hex_parts = hex_str.strip().split()
        if not hex_parts:
            return None

        bytes_list = [int(b, 16) for b in hex_parts]
        if not bytes_list:
            return None

        status = bytes_list[0]
        msg_type_nibble = (status & 0xF0) >> 4
        channel = status & 0x0F

        if msg_type_nibble == 0x9:  # Note On
            if len(bytes_list) >= 3:
                return mido.Message('note_on', channel=channel, note=bytes_list[1], velocity=bytes_list[2])
        elif msg_type_nibble == 0x8:  # Note Off
            if len(bytes_list) >= 3:
                return mido.Message('note_off', channel=channel, note=bytes_list[1], velocity=bytes_list[2])
        elif msg_type_nibble == 0xB:  # Control Change
            if len(bytes_list) >= 3:
                return mido.Message('control_change', channel=channel, control=bytes_list[1], value=bytes_list[2])

        return None
    except (ValueError, IndexError):
        return None


@cli.command()
@click.argument('logfile', type=click.Path(exists=True))
@click.option('--csv', 'csv_path', type=click.Path(exists=True), help='Path to Rekordbox CSV file')
@click.option('-f', '--full-row', is_flag=True, help='Show full CSV row (all columns)')
@click.option('-c', '--columns', 'columns_str', help='Show specific columns (e.g., "function,type" or "0,1,14")')
@click.option('--no-colors', is_flag=True, help='Disable colors')
@click.option('--speed', type=float, default=0.0, help='Playback speed multiplier (0=instant, 1=realtime)')
def replay(logfile, csv_path, full_row, columns_str, no_colors, speed):
    """
    Replay a MIDI log file with function names

    Parse a previously captured log file and display MIDI messages
    with Rekordbox function names. Useful for analyzing captured sessions.

    Examples:

        # Replay with auto-detected CSV
        rekordbox-sniffer replay session.log

        # Replay with specific CSV
        rekordbox-sniffer replay session.log --csv DDJ-GRV6.midi.csv

        # Show full CSV rows
        rekordbox-sniffer replay session.log -f

        # Realtime playback (with original timing)
        rekordbox-sniffer replay session.log --speed 1

        # Fast playback (2x speed)
        rekordbox-sniffer replay session.log --speed 0.5
    """
    import re
    import time

    # Check for mutually exclusive options
    if full_row and columns_str:
        click.echo(click.style("❌ --full-row and --columns are mutually exclusive.", fg='red'))
        sys.exit(1)

    log_path = Path(logfile)

    # Try to extract controller name from log file
    controller_name = None
    with open(log_path, 'r') as f:
        for line in f:
            if line.startswith('Controller:'):
                controller_name = line.split(':', 1)[1].strip()
                break
            if line.startswith('==='):
                break

    # Find CSV
    csv_parser = None
    if csv_path:
        csv_parser = RekordboxCSVParser(Path(csv_path))
        click.echo(click.style("✅ Loaded CSV: ", fg='green') + click.style(csv_parser.controller_name, fg='bright_white', bold=True))
    elif controller_name:
        csv_files = find_rekordbox_csv_files()
        if csv_files:
            matched_csv = auto_match_port_to_csv(controller_name, csv_files)
            if matched_csv:
                csv_parser = RekordboxCSVParser(matched_csv)
                click.echo(click.style("✅ Auto-matched CSV: ", fg='green') + click.style(csv_parser.controller_name, fg='bright_white', bold=True))

    if csv_parser:
        click.echo(f"   Functions mapped: {len(csv_parser.midi_to_function)}")
    else:
        click.echo(click.style("⚠️  No CSV loaded. Showing raw MIDI only.", fg='yellow'))

    # Parse columns if specified
    columns = None
    if columns_str and csv_parser:
        columns = parse_columns(columns_str, csv_parser)
        if columns:
            click.echo(f"   Showing columns: {', '.join(columns)}")

    # Create sniffer (no log file for replay)
    sniffer = RekordboxMIDISniffer(
        csv_parser=csv_parser,
        log_file=None,
        show_hex=True,
        show_timestamp=True,
        full_row=full_row,
        columns=columns,
        use_colors=not no_colors
    )

    click.echo(click.style(f"\n🔄 Replaying: ", fg='cyan') + click.style(str(log_path), fg='bright_white', bold=True))
    if speed > 0:
        click.echo(click.style(f"   Speed: {speed}x realtime", fg='white', dim=True))
    click.echo("=" * 80)

    # Parse log file format: [timestamp] | direction | hex_bytes | raw_message
    # Example: [23:02:07.155] | IN  | B6 08 33     | CC Ch:7 CC:8 Val:51
    log_pattern = re.compile(r'\[([^\]]+)\]\s*\|\s*(IN|OUT)\s*\|\s*([A-F0-9 ]+)\s*\|')

    message_count = 0
    last_timestamp = None

    try:
        with open(log_path, 'r') as f:
            for line in f:
                match = log_pattern.match(line)
                if not match:
                    continue

                timestamp_str, direction, hex_bytes = match.groups()

                # Handle timing for realtime playback
                if speed > 0 and last_timestamp:
                    try:
                        # Parse timestamps like "23:02:07.155"
                        current_parts = timestamp_str.split(':')
                        if len(current_parts) >= 3:
                            current_secs = float(current_parts[0]) * 3600 + float(current_parts[1]) * 60 + float(current_parts[2])
                            last_parts = last_timestamp.split(':')
                            last_secs = float(last_parts[0]) * 3600 + float(last_parts[1]) * 60 + float(last_parts[2])
                            delay = (current_secs - last_secs) / speed
                            if 0 < delay < 10:  # Cap at 10 seconds
                                time.sleep(delay)
                    except (ValueError, IndexError):
                        pass

                last_timestamp = timestamp_str

                # Parse hex to MIDI message
                msg = parse_hex_to_midi(hex_bytes)
                if msg:
                    sniffer.print_message(msg, direction)
                    message_count += 1

    except KeyboardInterrupt:
        click.echo(click.style("\n\n⏹️  Stopped", fg='yellow'))

    click.echo(click.style(f"\n✅ Replayed {message_count} messages", fg='green'))


if __name__ == '__main__':
    cli()
