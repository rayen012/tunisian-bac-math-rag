Attribute VB_Name = "Module_Main"
'============================================================================
' Module_Main
' Purpose : Top-level entry points.
'
'   RunFullCleaningWorkflow  — Full end-to-end: import + yellow fill + zone + validate
'   RunValidationsOnly       — Re-run rules on already-imported data
'   RunZoneDerivationOnly    — Re-run zone fill only
'
' HOW TO USE:
'   1. Open your TESTING copy of the workbook.
'   2. If importing fresh data, also open the SIESALES export file.
'   3. If filling yellow-zone values, also open the previous working file.
'   4. Run one of the entry-point macros.
'   5. Review the "Run Log" sheet for the audit trail.
'============================================================================
Option Explicit

' ─────────────────────────────────────────────────────────────────────────────
' RunFullCleaningWorkflow
' Full process:
'   1) Safety check
'   2) Optional import from SIESALES export
'   3) Optional yellow-zone backfill from old working file
'   4) Zone derivation
'   5) Business-rule validations
'   6) Log formatting + summary
' ─────────────────────────────────────────────────────────────────────────────
Public Sub RunFullCleaningWorkflow()
    Dim state As AppState
    Dim ws As Worksheet
    Dim wsLog As Worksheet
    Dim wsSrc As Worksheet
    Dim wsPrev As Worksheet
    Dim zoneDict As Object
    Dim summary As String
    Dim zonesUpdated As Long
    Dim doImport As VbMsgBoxResult
    Dim doYellow As VbMsgBoxResult
    Dim yellowArr() As String

    If Not IsTestingFile(ThisWorkbook) Then
        MsgBox "SAFETY STOP: This workbook does not appear to be the TESTING copy." & vbCrLf & _
               "Expected text in file path or name: """ & CFG_REQUIRED_TEST_PATH_TEXT & """" & vbCrLf & vbCrLf & _
               "Please work on the testing copy only.", _
               vbCritical, "Safety Guard"
        Exit Sub
    End If

    On Error GoTo HandleError
    SaveAppState state
    PauseApp

    Set ws = GetWorkingSheet(ThisWorkbook)
    If ws Is Nothing Then
        MsgBox "Working sheet """ & CFG_WORKING_SHEET & """ not found." & vbCrLf & _
               "Check CFG_WORKING_SHEET in Module_Config.", _
               vbCritical, "Sheet Not Found"
        GoTo CleanExit
    End If

    Set wsLog = InitLogSheet(ThisWorkbook)

    doImport = MsgBox("Do you want to clear old data and import fresh SIESALES data?", _
                      vbQuestion + vbYesNo, "Import Step")

    If doImport = vbYes Then
        Set wsSrc = PickSourceSheet("Select the SIESALES export sheet")
        If wsSrc Is Nothing Then
            MsgBox "No SIESALES source sheet selected. Import step skipped.", vbInformation
        Else
            ClearOldData ws
            ImportFromSIESALES ws, wsSrc, wsLog
        End If

        doYellow = MsgBox("Do you want to fill the yellow zone from the previous working file?", _
                          vbQuestion + vbYesNo, "Yellow Zone Fill")

        If doYellow = vbYes Then
            Set wsPrev = PickSourceSheet("Select the PREVIOUS working file sheet")
            If Not wsPrev Is Nothing Then
                yellowArr = SplitTrim(CFG_YELLOW_HEADERS, ",")
                FillYellowZoneFromPreviousFile ws, wsPrev, wsLog, yellowArr
            Else
                MsgBox "No previous-file sheet selected. Yellow-zone fill skipped.", vbInformation
            End If
        End If
    End If

    Set zoneDict = BuildZoneDictionary(ThisWorkbook)

    If zoneDict Is Nothing Then
        WriteLog wsLog, 0, "", "Zone Derivation", "", "", "", _
                 "WARNING: Zone dictionary could not be created"
        zonesUpdated = 0
    ElseIf zoneDict.Count = 0 Then
        WriteLog wsLog, 0, "", "Zone Derivation", "", "", "", _
                 "WARNING: Zone Structure sheet is empty or missing — zone derivation skipped"
        zonesUpdated = 0
    Else
        zonesUpdated = ApplyZoneDerivation(ws, wsLog, zoneDict)
    End If

    summary = RunAllValidations(ws, wsLog)

    FormatLogSheet wsLog

    RestoreAppState state

    MsgBox "Cleaning complete!" & vbCrLf & vbCrLf & _
           "Zone derivation:" & vbCrLf & _
           "Zones auto-filled: " & zonesUpdated & vbCrLf & vbCrLf & _
           "Validation summary:" & vbCrLf & _
           summary & vbCrLf & vbCrLf & _
           "Full audit trail available on sheet: """ & CFG_LOG_SHEET & """", _
           vbInformation, "Run Complete"

    wsLog.Activate
    Exit Sub

HandleError:
    RestoreAppState state
    MsgBox "ERROR in RunFullCleaningWorkflow:" & vbCrLf & _
           "Error " & Err.Number & ": " & Err.Description & vbCrLf & _
           "Source: " & Err.Source, _
           vbCritical, "Macro Error"
    Exit Sub

CleanExit:
    RestoreAppState state
End Sub

' ─────────────────────────────────────────────────────────────────────────────
' RunValidationsOnly
' Re-applies all business rules to the current data without importing.
' ─────────────────────────────────────────────────────────────────────────────
Public Sub RunValidationsOnly()
    Dim state As AppState
    Dim ws As Worksheet
    Dim wsLog As Worksheet
    Dim summary As String

    If Not IsTestingFile(ThisWorkbook) Then
        MsgBox "SAFETY STOP: This workbook does not appear to be the TESTING copy.", vbCritical
        Exit Sub
    End If

    On Error GoTo HandleError
    SaveAppState state
    PauseApp

    Set ws = GetWorkingSheet(ThisWorkbook)
    If ws Is Nothing Then
        MsgBox "Working sheet """ & CFG_WORKING_SHEET & """ not found.", vbCritical
        GoTo CleanExit
    End If

    Set wsLog = InitLogSheet(ThisWorkbook)

    summary = RunAllValidations(ws, wsLog)
    FormatLogSheet wsLog

    RestoreAppState state

    MsgBox "Validations complete:" & vbCrLf & vbCrLf & summary, _
           vbInformation, "Validations Done"

    wsLog.Activate
    Exit Sub

HandleError:
    RestoreAppState state
    MsgBox "ERROR in RunValidationsOnly:" & vbCrLf & _
           "Error " & Err.Number & ": " & Err.Description, _
           vbCritical, "Macro Error"
    Exit Sub

CleanExit:
    RestoreAppState state
End Sub

' ─────────────────────────────────────────────────────────────────────────────
' RunZoneDerivationOnly
' Re-runs only the zone derivation logic.
' ─────────────────────────────────────────────────────────────────────────────
Public Sub RunZoneDerivationOnly()
    Dim state As AppState
    Dim ws As Worksheet
    Dim wsLog As Worksheet
    Dim zoneDict As Object
    Dim zonesUpdated As Long

    If Not IsTestingFile(ThisWorkbook) Then
        MsgBox "SAFETY STOP: This workbook does not appear to be the TESTING copy.", vbCritical
        Exit Sub
    End If

    On Error GoTo HandleError
    SaveAppState state
    PauseApp

    Set ws = GetWorkingSheet(ThisWorkbook)
    If ws Is Nothing Then
        MsgBox "Working sheet """ & CFG_WORKING_SHEET & """ not found.", vbCritical
        GoTo CleanExit
    End If

    Set wsLog = InitLogSheet(ThisWorkbook)
    Set zoneDict = BuildZoneDictionary(ThisWorkbook)

    If zoneDict Is Nothing Then
        WriteLog wsLog, 0, "", "Zone Derivation", "", "", "", _
                 "WARNING: Zone dictionary could not be created"
        zonesUpdated = 0
    ElseIf zoneDict.Count = 0 Then
        WriteLog wsLog, 0, "", "Zone Derivation", "", "", "", _
                 "WARNING: Zone Structure sheet is empty or missing"
        zonesUpdated = 0
    Else
        zonesUpdated = ApplyZoneDerivation(ws, wsLog, zoneDict)
    End If

    FormatLogSheet wsLog

    RestoreAppState state

    MsgBox "Zone derivation complete." & vbCrLf & _
           "Zones filled: " & zonesUpdated, _
           vbInformation, "Zone Derivation Done"

    wsLog.Activate
    Exit Sub

HandleError:
    RestoreAppState state
    MsgBox "ERROR in RunZoneDerivationOnly:" & vbCrLf & _
           "Error " & Err.Number & ": " & Err.Description, _
           vbCritical, "Macro Error"
    Exit Sub

CleanExit:
    RestoreAppState state
End Sub

'=============================================================================
' PRIVATE HELPERS
'=============================================================================

' ─────────────────────────────────────────────────────────────────────────────
' IsTestingFile
' Returns True if the workbook path or name contains the configured test text.
' ─────────────────────────────────────────────────────────────────────────────
Private Function IsTestingFile(wb As Workbook) As Boolean
    If wb Is Nothing Then
        IsTestingFile = False
    Else
        IsTestingFile = (InStr(1, wb.FullName, CFG_REQUIRED_TEST_PATH_TEXT, vbTextCompare) > 0)
    End If
End Function

' ─────────────────────────────────────────────────────────────────────────────
' GetWorkingSheet
' Returns the main working worksheet or Nothing.
' ─────────────────────────────────────────────────────────────────────────────
Private Function GetWorkingSheet(wb As Workbook) As Worksheet
    On Error Resume Next
    Set GetWorkingSheet = wb.Worksheets(CFG_WORKING_SHEET)
    On Error GoTo 0
End Function

' ─────────────────────────────────────────────────────────────────────────────
' PickSourceSheet
' Prompts the user to select a worksheet from any open workbook by typing:
'   WorkbookName | SheetName
' Returns Nothing if cancelled or invalid.
' ─────────────────────────────────────────────────────────────────────────────
Private Function PickSourceSheet(prompt As String) As Worksheet
    Dim userInput As Variant
    Dim parts() As String
    Dim wb As Workbook
    Dim ws As Worksheet
    Dim choices As String
    Dim w As Workbook, s As Worksheet

    For Each w In Application.Workbooks
        For Each s In w.Worksheets
            If s.Name <> CFG_LOG_SHEET Then
                choices = choices & w.Name & " | " & s.Name & vbCrLf
            End If
        Next s
    Next w

    userInput = Application.InputBox( _
        prompt & vbCrLf & vbCrLf & _
        "Type exactly: WorkbookName | SheetName" & vbCrLf & _
        "----------------------------------------" & vbCrLf & _
        "Open sheets:" & vbCrLf & choices, _
        "Select Source Sheet", Type:=2)

    If VarType(userInput) = vbBoolean Then
        Set PickSourceSheet = Nothing
        Exit Function
    End If

    If Trim$(CStr(userInput)) = vbNullString Then
        Set PickSourceSheet = Nothing
        Exit Function
    End If

    parts = Split(CStr(userInput), "|")
    If UBound(parts) < 1 Then
        MsgBox "Invalid format. Please type: WorkbookName | SheetName", vbExclamation, "Invalid Input"
        Set PickSourceSheet = Nothing
        Exit Function
    End If

    On Error Resume Next
    Set wb = Application.Workbooks(Trim$(parts(0)))
    If Not wb Is Nothing Then
        Set ws = wb.Worksheets(Trim$(parts(1)))
    End If
    On Error GoTo 0

    If ws Is Nothing Then
        MsgBox "Workbook or sheet not found." & vbCrLf & _
               "Please make sure the file is open and the name is typed exactly.", _
               vbExclamation, "Selection Not Found"
    End If

    Set PickSourceSheet = ws
End Function

' ─────────────────────────────────────────────────────────────────────────────
' FormatLogSheet
' Auto-fits columns and color-codes rows based on action type.
' ─────────────────────────────────────────────────────────────────────────────
Private Sub FormatLogSheet(wsLog As Worksheet)
    Dim lastRow As Long
    Dim i As Long
    Dim action As String

    If wsLog Is Nothing Then Exit Sub

    lastRow = GetLastDataRow(wsLog)
    If lastRow <= 1 Then Exit Sub

    wsLog.Columns("A:H").AutoFit

    For i = 2 To lastRow
        action = CStr(wsLog.Cells(i, 8).Value)

        Select Case True
            Case InStr(1, action, "FILLED", vbTextCompare) > 0
                wsLog.Rows(i).Interior.Color = RGB(198, 239, 206)
            Case InStr(1, action, "CORRECTED", vbTextCompare) > 0
                wsLog.Rows(i).Interior.Color = RGB(255, 235, 156)
            Case InStr(1, action, "CLEARED", vbTextCompare) > 0
                wsLog.Rows(i).Interior.Color = RGB(255, 199, 206)
            Case InStr(1, action, "WARNING", vbTextCompare) > 0
                wsLog.Rows(i).Interior.Color = RGB(255, 165, 0)
            Case InStr(1, action, "IMPORTED", vbTextCompare) > 0
                wsLog.Rows(i).Interior.Color = RGB(221, 235, 247)
            Case Else
                wsLog.Rows(i).Interior.ColorIndex = xlNone
        End Select
    Next i
End Sub
