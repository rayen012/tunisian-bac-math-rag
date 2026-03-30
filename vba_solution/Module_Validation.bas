Attribute VB_Name = "Module_Validation"
'============================================================================
' Module_Validation
' Purpose : Apply all five business rules row-by-row.
'           Each rule is its own Sub so it can be tested independently.
'           All rules log changes and return a count of rows affected.
'============================================================================
Option Explicit

' ─────────────────────────────────────────────────────────────────────────────
' RunAllValidations
' Orchestrates all business-rule passes in one call.
' Returns a summary string.
' ─────────────────────────────────────────────────────────────────────────────
Public Function RunAllValidations(ws As Worksheet, wsLog As Worksheet) As String
    Dim n1 As Long, n2 As Long, n3 As Long, n4H2 As Long, n4H3 As Long

    n1   = Rule1_ClosedWonFC(ws, wsLog)
    n2   = Rule2_H2Naming(ws, wsLog)
    n3   = Rule3_ZL_Description(ws, wsLog)
    n4H2 = Rule4_BSS_H2(ws, wsLog)
    n4H3 = Rule4_BSS_H3(ws, wsLog)

    RunAllValidations = _
        "Rule 1 – Closed Won → FC:          " & n1   & " row(s)" & vbCrLf & _
        "Rule 2 – H2 Naming → SP7:          " & n2   & " row(s)" & vbCrLf & _
        "Rule 3 – #ZL Description blank FC: " & n3   & " row(s)" & vbCrLf & _
        "Rule 4a – H2 BSS correction:       " & n4H2 & " row(s)" & vbCrLf & _
        "Rule 4b – H3 BSS correction:       " & n4H3 & " row(s)"
End Function

' ─────────────────────────────────────────────────────────────────────────────
' Rule1_ClosedWonFC
' Business rule: If Stage = "Closed Won" and FC Relevant is blank → set "FC".
' Only blanks are filled; existing non-blank values are never overwritten.
' ─────────────────────────────────────────────────────────────────────────────
Public Function Rule1_ClosedWonFC(ws As Worksheet, wsLog As Worksheet) As Long
    Dim colStage  As Long, colFC As Long, colOppId As Long
    Dim lastRow   As Long, i As Long
    Dim stage     As String, fcVal As String, oppId As String
    Dim changed   As Long

    changed = 0

    colStage  = AssertColIndex(ws, COL_STAGE)
    colFC     = AssertColIndex(ws, COL_FC_RELEVANT)
    colOppId  = GetColIndex(ws, COL_OPPORTUNITY_ID)
    lastRow   = GetLastDataRow(ws)

    For i = CFG_HEADER_ROW + 1 To lastRow
        stage = Trim(ws.Cells(i, colStage).Value)
        If UCase(stage) = UCase(RULE_CLOSED_WON) Then
            fcVal = Trim(ws.Cells(i, colFC).Value)
            If fcVal = "" Then
                oppId = IIf(colOppId > 0, CStr(ws.Cells(i, colOppId).Value), "")
                WriteLog wsLog, i, oppId, _
                         "Rule 1: Closed Won → FC", COL_FC_RELEVANT, _
                         fcVal, RULE_FC_VALUE, "FILLED"
                ws.Cells(i, colFC).Value = RULE_FC_VALUE
                changed = changed + 1
            End If
        End If
    Next i

    Rule1_ClosedWonFC = changed
End Function

' ─────────────────────────────────────────────────────────────────────────────
' Rule2_H2Naming
' Business rule: If Business Type = "H2" → Naming field must be "SP7".
' Only writes if the current value differs (avoids unnecessary churn).
' ─────────────────────────────────────────────────────────────────────────────
Public Function Rule2_H2Naming(ws As Worksheet, wsLog As Worksheet) As Long
    Dim colBizType As Long, colNaming As Long, colOppId As Long
    Dim lastRow As Long, i As Long
    Dim bizType As String, namingVal As String, oppId As String
    Dim changed As Long

    changed = 0

    colBizType = AssertColIndex(ws, COL_BUSINESS_TYPE)
    colNaming  = AssertColIndex(ws, COL_NAMING)
    colOppId   = GetColIndex(ws, COL_OPPORTUNITY_ID)
    lastRow    = GetLastDataRow(ws)

    For i = CFG_HEADER_ROW + 1 To lastRow
        bizType = Trim(ws.Cells(i, colBizType).Value)
        If UCase(bizType) = UCase(RULE_H2_BIZ_TYPE) Then
            namingVal = Trim(ws.Cells(i, colNaming).Value)
            If UCase(namingVal) <> UCase(RULE_H2_NAMING_TARGET) Then
                oppId = IIf(colOppId > 0, CStr(ws.Cells(i, colOppId).Value), "")
                WriteLog wsLog, i, oppId, _
                         "Rule 2: H2 Naming", COL_NAMING, _
                         namingVal, RULE_H2_NAMING_TARGET, "CORRECTED"
                ws.Cells(i, colNaming).Value = RULE_H2_NAMING_TARGET
                changed = changed + 1
            End If
        End If
    Next i

    Rule2_H2Naming = changed
End Function

' ─────────────────────────────────────────────────────────────────────────────
' Rule3_ZL_Description
' Business rule: If Description contains "#ZL" AND Stage is
'   "Closed / Cancelled" or "Closed Lost" → FC Relevant must be blank.
' ─────────────────────────────────────────────────────────────────────────────
Public Function Rule3_ZL_Description(ws As Worksheet, wsLog As Worksheet) As Long
    Dim colDesc  As Long, colStage As Long, colFC As Long, colOppId As Long
    Dim lastRow  As Long, i As Long
    Dim desc     As String, stage As String, fcVal As String, oppId As String
    Dim changed  As Long

    changed = 0

    colDesc  = AssertColIndex(ws, COL_DESCRIPTION)
    colStage = AssertColIndex(ws, COL_STAGE)
    colFC    = AssertColIndex(ws, COL_FC_RELEVANT)
    colOppId = GetColIndex(ws, COL_OPPORTUNITY_ID)
    lastRow  = GetLastDataRow(ws)

    For i = CFG_HEADER_ROW + 1 To lastRow
        desc  = ws.Cells(i, colDesc).Value  ' Do NOT Trim — #ZL can be anywhere
        stage = Trim(ws.Cells(i, colStage).Value)

        Dim stageMatch As Boolean
        stageMatch = (UCase(stage) = UCase(RULE_CLOSED_CANCELLED)) Or _
                     (UCase(stage) = UCase(RULE_CLOSED_LOST))

        If InStr(1, desc, RULE_ZL_MARKER, vbTextCompare) > 0 And stageMatch Then
            fcVal = ws.Cells(i, colFC).Value
            If fcVal <> "" Then
                oppId = IIf(colOppId > 0, CStr(ws.Cells(i, colOppId).Value), "")
                WriteLog wsLog, i, oppId, _
                         "Rule 3: #ZL → blank FC", COL_FC_RELEVANT, _
                         CStr(fcVal), "", "CLEARED"
                ws.Cells(i, colFC).Value = ""
                changed = changed + 1
            End If
        End If
    Next i

    Rule3_ZL_Description = changed
End Function

' ─────────────────────────────────────────────────────────────────────────────
' Rule4_BSS_H2
' Business rule: If the H2 column contains "H2" →
'   Business Sub-Segment Short revised must be exactly RULE_H2_BSS.
' ─────────────────────────────────────────────────────────────────────────────
Public Function Rule4_BSS_H2(ws As Worksheet, wsLog As Worksheet) As Long
    Dim colH2  As Long, colBSS As Long, colOppId As Long
    Dim lastRow As Long, i As Long
    Dim h2Val  As String, bssVal As String, oppId As String
    Dim changed As Long

    changed = 0

    colH2    = AssertColIndex(ws, COL_H2)
    colBSS   = AssertColIndex(ws, COL_BSS_REVISED)
    colOppId = GetColIndex(ws, COL_OPPORTUNITY_ID)
    lastRow  = GetLastDataRow(ws)

    For i = CFG_HEADER_ROW + 1 To lastRow
        h2Val = Trim(ws.Cells(i, colH2).Value)
        If UCase(h2Val) = UCase(RULE_H2_BIZ_TYPE) Then
            bssVal = Trim(ws.Cells(i, colBSS).Value)
            If bssVal <> RULE_H2_BSS Then
                oppId = IIf(colOppId > 0, CStr(ws.Cells(i, colOppId).Value), "")
                WriteLog wsLog, i, oppId, _
                         "Rule 4a: H2 BSS", COL_BSS_REVISED, _
                         bssVal, RULE_H2_BSS, "CORRECTED"
                ws.Cells(i, colBSS).Value = RULE_H2_BSS
                changed = changed + 1
            End If
        End If
    Next i

    Rule4_BSS_H2 = changed
End Function

' ─────────────────────────────────────────────────────────────────────────────
' Rule4_BSS_H3
' Business rule: If the H3 column contains "H3" →
'   Business Sub-Segment Short revised must be exactly RULE_H3_BSS.
' ─────────────────────────────────────────────────────────────────────────────
Public Function Rule4_BSS_H3(ws As Worksheet, wsLog As Worksheet) As Long
    Dim colH3  As Long, colBSS As Long, colOppId As Long
    Dim lastRow As Long, i As Long
    Dim h3Val  As String, bssVal As String, oppId As String
    Dim changed As Long

    changed = 0

    colH3    = AssertColIndex(ws, COL_H3)
    colBSS   = AssertColIndex(ws, COL_BSS_REVISED)
    colOppId = GetColIndex(ws, COL_OPPORTUNITY_ID)
    lastRow  = GetLastDataRow(ws)

    For i = CFG_HEADER_ROW + 1 To lastRow
        h3Val = Trim(ws.Cells(i, colH3).Value)
        If UCase(h3Val) = UCase(RULE_H3_BIZ_TYPE) Then
            bssVal = Trim(ws.Cells(i, colBSS).Value)
            If bssVal <> RULE_H3_BSS Then
                oppId = IIf(colOppId > 0, CStr(ws.Cells(i, colOppId).Value), "")
                WriteLog wsLog, i, oppId, _
                         "Rule 4b: H3 BSS", COL_BSS_REVISED, _
                         bssVal, RULE_H3_BSS, "CORRECTED"
                ws.Cells(i, colBSS).Value = RULE_H3_BSS
                changed = changed + 1
            End If
        End If
    Next i

    Rule4_BSS_H3 = changed
End Function
