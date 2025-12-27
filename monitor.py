"""
Rekordbox MIDI Sniffer

Real-time MIDI monitoring with Rekordbox function name display.
"""

import sys
import time
import re
import mido
import click
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List, Tuple

from parser import RekordboxCSVParser


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
        use_colors: bool = True,
        enable_grouping: bool = True,
        use_rgb_hex: bool = True
    ):
        self.csv_parser = csv_parser
        self.log_file = log_file
        self.show_hex = show_hex
        self.show_timestamp = show_timestamp
        self.full_row = full_row
        self.columns = columns
        self.use_colors = use_colors
        self.use_rgb_hex = use_rgb_hex
        self.log_handle = None
        self.header_printed = False

        # Message grouping state
        self.enable_grouping = enable_grouping
        self.current_group: Optional[Dict] = None  # Active grouped message
        self.group_count: int = 0  # Counter for grouped messages
        self.group_start_time: float = 0.0  # When the current group started
        self.group_window_ms: int = 500  # Group window in milliseconds

        if log_file:
            try:
                self.log_handle = open(log_file, 'w', encoding='utf-8')
                self._write_log_header()
            except Exception:
                if self.log_handle:
                    self.log_handle.close()
                    self.log_handle = None
                raise

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
            # Skip adding val=XX for control_change when grouping (we'll add it properly in _flush_group)
            skip_value = self.enable_grouping and msg.type == 'control_change'
            func_str_colored, func_str_plain = self._format_function(msg, skip_value=skip_value)

        parts_colored.append(func_str_colored)
        parts_plain.append(func_str_plain)

        return " | ".join(parts_colored), " | ".join(parts_plain)

    def _midi_to_rgb(self, status: int, data1: int, data2: int) -> Tuple[int, int, int]:
        """
        Convert MIDI bytes to RGB color with proper normalization

        Each byte is mapped to its full 0-255 range based on expected min/max values:
        - Status byte: 0x80-0xBF (128-191) for note/CC messages
        - Data1 (note/CC): 0-127
        - Data2 (velocity/value): 0-127

        Args:
            status: MIDI status byte (typically 128-191)
            data1: First data byte (0-127)
            data2: Second data byte (0-127)

        Returns:
            (R, G, B) tuple with values 0-255
        """
        # Define min/max ranges for each component
        status_min, status_max = 128, 191  # 0x80-0xBF range
        data_min, data_max = 0, 127

        # Normalize each component to 0-255 range
        def normalize(value, vmin, vmax):
            """Map value from [vmin, vmax] to [0, 255]"""
            if vmax == vmin:
                return 0
            normalized = (value - vmin) / (vmax - vmin)  # 0.0-1.0
            return int(normalized * 255)  # 0-255

        r = normalize(status, status_min, status_max)
        g = normalize(data1, data_min, data_max)
        b = normalize(data2, data_min, data_max)

        # Visibility boost: ensure minimum brightness for dark terminals
        min_brightness = 80  # Minimum total brightness
        total = r + g + b

        if total < min_brightness and total > 0:
            # Boost all components proportionally
            boost_factor = min_brightness / total
            r = min(255, int(r * boost_factor))
            g = min(255, int(g * boost_factor))
            b = min(255, int(b * boost_factor))

        return (r, g, b)

    def _format_hex_bytes(self, msg: mido.Message) -> Tuple[str, str]:
        """Format MIDI message as hex bytes with RGB or fixed coloring"""
        if msg.type in ['note_on', 'note_off']:
            status = (0x90 if msg.type == 'note_on' else 0x80) | msg.channel
            bytes_list = [f"{status:02X}", f"{msg.note:02X}", f"{msg.velocity:02X}"]

            if self.use_colors:
                if self.use_rgb_hex:
                    # Use RGB coloring based on the 3 hex bytes
                    r, g, b = self._midi_to_rgb(status, msg.note, msg.velocity)
                    rgb_color = f"\033[38;2;{r};{g};{b}m"
                    reset = "\033[0m"
                    colored = rgb_color + " ".join(bytes_list) + reset
                else:
                    # Use original fixed colors
                    status_colored = click.style(bytes_list[0], fg='cyan')
                    note_colored = click.style(bytes_list[1], fg='yellow')
                    vel_color = 'green' if msg.velocity > 0 else 'red'
                    vel_colored = click.style(bytes_list[2], fg=vel_color)
                    colored = f"{status_colored} {note_colored} {vel_colored}"
            else:
                colored = " ".join(bytes_list)

        elif msg.type == 'control_change':
            status = 0xB0 | msg.channel
            bytes_list = [f"{status:02X}", f"{msg.control:02X}", f"{msg.value:02X}"]

            if self.use_colors:
                if self.use_rgb_hex:
                    # Use RGB coloring based on the 3 hex bytes
                    r, g, b = self._midi_to_rgb(status, msg.control, msg.value)
                    rgb_color = f"\033[38;2;{r};{g};{b}m"
                    reset = "\033[0m"
                    colored = rgb_color + " ".join(bytes_list) + reset
                else:
                    # Use original fixed colors
                    status_colored = click.style(bytes_list[0], fg='cyan')
                    control_colored = click.style(bytes_list[1], fg='yellow')
                    value_colored = click.style(bytes_list[2], fg='bright_white')
                    colored = f"{status_colored} {control_colored} {value_colored}"
            else:
                colored = " ".join(bytes_list)

        else:
            plain = str(msg)
            return (click.style(plain, fg='bright_white', bold=True) if self.use_colors else plain), plain

        plain = " ".join(bytes_list)
        return colored, plain

    def _format_function(self, msg: mido.Message, skip_value: bool = False) -> Tuple[str, str]:
        """Format Rekordbox function name with details

        Args:
            skip_value: If True, don't include val=XX (for grouped messages)
        """
        if not self.csv_parser:
            raw = self._format_raw_message(msg)
            return (click.style(raw, fg='white', dim=True) if self.use_colors else raw), raw

        func_info = self.csv_parser.lookup_function(msg)

        if not func_info:
            raw = self._format_raw_message(msg)
            return (click.style(raw, fg='white', dim=True) if self.use_colors else raw), raw

        # Build function string parts
        parts_plain = []
        parts_colored = []

        # Function name - color based on control type category
        func_name = func_info['function']
        control_type = func_info.get('type', '')

        # Choose color based on control type category
        if control_type in ['Button']:
            func_color = 'bright_cyan'
        elif control_type in ['Rotary', 'KnobSlider', 'KnobSliderHiRes']:
            func_color = 'bright_magenta'
        elif control_type in ['Jog']:
            func_color = 'bright_yellow'
        else:
            func_color = 'bright_white'

        parts_plain.append(func_name)
        parts_colored.append(click.style(func_name, fg=func_color, bold=True) if self.use_colors else func_name)

        # Add comment if available (strip "(LSB)" suffix for cleaner display)
        comment = func_info.get('comment', '')
        if comment:
            # Remove "(LSB)" suffix - LSB messages are handled internally
            comment = comment.replace(' (LSB)', '').replace('(LSB)', '')
            if comment:
                comment_str = f"({comment})"
                parts_plain.append(comment_str)
                parts_colored.append(click.style(comment_str, fg='white', dim=True) if self.use_colors else comment_str)

        # Add control type in brackets
        if control_type:
            type_str = f"[{control_type}]"
            parts_plain.append(type_str)
            parts_colored.append(click.style(type_str, fg='blue') if self.use_colors else type_str)

        # Add RO (Read-Only/Status) indicator for feedback messages
        if func_info.get('is_readonly'):
            ro_str = "[Status]"
            parts_plain.append(ro_str)
            parts_colored.append(click.style(ro_str, fg='yellow', bold=True) if self.use_colors else ro_str)

        # Add press/release indicator for buttons
        if msg.type in ['note_on', 'note_off'] and control_type == 'Button':
            if msg.velocity > 0:
                press_str = "PRESS"
                parts_plain.append(press_str)
                parts_colored.append(click.style(press_str, fg='green', bold=True) if self.use_colors else press_str)
            else:
                release_str = "release"
                parts_plain.append(release_str)
                parts_colored.append(click.style(release_str, fg='red', dim=True) if self.use_colors else release_str)

        # Add value for CC messages (skip if requested, e.g., for grouped messages)
        if msg.type == 'control_change' and not skip_value:
            val_str = f"val={msg.value}"
            parts_plain.append(val_str)
            parts_colored.append(click.style(val_str, fg='bright_white') if self.use_colors else val_str)

        plain = " ".join(parts_plain)
        colored = " ".join(parts_colored)

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

        # For hi-res controls: check if this is an LSB message (skip printing)
        is_lsb_hires = False
        if self.csv_parser and msg.type == 'control_change' and 32 <= msg.control <= 63:
            func_info = self.csv_parser.lookup_function(msg)
            if func_info and func_info.get('type') == 'KnobSliderHiRes':
                is_lsb_hires = True

        colored, plain = self.format_message(msg, direction)

        # Non-grouped mode: print immediately (original behavior)
        if not self.enable_grouping:
            # Skip LSB messages entirely (even in non-grouped mode)
            if is_lsb_hires:
                return
            print(colored)
            if self.log_handle:
                self.log_handle.write(plain + "\n")
                self.log_handle.flush()
            return

        # Grouped mode with 500ms window
        now = time.time()

        # Check if current group window expired
        if self.current_group and (now - self.group_start_time) >= (self.group_window_ms / 1000):
            self._flush_group()

        # Check if message can be grouped with current group
        if self._should_group(msg, direction):
            # Add to current group
            self.group_count += 1
            self.current_group['msg'] = msg
            self.current_group['plain_output'] = plain
            self.current_group['colored_output'] = colored

            # Track MSB/LSB values for hi-res controls
            if msg.type == 'control_change':
                func_info = self.csv_parser.lookup_function(msg) if self.csv_parser else None
                if func_info and func_info.get('type') == 'KnobSliderHiRes':
                    norm_cc = msg.control if msg.control < 32 else msg.control - 32
                    if 'msb_values' not in self.current_group:
                        self.current_group['msb_values'] = {}
                    if 'lsb_values' not in self.current_group:
                        self.current_group['lsb_values'] = {}

                    if msg.control < 32:
                        self.current_group['msb_values'][norm_cc] = msg.value
                    else:
                        self.current_group['lsb_values'][norm_cc] = msg.value
        else:
            # Different message - flush current group and start new one
            self._flush_group()

            # Handle LSB messages - create pending group if none exists
            if is_lsb_hires:
                func_info = self.csv_parser.lookup_function(msg) if self.csv_parser else None
                if func_info and func_info.get('type') == 'KnobSliderHiRes':
                    norm_cc = msg.control if msg.control < 32 else msg.control - 32

                    # Create pending group for orphaned LSB (arrives before MSB)
                    if not self.current_group:
                        self.current_group = {
                            'msg': msg,
                            'func_info': func_info,
                            'direction': direction,
                            'plain_output': plain,
                            'colored_output': colored,
                            'msb_values': {},
                            'lsb_values': {}
                        }
                        self.group_count = 1
                        self.group_start_time = now

                    # Track the LSB value
                    if 'lsb_values' not in self.current_group:
                        self.current_group['lsb_values'] = {}
                    self.current_group['lsb_values'][norm_cc] = msg.value
                return

            # Start new group
            func_info = self.csv_parser.lookup_function(msg) if self.csv_parser else None
            self.current_group = {
                'msg': msg,
                'func_info': func_info,
                'direction': direction,
                'plain_output': plain,
                'colored_output': colored
            }
            self.group_count = 1
            self.group_start_time = now

    def monitor(self, input_port: mido.ports.BaseInput, direction: str = "IN"):
        """Monitor MIDI port in real-time"""
        try:
            for msg in input_port:
                self.print_message(msg, direction)
        except KeyboardInterrupt:
            pass
        finally:
            # Flush any pending group on exit
            self._flush_group()

    def close(self):
        """Close log file and flush pending groups"""
        self._flush_group()
        if self.log_handle:
            self.log_handle.close()

    def _value_to_color(self, value: int, min_val: int = 0, max_val: int = 127) -> str:
        """
        Map MIDI value to color gradient: green → cyan → blue → magenta → red

        Args:
            value: MIDI value (typically 0-127)
            min_val: Minimum value in range
            max_val: Maximum value in range

        Returns:
            Color name for click.style()
        """
        # Normalize to 0-1 range
        normalized = (value - min_val) / (max_val - min_val) if max_val > min_val else 0
        normalized = max(0.0, min(1.0, normalized))  # Clamp to 0-1

        # Map to color gradient (0=green, 1=red)
        if normalized < 0.2:  # 0-25: green (low)
            return 'green'
        elif normalized < 0.4:  # 26-51: cyan (low-mid)
            return 'cyan'
        elif normalized < 0.6:  # 52-76: blue (mid)
            return 'blue'
        elif normalized < 0.8:  # 77-102: magenta (mid-high)
            return 'magenta'
        else:  # 103-127: red (high)
            return 'red'

    def _should_group(self, msg: mido.Message, direction: str) -> bool:
        """
        Determine if message should be grouped with current group

        Grouping criteria:
        - Same function name
        - Same MIDI address (channel, data1)
        - Same control type
        - Same deck assignment
        - Same state for buttons (velocity for note_on/note_off)

        Returns:
            True if message can be grouped with current_group
        """
        if not self.enable_grouping or not self.current_group:
            return False

        if not self.csv_parser:
            return False

        func_info = self.csv_parser.lookup_function(msg)
        if not func_info:
            return False

        prev_msg = self.current_group['msg']
        prev_func = self.current_group['func_info']

        # If previous message wasn't recognized, can't group
        if not prev_func:
            return False

        # Must match: direction, function, type, deck, MIDI address, velocity (buttons only)
        if direction != self.current_group['direction']:
            return False
        if func_info['function'] != prev_func['function']:
            return False
        if func_info.get('type') != prev_func.get('type'):
            return False
        # NO jog wheel exclusion - jog wheels are the main use case!
        if func_info.get('deck') != prev_func.get('deck'):
            return False
        if msg.type != prev_msg.type or msg.channel != prev_msg.channel:
            return False

        if msg.type in ['note_on', 'note_off']:
            if msg.note != prev_msg.note or msg.velocity != prev_msg.velocity:
                return False
        elif msg.type == 'control_change':
            # Normalize LSB (CC 32-63) to MSB (CC 0-31) for hi-res controls
            # This allows MSB and LSB messages to group together
            curr_control = msg.control if msg.control < 32 else msg.control - 32
            prev_control = prev_msg.control if prev_msg.control < 32 else prev_msg.control - 32
            if curr_control != prev_control:
                return False

        return True

    def _flush_group(self):
        """
        Finalize current group and output it

        Called when:
        - New message doesn't match current group
        - Group window expires (500ms)
        - Monitoring stops (Ctrl+C, port close)
        """
        if not self.current_group or self.group_count == 0:
            return

        colored = self.current_group['colored_output']
        plain = self.current_group['plain_output']
        msg = self.current_group['msg']

        # For grouped messages OR control_change in grouped mode, add count and value
        if self.group_count > 1 or (self.enable_grouping and msg.type == 'control_change'):
            func_info = self.current_group.get('func_info')
            display_value = msg.value
            max_val = 127

            if func_info and func_info.get('type') == 'KnobSliderHiRes':
                norm_cc = msg.control if msg.control < 32 else msg.control - 32
                msb_val = self.current_group.get('msb_values', {}).get(norm_cc, 0)
                lsb_val = self.current_group.get('lsb_values', {}).get(norm_cc, 0)
                # Always show combined value for hi-res
                display_value = msb_val * 128 + lsb_val
                max_val = 16383

            # Build suffix: "(xNNN) val: XX" or just "val: XX" for single messages
            if self.group_count > 1:
                counter_text = f" (x{self.group_count})"
            else:
                counter_text = ""

            if msg.type == 'control_change':
                value_text = f" val: {display_value}"
                plain_suffix = counter_text + value_text

                if self.use_colors:
                    if counter_text:
                        counter_colored = click.style(counter_text, fg='white', dim=True)
                    else:
                        counter_colored = ""
                    value_color = self._value_to_color(display_value, 0, max_val)
                    value_colored = " val: " + click.style(str(display_value), fg=value_color, bold=True)
                    colored_suffix = counter_colored + value_colored
                else:
                    colored_suffix = plain_suffix
            else:
                # Non-CC messages (buttons, etc.) - just counter if grouped
                if counter_text:
                    colored_suffix = click.style(counter_text, fg='white', dim=True) if self.use_colors else counter_text
                    plain_suffix = counter_text
                else:
                    colored_suffix = ""
                    plain_suffix = ""

            colored = colored + colored_suffix
            plain = plain + plain_suffix

        # Print the grouped message
        print(colored)

        # Write to log file
        if self.log_handle:
            self.log_handle.write(plain + "\n")
            self.log_handle.flush()

        # Reset group state
        self.current_group = None
        self.group_count = 0
        self.group_start_time = 0.0


def scan_midi_ports() -> Tuple[List[str], List[str]]:
    """Scan and list all MIDI ports"""
    inputs = mido.get_input_names()
    outputs = mido.get_output_names()
    return inputs, outputs


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
