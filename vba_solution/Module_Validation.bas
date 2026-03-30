Attribute VB_Name = "Module_Validation"
'============================================================================
' Module_Validation
' Purpose : Apply the business rules row-by-row.
'           Each rule logs changes and returns a count of rows affected.
'
' IMPORTANT:
' - This module is aligned to the WORKING file structure.
' - Key column used for logging = SieSales ID
' - FC column used for corrections = FC relevant
' - Rule 2 (Naming/SP7) is treated as OPTIONAL unless a "Naming" column exists
'============================================================================
Option Explicit

' ─────────────────────────────────────────────────────────────────────────────
' Optional Rule 2 settings
' These are kept local because "Naming" was NOT present in the headers you sent.
' If a Naming column exists in the real file, this rule will run.
' If not, the rule will log one warning and skip safely.
' ─────────────────────────────────────────────────────────────────────────────
Private Const OPTIONAL_NAMING_HEADER As String = "Naming"
Private Const OPTIONAL_H2_NAMING_TARGET As String = "SP7"

' ─────────────────────────────────────────────────────────────────────────────
' RunAllValidations
' Orchestrates all business-rule passes in one call.
' Returns a summary string.
' ─────────────────────────────────────────────────────────────────────────────
Public Function RunAllValidations(ws As Worksheet, wsLog As Worksheet) As String
    Dim n1 As Long, n2 As Long, n3 As Long, n4H2 As Long, n4H3 As Long

    n1 = Rule1_ClosedWonFC(ws, wsLog)
    n2 = Rule2_H2Naming_Optional(ws, wsLog)
    n3 = Rule3_ZL_Description(ws, wsLog)
    n4H2 = Rule4_BSS_H2(ws, wsLog)
    n4H3 = Rule4_BSS_H3(ws, wsLog)

    RunAllValidations = _
        "Rule 1 – Closed Won -> FC relevant:      " & n1 & " row(s)" & vbCrLf & _
        "Rule 2 – H2 Naming -> SP7 (optional):    " & n2 & " row(s)" & vbCrLf & _
        "Rule 3 – #ZL + closed stage -> blank FC: " & n3 & " row(s)" & vbCrLf & _
        "Rule 4a – H2 BSS correction:             " & n4H2 & " row(s)" & vbCrLf & _
        "Rule 4b – H3 BSS correction:             " & n4H3 & " row(s)"
End Function

' ─────────────────────────────────────────────────────────────────────────────
' Rule1_ClosedWonFC
' If Stage = "Closed Won" and FC relevant is blank -> set "FC".
' Only blanks are filled; existing non-blank values are not overwritten.
' ─────────────────────────────────────────────────────────────────────────────
Public Function Rule1_ClosedWonFC(ws As Worksheet, wsLog As Worksheet) As Long
    Dim colStage As Long
    Dim colFC As Long
    Dim colKey As Long
    Dim lastRow As Long
    Dim i As Long
    Dim stageVal As String
    Dim fcVal As String
    Dim rowKey As String
    Dim changed As Long

    changed = 0

    colStage = AssertColIndex(ws, COL_STAGE, CFG_HEADER_ROW)
    colFC = AssertColIndex(ws, COL_FC_RELEVANT_WORKING, CFG_HEADER_ROW)
    colKey = AssertColIndex(ws, COL_WORKING_KEY, CFG_HEADER_ROW)
    lastRow = GetLastDataRow(ws)

    If lastRow <= CFG_HEADER_ROW Then
        Rule1_ClosedWonFC = 0
        Exit Function
    End If

    For i = CFG_HEADER_ROW + 1 To lastRow
        stageVal = Trim$(CStr(ws.Cells(i, colStage).Value))
        If StrComp(stageVal, RULE_CLOSED_WON, vbTextCompare) = 0 Then
            fcVal = Trim$(CStr(ws.Cells(i, colFC).Value))
            If fcVal = vbNullString Then
                rowKey = GetRowKey(ws, i, colKey)

                WriteLog wsLog, i, rowKey, _
                         "Rule 1: Closed Won -> FC relevant", _
                         COL_FC_RELEVANT_WORKING, _
                         fcVal, RULE_FC_VALUE, "FILLED"

                ws.Cells(i, colFC).Value = RULE_FC_VALUE
                changed = changed + 1
            End If
        End If
    Next i

    Rule1_ClosedWonFC = changed
End Function

' ─────────────────────────────────────────────────────────────────────────────
' Rule2_H2Naming_Optional
' If Business Type = "H2" -> Naming field should be "SP7".
'
' SAFE BEHAVIOR:
' - If the "Naming" column does not exist, the rule is skipped.
' - One warning is written to the log instead of crashing the macro.
' ─────────────────────────────────────────────────────────────────────────────
Public Function Rule2_H2Naming_Optional(ws As Worksheet, wsLog As Worksheet) As Long
    Dim colBizType As Long
    Dim colNaming As Long
    Dim colKey As Long
    Dim lastRow As Long
    Dim i As Long
    Dim bizType As String
    Dim namingVal As String
    Dim rowKey As String
    Dim changed As Long

    changed = 0

    colBizType = GetColIndex(ws, COL_BUSINESS_TYPE, CFG_HEADER_ROW)
    colNaming = GetColIndex(ws, OPTIONAL_NAMING_HEADER, CFG_HEADER_ROW)
    colKey = GetColIndex(ws, COL_WORKING_KEY, CFG_HEADER_ROW)

    If colBizType = 0 Then
        WriteLog wsLog, 0, "", _
                 "Rule 2: H2 Naming", _
                 OPTIONAL_NAMING_HEADER, "", "", _
                 "WARNING: Business Type column not found; rule skipped"
        Rule2_H2Naming_Optional = 0
        Exit Function
    End If

    If colNaming = 0 Then
        WriteLog wsLog, 0, "", _
                 "Rule 2: H2 Naming", _
                 OPTIONAL_NAMING_HEADER, "", "", _
                 "WARNING: Naming column not found; rule skipped"
        Rule2_H2Naming_Optional = 0
        Exit Function
    End If

    lastRow = GetLastDataRow(ws)
    If lastRow <= CFG_HEADER_ROW Then
        Rule2_H2Naming_Optional = 0
        Exit Function
    End If

    For i = CFG_HEADER_ROW + 1 To lastRow
        bizType = Trim$(CStr(ws.Cells(i, colBizType).Value))

        If StrComp(bizType, RULE_H2_BIZ_TYPE, vbTextCompare) = 0 Then
            namingVal = Trim$(CStr(ws.Cells(i, colNaming).Value))

            If StrComp(namingVal, OPTIONAL_H2_NAMING_TARGET, vbTextCompare) <> 0 Then
                rowKey = GetRowKey(ws, i, colKey)

                WriteLog wsLog, i, rowKey, _
                         "Rule 2: H2 Naming", _
                         OPTIONAL_NAMING_HEADER, _
                         namingVal, OPTIONAL_H2_NAMING_TARGET, "CORRECTED"

                ws.Cells(i, colNaming).Value = OPTIONAL_H2_NAMING_TARGET
                changed = changed + 1
            End If
        End If
    Next i

    Rule2_H2Naming_Optional = changed
End Function

' ─────────────────────────────────────────────────────────────────────────────
' Rule3_ZL_Description
' If Description contains "#ZL" AND Stage is
'   "Closed / Cancelled" or "Closed Lost"
' then FC relevant must be blank.
' ─────────────────────────────────────────────────────────────────────────────
Public Function Rule3_ZL_Description(ws As Worksheet, wsLog As Worksheet) As Long
    Dim colDesc As Long
    Dim colStage As Long
    Dim colFC As Long
    Dim colKey As Long
    Dim lastRow As Long
    Dim i As Long
    Dim descVal As String
    Dim stageVal As String
    Dim fcVal As String
    Dim rowKey As String
    Dim changed As Long
    Dim stageMatch As Boolean

    changed = 0

    colDesc = AssertColIndex(ws, COL_DESCRIPTION, CFG_HEADER_ROW)
    colStage = AssertColIndex(ws, COL_STAGE, CFG_HEADER_ROW)
    colFC = AssertColIndex(ws, COL_FC_RELEVANT_WORKING, CFG_HEADER_ROW)
    colKey = AssertColIndex(ws, COL_WORKING_KEY, CFG_HEADER_ROW)
    lastRow = GetLastDataRow(ws)

    If lastRow <= CFG_HEADER_ROW Then
        Rule3_ZL_Description = 0
        Exit Function
    End If

    For i = CFG_HEADER_ROW + 1 To lastRow
        descVal = CStr(ws.Cells(i, colDesc).Value)
        stageVal = Trim$(CStr(ws.Cells(i, colStage).Value))

        stageMatch = _
            (StrComp(stageVal, RULE_CLOSED_CANCELLED, vbTextCompare) = 0) Or _
            (StrComp(stageVal, RULE_CLOSED_LOST, vbTextCompare) = 0)

        If InStr(1, descVal, RULE_ZL_MARKER, vbTextCompare) > 0 And stageMatch Then
            fcVal = CStr(ws.Cells(i, colFC).Value)

            If Trim$(fcVal) <> vbNullString Then
                rowKey = GetRowKey(ws, i, colKey)

                WriteLog wsLog, i, rowKey, _
                         "Rule 3: #ZL -> blank FC relevant", _
                         COL_FC_RELEVANT_WORKING, _
                         fcVal, "", "CLEARED"

                ws.Cells(i, colFC).ClearContents
                changed = changed + 1
            End If
        End If
    Next i

    Rule3_ZL_Description = changed
End Function

' ─────────────────────────────────────────────────────────────────────────────
' Rule4_BSS_H2
' If the H2 column contains "H2", then
' Business Sub-Segment Short revised must be RULE_H2_BSS.
' ─────────────────────────────────────────────────────────────────────────────
Public Function Rule4_BSS_H2(ws As Worksheet, wsLog As Worksheet) As Long
    Rule4_BSS_H2 = Rule4_BSS_Generic( _
        ws, wsLog, _
        COL_H2, _
        RULE_H2_BIZ_TYPE, _
        RULE_H2_BSS, _
        "Rule 4a: H2 BSS" _
    )
End Function

' ─────────────────────────────────────────────────────────────────────────────
' Rule4_BSS_H3
' If the H3 column contains "H3", then
' Business Sub-Segment Short revised must be RULE_H3_BSS.
' ─────────────────────────────────────────────────────────────────────────────
Public Function Rule4_BSS_H3(ws As Worksheet, wsLog As Worksheet) As Long
    Rule4_BSS_H3 = Rule4_BSS_Generic( _
        ws, wsLog, _
        COL_H3, _
        RULE_H3_BIZ_TYPE, _
        RULE_H3_BSS, _
        "Rule 4b: H3 BSS" _
    )
End Function

'============================================================================
' PRIVATE HELPERS
'============================================================================

' ─────────────────────────────────────────────────────────────────────────────
' Rule4_BSS_Generic
' Generic engine for H2/H3 business sub-segment correction.
' ─────────────────────────────────────────────────────────────────────────────
Private Function Rule4_BSS_Generic(ws As Worksheet, _
                                   wsLog As Worksheet, _
                                   triggerHeader As String, _
                                   triggerValue As String, _
                                   targetBSS As String, _
                                   ruleLabel As String) As Long
    Dim colTrigger As Long
    Dim colBSS As Long
    Dim colKey As Long
    Dim lastRow As Long
    Dim i As Long
    Dim triggerVal As String
    Dim bssVal As String
    Dim rowKey As String
    Dim changed As Long

    changed = 0

    colTrigger = AssertColIndex(ws, triggerHeader, CFG_HEADER_ROW)
    colBSS = AssertColIndex(ws, COL_BSS_REVISED, CFG_HEADER_ROW)
    colKey = AssertColIndex(ws, COL_WORKING_KEY, CFG_HEADER_ROW)
    lastRow = GetLastDataRow(ws)

    If lastRow <= CFG_HEADER_ROW Then
        Rule4_BSS_Generic = 0
        Exit Function
    End If

    For i = CFG_HEADER_ROW + 1 To lastRow
        triggerVal = Trim$(CStr(ws.Cells(i, colTrigger).Value))

        If StrComp(triggerVal, triggerValue, vbTextCompare) = 0 Then
            bssVal = Trim$(CStr(ws.Cells(i, colBSS).Value))

            If StrComp(bssVal, targetBSS, vbTextCompare) <> 0 Then
                rowKey = GetRowKey(ws, i, colKey)

                WriteLog wsLog, i, rowKey, _
                         ruleLabel, _
                         COL_BSS_REVISED, _
                         bssVal, targetBSS, "CORRECTED"

                ws.Cells(i, colBSS).Value = targetBSS
                changed = changed + 1
            End If
        End If
    Next i

    Rule4_BSS_Generic = changed
End Function

' ─────────────────────────────────────────────────────────────────────────────
' GetRowKey
' Returns the SieSales ID for the current row if available.
' ─────────────────────────────────────────────────────────────────────────────
Private Function GetRowKey(ws As Worksheet, ByVal rowNum As Long, ByVal colKey As Long) As String
    If colKey > 0 Then
        GetRowKey = Trim$(CStr(ws.Cells(rowNum, colKey).Value))
    Else
        GetRowKey = vbNullString
    End If
End Function
