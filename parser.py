"""
Rekordbox CSV Parser

Parse Rekordbox MIDI Learn CSV files to build MIDI → function lookup tables.
"""

import csv
import mido
from pathlib import Path
from typing import Optional, Dict, List


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
                option = cols[13].strip() if len(cols) > 13 else ''
                comment = cols[14].strip() if len(cols) > 14 else ''

                # Parse options (semicolon-separated: Fast;Priority=50;Dual;RO)
                options = {}
                if option:
                    for opt in option.split(';'):
                        opt = opt.strip()
                        if '=' in opt:
                            key, val = opt.split('=', 1)
                            options[key.strip()] = val.strip()
                        elif opt:
                            options[opt] = True
                is_readonly = 'RO' in options

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
                    self._add_midi_mapping(input_midi, function_name, control_type, comment, 'input', row, input_deck_offsets, is_readonly)
                elif not input_midi and any(input_deck_offsets):
                    # Deck columns contain full MIDI bytes, not offsets
                    for i, deck_midi in enumerate(input_deck_offsets):
                        if deck_midi and not deck_midi.startswith('#'):
                            self._add_midi_mapping_direct(deck_midi, function_name, control_type, comment, 'input', row, i + 1, is_readonly)

                # Parse output MIDI (LED feedback) - same two patterns
                if output_midi and not output_midi.startswith('#'):
                    self._add_midi_mapping(output_midi, function_name, control_type, comment, 'output', row, output_deck_offsets, is_readonly)
                elif not output_midi and any(output_deck_offsets):
                    # Deck columns contain full MIDI bytes, not offsets
                    for i, deck_midi in enumerate(output_deck_offsets):
                        if deck_midi and not deck_midi.startswith('#'):
                            self._add_midi_mapping_direct(deck_midi, function_name, control_type, comment, 'output', row, i + 1, is_readonly)

    def _add_midi_mapping(self, midi_str: str, function: str, control_type: str, comment: str, direction: str, csv_row: Dict, deck_offsets: List[str] = None, is_readonly: bool = False):
        """
        Add MIDI mapping from CSV string

        Format examples:
        - Button: "900B" → status=0x90, data1=0x0B, channel=0
        - CC: "B640" → status=0xB6, data1=0x40, channel=6
        - Rotary: "B640" (similar to CC)

        Deck offsets (0,1,2,3) are added to the base channel to create
        mappings for all 4 decks.

        Args:
            is_readonly: If True, this is a status/feedback message (RO option in CSV)
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
                            channel = base_channel + offset
                            # Validate channel is within MIDI spec (0-15)
                            if 0 <= channel <= 15:
                                channels_to_map.append((channel, i + 1))  # (channel, deck_num)
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
                    'is_readonly': is_readonly,
                }

                # Store full CSV row
                self.midi_to_csv_row[key] = dict(csv_row)

        except (ValueError, IndexError):
            pass

    def _add_midi_mapping_direct(self, midi_str: str, function: str, control_type: str, comment: str, direction: str, csv_row: Dict, deck_num: int, is_readonly: bool = False):
        """
        Add MIDI mapping from full MIDI hex string (no offsets)

        Used when deck columns contain complete MIDI addresses like "9646"
        instead of channel offsets like "0", "1", "2", "3".

        Args:
            is_readonly: If True, this is a status/feedback message (RO option in CSV)
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
                'is_readonly': is_readonly,
            }

            # Store full CSV row
            self.midi_to_csv_row[key] = dict(csv_row)

        except (ValueError, IndexError):
            pass

    def _add_builtin_mappings(self):
        """
        Add built-in mappings for common controls not in CSV

        Some controllers don't include hardware mixer controls (Master/Booth Level,
        Headphones, Mic, etc.) in their MIDI mapping CSV, but these controls do
        send MIDI and work in Rekordbox.

        Controller families use different channels/CCs:
        - DDJ controllers: Channel 6 (confirmed on DDJ-GRV6, may vary on other models)
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
                (6, 5, 'MicLevel', 'Mic Level (built-in)'),
                (6, 8, 'MasterLevel', 'Master Level (built-in)'),
                (6, 9, 'BoothLevel', 'Booth Level (built-in)'),
                (6, 12, 'CueMasterMix', 'Cue/Master Mix (built-in)'),
                (6, 13, 'HeadphonesLevel', 'Headphones Level (built-in)'),
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


def find_rekordbox_csv_files() -> List[Path]:
    """
    Find Rekordbox CSV files in common locations

    Search paths:
    - /Applications/rekordbox 7/rekordbox.app/Contents/Resources/MidiMappings/
    - ~/Library/Pioneer/rekordbox/
    - Project references/ directory
    """
    search_paths = [
        Path("/Applications/rekordbox 7/rekordbox.app/Contents/Resources/MidiMappings"),
        Path.home() / "Library" / "Pioneer" / "rekordbox",
        Path(__file__).parent / "references",
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
    import click

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
                click.echo(f"Warning: Column index {index} out of range (0-{len(headers)-1})")
        except ValueError:
            # It's a column name
            if col_spec in headers:
                result.append(col_spec)
            else:
                click.echo(f"Warning: Column '{col_spec}' not found in CSV")

    return result
