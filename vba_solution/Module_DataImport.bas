Attribute VB_Name = "Module_Config"
'============================================================================
' Module_Config
' Purpose : Central configuration for the 3-file workflow
'           1) SIESALES export file
'           2) New working file
'           3) Old working file (used to backfill yellow-zone fields)
'
' IMPORTANT:
' - Change values HERE only.
' - Header texts must match Excel row 1 exactly.
'============================================================================
Option Explicit

' ── Sheet names ─────────────────────────────────────────────────────────────
Public Const CFG_WORKING_SHEET           As String = "Data"
Public Const CFG_OLD_WORKING_SHEET       As String = "Data"
Public Const CFG_EXPORT_SHEET            As String = "Data"
Public Const CFG_ZONE_SHEET              As String = "Zone Structure"
Public Const CFG_LOG_SHEET               As String = "Run Log"

' ── Header row number ───────────────────────────────────────────────────────
Public Const CFG_HEADER_ROW              As Long = 1

' ── Key headers used for matching ───────────────────────────────────────────
' Export file key
Public Const COL_EXPORT_KEY              As String = "Opportunity ID"

' Working / old working file key
Public Const COL_WORKING_KEY             As String = "SieSales ID"

' ── Yellow-zone headers in working file / old working file ─────────────────
' IMPORTANT:
' Yellow zone starts at column B, NOT column A.
' Column A (SieSales ID) is the lookup key and is NOT part of the yellow zone.
Public Const COL_BUSINESS_TYPE           As String = "Business Type"
Public Const COL_PRODUCT_TYPE            As String = "Product type"
Public Const COL_PRIO                    As String = "Prio"
Public Const COL_H2                      As String = "H2"
Public Const COL_H3                      As String = "H3"
Public Const COL_BSS_REVISED             As String = "Business Sub-Segment Short revised"
Public Const COL_FC_RELEVANT_WORKING     As String = "FC relevant"
Public Const COL_ZONE                    As String = "Zone"

' These are the yellow-zone fields to copy from OLD working file into NEW working file
' using SieSales ID as the match key.
Public Const CFG_YELLOW_HEADERS          As String = _
    "Business Type,Product type,Prio,H2,H3,Business Sub-Segment Short revised,FC relevant,Zone"

' Columns to preserve when clearing old rows
' These are exact HEADER NAMES, not column letters.
Public Const CFG_PRESERVE_HEADERS        As String = "H2,H3"

' ── Headers common to export + working file ────────────────────────────────
Public Const COL_COUNTRY_INSTALL         As String = "Country of Installation"
Public Const COL_LEVEL_04                As String = "Level 04"
Public Const COL_FISCAL_PERIOD           As String = "Fiscal Period"
Public Const COL_FISCAL_YEAR             As String = "Fiscal Year"
Public Const COL_SDH_COUNTRY             As String = "SDH Country"
Public Const COL_OPPORTUNITY_NAME        As String = "Opportunity Name"
Public Const COL_ACCOUNT_NAME            As String = "Account Name"
Public Const COL_END_ACCOUNT             As String = "End-Account"
Public Const COL_GCK_CODE                As String = "GCK Code"
Public Const COL_BSS_SHORT               As String = "Business Sub-Segment Short"
Public Const COL_SALES_TYPE              As String = "Sales Type"
Public Const COL_SPG_CODE                As String = "Depth Structure: SPG Code"
Public Const COL_SIEMENS_ACCOUNT_TYPE    As String = "Siemens Account Type"
Public Const COL_STAGE                   As String = "Stage"
Public Const COL_BID_APPROVAL            As String = "Bid approval (PM040)"
Public Const COL_ORDER_INTAKE_DATE       As String = "Order Intake Date (PM070)"
Public Const COL_GROSS_MARGIN            As String = "Gross Margin %"
Public Const COL_WINNER                  As String = "Winner"
Public Const COL_COMPETITOR              As String = "Competitor"
Public Const COL_MAIN_REASON             As String = "Main Reason"
Public Const COL_OPP_INDUSTRY_DESC       As String = "Opportunity Industry Description"
Public Const COL_OPPORTUNITY_OWNER       As String = "Opportunity Owner"
Public Const COL_DESCRIPTION             As String = "Description"
Public Const COL_STRATEGIC_PRIORITY      As String = "Strategic Priority"
Public Const COL_LOA_ID                  As String = "LoA-ID Number"
Public Const COL_RELEVANT_FORECAST       As String = "Relevant for Forecast"
Public Const COL_HAS_PRODUCTS            As String = "Has Products"
Public Const COL_PRODUCT_NAME            As String = "Depth Structure: Product Name"
Public Const COL_PRODUCT_CODE            As String = "Depth Structure: Product Code"
Public Const COL_PCK_CODE                As String = "Depth Structure: PCK Code"
Public Const COL_CROSS_BORDER            As String = "Cross Border (International) Business"
Public Const COL_ALTERNATIVE_OPP         As String = "Alternative Opportunity"
Public Const COL_BID_EXPIRATION_DATE     As String = "Bid Expiration Date"
Public Const COL_SAP_NUMBER              As String = "SAP Number"
Public Const COL_RFQ_RECEIVED_DATE       As String = "RFQ Received Date"
Public Const COL_SALES_STATUS            As String = "Sales Status"
Public Const COL_IFA                     As String = "IfA"
Public Const COL_SALES_COUNTRY           As String = "Sales Country"

' ── Export-only headers ─────────────────────────────────────────────────────
Public Const COL_EXPORT_DEL_OI_EUR       As String = "DEL_Order Intake EUR"
Public Const COL_EXPORT_DEL_WEIGHTED_OI  As String = "DEL_Weighted Order Intake EUR"

' ── Working-file-only headers ───────────────────────────────────────────────
Public Const COL_CHANCE_EXECUTION        As String = "Chance of Execution %"
Public Const COL_CHANCE_SUCCESS          As String = "Chance of Success %"
Public Const COL_WORKING_OI_EUR          As String = " Order Intake EUR "
Public Const COL_WORKING_WEIGHTED_OI     As String = " Weighted Order Intake EUR "
Public Const COL_OI_PREV                 As String = " OI prev "
Public Const COL_MATCH                   As String = " Match "

' ── Zone structure headers ──────────────────────────────────────────────────
Public Const ZONE_COL_COUNTRY            As String = "Country"
Public Const ZONE_COL_ZONE               As String = "Zone"

' ── Business-rule constants ─────────────────────────────────────────────────
Public Const RULE_CLOSED_WON             As String = "Closed Won"
Public Const RULE_FC_VALUE               As String = "FC"

Public Const RULE_H2_BIZ_TYPE            As String = "H2"
Public Const RULE_H3_BIZ_TYPE            As String = "H3"

Public Const RULE_ZL_MARKER              As String = "#ZL"
Public Const RULE_CLOSED_CANCELLED       As String = "Closed / Cancelled"
Public Const RULE_CLOSED_LOST            As String = "Closed Lost"

Public Const RULE_H2_BSS                 As String = "SI GSW SOL SPL Operations"
Public Const RULE_H3_BSS                 As String = "SI GSW SOL SPL Operations"

Public Const RULE_NA_ZONE                As String = "N/A"

' ── Safety / path check ─────────────────────────────────────────────────────
Public Const CFG_REQUIRED_TEST_PATH_TEXT As String = "TEST"
