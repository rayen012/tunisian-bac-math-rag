Attribute VB_Name = "Module_Helpers"
'============================================================================
' Module_Helpers
' Purpose : Low-level utilities:
'             - Column-index lookup by header name
'             - Log-sheet initialisation and row writing
'             - Application-state save/restore
'             - Split of a comma-delimited string
'============================================================================
Option Explicit

' ─────────────────────────────────────────────────────────────────────────────
' Type used to snapshot and restore Excel's application state
' ─────────────────────────────────────────────────────────────────────────────
Public Type AppState
    Calculation   As XlCalculation
    ScreenUpdate  As Boolean
    EnableEvents  As Boolean
End Type

' ─────────────────────────────────────────────────────────────────────────────
' GetColIndex
' Returns the 1-based column index of the first cell in headerRow whose
' value matches headerName (case-insensitive).
' Returns 0 if not found.
' ─────────────────────────────────────────────────────────────────────────────
Public Function GetColIndex(ws As Worksheet, _
                            headerName As String, _
                            Optional headerRow As Long = 1) As Long
    Dim c As Range
    Dim lastCol As Long

    lastCol = ws.Cells(headerRow, ws.Columns.Count).End(xlToLeft).Column
    If lastCol < 1 Then
        GetColIndex = 0
        Exit Function
    End If

    For Each c In ws.Range(ws.Cells(headerRow, 1), ws.Cells(headerRow, lastCol))
        If LCase(Trim(c.Value)) = LCase(Trim(headerName)) Then
            GetColIndex = c.Column
            Exit Function
        End If
    Next c

    GetColIndex = 0   ' not found
End Function

' ─────────────────────────────────────────────────────────────────────────────
' AssertColIndex
' Like GetColIndex but raises an error with a friendly message if not found.
' ─────────────────────────────────────────────────────────────────────────────
Public Function AssertColIndex(ws As Worksheet, _
                               headerName As String, _
                               Optional headerRow As Long = 1) As Long
    Dim idx As Long
    idx = GetColIndex(ws, headerName, headerRow)
    If idx = 0 Then
        Err.Raise vbObjectError + 1001, "AssertColIndex", _
            "Column header not found: """ & headerName & """ in sheet """ & ws.Name & """"
    End If
    AssertColIndex = idx
End Function

' ─────────────────────────────────────────────────────────────────────────────
' SplitTrim
' Splits a delimited string and trims each element. Returns a 0-based array.
' ─────────────────────────────────────────────────────────────────────────────
Public Function SplitTrim(s As String, Optional delimiter As String = ",") As String()
    Dim parts() As String
    Dim i As Long
    parts = Split(s, delimiter)
    For i = 0 To UBound(parts)
        parts(i) = Trim(parts(i))
    Next i
    SplitTrim = parts
End Function

' ─────────────────────────────────────────────────────────────────────────────
' SaveAppState / RestoreAppState
' ─────────────────────────────────────────────────────────────────────────────
Public Sub SaveAppState(ByRef state As AppState)
    state.Calculation  = Application.Calculation
    state.ScreenUpdate = Application.ScreenUpdating
    state.EnableEvents = Application.EnableEvents
End Sub

Public Sub PauseApp()
    Application.ScreenUpdating  = False
    Application.EnableEvents    = False
    Application.Calculation     = xlCalculationManual
End Sub

Public Sub RestoreAppState(ByRef state As AppState)
    Application.Calculation     = state.Calculation
    Application.ScreenUpdating  = state.ScreenUpdate
    Application.EnableEvents    = state.EnableEvents
End Sub

' ─────────────────────────────────────────────────────────────────────────────
' InitLogSheet
' Creates (or clears) the run-log worksheet and writes a header row.
' Returns the log sheet object.
' ─────────────────────────────────────────────────────────────────────────────
Public Function InitLogSheet(wb As Workbook) As Worksheet
    Dim ws As Worksheet

    ' Try to find existing log sheet
    On Error Resume Next
    Set ws = wb.Worksheets(CFG_LOG_SHEET)
    On Error GoTo 0

    If ws Is Nothing Then
        Set ws = wb.Worksheets.Add(After:=wb.Worksheets(wb.Worksheets.Count))
        ws.Name = CFG_LOG_SHEET
    Else
        ws.Cells.ClearContents
    End If

    ' Write header row
    With ws
        .Cells(1, 1).Value = "Timestamp"
        .Cells(1, 2).Value = "Row"
        .Cells(1, 3).Value = "Opportunity ID"
        .Cells(1, 4).Value = "Rule"
        .Cells(1, 5).Value = "Field Changed"
        .Cells(1, 6).Value = "Old Value"
        .Cells(1, 7).Value = "New Value"
        .Cells(1, 8).Value = "Action"

        ' Bold header
        .Range(.Cells(1, 1), .Cells(1, 8)).Font.Bold = True
        .Columns("A:H").AutoFit
    End With

    Set InitLogSheet = ws
End Function

' ─────────────────────────────────────────────────────────────────────────────
' WriteLog
' Appends one entry to the log sheet.
' ─────────────────────────────────────────────────────────────────────────────
Public Sub WriteLog(wsLog As Worksheet, _
                    dataRow As Long, _
                    oppId As String, _
                    ruleName As String, _
                    fieldName As String, _
                    oldVal As String, _
                    newVal As String, _
                    action As String)

    Dim nextRow As Long
    nextRow = wsLog.Cells(wsLog.Rows.Count, 1).End(xlUp).Row + 1

    wsLog.Cells(nextRow, 1).Value = Now
    wsLog.Cells(nextRow, 2).Value = dataRow
    wsLog.Cells(nextRow, 3).Value = oppId
    wsLog.Cells(nextRow, 4).Value = ruleName
    wsLog.Cells(nextRow, 5).Value = fieldName
    wsLog.Cells(nextRow, 6).Value = oldVal
    wsLog.Cells(nextRow, 7).Value = newVal
    wsLog.Cells(nextRow, 8).Value = action
End Sub

' ─────────────────────────────────────────────────────────────────────────────
' GetLastDataRow
' Returns the last row that has data in any column of the sheet.
' Relies on UsedRange to avoid column-specific bias.
' ─────────────────────────────────────────────────────────────────────────────
Public Function GetLastDataRow(ws As Worksheet) As Long
    GetLastDataRow = ws.UsedRange.Row + ws.UsedRange.Rows.Count - 1
End Function
