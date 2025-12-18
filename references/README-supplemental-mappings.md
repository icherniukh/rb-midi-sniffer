# Supplemental MIDI Mappings

## Purpose

This directory contains supplemental MIDI mapping files for controls that are **not documented** in the official Rekordbox CSV files. These may include:

- Undocumented modifier combinations (e.g., Shift+Jog)
- Hardware-specific features not in official CSV
- Community-discovered controls
- Firmware update additions

## Usage

### Option 1: Merge with Official CSV (Manual)

1. Locate your controller's official CSV:
   ```
   /Applications/rekordbox 7/rekordbox.app/Contents/Resources/MidiMappings/DDJ-GRV6.midi.csv
   ```

2. Open `supplemental-mappings-template.csv` in this directory

3. Copy the relevant mapping rows and paste them into your controller's CSV file

4. Save and test with the sniffer

### Option 2: Use Alongside Official CSV (Future Feature)

*Note: Multi-CSV support is not yet implemented. Track progress in issue #XX*

## File Format

Supplemental mapping files use the same format as official Rekordbox CSVs. See `REKORDBOX-MIDI-CSV-SPEC.md` for detailed format specification.

### Quick Template

```csv
@file,1,YourControllerName-Supplemental
#name,function,type,input,deck1,deck2,deck3,deck4,output,deck1,deck2,deck3,deck4,option,comment
FunctionName,FunctionName+Modifier,ControlType,B0XX,0,1,2,3,,,,,,Options,Description
```

## Documented Undocumented Controls

### DDJ-GRV6

#### Shift+Jog Rotation (CC 41)
**Discovered**: 2025-12-18
**MIDI Code**: `B029` (CC 41 on Channel 0) + deck offsets (0,1,2,3)
**Function**: Fast track search/scan when Shift is held and jog wheel is rotated
**Evidence**: 5,007 instances observed in test session log

```csv
JogFastSearch,JogFastSearch+Shift,JogRotate,B029,0,1,2,3,,,,,,RO,Fast Track Search (Shift+Jog)
```

**Usage Notes**:
- Generates high-frequency messages (~2-4ms intervals)
- Value range 59-71 encodes rotation speed/direction
- Center value is 64 (0x40)
- Faster rewind/forward than regular jog pitch bend

## Contributing New Mappings

If you discover undocumented controls:

1. **Document your discovery**:
   - Controller model and firmware version
   - Physical action (e.g., "Hold Shift, turn jog wheel")
   - MIDI messages observed (use `python sniffer.py monitor`)
   - Rekordbox behavior (what happens in the software)

2. **Create the mapping entry**:
   - Follow the CSV format in the template
   - Use descriptive function names
   - Include helpful comments

3. **Share with the community**:
   - Update this README with your findings
   - Create a pull request or issue on the project repository
   - Reference your test data/logs

## Test Data

Test logs demonstrating undocumented controls can be found in:
- `tasks/121825_test_findings/` - DDJ-GRV6 Shift+Jog discovery

## See Also

- `REKORDBOX-MIDI-CSV-SPEC.md` - Complete CSV format specification
- `references/rekordbox7.0.5_midi_learn_operation_guide_EN.pdf` - Official AlphaTheta guide (UI/workflow only)
