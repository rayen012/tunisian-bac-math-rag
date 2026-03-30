Attribute VB_Name = "Module_Config"
'============================================================================
' Module_Config
' Purpose : Central configuration for all column headers, sheet names,
'           and business-rule constants.
'           Change values HERE only — the rest of the code adapts.
'============================================================================
Option Explicit

' ── Sheet names ─────────────────────────────────────────────────────────────
Public Const CFG_DATA_SHEET          As String = "Data"          ' Main data sheet
Public Const CFG_ZONE_SHEET          As String = "Zone Structure" ' Zone lookup table
Public Const CFG_LOG_SHEET           As String = "Run Log"        ' Audit / report sheet

' ── Header row number ────────────────────────────────────────────────────────
Public Const CFG_HEADER_ROW          As Long = 1

' ── Column headers (exact text as they appear in row 1) ─────────────────────
Public Const COL_OPPORTUNITY_ID      As String = "Opportunity ID"
Public Const COL_STAGE               As String = "Stage"
Public Const COL_FC_RELEVANT         As String = "FC Relevant"
Public Const COL_BUSINESS_TYPE       As String = "Business Type"
Public Const COL_NAMING              As String = "Naming"          ' H2 naming field
Public Const COL_DESCRIPTION         As String = "Description"
Public Const COL_BSS_REVISED         As String = "Business Sub-Segment Short revised"
Public Const COL_ZONE                As String = "Zone"
Public Const COL_COUNTRY_INSTALL     As String = "Country of Installation"
Public Const COL_H2                  As String = "H2"              ' H2 flag column
Public Const COL_H3                  As String = "H3"              ' H3 flag column

' Zone lookup sheet column headers
Public Const ZONE_COL_COUNTRY        As String = "Country"
Public Const ZONE_COL_ZONE          As String = "Zone"

' ── Business-rule constants (change here if values shift) ────────────────────
Public Const RULE_CLOSED_WON         As String = "Closed Won"
Public Const RULE_FC_VALUE           As String = "FC"
Public Const RULE_H2_BIZ_TYPE        As String = "H2"
Public Const RULE_H2_NAMING_TARGET   As String = "SP7"             ' <<< CONFIGURABLE
Public Const RULE_H3_BIZ_TYPE        As String = "H3"
Public Const RULE_ZL_MARKER          As String = "#ZL"
Public Const RULE_CLOSED_CANCELLED   As String = "Closed / Cancelled"
Public Const RULE_CLOSED_LOST        As String = "Closed Lost"
Public Const RULE_H2_BSS             As String = "SI GSW SOL SPL Operations"
Public Const RULE_H3_BSS             As String = "SI GSW SOL SPL Operations" ' adjust if H3 differs
Public Const RULE_NA_ZONE            As String = "N/A"

' ── Formula-preservation columns (1-based column letters/indices to protect) ─
' These are the columns that contain formulas that must NOT be cleared.
' Add column header names here (comma-separated concept); code will resolve them.
Public Const CFG_PRESERVE_HEADERS    As String = "H2,H3"          ' <<< comma-separated
