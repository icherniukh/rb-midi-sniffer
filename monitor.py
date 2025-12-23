"""
Rekordbox MIDI Sniffer

Real-time MIDI monitoring with Rekordbox function name display.
"""

import sys
import time
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
        enable_grouping: bool = True
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

        # Message grouping state
        self.enable_grouping = enable_grouping
        self.current_group: Optional[Dict] = None  # Active grouped message
        self.group_count: int = 0  # Counter for grouped messages
        self.last_output_length: int = 0  # Track line length for \r overwrites
        self.last_display_update: float = 0.0  # Timestamp for throttling updates
        self.display_throttle_ms: int = 250  # Throttle display updates (prevent flicker)

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
            func_str_colored, func_str_plain = self._format_function(msg)

        parts_colored.append(func_str_colored)
        parts_plain.append(func_str_plain)

        return " | ".join(parts_colored), " | ".join(parts_plain)

    def _format_hex_bytes(self, msg: mido.Message) -> Tuple[str, str]:
        """Format MIDI message as hex bytes with strategic coloring"""
        if msg.type in ['note_on', 'note_off']:
            status = (0x90 if msg.type == 'note_on' else 0x80) | msg.channel
            bytes_list = [f"{status:02X}", f"{msg.note:02X}", f"{msg.velocity:02X}"]
            # Color: status=cyan, note=yellow, velocity=green/red based on value
            if self.use_colors:
                vel_color = 'green' if msg.velocity > 0 else 'red'
                colored = (
                    click.style(bytes_list[0], fg='cyan') + " " +
                    click.style(bytes_list[1], fg='yellow') + " " +
                    click.style(bytes_list[2], fg=vel_color)
                )
            else:
                colored = " ".join(bytes_list)
        elif msg.type == 'control_change':
            status = 0xB0 | msg.channel
            bytes_list = [f"{status:02X}", f"{msg.control:02X}", f"{msg.value:02X}"]
            # Color: status=magenta, control=yellow, value=bright_white
            if self.use_colors:
                colored = (
                    click.style(bytes_list[0], fg='magenta') + " " +
                    click.style(bytes_list[1], fg='yellow') + " " +
                    click.style(bytes_list[2], fg='bright_white')
                )
            else:
                colored = " ".join(bytes_list)
        else:
            plain = str(msg)
            return (click.style(plain, fg='bright_white', bold=True) if self.use_colors else plain), plain

        plain = " ".join(bytes_list)
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

        # Add comment if available
        if func_info.get('comment'):
            comment_str = f"({func_info['comment']})"
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

        # Add value for CC messages
        if msg.type == 'control_change':
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

        colored, plain = self.format_message(msg, direction)

        # Non-grouped mode: print immediately (original behavior)
        if not self.enable_grouping:
            print(colored)
            if self.log_handle:
                self.log_handle.write(plain + "\n")
                self.log_handle.flush()
            return

        # Grouped mode: check if message can be grouped
        if self._should_group(msg, direction):
            # Increment counter for this group
            self.group_count += 1

            # Throttled display update (prevent jog wheel flicker)
            now = time.time()
            if now - self.last_display_update >= (self.display_throttle_ms / 1000):
                self._update_group_display()
                self.last_display_update = now
        else:
            # Flush previous group (if any)
            self._flush_group()

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
            self.last_display_update = time.time()

            # Display new group immediately
            self._update_group_display()

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

    def _update_group_display(self):
        """
        Update console with current group count (throttled to prevent flicker)

        Uses \\r (carriage return) to overwrite current line.
        Shows incrementing counter for grouped messages (e.g., "JogScratch x42")
        """
        if not self.current_group:
            return

        colored = self.current_group['colored_output']
        plain = self.current_group['plain_output']

        # Add counter suffix if > 1
        counter_suffix = ""
        if self.group_count > 1:
            counter_suffix = f" x{self.group_count}"
            if self.use_colors:
                colored += click.style(counter_suffix, fg='white', dim=True)
            else:
                colored += counter_suffix

        # Overwrite current line with \r
        # Use plain text length for accurate padding (colored has ANSI codes)
        output = f"\r{colored}"
        output_len = len(plain) + len(counter_suffix)

        if output_len < self.last_output_length:
            output += " " * (self.last_output_length - output_len)

        sys.stdout.write(output)
        sys.stdout.flush()

        self.last_output_length = output_len

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
            if msg.control != prev_msg.control:
                return False

        return True

    def _flush_group(self):
        """
        Finalize current group and write to log file

        Called when:
        - New message doesn't match current group
        - Monitoring stops (Ctrl+C, port close)
        """
        if not self.current_group or self.group_count == 0:
            return

        # Write grouped message to log file (once, with final counter)
        if self.log_handle:
            plain = self.current_group['plain_output']

            # Add counter suffix if > 1
            if self.group_count > 1:
                plain += f" x{self.group_count}"

            self.log_handle.write(plain + "\n")
            self.log_handle.flush()

        # Print newline to finalize console output
        if self.enable_grouping:
            sys.stdout.write("\n")
            sys.stdout.flush()

        # Reset group state
        self.current_group = None
        self.group_count = 0
        self.last_output_length = 0


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
