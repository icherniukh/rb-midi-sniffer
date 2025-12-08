# CSV-FORMAT.md - Technical Reference Review

**Review Date**: 2025-12-08
**Reviewed Against**: DDJ-FLX10.midi.csv (567 lines), DDJ-GRV6.midi.csv (339 lines)
**Overall Assessment**: Good foundational specification with significant gaps in precision and coverage

---

## Executive Summary

The specification provides a solid conceptual overview but lacks the precision needed for a robust parser implementation. Key issues:

1. **Missing Control Types**: `JogIndicator` documented only in Parameter context, actual control type not in main table
2. **Incomplete Option Flags**: `Min=N` and `Max=N` found in real data but not documented
3. **Ambiguous Row Classification**: No clear rules for distinguishing functional vs. non-functional rows
4. **Inconsistent Column 0 Behavior**: Multiple undocumented patterns and edge cases
5. **Incomplete #-Prefix Semantics**: Three separate uses not clearly distinguished
6. **Missing Control Type Patterns**: Several control type behaviors not fully captured

---

## 1. PRECISION ISSUES

### 1.1 Control Types - Missing Type: `JogIndicator`

**Finding**: `JogIndicator` control type exists in actual CSV data but is NOT listed in the main Control Types table.

**Evidence (DDJ-GRV6.midi.csv, line 321)**:
```csv
JogPlayPauseIndicatorShort,JogPlayPauseIndicatorShort,JogIndicator,,,,,,,BF00,BF01,BF02,BF03,RO;Min=1;Max=72;Priority=100,Playing States for the trigger for JOG illumination
```

**Evidence (DDJ-FLX10.midi.csv)**:
Only appears as `JogIndicatorInterval,JogIndicatorInterval,Parameter,FFF1...` (not as control type)

**Impact**: Parser implementing the spec would reject valid `JogIndicator` rows as unknown type.

**Recommendation**: Add to output-only controls table:
```
| `JogIndicator` | Jog wheel illumination feedback | 14-bit (0-16383) value |
```

---

### 1.2 Options Field - Missing Flags

**Finding**: `Min=N` and `Max=N` option flags exist in real data but are completely undocumented.

**Evidence (DDJ-GRV6.midi.csv, line 321)**:
```csv
RO;Min=1;Max=72;Priority=100
```

**Evidence (DDJ-FLX10.midi.csv)**:
```csv
JogPlayPauseIndicatorShort,JogPlayPauseIndicatorShort,JogIndicator,,,,,,,BF00,BF01,BF02,BF03,RO;Min=1;Max=72;Priority=100,Playing States for the trigger for JOG illumination
```

**Impact**:
- Specification claims comprehensive option coverage
- Implementation would silently ignore range constraints
- Critical for value validation in jog wheel illumination (0-72 range)

**Recommendation**: Add to Options Field table:
```
| `Min=N` | Minimum valid value for this control |
| `Max=N` | Maximum valid value for this control |
```

---

### 1.3 MIDI Code Format - Incomplete Example Coverage

**Finding**: Documentation shows `4-digit hex` format but doesn't address edge cases in actual data.

**Examples from GRV6**:
- Standard: `900B` (✓ matches spec)
- Edge case line 14: Empty `input` column with deck values `9658,9659,9660,9661`
- Edge case line 109: `Indicator` type with empty input, output in deck columns only

**Issue**: Specification treats deck value columns as containing only channel offsets (0,1,2,3) or complete MIDI codes, but doesn't clearly state when each appears or how to distinguish them.

**Recommendation**: Explicitly document:
- When deck columns contain channel offsets (0-15)
- When they contain complete 4-digit MIDI codes
- How to detect which pattern applies (empty vs. filled input column)

---

## 2. COVERAGE ISSUES

### 2.1 Column 0 (`#name`) - Incomplete Pattern Documentation

**Finding**: The spec states purpose is "Internal identifier (purpose unclear)" with examples, but misses critical patterns.

**Undocumented Pattern 1: Empty `#name`** (rows with just `#`)

**Evidence (DDJ-GRV6.midi.csv, lines 14, 156, 173, etc.)**:
```csv
#,Load+Press+Shift,Button,,9658,9659,9660,9661,,,,,,,No function assigned here
#,,Pad,9010,8,10,12,14,9010,8,10,12,14,Fast,No function assigned here
```

**Undocumented Pattern 2: Section divider with function name**

**Evidence (DDJ-GRV6.midi.csv, line 4)**:
```csv
# Browser,,,,,,,,,,,,,,
```
vs. lines with `#` prefix but actual data:
```csv
#JogSearch,JogSearch,Difference,B029,0,1,2,3,,,,,,RO,Search
```

**Issue**: Specification mentions "Column 0 contains text (often `# SectionName`)" but doesn't document the hierarchy:
1. `#` alone = placeholder/unassigned
2. `# SectionName` = section divider
3. `#FunctionName` with function in col1 = what role?
4. Rows with matching col0/col1 = functional mapping

**Testability Problem**: A parser cannot reliably distinguish intended behavior without clear rules.

**Recommendation**: Document all four patterns explicitly with occurrence counts:
- `#` (appears 40+ times): placeholder row, ignored by parser
- `# Section Name` (appears ~12 times): section divider, visual only
- `#FunctionName,FunctionName,...` (appears ~30 times in FLX10): TBD - what semantic difference from normal?
- `Name,Name,...` (appears ~200 times): functional mapping

---

### 2.2 Row Type Classification - Ambiguous Rows

**Finding**: Specification defines 4 row types but real data has ambiguous entries that don't fit categories cleanly.

**Ambiguous Case 1: Empty Function with Unassigned Comment**

**Evidence (DDJ-GRV6.midi.csv, line 155)**:
```csv
ActivePartVocal,,Button,9010,7,9,11,13,9010,7,9,11,13,,ACTIVE PART VOCAL
```

**Analysis**:
- Has `#name` value: `ActivePartVocal`
- Has empty `function` (column 1)
- Has complete `type`, `input`, deck values
- Has valid comment (not "No function assigned")
- Next line (156) is nearly identical but starts with `#` and says "No function assigned"

**Question**: Is this functional or placeholder? The spec would classify as "Placeholder" (empty function), but it has more structure than other placeholders.

**Ambiguous Case 2: Empty input with filled deck columns**

**Evidence (DDJ-GRV6.midi.csv, line 13)**:
```csv
Load,Load,Button,,9646,9647,9648,9649,,,,,,,Load to Deck / Instant Double (double click)
```

**Current spec treatment**: "Pattern 2: Empty Base + Direct MIDI Codes" - correct identification
**Missing**: How should a parser handle validation? Should it require either (input XOR deck_columns), or is this valid?

**Recommendation**: Add explicit row validation rules:
```
Valid functional mappings:
- function column must be non-empty AND
- Either: (input non-empty AND deck_columns numeric)
  OR: (input empty AND all deck_columns filled with MIDI codes)
  OR: (both input and deck_columns empty) = global control

Invalid combinations trigger parser warnings.
```

---

### 2.3 Modifier Syntax - Incomplete Documentation

**Finding**: Function modifiers like `PlayPause+Shift`, `Browse+Press+LongPress` are mentioned as "assumed" but actual patterns are richer and more complex.

**Evidence - Observed Modifiers (DDJ-GRV6 and FLX10)**:
- `+Shift` (appears ~150 times)
- `+LongPress` (appears ~20 times)
- `+Press` (appears ~20 times)
- `+Dual` (NOT a modifier - this is in options field!)
- Compound: `PlayPause+Shift`, `Browse+Press+Shift`, `Browse+Press`, `ActivePartVocal+Shift`

**Problem 1**: Specification doesn't distinguish between:
- Modifiers (change function behavior)
- Options (flags like `Dual`, `Fast`)

**Problem 2**: Specification doesn't document nesting rules - can you have `+Shift+LongPress`? Evidence suggests no, but this isn't stated.

**Problem 3**: "Assumed to indicate modifier key combinations" is vague - what are the exact semantics?

**Evidence for actual use** (DDJ-GRV6 lines 223-226):
```csv
FXPartSelectVocalOn,,Button,9714,,,,,9714,,,,,,FX PART SELECT VOCAL
FXPartSelectVocalOn,,Button,9914,,,,,9914,,,,,,FX PART SELECT VOCAL
FXPartSelectVocalOn,,Button,9B14,,,,,9B14,,,,,,FX PART SELECT VOCAL
FXPartSelectVocalOn,,Button,9D14,,,,,9D14,,,,,,FX PART SELECT VOCAL
```

Multiple rows with identical function but different MIDI codes - no modifier. This contradicts the implied assumption that functions are unique.

**Recommendation**: Document:
1. List of valid modifiers: `Shift`, `LongPress`, `Press`
2. Composition rules (if any)
3. Semantics: How do modifiers affect MIDI routing vs. software behavior?
4. Note that same function can appear multiple times with different MIDI codes (see 223-226)

---

## 3. AMBIGUITY & CLARITY ISSUES

### 3.1 `#` Prefix Semantics - Three Distinct Uses

**Finding**: The `#` character in column 0 has at least three different semantic meanings, only partially documented.

**Use 1: Section Divider** (documented)
```csv
# Browser,,,,,,,,,,,,,,
# Deck,,,,,,,,,,,,,,
```

**Use 2: Placeholder/Unassigned** (partially documented)
```csv
#,Load+Press+Shift,Button,,9658,9659,9660,9661,,,,,,,No function assigned here
```

**Use 3: Functional row with # prefix** (NOT documented, appears ~30 times)
```csv
#JogSearch,JogSearch,Difference,B029,0,1,2,3,,,,,,RO,Search
#JogPitchBend,JogPitchBend,JogRotate,B023,0,1,2,3,,,,,,RO;Dual,Pitch Bend
#WheelSearch,WheelSearch,JogRotate,B026,0,1,2,3,,,,,,RO;Dual,Pitch Bend
```

These rows have:
- `#` prefix in col0
- Valid function in col1
- Valid type, input, deck values
- RO flag (read-only)
- No "No function assigned" comment

**Question**: Does `#` prefix mean "commented out" (disabled)? But then why in actual CSV files? Or does it mean something else specific to jog wheel functions?

**Current spec interpretation**:
> "Rows with `#` in col0 but valid function in col1 are ambiguous"

**This is insufficient** - a parser needs to know: should these rows be processed or ignored?

**Recommendation**: Research and document the actual semantic. Possibilities:
- These are optional/alternative mappings
- The `#` indicates hardware-defined mappings (not user-configurable)
- The `#` indicates output-only mappings
- The `#` indicates disabled mappings that can be enabled

Based on RO flag correlation, hypothesis: `#` prefix + RO flag = hardware output feedback, not user input control. **This should be verified and documented explicitly.**

---

### 3.2 Read-Only (`RO`) Flag Semantics - Incomplete

**Finding**: `RO` is documented as "Read-Only (output only, no input processing)" but usage patterns suggest subtler meaning.

**Pattern 1: RO with input MIDI codes**
```csv
JogScratch,JogScratch,JogRotate,B022,0,1,2,3,,,,,,RO,Scratch
```
Has input MIDI code but marked RO - contradicts the definition.

**Pattern 2: RO with no input codes**
```csv
DeckState,DeckState,Button,903C,0,1,2,3,,,,,,RO,LED State of the DECK 1/2/3/4
```
No input codes, has output codes - matches definition.

**Pattern 3: RO on feedback-only rows**
```csv
LoadedIndicator,LoadedIndicator,Indicator,,,,,,,9F00,9F01,9F02,9F03,RO;Priority=100,Load illumination
```
No input at all, only output indicator codes.

**Spec Issue**: Definition assumes RO = "no input", but Pattern 1 clearly has input MIDI codes. Possible reinterpretations:
- RO = "Software doesn't process user input for this function" (output-driven instead)
- RO = "This is a status/feedback row, not a control row"
- RO = "The hardware device handles this function, not software"

**Impact on Parser**: If implementing as "skip rows with RO flag in input processing", you'd incorrectly skip JogScratch/JogPitchBend operations.

**Recommendation**: Clarify RO semantics with specific examples of:
- RO rows that should generate input events (JogScratch case)
- RO rows that should only be status feedback (Indicator case)

---

### 3.3 `Blink=N` Option - Only One Example

**Finding**: Option `Blink=N` is documented with description "LED blink rate in milliseconds" but only one example in entire dataset.

**Evidence (DDJ-GRV6.midi.csv, line 45)**:
```csv
Sync,Sync,Button,9058,0,1,2,3,9058,0,1,2,3,Blink=600,Sync On/Off
```

**Evidence (DDJ-FLX10.midi.csv, line 36)**:
```csv
Sync,Sync,Button,9058,0,1,2,3,9058,0,1,2,3,Blink=600;Dual,Sync On/Off
```

**Issue**: Only appears for Sync button in both controllers. No validation provided for:
- Valid range of N values
- Whether all blink rates are multiples of some unit
- Whether this applies only to Button type or other types
- Edge case: What if `Blink=0`? Does it mean no blinking?

**Recommendation**: Either document the narrow applicability:
> "Blink flag only appears for hardware LED feedback on Sync buttons. Value represents blink cycle in milliseconds (observed: 600ms)."

Or expand research to confirm whether Blink values appear in other contexts in Rekordbox versions beyond 7.

---

## 4. TESTABILITY ISSUES

### 4.1 Unverified Function Name Modifiers

**Finding**: Specification marks function modifiers as "Not verified against official documentation" - this severely limits implementation confidence.

**Current status**:
> "Syntax like `PlayPause+Shift`, `Browse+Press+LongPress` observed in column 1."
> "Assumed to indicate modifier key combinations"
> "Not verified against official documentation"

**Problem**: Without verification, a parser must either:
1. Trust the assumption (risk of incorrect behavior)
2. Treat as opaque strings (lose semantic information)
3. Reverse-engineer from Rekordbox binary (not practical)

**Actual modifiers observed**:
- `+Shift` - ~150 occurrences (high confidence: clearly intentional pattern)
- `+LongPress` - ~20 occurrences (moderate confidence: distinct from Press)
- `+Press` - ~10 occurrences (unclear: semantics vs. part of function name?)

**Recommendation**: Mark confidence levels explicitly:
```
| `+Shift` | VERIFIED (pattern consistent, functional doubling) |
| `+LongPress` | INFERRED (distinct from +Press, used for mode selection) |
| `+Press` | UNCERTAIN (may be part of function name vs. modifier) |
```

---

### 4.2 Unverifiable Claims about Parameter Type

**Finding**: Spec claims about `FFFx` Parameter codes are impossible to verify without Rekordbox source.

**Specification claims**:
> "Likely internal to Rekordbox/hardware communication"
> "Processing mechanism unknown"

**Evidence**:
```csv
JogIndicatorInterval,JogIndicatorInterval,Parameter,FFF1,,,,,,,,,,Value=12,
MidiOutInterval,MidiOutInterval,Parameter,FFF3,,,,,,,,,,Value=2,
```

**Testability**: These codes are outside standard MIDI range (>255 in data byte position). Without reverse-engineering Rekordbox or reading official docs, behavior cannot be verified. **This is appropriately marked as "unknown" in the spec - good.**

---

## 5. MISSING PATTERNS

### 5.1 Multiple MIDI Codes for Same Function (No Modifier)

**Finding**: Real data shows same function appearing multiple times with different MIDI codes, with no documented pattern explaining why.

**Evidence (DDJ-GRV6.midi.csv, lines 223-226)**:
```csv
FXPartSelectVocalOn,,Button,9714,,,,,9714,,,,,,FX PART SELECT VOCAL
FXPartSelectVocalOn,,Button,9914,,,,,9914,,,,,,FX PART SELECT VOCAL
FXPartSelectVocalOn,,Button,9B14,,,,,9B14,,,,,,FX PART SELECT VOCAL
FXPartSelectVocalOn,,Button,9D14,,,,,9D14,,,,,,FX PART SELECT VOCAL
```

Same function, four different MIDI codes:
- `9714` = Note 0x14 on Channel 7
- `9914` = Note 0x14 on Channel 9
- `9B14` = Note 0x14 on Channel 11
- `9D14` = Note 0x14 on Channel 13

**Pattern**: These are deck-specific mappings without using the deck offset columns. This is a 4th deck assignment pattern not documented in the spec.

**Similar cases**:
- Lines 243-246: FXPartSelectInstOn (same pattern)
- Lines 263-266: FXPartSelectBassOn (same pattern)
- Lines 283-286: FXPartSelectDrumsOn (same pattern)

**Spec issue**: Only documents 4 deck assignment patterns:
1. Base + Channel Offsets
2. Empty Base + Direct MIDI Codes
3. Global (No Deck Assignment)
4. Non-Sequential Channels (Performance Pads)

But this example (FXPartSelectVocalOn) doesn't match any of these patterns perfectly:
- Not Pattern 1 (different MIDI note numbers)
- Partially matches Pattern 2 (multiple codes, not in deck columns)
- Not Pattern 3 (deck-specific, not global)
- Not Pattern 4 (sequential channels, not performance pads)

**Recommendation**: Add Pattern 5:
```
### Pattern 5: Multi-Row Deck Assignment (Deck-Specific Alternative Codes)

When deck assignment would require 4 different MIDI codes on a single row,
they may instead appear as 4 separate rows with the same function name.

Example (DDJ-GRV6, line 223-226):
- Row 1: Function=FXPartSelectVocalOn, MIDI=9714 (Deck 1 / Channel 7)
- Row 2: Function=FXPartSelectVocalOn, MIDI=9914 (Deck 2 / Channel 9)
- Row 3: Function=FXPartSelectVocalOn, MIDI=9B14 (Deck 3 / Channel 11)
- Row 4: Function=FXPartSelectVocalOn, MIDI=9D14 (Deck 4 / Channel 13)

Parser should deduplicate and treat as single 4-deck mapping.
```

---

### 5.2 Type Mismatch: Indicator vs. No Type

**Finding**: Some feedback-only rows have empty type field while others use `Indicator` type.

**Evidence of Indicator type**:
```csv
Permission_PadMode1,Permission_PadMode1,Indicator,,,,,,9021,0,1,2,3,RO,Permission flag
ChannelLevel,ChannelLevel,Indicator,,,,,,B002,0,1,2,3,RO;Priority=50,CH Level Indicator
```

**Evidence of empty type**:
```csv
FailSafeState,FailSafeState,,967E,,,,,,,,,,RO,State of Fail Safe
```

**Question**: Is empty type field valid? Should parser require `Indicator` for feedback rows?

**Spec says**: Lists `Indicator` as output-only control type, but doesn't state whether it's required or whether empty type is acceptable.

**Recommendation**: Clarify:
1. Is empty type field valid for any row types?
2. Should feedback-only rows always specify `Indicator` type?
3. If not, what are the rules for when type can be empty?

---

## 6. DOCUMENTATION QUALITY ISSUES

### 6.1 Line Count in References Section Outdated

**Finding**: Reference section states file sizes but they're incorrect or outdated.

**Spec states**:
```
- **Analyzed Files**: DDJ-FLX10.midi.csv (567 lines), DDJ-GRV6.midi.csv
```

**Actual file sizes** (verified 2025-12-08):
- DDJ-FLX10.midi.csv: 567 lines ✓ (correct)
- DDJ-GRV6.midi.csv: 339 lines (not stated in spec)

**Impact**: Minor, but shows spec needs maintenance. Reader can't tell if GRV6 was fully analyzed.

**Recommendation**: Update to:
```
- **Analyzed Files**:
  - DDJ-FLX10.midi.csv (567 lines)
  - DDJ-GRV6.midi.csv (339 lines, used for pattern comparison)
```

---

### 6.2 Official Documentation Reference

**Spec states**:
```
- **Official**: Rekordbox MIDI Learn Guide v5.3.0 (PDF)
```

**Issue**: No actual verification shown that spec matches official guide. It's unclear whether this guide documents the CSV format or only MIDI Learn functionality.

**Recommendation**: Either:
1. Include quote from official guide matching key patterns, or
2. Change to: "Referenced but not verified against: Rekordbox MIDI Learn Guide v5.3.0 (PDF)"

---

## 7. IMPLEMENTATION IMPACT SUMMARY

| Issue | Severity | Parser Impact | Recommendation |
|-------|----------|---------------|-----------------|
| Missing `JogIndicator` control type | **HIGH** | Would reject valid rows | Add to control types table |
| Missing `Min=N`, `Max=N` options | **HIGH** | Would lose value constraints | Add to options table + define ranges |
| Ambiguous `#` prefix semantics | **HIGH** | Cannot determine if rows processed | Research and document 3 distinct uses |
| Undocumented deck assignment pattern | **MEDIUM** | Multi-row deck mapping fails | Add Pattern 5 to deck assignment section |
| RO flag contradicts definition | **MEDIUM** | May skip input processing | Clarify RO semantics with examples |
| Empty type field validity | **MEDIUM** | Parser validation rules unclear | Document when type can be empty |
| Unverified function modifiers | **MEDIUM** | Treat as opaque vs. semantic | Mark confidence levels explicitly |
| Incomplete Blink option documentation | **LOW** | May reject valid values | Document range and applicability scope |

---

## 8. SUMMARY OF REQUIRED ADDITIONS

To make this a production-grade reference, add:

**1. New Control Type** (required for completeness):
```
| `JogIndicator` | Jog wheel illumination feedback | 14-bit value |
```

**2. New Options** (required for validation):
```
| `Min=N` | Minimum valid value |
| `Max=N` | Maximum valid value |
```

**3. Expanded Row Type Section** (required for implementation):
- Explicit rules for distinguishing functional vs. non-functional rows
- Validation rules for deck assignment patterns
- Pattern 5: Multi-row deck assignment

**4. Clarification Section** (required for unambiguous parsing):
- Three distinct uses of `#` prefix with occurrence counts
- RO flag semantics with contradicting examples
- When type field can be empty
- Confidence levels for unverified function modifiers

**5. Parser Implementation Guide** (optional but valuable):
- Pseudocode or state machine for row type detection
- Validation checklist for each pattern
- Error handling for malformed rows

---

## Conclusion

The CSV-FORMAT.md specification provides a solid foundation but needs significant enhancement for production use. The issues identified are not fatal but would cause:

1. **Parsers** to reject valid data or misinterpret row semantics
2. **Implementers** to make incorrect assumptions about modifier syntax and RO flag meaning
3. **Maintainers** to struggle with ambiguous edge cases

**Estimated effort to remediate**: 4-6 hours of research + documentation
**Priority**: HIGH - blocks reliable MIDI sniffer implementation

The specification should be marked as **"Requires Verification"** rather than **"Draft"** until items in Section 7 are resolved.
