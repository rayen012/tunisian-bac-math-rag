Attribute VB_Name = "Module_ZoneLookup"
'============================================================================
' Module_ZoneLookup
' Purpose : Build an in-memory VBA Dictionary from the "Zone Structure" sheet
'           and use it to derive the Zone for rows where it is blank or "N/A".
'
' WHY Dictionary over worksheet VLOOKUP formulas?
' ┌─────────────────────────────────────────────────────────────────────────┐
' │  VBA Dictionary (chosen here)        │  Worksheet VLOOKUP formula       │
' ├──────────────────────────────────────┼──────────────────────────────────┤
' │ + Loaded once → O(1) per lookup      │ - Recalculates on every change   │
' │ + Survives column moves in Zone sheet│ - Breaks if Zone sheet is moved  │
' │ + Case-insensitive key matching      │ - Case sensitive by default       │
' │ + No formula residue in cells        │ - Leaves formula strings in cells │
' │ + Works even if Zone sheet is hidden │ + No VBA dependency              │
' │ - Requires VBA to run               │ + Visible to user in cell         │
' └──────────────────────────────────────┴──────────────────────────────────┘
' For a production macro that runs automatically, Dictionary is clearly better.
'============================================================================
Option Explicit

' ─────────────────────────────────────────────────────────────────────────────
' BuildZoneDictionary
' Reads the Zone Structure sheet and returns a Scripting.Dictionary keyed by
' Country (lowercase) → Zone string.
' ─────────────────────────────────────────────────────────────────────────────
Public Function BuildZoneDictionary(wb As Workbook) As Object   ' Scripting.Dictionary
    Dim wsZone  As Worksheet
    Dim dict    As Object
    Dim lastRow As Long
    Dim colCty  As Long, colZone As Long
    Dim i       As Long
    Dim country As String, zone As String

    Set dict = CreateObject("Scripting.Dictionary")
    dict.CompareMode = 1   ' vbTextCompare → case-insensitive keys

    ' Locate the Zone Structure sheet
    On Error Resume Next
    Set wsZone = wb.Worksheets(CFG_ZONE_SHEET)
    On Error GoTo 0

    If wsZone Is Nothing Then
        ' No Zone Structure sheet → return empty dictionary; caller handles this
        Set BuildZoneDictionary = dict
        Exit Function
    End If

    ' Locate the required columns by header name (robust to column moves)
    colCty  = GetColIndex(wsZone, ZONE_COL_COUNTRY)
    colZone = GetColIndex(wsZone, ZONE_COL_ZONE)

    If colCty = 0 Or colZone = 0 Then
        ' Headers not found → return empty dictionary
        Set BuildZoneDictionary = dict
        Exit Function
    End If

    lastRow = GetLastDataRow(wsZone)

    For i = CFG_HEADER_ROW + 1 To lastRow
        country = Trim(wsZone.Cells(i, colCty).Value)
        zone    = Trim(wsZone.Cells(i, colZone).Value)

        If country <> "" And zone <> "" Then
            If Not dict.Exists(country) Then
                dict.Add country, zone
            End If
        End If
    Next i

    Set BuildZoneDictionary = dict
End Function

' ─────────────────────────────────────────────────────────────────────────────
' ApplyZoneDerivation
' Iterates all data rows; where Zone is blank or "N/A", looks up the country
' in the dictionary and fills the Zone cell.
' Returns the number of rows updated.
' ─────────────────────────────────────────────────────────────────────────────
Public Function ApplyZoneDerivation(ws As Worksheet, _
                                    wsLog As Worksheet, _
                                    zoneDict As Object) As Long
    Dim colZone    As Long, colCountry As Long, colOppId As Long
    Dim lastRow    As Long
    Dim i          As Long
    Dim zoneVal    As String, country As String, derivedZone As String
    Dim oppId      As String
    Dim updated    As Long

    updated = 0

    ' Resolve column indices once
    colZone    = AssertColIndex(ws, COL_ZONE)
    colCountry = AssertColIndex(ws, COL_COUNTRY_INSTALL)
    colOppId   = GetColIndex(ws, COL_OPPORTUNITY_ID)   ' optional — for logging

    lastRow = GetLastDataRow(ws)

    For i = CFG_HEADER_ROW + 1 To lastRow
        zoneVal = Trim(ws.Cells(i, colZone).Value)

        ' Only act if Zone is blank or N/A
        If zoneVal = "" Or UCase(zoneVal) = UCase(RULE_NA_ZONE) Then
            country = Trim(ws.Cells(i, colCountry).Value)

            If country <> "" Then
                If zoneDict.Exists(country) Then
                    derivedZone = zoneDict(country)
                    oppId = IIf(colOppId > 0, CStr(ws.Cells(i, colOppId).Value), "")

                    WriteLog wsLog, i, oppId, _
                             "Zone Derivation", COL_ZONE, _
                             zoneVal, derivedZone, "AUTO-FILLED"

                    ws.Cells(i, colZone).Value = derivedZone
                    updated = updated + 1
                Else
                    ' Country exists but no mapping found — log as warning
                    oppId = IIf(colOppId > 0, CStr(ws.Cells(i, colOppId).Value), "")
                    WriteLog wsLog, i, oppId, _
                             "Zone Derivation", COL_ZONE, _
                             zoneVal, "", "WARNING: Country not in Zone Structure: " & country
                End If
            End If
        End If
    Next i

    ApplyZoneDerivation = updated
End Function
