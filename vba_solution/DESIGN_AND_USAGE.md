# SIESALES Data Cleaning VBA Solution

## My Understanding of the Task

You maintain an Excel workbook that receives data exports from SIESALES.
The workflow is:

1. Export raw data from SIESALES
2. Create a working copy (TESTING) of the macro-enabled template
3. Clear old data rows, preserving formula columns H2/H3
4. Paste fresh SIESALES data, mapping source → destination columns
5. Fill "yellow zone" columns from a previous file via Opportunity ID lookup
6. Derive missing Zone values from a "Zone Structure" reference sheet
7. Apply five business validation/correction rules
8. Produce a full audit report on a dedicated log sheet

---

## Assumptions Made (adjust in Module_Config if wrong)

| # | Assumption | Where to change |
|---|-----------|-----------------|
| 1 | Header row is row 1 | `CFG_HEADER_ROW` in Module_Config |
| 2 | Data sheet is named `"Data"` | `CFG_DATA_SHEET` |
| 3 | Zone lookup sheet is `"Zone Structure"` with columns `"Country"` and `"Zone"` | `CFG_ZONE_SHEET`, `ZONE_COL_COUNTRY`, `ZONE_COL_ZONE` |
| 4 | Formula columns to preserve are H2 and H3 (by header name) | `CFG_PRESERVE_HEADERS` |
| 5 | H2 naming target value is `"SP7"` | `RULE_H2_NAMING_TARGET` |
| 6 | H2/H3 BSS value is `"SI GSW SOL SPL Operations"` | `RULE_H2_BSS`, `RULE_H3_BSS` |
| 7 | "Testing file" is identified by `"TESTING"` anywhere in the file path | `IsTestingFile()` in Module_Main |
| 8 | Yellow zone columns are `"FC Relevant"` and `"Business Sub-Segment Short revised"` | `YELLOW_ZONE_COLS` constant in Module_Main |
| 9 | SIESALES source column names match those listed in `ImportFromSIESALES()` | Column mapping array in Module_DataImport |
| 10 | Opportunity ID is the unique join key for yellow-zone and previous-file lookups | Only Opportunity ID is used as join key |

---

## Architecture

```
Module_Config       ← All constants/settings. THE ONLY FILE YOU SHOULD NEED TO EDIT.
Module_Helpers      ← Column-finder, log writer, app-state save/restore
Module_ZoneLookup   ← Dictionary-based zone derivation
Module_Validation   ← Five business rules, each in its own function
Module_DataImport   ← Data clear, SIESALES import, yellow-zone fill
Module_Main         ← Entry points (RunFullCleaningWorkflow, etc.)
```

### Why this structure is better than one monolithic macro

| Concern | Old single macro | New modular design |
|---------|----------------|--------------------|
| Testability | Can only test the whole thing | Each rule is a standalone `Function` |
| Maintainability | Change anything = risk breaking everything | Change one module without touching others |
| Column robustness | Hard-coded column letters (e.g., col 23) | Resolved by header name at runtime |
| Audit trail | None | Full colour-coded log sheet |
| Safety | No guard | `IsTestingFile()` blocks accidental live-file execution |
| Re-usability | One-shot | Can run `RunValidationsOnly` or `RunZoneDerivationOnly` independently |
| Error handling | `GoTo CleanFail` pattern | Consistent pattern + `AppState` struct ensures restore |

---

## Dictionary vs VLOOKUP for Zone Lookup

| | VBA Dictionary (chosen) | Worksheet VLOOKUP |
|--|------------------------|-------------------|
| Speed | O(1) per lookup after one-time load | Recalculates on every change |
| Robustness | Survives column moves in Zone sheet | Breaks if columns shift |
| Case-sensitivity | `CompareMode = 1` → case-insensitive | Case-sensitive by default |
| Formula residue | No formula left in cells | Leaves formula strings visible |
| Works on hidden sheets | Yes | Yes |
| Requires VBA | Yes | No |
| Visible to user | No (code-side only) | Yes (formula in cell) |

**Verdict:** Dictionary is clearly better for an automated macro. VLOOKUP only makes sense if end-users need to see the formula logic in the cell or if the workbook is sometimes used without macros.

---

## How to Import the Modules

1. Open your macro-enabled workbook (`.xlsm`)
2. Press `Alt + F11` to open the VBA Editor
3. In the menu: **File → Import File**
4. Import in this order:
   - `Module_Config.bas`
   - `Module_Helpers.bas`
   - `Module_ZoneLookup.bas`
   - `Module_Validation.bas`
   - `Module_DataImport.bas`
   - `Module_Main.bas`
5. Close the VBA Editor

---

## How to Run

### Full workflow (import + validate):
1. Open the TESTING copy of your workbook
2. Also open the SIESALES export file (if importing)
3. Run macro: `RunFullCleaningWorkflow`
4. Follow the prompts (import? previous file? etc.)
5. Review the `Run Log` sheet

### Validations only (no import):
- Run macro: `RunValidationsOnly`

### Zone derivation only:
- Run macro: `RunZoneDerivationOnly`

---

## Adjust Column Names Here

All column header names are in `Module_Config.bas`. If a column is renamed in the sheet, update the corresponding constant — nothing else needs changing.

```vba
' Example: if "Naming" column is renamed to "H2 Naming Field"
Public Const COL_NAMING As String = "H2 Naming Field"   ' ← change only here
```

---

## Column Mapping for SIESALES Import

In `Module_DataImport.bas`, inside `ImportFromSIESALES()`, find this section and extend it:

```vba
Dim mapping(0 To 4, 0 To 1) As String
mapping(0, 0) = "Opportunity ID"         : mapping(0, 1) = COL_OPPORTUNITY_ID
mapping(1, 0) = "Country of Installation": mapping(1, 1) = COL_COUNTRY_INSTALL
' ... add more pairs ...
mapping(5, 0) = "Your SIESALES column"   : mapping(5, 1) = "Your dest header"
```

Also update the array dimension from `(0 To 4, ...)` to `(0 To 5, ...)`.

---

## Run Log — Colour Coding

| Colour | Meaning |
|--------|---------|
| Green | Value was FILLED (blank → value) |
| Yellow | Value was CORRECTED (wrong → right) |
| Red | Value was CLEARED (value → blank, Rule 3) |
| Orange | WARNING (e.g., country not in Zone Structure) |
| Blue | Row imported from SIESALES |

---

## Further Improvement Ideas

### Performance
- **Bulk read/write with arrays**: Instead of `ws.Cells(i, j)` in a loop, read the entire data range into a 2D `Variant` array, process in memory, then write back in one shot. For datasets >5,000 rows this can be 10–100x faster.
- **Turn off AutoFilter during processing**: Already done via `PauseApp`.

### Robustness
- **Input validation on import**: Check for duplicate Opportunity IDs in the SIESALES source before importing.
- **Backup step**: Before `ClearOldData`, save a backup sheet named `"Backup_YYYYMMDD"` using `ws.Copy` — instant undo if something goes wrong.
- **Schema validation**: Before processing, check that all required headers exist and warn if any are missing (instead of stopping on the first `AssertColIndex` failure).

### Maintainability
- **Unit test module**: Add a `Module_Tests` with small `Sub Test_Rule1()` etc. procedures that inject known data into a temp sheet and assert expected outcomes.
- **Version stamp**: Write the macro version and run timestamp into cell A1 of the log sheet.

### Safety
- **Require explicit confirmation before overwriting**: Add a second prompt before `ClearOldData` listing how many rows will be deleted.
- **Dry-run mode**: Add a `DryRun As Boolean` parameter to all rule functions so they log what they *would* change without actually writing, letting you preview impact first.
