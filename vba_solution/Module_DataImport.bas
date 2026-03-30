Attribute VB_Name = "Module_DataImport"
'============================================================================
' Module_DataImport
' Purpose : Handles the data-refresh workflow:
'             1. Clear old data rows (below header) while preserving formula columns
'             2. Import new data from a SIESALES export sheet into the working sheet
'             3. Backfill yellow-zone columns from the previous working file
'
' IMPORTANT:
' - This module is designed for the TESTING workflow only.
' - Export key      = Opportunity ID
' - Working-file key = SieSales ID
'============================================================================
Option Explicit

' ─────────────────────────────────────────────────────────────────────────────
' ClearOldData
' Clears all data rows below the header while preserving columns listed in
' CFG_PRESERVE_HEADERS.
'
' Faster strategy:
' - Build a set of preserved columns
' - Clear whole non-preserved column ranges at once
' ─────────────────────────────────────────────────────────────────────────────
Public Sub ClearOldData(ws As Worksheet)
    Dim lastRow As Long
    Dim lastCol As Long
    Dim j As Long
    Dim preserveCols As Object
    Dim rngToClear As Range
    Dim colRange As Range

    If ws Is Nothing Then Exit Sub

    lastRow = GetLastDataRow(ws)
    If lastRow <= CFG_HEADER_ROW Then Exit Sub

    lastCol = ws.Cells(CFG_HEADER_ROW, ws.Columns.Count).End(xlToLeft).Column
    If lastCol < 1 Then Exit Sub

    Set preserveCols = BuildPreserveColumnDict(ws)

    For j = 1 To lastCol
        If Not preserveCols.Exists(CStr(j)) Then
            Set colRange = ws.Range(ws.Cells(CFG_HEADER_ROW + 1, j), ws.Cells(lastRow, j))
            If rngToClear Is Nothing Then
                Set rngToClear = colRange
            Else
                Set rngToClear = Union(rngToClear, colRange)
            End If
        End If
    Next j

    If Not rngToClear Is Nothing Then
        rngToClear.ClearContents
    End If
End Sub

' ─────────────────────────────────────────────────────────────────────────────
' ImportFromSIESALES
' Copies data from the SIESALES export sheet into the working sheet.
'
' Important mapping logic:
' - Export "Opportunity ID" -> Working "SieSales ID"
' - Shared columns are copied by matching exact header names
' - Yellow-zone columns are NOT imported from export
' ─────────────────────────────────────────────────────────────────────────────
Public Sub ImportFromSIESALES(wsDest As Worksheet, _
                              wsSrc As Worksheet, _
                              wsLog As Worksheet)

    Dim srcHeaders As Variant
    Dim destHeaders As Variant
    Dim srcCols() As Long
    Dim destCols() As Long
    Dim pairCount As Long
    Dim srcLastRow As Long
    Dim destRow As Long
    Dim i As Long, m As Long
    Dim keyVal As String

    If wsDest Is Nothing Or wsSrc Is Nothing Then Exit Sub

    ' Source/export headers
    srcHeaders = Array( _
        COL_EXPORT_KEY, _
        COL_COUNTRY_INSTALL, _
        COL_LEVEL_04, _
        COL_FISCAL_PERIOD, _
        COL_FISCAL_YEAR, _
        COL_SDH_COUNTRY, _
        COL_OPPORTUNITY_NAME, _
        COL_ACCOUNT_NAME, _
        COL_END_ACCOUNT, _
        COL_GCK_CODE, _
        COL_BSS_SHORT, _
        COL_SALES_TYPE, _
        COL_SPG_CODE, _
        COL_SIEMENS_ACCOUNT_TYPE, _
        COL_STAGE, _
        COL_BID_APPROVAL, _
        COL_ORDER_INTAKE_DATE, _
        COL_EXPORT_DEL_OI_EUR, _
        COL_EXPORT_DEL_WEIGHTED_OI, _
        COL_GROSS_MARGIN, _
        COL_WINNER, _
        COL_COMPETITOR, _
        COL_MAIN_REASON, _
        COL_OPP_INDUSTRY_DESC, _
        COL_OPPORTUNITY_OWNER, _
        COL_DESCRIPTION, _
        COL_STRATEGIC_PRIORITY, _
        COL_LOA_ID, _
        COL_RELEVANT_FORECAST, _
        COL_HAS_PRODUCTS, _
        COL_PRODUCT_NAME, _
        COL_PRODUCT_CODE, _
        COL_PCK_CODE, _
        COL_CROSS_BORDER, _
        COL_ALTERNATIVE_OPP, _
        COL_BID_EXPIRATION_DATE, _
        COL_SAP_NUMBER, _
        COL_RFQ_RECEIVED_DATE, _
        COL_SALES_STATUS, _
        COL_IFA, _
        COL_SALES_COUNTRY _
    )

    ' Destination/working headers
    destHeaders = Array( _
        COL_WORKING_KEY, _
        COL_COUNTRY_INSTALL, _
        COL_LEVEL_04, _
        COL_FISCAL_PERIOD, _
        COL_FISCAL_YEAR, _
        COL_SDH_COUNTRY, _
        COL_OPPORTUNITY_NAME, _
        COL_ACCOUNT_NAME, _
        COL_END_ACCOUNT, _
        COL_GCK_CODE, _
        COL_BSS_SHORT, _
        COL_SALES_TYPE, _
        COL_SPG_CODE, _
        COL_SIEMENS_ACCOUNT_TYPE, _
        COL_STAGE, _
        COL_BID_APPROVAL, _
        COL_ORDER_INTAKE_DATE, _
        COL_WORKING_OI_EUR, _
        COL_WORKING_WEIGHTED_OI, _
        COL_GROSS_MARGIN, _
        COL_WINNER, _
        COL_COMPETITOR, _
        COL_MAIN_REASON, _
        COL_OPP_INDUSTRY_DESC, _
        COL_OPPORTUNITY_OWNER, _
        COL_DESCRIPTION, _
        COL_STRATEGIC_PRIORITY, _
        COL_LOA_ID, _
        COL_RELEVANT_FORECAST, _
        COL_HAS_PRODUCTS, _
        COL_PRODUCT_NAME, _
        COL_PRODUCT_CODE, _
        COL_PCK_CODE, _
        COL_CROSS_BORDER, _
        COL_ALTERNATIVE_OPP, _
        COL_BID_EXPIRATION_DATE, _
        COL_SAP_NUMBER, _
        COL_RFQ_RECEIVED_DATE, _
        COL_SALES_STATUS, _
        COL_IFA, _
        COL_SALES_COUNTRY _
    )

    pairCount = UBound(srcHeaders) - LBound(srcHeaders) + 1
    ReDim srcCols(0 To pairCount - 1)
    ReDim destCols(0 To pairCount - 1)

    ' Resolve all headers once
    For m = 0 To pairCount - 1
        srcCols(m) = AssertColIndex(wsSrc, CStr(srcHeaders(m)), CFG_HEADER_ROW)
        destCols(m) = AssertColIndex(wsDest, CStr(destHeaders(m)), CFG_HEADER_ROW)
    Next m

    srcLastRow = GetLastDataRow(wsSrc)
    destRow = CFG_HEADER_ROW + 1

    For i = CFG_HEADER_ROW + 1 To srcLastRow
        keyVal = Trim$(CStr(wsSrc.Cells(i, srcCols(0)).Value))

        ' Skip empty source rows
        If keyVal <> vbNullString Then
            For m = 0 To pairCount - 1
                wsDest.Cells(destRow, destCols(m)).Value = wsSrc.Cells(i, srcCols(m)).Value
            Next m

            WriteLog wsLog, destRow, keyVal, "Import", "Mapped export columns", "", "", "IMPORTED"
            destRow = destRow + 1
        End If
    Next i
End Sub

' ─────────────────────────────────────────────────────────────────────────────
' FillYellowZoneFromPreviousFile
' Copies yellow-zone values from the old working file to the new working file
' by matching SieSales ID.
'
' Important:
' - Join key is SieSales ID on BOTH working files
' - Headers listed in CFG_PRESERVE_HEADERS are skipped here, so formula columns
'   such as H2/H3 are not overwritten
' ─────────────────────────────────────────────────────────────────────────────
Public Sub FillYellowZoneFromPreviousFile(wsDest As Worksheet, _
                                          wsPrev As Worksheet, _
                                          wsLog As Worksheet, _
                                          yellowCols() As String)

    Dim prevDict As Object
    Dim preserveHeaders As Object
    Dim colPrevKey As Long
    Dim colDestKey As Long
    Dim lastRowPrev As Long
    Dim lastRowDest As Long
    Dim i As Long, m As Long
    Dim keyVal As String
    Dim prevRow As Long
    Dim oldVal As String, newVal As String

    Dim activeHeaders() As String
    Dim prevCols() As Long
    Dim destCols() As Long
    Dim activeCount As Long
    Dim headerName As String
    Dim prevColIdx As Long, destColIdx As Long

    If wsDest Is Nothing Or wsPrev Is Nothing Then Exit Sub

    Set prevDict = CreateObject("Scripting.Dictionary")
    prevDict.CompareMode = 1

    Set preserveHeaders = BuildPreserveHeaderDict()

    colPrevKey = AssertColIndex(wsPrev, COL_WORKING_KEY, CFG_HEADER_ROW)
    colDestKey = AssertColIndex(wsDest, COL_WORKING_KEY, CFG_HEADER_ROW)

    lastRowPrev = GetLastDataRow(wsPrev)
    lastRowDest = GetLastDataRow(wsDest)

    ' Index old working file by SieSales ID
    For i = CFG_HEADER_ROW + 1 To lastRowPrev
        keyVal = Trim$(CStr(wsPrev.Cells(i, colPrevKey).Value))
        If keyVal <> vbNullString Then
            If Not prevDict.Exists(keyVal) Then
                prevDict.Add keyVal, i
            End If
        End If
    Next i

    ' Resolve only the yellow headers that should actually be copied
    activeCount = -1

    For m = LBound(yellowCols) To UBound(yellowCols)
        headerName = Trim$(CStr(yellowCols(m)))

        ' Skip preserved columns such as H2 / H3 so formulas are not overwritten
        If Not preserveHeaders.Exists(LCase$(headerName)) Then
            destColIdx = GetColIndex(wsDest, headerName, CFG_HEADER_ROW)
            prevColIdx = GetColIndex(wsPrev, headerName, CFG_HEADER_ROW)

            If destColIdx > 0 And prevColIdx > 0 Then
                activeCount = activeCount + 1
                ReDim Preserve activeHeaders(0 To activeCount)
                ReDim Preserve destCols(0 To activeCount)
                ReDim Preserve prevCols(0 To activeCount)

                activeHeaders(activeCount) = headerName
                destCols(activeCount) = destColIdx
                prevCols(activeCount) = prevColIdx
            End If
        End If
    Next m

    If activeCount < 0 Then Exit Sub

    ' Fill yellow-zone values from old working file
    For i = CFG_HEADER_ROW + 1 To lastRowDest
        keyVal = Trim$(CStr(wsDest.Cells(i, colDestKey).Value))

        If keyVal <> vbNullString And prevDict.Exists(keyVal) Then
            prevRow = CLng(prevDict(keyVal))

            For m = 0 To activeCount
                oldVal = CStr(wsDest.Cells(i, destCols(m)).Value)
                newVal = CStr(wsPrev.Cells(prevRow, prevCols(m)).Value)

                If oldVal <> newVal Then
                    wsDest.Cells(i, destCols(m)).Value = newVal
                    WriteLog wsLog, i, keyVal, _
                             "Yellow Zone Fill", activeHeaders(m), _
                             oldVal, newVal, "FILLED FROM PREV"
                End If
            Next m
        End If
    Next i
End Sub

' ─────────────────────────────────────────────────────────────────────────────
' BuildPreserveColumnDict
' Returns a dictionary whose keys are the column numbers that must be preserved
' according to CFG_PRESERVE_HEADERS.
' ─────────────────────────────────────────────────────────────────────────────
Private Function BuildPreserveColumnDict(ws As Worksheet) As Object
    Dim dict As Object
    Dim headers() As String
    Dim i As Long
    Dim colIdx As Long

    Set dict = CreateObject("Scripting.Dictionary")
    dict.CompareMode = 1

    headers = SplitTrim(CFG_PRESERVE_HEADERS, ",")

    For i = LBound(headers) To UBound(headers)
        colIdx = GetColIndex(ws, headers(i), CFG_HEADER_ROW)
        If colIdx > 0 Then
            dict(CStr(colIdx)) = True
        End If
    Next i

    Set BuildPreserveColumnDict = dict
End Function

' ─────────────────────────────────────────────────────────────────────────────
' BuildPreserveHeaderDict
' Returns a dictionary of preserved header names in lowercase.
' Used to skip formula columns during yellow-zone backfill.
' ─────────────────────────────────────────────────────────────────────────────
Private Function BuildPreserveHeaderDict() As Object
    Dim dict As Object
    Dim headers() As String
    Dim i As Long

    Set dict = CreateObject("Scripting.Dictionary")
    dict.CompareMode = 1

    headers = SplitTrim(CFG_PRESERVE_HEADERS, ",")

    For i = LBound(headers) To UBound(headers)
        dict(LCase$(headers(i))) = True
    Next i

    Set BuildPreserveHeaderDict = dict
End Function
