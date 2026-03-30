Attribute VB_Name = "Module_Main"
'============================================================================
' Module_Main
' Purpose : Top-level entry points.
'
'   RunFullCleaningWorkflow  — Full end-to-end: import + clean + validate
'   RunValidationsOnly       — Re-run rules on already-imported data
'   RunZoneDerivationOnly    — Re-run zone fill only
'
' HOW TO USE:
'   1. Open your TESTING copy of the workbook.
'   2. If importing fresh data, also open the SIESALES export file.
'   3. Run  RunFullCleaningWorkflow  or one of the narrower entry points.
'   4. Review the "Run Log" sheet for a full audit trail.
'
' ASSUMPTIONS (adjust in Module_Config if wrong):
'   A. Header row is row 1.
'   B. Data sheet is named "Data".
'   C. Zone lookup sheet is named "Zone Structure" with columns "Country","Zone".
'   D. Formula-preservation columns are H2 and H3 (by header name).
'   E. SIESALES source sheet name is asked interactively (or hardcode below).
'   F. Yellow zone columns are listed in YELLOW_ZONE_COLS constant below.
'   G. Previous-file lookup is optional; skip it if wsPrev is Nothing.
'============================================================================
Option Explicit

' ─────────────────────────────────────────────────────────────────────────────
' CONFIGURABLE: list the yellow-zone column headers here (comma-separated).
' These are the columns whose values will be copied from the previous file.
' ─────────────────────────────────────────────────────────────────────────────
Private Const YELLOW_ZONE_COLS As String = "FC Relevant,Business Sub-Segment Short revised"

' ─────────────────────────────────────────────────────────────────────────────
' RunFullCleaningWorkflow
' ─────────────────────────────────────────────────────────────────────────────
Public Sub RunFullCleaningWorkflow()
    ' ── Safety guard: ensure we are NOT on the live file ──────────────────────
    If Not IsTestingFile(ThisWorkbook) Then
        MsgBox "SAFETY STOP: This workbook does not appear to be the TESTING copy." & vbCrLf & _
               "Expected 'TESTING' in the file path or name." & vbCrLf & vbCrLf & _
               "Please work on the testing copy only.", _
               vbCritical, "Safety Guard"
        Exit Sub
    End If

    Dim state   As AppState
    Dim ws      As Worksheet
    Dim wsLog   As Worksheet
    Dim zoneDict As Object
    Dim summary  As String
    Dim zonesUpdated As Long

    On Error GoTo HandleError
    SaveAppState state
    PauseApp

    ' Locate the main data sheet
    Set ws = GetDataSheet(ThisWorkbook)
    If ws Is Nothing Then
        MsgBox "Data sheet """ & CFG_DATA_SHEET & """ not found. Check CFG_DATA_SHEET in Module_Config.", _
               vbCritical, "Sheet Not Found"
        GoTo CleanExit
    End If

    ' Initialise (or recreate) the log sheet
    Set wsLog = InitLogSheet(ThisWorkbook)

    ' ── Step 1: Optional – clear old data and import from SIESALES ────────────
    Dim doImport As VbMsgBoxResult
    doImport = MsgBox("Do you want to CLEAR old data and import fresh SIESALES data?" & vbCrLf & _
                      "(Click No to skip to validations only)", _
                      vbQuestion + vbYesNo, "Import Step")

    If doImport = vbYes Then
        ' Prompt for the SIESALES source workbook/sheet
        Dim wsSrc As Worksheet
        Set wsSrc = PickSourceSheet("Select the SIESALES data sheet")
        If wsSrc Is Nothing Then
            MsgBox "No source sheet selected. Import cancelled.", vbInformation
        Else
            ClearOldData ws
            ImportFromSIESALES ws, wsSrc, wsLog
        End If

        ' ── Step 2: Optional – fill yellow zone from previous file ────────────
        Dim doYellow As VbMsgBoxResult
        doYellow = MsgBox("Do you want to fill the YELLOW ZONE from a previous file?", _
                          vbQuestion + vbYesNo, "Yellow Zone Fill")

        If doYellow = vbYes Then
            Dim wsPrev As Worksheet
            Set wsPrev = PickSourceSheet("Select the PREVIOUS file's data sheet")
            If Not wsPrev Is Nothing Then
                Dim yellowArr() As String
                yellowArr = SplitTrim(YELLOW_ZONE_COLS, ",")
                FillYellowZoneFromPreviousFile ws, wsPrev, wsLog, yellowArr
            End If
        End If
    End If

    ' ── Step 3: Zone derivation ────────────────────────────────────────────────
    Set zoneDict = BuildZoneDictionary(ThisWorkbook)
    If zoneDict.Count = 0 Then
        WriteLog wsLog, 0, "", "Zone Derivation", "", "", "", _
                 "WARNING: Zone Structure sheet is empty or missing — zone derivation skipped"
    End If
    zonesUpdated = ApplyZoneDerivation(ws, wsLog, zoneDict)

    ' ── Step 4: All business-rule validations ─────────────────────────────────
    summary = RunAllValidations(ws, wsLog)

    ' ── Step 5: Format the log sheet ──────────────────────────────────────────
    FormatLogSheet wsLog

    ' ── Step 6: Show summary ──────────────────────────────────────────────────
    RestoreAppState state

    MsgBox "Cleaning complete!" & vbCrLf & vbCrLf & _
           "── Zone Derivation ──" & vbCrLf & _
           "Zones auto-filled: " & zonesUpdated & vbCrLf & vbCrLf & _
           "── Validation Rules ──" & vbCrLf & _
           summary & vbCrLf & vbCrLf & _
           "Full audit trail available on sheet: """ & CFG_LOG_SHEET & """", _
           vbInformation, "Run Complete"

    ' Activate the log sheet so the user sees the report immediately
    wsLog.Activate
    Exit Sub

HandleError:
    RestoreAppState state
    MsgBox "ERROR in RunFullCleaningWorkflow:" & vbCrLf & _
           "  Error " & Err.Number & ": " & Err.Description & vbCrLf & _
           "  Source: " & Err.Source, _
           vbCritical, "Macro Error"

CleanExit:
    RestoreAppState state
End Sub

' ─────────────────────────────────────────────────────────────────────────────
' RunValidationsOnly
' Re-applies all five business rules to the current data without importing.
' ─────────────────────────────────────────────────────────────────────────────
Public Sub RunValidationsOnly()
    If Not IsTestingFile(ThisWorkbook) Then
        MsgBox "SAFETY STOP: Not a testing file.", vbCritical
        Exit Sub
    End If

    Dim state   As AppState
    Dim ws      As Worksheet
    Dim wsLog   As Worksheet
    Dim summary As String

    On Error GoTo HandleError
    SaveAppState state
    PauseApp

    Set ws    = GetDataSheet(ThisWorkbook)
    Set wsLog = InitLogSheet(ThisWorkbook)

    summary = RunAllValidations(ws, wsLog)
    FormatLogSheet wsLog

    RestoreAppState state
    MsgBox "Validations complete:" & vbCrLf & vbCrLf & summary, vbInformation, "Validations Done"
    wsLog.Activate
    Exit Sub

HandleError:
    RestoreAppState state
    MsgBox "ERROR: " & Err.Number & " – " & Err.Description, vbCritical
End Sub

' ─────────────────────────────────────────────────────────────────────────────
' RunZoneDerivationOnly
' ─────────────────────────────────────────────────────────────────────────────
Public Sub RunZoneDerivationOnly()
    If Not IsTestingFile(ThisWorkbook) Then
        MsgBox "SAFETY STOP: Not a testing file.", vbCritical
        Exit Sub
    End If

    Dim state        As AppState
    Dim ws           As Worksheet
    Dim wsLog        As Worksheet
    Dim zoneDict     As Object
    Dim zonesUpdated As Long

    On Error GoTo HandleError
    SaveAppState state
    PauseApp

    Set ws       = GetDataSheet(ThisWorkbook)
    Set wsLog    = InitLogSheet(ThisWorkbook)
    Set zoneDict = BuildZoneDictionary(ThisWorkbook)
    zonesUpdated = ApplyZoneDerivation(ws, wsLog, zoneDict)
    FormatLogSheet wsLog

    RestoreAppState state
    MsgBox "Zone derivation complete." & vbCrLf & "Zones filled: " & zonesUpdated, _
           vbInformation, "Zone Derivation Done"
    wsLog.Activate
    Exit Sub

HandleError:
    RestoreAppState state
    MsgBox "ERROR: " & Err.Number & " – " & Err.Description, vbCritical
End Sub

'=============================================================================
' PRIVATE HELPERS (internal to this module)
'=============================================================================

' ─────────────────────────────────────────────────────────────────────────────
' IsTestingFile
' Returns True if the workbook path or name contains "TESTING" (case-insensitive).
' Adjust the check string to match your naming convention.
' ─────────────────────────────────────────────────────────────────────────────
Private Function IsTestingFile(wb As Workbook) As Boolean
    IsTestingFile = (InStr(1, wb.FullName, "TESTING", vbTextCompare) > 0) Or _
                   (InStr(1, wb.FullName, "testing", vbTextCompare) > 0)
End Function

' ─────────────────────────────────────────────────────────────────────────────
' GetDataSheet
' Returns the data worksheet or Nothing.
' ─────────────────────────────────────────────────────────────────────────────
Private Function GetDataSheet(wb As Workbook) As Worksheet
    On Error Resume Next
    Set GetDataSheet = wb.Worksheets(CFG_DATA_SHEET)
    On Error GoTo 0
End Function

' ─────────────────────────────────────────────────────────────────────────────
' PickSourceSheet
' Prompts the user to select a worksheet from any open workbook.
' Uses InputBox to collect  "WorkbookName|SheetName"  then resolves it.
' ─────────────────────────────────────────────────────────────────────────────
Private Function PickSourceSheet(prompt As String) As Worksheet
    Dim input As String
    Dim parts() As String
    Dim wb As Workbook
    Dim ws As Worksheet

    ' Build a list of all open workbook+sheet combos for the user
    Dim choices As String
    Dim w As Workbook, s As Worksheet
    For Each w In Application.Workbooks
        For Each s In w.Worksheets
            choices = choices & w.Name & " | " & s.Name & vbCrLf
        Next s
    Next w

    input = Application.InputBox( _
        prompt & vbCrLf & vbCrLf & _
        "Type exactly:  WorkbookName | SheetName" & vbCrLf & _
        "─────────────────────────────────────────" & vbCrLf & _
        "Open sheets:" & vbCrLf & choices, _
        "Select Source Sheet", Type:=2)

    If input = "False" Or input = "" Then
        Set PickSourceSheet = Nothing
        Exit Function
    End If

    parts = Split(input, "|")
    If UBound(parts) < 1 Then
        Set PickSourceSheet = Nothing
        Exit Function
    End If

    On Error Resume Next
    Set wb = Application.Workbooks(Trim(parts(0)))
    If Not wb Is Nothing Then
        Set ws = wb.Worksheets(Trim(parts(1)))
    End If
    On Error GoTo 0

    Set PickSourceSheet = ws
End Function

' ─────────────────────────────────────────────────────────────────────────────
' FormatLogSheet
' Auto-fits columns and colour-codes action types for easy visual review.
' ─────────────────────────────────────────────────────────────────────────────
Private Sub FormatLogSheet(wsLog As Worksheet)
    Dim lastRow As Long
    Dim i       As Long
    Dim action  As String

    lastRow = GetLastDataRow(wsLog)
    If lastRow <= 1 Then Exit Sub

    ' Auto-fit
    wsLog.Columns("A:H").AutoFit

    ' Colour-code by action type
    For i = 2 To lastRow
        action = CStr(wsLog.Cells(i, 8).Value)
        Select Case True
            Case InStr(1, action, "FILLED", vbTextCompare) > 0
                wsLog.Rows(i).Interior.Color = RGB(198, 239, 206)   ' green
            Case InStr(1, action, "CORRECTED", vbTextCompare) > 0
                wsLog.Rows(i).Interior.Color = RGB(255, 235, 156)   ' yellow
            Case InStr(1, action, "CLEARED", vbTextCompare) > 0
                wsLog.Rows(i).Interior.Color = RGB(255, 199, 206)   ' red
            Case InStr(1, action, "WARNING", vbTextCompare) > 0
                wsLog.Rows(i).Interior.Color = RGB(255, 165, 0)     ' orange
            Case InStr(1, action, "IMPORTED", vbTextCompare) > 0
                wsLog.Rows(i).Interior.Color = RGB(221, 235, 247)   ' blue
            Case Else
                wsLog.Rows(i).Interior.ColorIndex = xlNone
        End Select
    Next i
End Sub
