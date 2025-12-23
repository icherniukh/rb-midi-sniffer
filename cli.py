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
def monitor(csv_path, input_port, output_port, no_log, log_filename, direction, full_row, columns_str, no_colors, no_grouping):
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
        enable_grouping=not no_grouping
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
@click.option('--speed', type=click.FloatRange(min=0.0, max=MAX_REPLAY_SPEED), default=0.0, help=f'Playback speed multiplier (0=instant, 1=realtime, max={MAX_REPLAY_SPEED:.0f})')
def replay(logfile, csv_path, full_row, columns_str, no_colors, no_grouping, speed):
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
        enable_grouping=not no_grouping
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


if __name__ == '__main__':
    cli()
