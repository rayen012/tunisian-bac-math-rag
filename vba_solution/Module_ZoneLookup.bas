Attribute VB_Name = "Module_ZoneLookup"
'============================================================================
' Module_ZoneLookup
' Purpose : Build an in-memory VBA Dictionary from the "Zone Structure" sheet
'           and use it to derive the Zone for rows where it is blank or "N/A".
'
' WHY Dictionary over worksheet VLOOKUP formulas?
' - Loaded once -> fast lookups
' - Safer if columns move
' - No leftover formulas in cells
' - Case-insensitive matching
'============================================================================
Option Explicit

' ─────────────────────────────────────────────────────────────────────────────
' BuildZoneDictionary
' Reads the Zone Structure sheet and returns a Scripting.Dictionary keyed by
' Country -> Zone.
' ─────────────────────────────────────────────────────────────────────────────
Public Function BuildZoneDictionary(wb As Workbook) As Object
    Dim wsZone As Worksheet
    Dim dict As Object
    Dim lastRow As Long
    Dim colCountry As Long
    Dim colZone As Long
    Dim i As Long
    Dim countryVal As String
    Dim zoneVal As String

    Set dict = CreateObject("Scripting.Dictionary")
    dict.CompareMode = 1   ' vbTextCompare

    If wb Is Nothing Then
        Set BuildZoneDictionary = dict
        Exit Function
    End If

    On Error Resume Next
    Set wsZone = wb.Worksheets(CFG_ZONE_SHEET)
    On Error GoTo 0

    If wsZone Is Nothing Then
        Set BuildZoneDictionary = dict
        Exit Function
    End If

    colCountry = GetColIndex(wsZone, ZONE_COL_COUNTRY, CFG_HEADER_ROW)
    colZone = GetColIndex(wsZone, ZONE_COL_ZONE, CFG_HEADER_ROW)

    If colCountry = 0 Or colZone = 0 Then
        Set BuildZoneDictionary = dict
        Exit Function
    End If

    lastRow = GetLastDataRow(wsZone)
    If lastRow <= CFG_HEADER_ROW Then
        Set BuildZoneDictionary = dict
        Exit Function
    End If

    For i = CFG_HEADER_ROW + 1 To lastRow
        countryVal = Trim$(CStr(wsZone.Cells(i, colCountry).Value))
        zoneVal = Trim$(CStr(wsZone.Cells(i, colZone).Value))

        If countryVal <> vbNullString And zoneVal <> vbNullString Then
            If Not dict.Exists(countryVal) Then
                dict.Add countryVal, zoneVal
            End If
        End If
    Next i

    Set BuildZoneDictionary = dict
End Function

' ─────────────────────────────────────────────────────────────────────────────
' ApplyZoneDerivation
' Fills Zone where current Zone is blank or "N/A", using Country of
' Installation and the zone dictionary.
'
' Returns the number of updated rows.
' ─────────────────────────────────────────────────────────────────────────────
Public Function ApplyZoneDerivation(ws As Worksheet, _
                                    wsLog As Worksheet, _
                                    zoneDict As Object) As Long
    Dim colZone As Long
    Dim colCountry As Long
    Dim colKey As Long
    Dim lastRow As Long
    Dim i As Long
    Dim zoneVal As String
    Dim countryVal As String
    Dim derivedZone As String
    Dim rowKey As String
    Dim updated As Long

    updated = 0

    If ws Is Nothing Then
        ApplyZoneDerivation = 0
        Exit Function
    End If

    If zoneDict Is Nothing Then
        ApplyZoneDerivation = 0
        Exit Function
    End If

    colZone = AssertColIndex(ws, COL_ZONE, CFG_HEADER_ROW)
    colCountry = AssertColIndex(ws, COL_COUNTRY_INSTALL, CFG_HEADER_ROW)
    colKey = GetColIndex(ws, COL_WORKING_KEY, CFG_HEADER_ROW)

    lastRow = GetLastDataRow(ws)
    If lastRow <= CFG_HEADER_ROW Then
        ApplyZoneDerivation = 0
        Exit Function
    End If

    For i = CFG_HEADER_ROW + 1 To lastRow
        zoneVal = Trim$(CStr(ws.Cells(i, colZone).Value))

        If zoneVal = vbNullString Or StrComp(zoneVal, RULE_NA_ZONE, vbTextCompare) = 0 Then
            countryVal = Trim$(CStr(ws.Cells(i, colCountry).Value))

            If countryVal <> vbNullString Then
                rowKey = GetRowKeyForZone(ws, i, colKey)

                If zoneDict.Exists(countryVal) Then
                    derivedZone = CStr(zoneDict(countryVal))

                    WriteLog wsLog, i, rowKey, _
                             "Zone Derivation", _
                             COL_ZONE, _
                             zoneVal, derivedZone, "AUTO-FILLED"

                    ws.Cells(i, colZone).Value = derivedZone
                    updated = updated + 1
                Else
                    WriteLog wsLog, i, rowKey, _
                             "Zone Derivation", _
                             COL_ZONE, _
                             zoneVal, "", _
                             "WARNING: Country not in Zone Structure: " & countryVal
                End If
            End If
        End If
    Next i

    ApplyZoneDerivation = updated
End Function

' ─────────────────────────────────────────────────────────────────────────────
' GetRowKeyForZone
' Returns the working-file key (SieSales ID) for logging.
' ─────────────────────────────────────────────────────────────────────────────
Private Function GetRowKeyForZone(ws As Worksheet, ByVal rowNum As Long, ByVal colKey As Long) As String
    If colKey > 0 Then
        GetRowKeyForZone = Trim$(CStr(ws.Cells(rowNum, colKey).Value))
    Else
        GetRowKeyForZone = vbNullString
    End If
End Function
