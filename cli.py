"""
Rekordbox MIDI Sniffer CLI

Command-line interface for MIDI monitoring and CSV inspection.
"""

import sys
import re
import time
import mido
import click
from pathlib import Path
from datetime import datetime

from parser import (
    RekordboxCSVParser,
    find_rekordbox_csv_files,
    auto_match_port_to_csv,
    parse_columns,
)
from monitor import (
    RekordboxMIDISniffer,
    scan_midi_ports,
    parse_hex_to_midi,
)


# Replay speed limits
# Maximum playback speed multiplier - prevents excessive CPU usage while still allowing
# reasonable fast-forward (10x realtime is sufficient for most log analysis)
MAX_REPLAY_SPEED = 10.0


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
@click.pass_context
def help(ctx):
    """Show help information"""
    click.echo(ctx.parent.get_help())


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
@click.option('--no-grouping', is_flag=True, help='Disable message grouping for jog wheels and repeated actions')
@click.option('--no-rgbmidi', is_flag=True, help='Disable RGB hex coloring (use fixed colors instead)')
def monitor(csv_path, input_port, output_port, no_log, log_filename, direction, full_row, columns_str, no_colors, no_grouping, no_rgbmidi):
    """
    Monitor MIDI messages in real-time

    Examples:

        # Auto-detect controller and CSV
        python sniffer.py monitor

        # Specify port (-i/--input)
        python sniffer.py monitor -i "DDJ-GRV6"

        # Show full CSV rows (-f/--full-row)
        python sniffer.py monitor -f

        # Show specific columns (-c/--columns)
        python sniffer.py monitor -c "function,type,comment"
        python sniffer.py monitor -c "0,1,14"

        # Disable logging (-n/--no-log)
        python sniffer.py monitor -n

        # Custom log file (-l/--log-filename)
        python sniffer.py monitor -l "my_session.log"

        # Disable colors
        python sniffer.py monitor --no-colors
    """
    # Check for mutually exclusive options
    if full_row and columns_str:
        click.echo(click.style("Error: --full-row and --columns are mutually exclusive. Use one or the other.", fg='red'))
        sys.exit(1)

    # Warn about unimplemented direction options
    if direction in ['out', 'both']:
        click.echo(click.style(f"Warning: --direction={direction} is not yet implemented.", fg='yellow'))
        click.echo(click.style("   Output monitoring requires virtual MIDI routing.", fg='yellow'))
        click.echo(click.style("   Falling back to input-only monitoring.\n", fg='yellow'))
        direction = 'in'

    # Auto-detect MIDI port if not specified
    if not input_port:
        inputs, outputs = scan_midi_ports()
        if not inputs:
            click.echo(click.style("Error: No MIDI input ports found. Connect a controller and try again.", fg='red'))
            sys.exit(1)
        elif len(inputs) == 1:
            input_port = inputs[0]
            click.echo(click.style(f"Auto-detected controller: ", fg='cyan') + click.style(input_port, fg='bright_white', bold=True))
        else:
            click.echo(click.style("Error: Multiple MIDI ports found. Please specify one with --input:", fg='red'))
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
        click.echo(click.style("Loaded CSV: ", fg='green') + click.style(csv_parser.controller_name, fg='bright_white', bold=True))
        click.echo(f"   Functions mapped: {len(csv_parser.midi_to_function)}")
    else:
        # Try to auto-match port to CSV
        if csv_files:
            matched_csv = auto_match_port_to_csv(input_port, csv_files)
            if matched_csv:
                csv_parser = RekordboxCSVParser(matched_csv)
                click.echo(click.style("Auto-matched CSV: ", fg='green') + click.style(csv_parser.controller_name, fg='bright_white', bold=True))
                click.echo(f"   CSV: {matched_csv.name}")
                click.echo(f"   Functions mapped: {len(csv_parser.midi_to_function)}")
            else:
                click.echo(click.style(f"Warning: No matching CSV found for '{input_port}'", fg='yellow'))
                click.echo(f"   Found {len(csv_files)} CSV files (use 'list-csv' command to see them)")
                click.echo(f"   Monitoring without function names\n")
        else:
            click.echo(click.style("Warning: No CSV files found. Monitoring without function names", fg='yellow'))

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
        click.echo(f"Logging to: {log_file}\n")

    # Create sniffer
    sniffer = RekordboxMIDISniffer(
        csv_parser=csv_parser,
        log_file=log_file,
        show_hex=True,
        show_timestamp=True,
        full_row=full_row,
        columns=columns,
        use_colors=not no_colors,
        enable_grouping=not no_grouping,
        use_rgb_hex=not no_rgbmidi
    )

    try:
        click.echo(click.style(f"Monitoring: ", fg='cyan') + click.style(input_port, fg='bright_white', bold=True))
        click.echo(click.style(f"   Press Ctrl+C to stop\n", fg='white', dim=True))
        click.echo("=" * 80)

        # Try IOPort first (bidirectional), fall back to input-only
        # NOTE: IOPort iteration only yields received messages, not sent
        # TODO: Implement OUT monitoring via virtual MIDI or threading
        port = None
        try:
            port = mido.open_ioport(input_port)
            click.echo(click.style("Port mode: Bidirectional port opened", fg='green'))
            click.echo(click.style("   Note: OUT monitoring requires virtual MIDI routing (see docs)", fg='white', dim=True))
        except (OSError, IOError):
            try:
                port = mido.open_input(input_port)
                click.echo(click.style("Port mode: Input-only", fg='yellow'))
                click.echo(click.style("   Tip: For OUT monitoring, setup virtual MIDI routing", fg='white', dim=True))
            except Exception as fallback_error:
                click.echo(click.style(f"Error: Cannot open MIDI port: {fallback_error}", fg='red'))
                sys.exit(1)

        try:
            sniffer.monitor(port, direction="IN")
        finally:
            sniffer._flush_group()  # Finalize any active group
            if port:
                port.close()

    except KeyboardInterrupt:
        click.echo(click.style("\n\nStopped", fg='green'))
    except Exception as e:
        click.echo(click.style(f"\nError: {e}", fg='red'))
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
        python sniffer.py show-headers

        # Show headers from specific CSV
        python sniffer.py show-headers --csv /path/to/DDJ-GRV6.midi.csv
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
                click.echo(click.style("Error: Multiple MIDI ports found. Please specify one with --input:", fg='red'))
                for i, name in enumerate(inputs):
                    click.echo(f"   [{i}] {name}")
                sys.exit(1)
            else:
                click.echo(click.style("Error: No MIDI ports found. Please specify CSV with --csv", fg='red'))
                sys.exit(1)

        # Auto-match CSV
        csv_files = find_rekordbox_csv_files()
        if csv_files:
            matched_csv = auto_match_port_to_csv(input_port, csv_files)
            if matched_csv:
                csv_parser = RekordboxCSVParser(matched_csv)
            else:
                click.echo(click.style(f"Error: No matching CSV found for '{input_port}'", fg='red'))
                sys.exit(1)
        else:
            click.echo(click.style("Error: No CSV files found", fg='red'))
            sys.exit(1)

    if not csv_parser:
        click.echo(click.style("Error: Could not load CSV file", fg='red'))
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
    click.echo("  python sniffer.py monitor --columns \"0,1,function,type\"")
    click.echo("  python sniffer.py monitor --columns \"#name,function,comment\"")
    click.echo()


@cli.command()
@click.argument('logfile', type=click.Path(exists=True))
@click.option('--csv', 'csv_path', type=click.Path(exists=True), help='Path to Rekordbox CSV file')
@click.option('-f', '--full-row', is_flag=True, help='Show full CSV row (all columns)')
@click.option('-c', '--columns', 'columns_str', help='Show specific columns (e.g., "function,type" or "0,1,14")')
@click.option('--no-colors', is_flag=True, help='Disable colors')
@click.option('--no-grouping', is_flag=True, help='Disable message grouping for jog wheels and repeated actions')
@click.option('--no-rgbmidi', is_flag=True, help='Disable RGB hex coloring (use fixed colors instead)')
@click.option('--speed', type=click.FloatRange(min=0.0, max=MAX_REPLAY_SPEED), default=0.0, help=f'Playback speed multiplier (0=instant, 1=realtime, max={MAX_REPLAY_SPEED:.0f})')
def replay(logfile, csv_path, full_row, columns_str, no_colors, no_grouping, no_rgbmidi, speed):
    """
    Replay a MIDI log file with function names

    Parse a previously captured log file and display MIDI messages
    with Rekordbox function names. Useful for analyzing captured sessions.

    Examples:

        # Replay with auto-detected CSV
        python sniffer.py replay session.log

        # Replay with specific CSV
        python sniffer.py replay session.log --csv DDJ-GRV6.midi.csv

        # Show full CSV rows
        python sniffer.py replay session.log -f

        # Realtime playback (with original timing)
        python sniffer.py replay session.log --speed 1

        # Fast playback (2x speed)
        python sniffer.py replay session.log --speed 0.5
    """
    # Check for mutually exclusive options
    if full_row and columns_str:
        click.echo(click.style("Error: --full-row and --columns are mutually exclusive.", fg='red'))
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
        click.echo(click.style("Loaded CSV: ", fg='green') + click.style(csv_parser.controller_name, fg='bright_white', bold=True))
    elif controller_name:
        csv_files = find_rekordbox_csv_files()
        if csv_files:
            matched_csv = auto_match_port_to_csv(controller_name, csv_files)
            if matched_csv:
                csv_parser = RekordboxCSVParser(matched_csv)
                click.echo(click.style("Auto-matched CSV: ", fg='green') + click.style(csv_parser.controller_name, fg='bright_white', bold=True))

    if csv_parser:
        click.echo(f"   Functions mapped: {len(csv_parser.midi_to_function)}")
    else:
        click.echo(click.style("Warning: No CSV loaded. Showing raw MIDI only.", fg='yellow'))

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
        use_colors=not no_colors,
        enable_grouping=not no_grouping,
        use_rgb_hex=not no_rgbmidi
    )

    click.echo(click.style(f"\nReplaying: ", fg='cyan') + click.style(str(log_path), fg='bright_white', bold=True))
    if speed > 0:
        click.echo(click.style(f"   Speed: {speed}x realtime", fg='white', dim=True))
    click.echo("=" * 80)

    # Parse log file format: [timestamp] | direction | hex_bytes | raw_message
    # Example: [23:02:07.155] | IN  | B6 08 33     | CC Ch:7 CC:8 Val:51
    log_pattern = re.compile(r'\[([^\]]+)\]\s*\|\s*(IN|OUT)\s*\|\s*([A-Fa-f0-9 ]+)\s*\|')

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
        click.echo(click.style("\n\nStopped", fg='yellow'))
    finally:
        sniffer._flush_group()  # Finalize any active group

    click.echo(click.style(f"\nReplayed {message_count} messages", fg='green'))


@cli.command('test')
@click.option('--duration', 'duration', type=int, default=10, help='Test duration in seconds')
@click.option('--csv', 'csv_path', type=click.Path(exists=True), help='Path to Rekordbox CSV file')
@click.option('--no-colors', is_flag=True, help='Disable colors')
@click.option('--no-grouping', is_flag=True, help='Disable message grouping')
@click.option('--no-rgbmidi', is_flag=True, help='Disable RGB hex coloring')
@click.option('--direct', is_flag=True, help='Use direct message injection (no virtual port needed)')
def test_command(duration, csv_path, no_colors, no_grouping, no_rgbmidi, direct):
    """
    Run virtual controller test (emulates DDJ controller without hardware)

    Creates a virtual MIDI port and sends test messages, or uses direct injection
    if virtual ports aren't available. Useful for testing without actual hardware.

    Examples:

        # Run 10 second test with auto-detected CSV
        python sniffer.py test

        # Run 30 second test
        python sniffer.py test --duration 30

        # Test with specific CSV
        python sniffer.py test --csv DDJ-FLX10.midi.csv

        # Force direct injection mode (no virtual port)
        python sniffer.py test --direct
    """
    # Try to load CSV
    csv_parser = None
    if csv_path:
        csv_parser = RekordboxCSVParser(Path(csv_path))
        click.echo(click.style("Loaded CSV: ", fg='green') + click.style(csv_parser.controller_name, fg='bright_white', bold=True))
    else:
        csv_files = find_rekordbox_csv_files()
        if csv_files:
            # Try to find a DDJ CSV
            for csv_file in csv_files:
                if 'DDJ' in csv_file.name.upper():
                    csv_parser = RekordboxCSVParser(csv_file)
                    click.echo(click.style("Auto-loaded CSV: ", fg='green') + click.style(csv_parser.controller_name, fg='bright_white', bold=True))
                    break

    if csv_parser:
        click.echo(f"   Functions mapped: {len(csv_parser.midi_to_function)}")
    else:
        click.echo(click.style("Warning: No CSV loaded. Showing raw MIDI only.", fg='yellow'))

    click.echo()
    click.echo(click.style("Creating virtual DDJ controller...", fg='cyan'))
    click.echo(click.style(f"Sending test messages for {duration} seconds...", fg='white', dim=True))
    click.echo(click.style("   Press Ctrl+C to stop early\n", fg='white', dim=True))
    click.echo("=" * 80)

    # Create virtual controller in a background thread
    import threading

    controller_thread = None
    try:
        # Create virtual controller
        virtual_controller = VirtualController()

        # Try virtual port mode first (unless --direct is specified)
        if not direct:
            try:
                # Start the controller in background thread
                def run_controller():
                    virtual_controller.run_test(duration, csv_parser)

                controller_thread = threading.Thread(target=run_controller, daemon=True)
                controller_thread.start()

                # Create sniffer to monitor the virtual port
                sniffer = RekordboxMIDISniffer(
                    csv_parser=csv_parser,
                    log_file=None,
                    show_hex=True,
                    show_timestamp=True,
                    full_row=False,
                    columns=None,
                    use_colors=not no_colors,
                    enable_grouping=not no_grouping,
                    use_rgb_hex=not no_rgbmidi
                )

                # Open the virtual port for input
                port_name = virtual_controller.get_port_name()
                port = mido.open_input(port_name)

                # Monitor
                sniffer.monitor(port, direction="IN")

            except KeyboardInterrupt:
                click.echo(click.style("\n\nTest stopped", fg='green'))
            except Exception as e:
                # Fall through to direct injection mode
                if "no ports available" in str(e).lower() or "virtual" in str(e).lower():
                    click.echo(click.style(f"\nVirtual port not available, switching to direct injection mode...", fg='yellow'))
                    direct = True
                else:
                    raise

        # Direct injection mode (fallback)
        if direct:
            _run_direct_injection_test(duration, csv_parser, not no_colors, not no_grouping, not no_rgbmidi)

    except KeyboardInterrupt:
        click.echo(click.style("\n\nTest stopped", fg='green'))
    except Exception as e:
        click.echo(click.style(f"\nError: {e}", fg='red'))
        click.echo(click.style("Note: Virtual ports require compatible mido backend.", fg='yellow'))
        click.echo(click.style("Try: pip install python-rtmidi or use --direct flag", fg='yellow'))
        sys.exit(1)
    finally:
        if controller_thread and controller_thread.is_alive():
            virtual_controller.stop()
        if 'port' in locals():
            port.close()


def _run_direct_injection_test(duration, csv_parser, use_colors, enable_grouping, use_rgb_hex):
    """
    Direct message injection mode - doesn't require virtual MIDI ports

    Creates mido.Message objects directly and passes them to the sniffer.
    """
    # Create sniffer
    sniffer = RekordboxMIDISniffer(
        csv_parser=csv_parser,
        log_file=None,
        show_hex=True,
        show_timestamp=True,
        full_row=False,
        columns=None,
        use_colors=use_colors,
        enable_grouping=enable_grouping,
        use_rgb_hex=use_rgb_hex
    )

    click.echo(click.style("[Direct Injection Mode]", fg='cyan', dim=True))
    click.echo("=" * 80)

    start_time = time.time()
    message_count = 0

    # Test message sequences
    test_messages = [
        # Play button press/release
        mido.Message('note_on', channel=0, note=0x0B, velocity=127),  # Press
        mido.Message('note_off', channel=0, note=0x0B, velocity=0),    # Release

        # Cue button
        mido.Message('note_on', channel=0, note=0x0C, velocity=127),
        mido.Message('note_off', channel=0, note=0x0C, velocity=0),

        # Sync button
        mido.Message('note_on', channel=0, note=0x0E, velocity=127),
        mido.Message('note_off', channel=0, note=0x0E, velocity=0),

        # Hot Cue 1
        mido.Message('note_on', channel=0, note=0x10, velocity=127),
        mido.Message('note_off', channel=0, note=0x10, velocity=0),

        # Hot Cue 2
        mido.Message('note_on', channel=0, note=0x11, velocity=127),
        mido.Message('note_off', channel=0, note=0x11, velocity=0),
    ]

    try:
        while (time.time() - start_time) < duration:
            # Send button sequences
            for msg in test_messages:
                if (time.time() - start_time) >= duration:
                    break
                sniffer.print_message(msg, direction="IN")
                message_count += 1
                time.sleep(0.1)

            # Send CC messages with varying values
            cc_params = [
                (4, 64),   # Gain knob
                (7, 100),  # High EQ
                (11, 50),  # Mid EQ
                (15, 75),  # Low EQ
                (19, 90),  # Channel Fader MSB
                (51, 45),  # Channel Fader LSB
            ]

            for cc, base_val in cc_params:
                if (time.time() - start_time) >= duration:
                    break
                val = (base_val + int((time.time() * 10) % 20)) % 128
                msg = mido.Message('control_change', channel=0, control=cc, value=val)
                sniffer.print_message(msg, direction="IN")
                message_count += 1
                time.sleep(0.05)

            time.sleep(0.5)

    except KeyboardInterrupt:
        pass
    finally:
        sniffer._flush_group()


class VirtualController:
    """
    Virtual DDJ controller for testing

    Creates a virtual MIDI port and sends test messages emulating
    common DDJ controller behavior.
    """

    def __init__(self, port_name="DDJ-Virtual Test"):
        self.port_name = port_name
        self.running = False
        self._port = None

    def get_port_name(self):
        return self.port_name

    def stop(self):
        self.running = False

    def run_test(self, duration, csv_parser):
        """Send test MIDI messages for specified duration"""
        self.running = True

        try:
            self._port = mido.open_output(self.port_name, virtual=True)
        except Exception as e:
            click.echo(click.style(f"Could not create virtual port: {e}", fg='red'))
            return

        start_time = time.time()
        message_count = 0

        # Test message sequences (status, data1, data2)
        # Emulating DDJ-FLX10/DDJ-GRV6 style messages on Channel 0
        test_sequences = [
            # Play button press/release
            [0x90, 0x0B, 0x7F],  # Note On, Ch 0, Note 11, Vel 127 (Press)
            [0x80, 0x0B, 0x00],  # Note Off, Ch 0, Note 11 (Release)

            # Cue button
            [0x90, 0x0C, 0x7F],  # Press
            [0x80, 0x0C, 0x00],  # Release

            # Sync button
            [0x90, 0x0E, 0x7F],  # Press
            [0x80, 0x0E, 0x00],  # Release

            # Hot Cue 1 (Pad)
            [0x90, 0x10, 0x7F],  # Press
            [0x80, 0x10, 0x00],  # Release

            # Hot Cue 2
            [0x90, 0x11, 0x7F],  # Press
            [0x80, 0x11, 0x00],  # Release
        ]

        # CC messages (knobs, faders)
        cc_messages = [
            (0xB0, 0x04, 64),   # Gain knob (Ch 0, CC 4, val 64)
            (0xB0, 0x07, 100),  # High EQ (Ch 0, CC 7)
            (0xB0, 0x0B, 50),   # Mid EQ (Ch 0, CC 11)
            (0xB0, 0x0F, 75),   # Low EQ (Ch 0, CC 15)
            (0xB0, 0x13, 90),   # Channel Fader MSB (Ch 0, CC 19)
            (0xB0, 0x33, 45),   # Channel Fader LSB (Ch 0, CC 51)
        ]

        try:
            while self.running and (time.time() - start_time) < duration:
                # Send button sequences
                for seq in test_sequences:
                    if not self.running:
                        break
                    msg = mido.Message.from_bytes(seq)
                    self._port.send(msg)
                    message_count += 1
                    time.sleep(0.1)

                # Send CC messages with varying values
                for status, cc, base_val in cc_messages:
                    if not self.running:
                        break
                    # Vary the value slightly
                    val = (base_val + int((time.time() * 10) % 20)) % 128
                    msg = mido.Message('control_change', channel=0, control=cc, value=val)
                    self._port.send(msg)
                    message_count += 1
                    time.sleep(0.05)

                # Small pause between cycles
                time.sleep(0.5)

        except Exception as e:
            click.echo(click.style(f"\nVirtual controller error: {e}", fg='red'))
        finally:
            if self._port:
                self._port.close()


if __name__ == '__main__':
    cli()
