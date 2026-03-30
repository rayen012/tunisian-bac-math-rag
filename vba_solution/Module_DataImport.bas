Attribute VB_Name = "Module_DataImport"
'============================================================================
' Module_DataImport
' Purpose : Handles the data-refresh workflow:
'             1. Clear old data rows (below header) while preserving formula columns
'             2. Paste/import new data from a SIESALES source workbook
'             3. (Optional) Yellow-zone lookup from a previous-file mapping
'
' IMPORTANT: This module ONLY operates on the TESTING copy of the file.
'            Never pass the live production workbook here.
'============================================================================
Option Explicit

' ─────────────────────────────────────────────────────────────────────────────
' ClearOldData
' Deletes all data rows below the header while PRESERVING formula columns
' listed in CFG_PRESERVE_HEADERS (comma-separated in Module_Config).
'
' Strategy:
'   - Collect column indices that must be preserved
'   - For each data row, clear only the non-preserved columns
'   - This keeps H2 / H3 formula columns intact
' ─────────────────────────────────────────────────────────────────────────────
Public Sub ClearOldData(ws As Worksheet)
    Dim lastRow     As Long
    Dim lastCol     As Long
    Dim i           As Long, j As Long
    Dim preserveArr() As String
    Dim preserveCols() As Long
    Dim k           As Long
    Dim isPreserved As Boolean
    Dim headerCount As Long

    lastRow = GetLastDataRow(ws)
    lastCol = ws.UsedRange.Column + ws.UsedRange.Columns.Count - 1

    ' Build the list of column indices to PRESERVE
    preserveArr = SplitTrim(CFG_PRESERVE_HEADERS, ",")
    headerCount = UBound(preserveArr) + 1
    ReDim preserveCols(0 To headerCount - 1)

    For k = 0 To UBound(preserveArr)
        preserveCols(k) = GetColIndex(ws, preserveArr(k), CFG_HEADER_ROW)
        ' If 0, the header wasn't found — we'll just skip preserving it
    Next k

    ' Clear row-by-row, skipping preserved columns
    For i = CFG_HEADER_ROW + 1 To lastRow
        For j = 1 To lastCol
            isPreserved = False
            For k = 0 To UBound(preserveCols)
                If preserveCols(k) = j And preserveCols(k) > 0 Then
                    isPreserved = True
                    Exit For
                End If
            Next k
            If Not isPreserved Then
                ws.Cells(i, j).ClearContents
            End If
        Next j
    Next i
End Sub

' ─────────────────────────────────────────────────────────────────────────────
' ImportFromSIESALES
' Copies data from a SIESALES source workbook/sheet into the data sheet.
' Maps columns by header name so column order differences are handled.
'
' Parameters:
'   wsDest      : The destination (testing) data sheet
'   wsSrc       : The SIESALES source sheet
'   wsLog       : Log sheet for recording import actions
'
' Column mapping is defined in the local colMap array below.
' Extend it as needed — add more Source→Destination header pairs.
' ─────────────────────────────────────────────────────────────────────────────
Public Sub ImportFromSIESALES(wsDest As Worksheet, _
                               wsSrc  As Worksheet, _
                               wsLog  As Worksheet)
    ' ── Define column mapping: Source header → Destination header ────────────
    ' Adjust these pairs to match your actual SIESALES export column names.
    Dim mapping(0 To 4, 0 To 1) As String   ' (row, 0=src, 1=dest)
    mapping(0, 0) = "Opportunity ID"         : mapping(0, 1) = COL_OPPORTUNITY_ID
    mapping(1, 0) = "Country of Installation": mapping(1, 1) = COL_COUNTRY_INSTALL
    mapping(2, 0) = "Stage"                  : mapping(2, 1) = COL_STAGE
    mapping(3, 0) = "Description"            : mapping(3, 1) = COL_DESCRIPTION
    mapping(4, 0) = "Zone"                   : mapping(4, 1) = COL_ZONE
    ' ─────────────────────────────────────────────────────────────────────────
    ' ADD more rows here as needed, adjusting the array dimension above:
    '   mapping(5, 0) = "Source Header"  : mapping(5, 1) = "Dest Header"
    ' ─────────────────────────────────────────────────────────────────────────

    Dim srcLastRow  As Long
    Dim destRow     As Long
    Dim i           As Long, m As Long
    Dim srcCols()   As Long, destCols() As Long
    Dim pairCount   As Long
    Dim oppId       As String

    pairCount = UBound(mapping, 1) + 1
    ReDim srcCols(0 To pairCount - 1)
    ReDim destCols(0 To pairCount - 1)

    ' Resolve all column indices once before the row loop
    For m = 0 To pairCount - 1
        srcCols(m)  = AssertColIndex(wsSrc,  mapping(m, 0))
        destCols(m) = AssertColIndex(wsDest, mapping(m, 1))
    Next m

    srcLastRow = GetLastDataRow(wsSrc)
    destRow    = CFG_HEADER_ROW + 1   ' Start writing at first data row of dest

    For i = CFG_HEADER_ROW + 1 To srcLastRow
        For m = 0 To pairCount - 1
            wsDest.Cells(destRow, destCols(m)).Value = wsSrc.Cells(i, srcCols(m)).Value
        Next m

        ' Log the import (use Opportunity ID for traceability)
        oppId = CStr(wsDest.Cells(destRow, destCols(0)).Value)
        WriteLog wsLog, destRow, oppId, "Import", "All mapped columns", "", "", "IMPORTED"

        destRow = destRow + 1
    Next i
End Sub

' ─────────────────────────────────────────────────────────────────────────────
' FillYellowZoneFromPreviousFile
' Fills the "yellow zone" columns by looking up Opportunity ID in a previous
' version of the file and copying values for the mapped columns.
'
' Parameters:
'   wsDest    : Current (testing) data sheet
'   wsPrev    : Sheet from the previous file (open in the same Excel instance)
'   wsLog     : Log sheet
'   yellowCols: Array of column header names that constitute the yellow zone
'
' Assumption: Opportunity ID is the join key.
' ─────────────────────────────────────────────────────────────────────────────
Public Sub FillYellowZoneFromPreviousFile(wsDest     As Worksheet, _
                                          wsPrev     As Worksheet, _
                                          wsLog      As Worksheet, _
                                          yellowCols() As String)
    ' Build a lookup dictionary: OppId → row number in previous sheet
    Dim prevDict    As Object
    Dim colPrevId   As Long, colDestId As Long
    Dim lastRowPrev As Long, lastRowDest As Long
    Dim i As Long, m As Long
    Dim destColIdx  As Long, prevColIdx As Long
    Dim oppId As String, oldVal As String, newVal As String

    Set prevDict = CreateObject("Scripting.Dictionary")
    prevDict.CompareMode = 1   ' case-insensitive

    colPrevId = AssertColIndex(wsPrev, COL_OPPORTUNITY_ID)
    colDestId = AssertColIndex(wsDest, COL_OPPORTUNITY_ID)

    lastRowPrev = GetLastDataRow(wsPrev)
    lastRowDest = GetLastDataRow(wsDest)

    ' Index previous file: OppId → row
    For i = CFG_HEADER_ROW + 1 To lastRowPrev
        oppId = Trim(wsPrev.Cells(i, colPrevId).Value)
        If oppId <> "" And Not prevDict.Exists(oppId) Then
            prevDict.Add oppId, i
        End If
    Next i

    ' For each yellow-zone column, copy values where OppId matches
    For m = 0 To UBound(yellowCols)
        destColIdx = GetColIndex(wsDest, yellowCols(m))
        prevColIdx = GetColIndex(wsPrev, yellowCols(m))

        ' Only process if both sheets have this column
        If destColIdx = 0 Or prevColIdx = 0 Then GoTo NextCol

        For i = CFG_HEADER_ROW + 1 To lastRowDest
            oppId = Trim(wsDest.Cells(i, colDestId).Value)
            If oppId <> "" And prevDict.Exists(oppId) Then
                Dim prevRow As Long
                prevRow = prevDict(oppId)
                oldVal  = CStr(wsDest.Cells(i, destColIdx).Value)
                newVal  = CStr(wsPrev.Cells(prevRow, prevColIdx).Value)

                If oldVal <> newVal Then
                    WriteLog wsLog, i, oppId, _
                             "Yellow Zone Fill", yellowCols(m), _
                             oldVal, newVal, "FILLED FROM PREV"
                    wsDest.Cells(i, destColIdx).Value = newVal
                End If
            End If
        Next i

NextCol:
    Next m
End Sub
