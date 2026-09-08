"""
Generates a realistic, multi-page sample financial audit report PDF
specifically designed to test cross-document extraction, corroboration,
contradiction, and contextual reconciliation with Delhivery datasets in Verity.
"""
from pathlib import Path
import fitz  # PyMuPDF

def generate_sample_pdf(output_path: Path):
    doc = fitz.open()

    # Page 1: Title & Executive Overview
    page1 = doc.new_page(width=595, height=842) # A4
    page1.insert_text((50, 70), "INDEPENDENT INDUSTRY RESEARCH & FORENSIC BENCHMARK", fontsize=10, fontname="helv", color=(0.4, 0.4, 0.5))
    page1.insert_text((50, 95), "Indian Express Logistics & Supply Chain Review (FY 2023-24)", fontsize=16, fontname="hebo", color=(0.1, 0.1, 0.2))
    page1.insert_text((50, 115), "Published: June 2024 | Benchmark Analysis: Delhivery Limited", fontsize=9, fontname="helv", color=(0.5, 0.5, 0.5))
    page1.draw_line((50, 125), (545, 125), color=(0.8, 0.8, 0.8), width=1)

    p1_text = (
        "1. EXECUTIVE SUMMARY AND CONSOLIDATED PERFORMANCE\n\n"
        "This independent research brief analyzes the operational and financial performance of Delhivery Limited for the fiscal year ended March 31, 2024 (FY24).\n\n"
        "Key Verified Findings:\n"
        "• Total Revenue from Operations: Delhivery Limited recorded consolidated revenue from operations of INR 8,142 Crore in FY24, representing solid 13% year-on-year growth compared to INR 7,225 Crore in FY23.\n"
        "• Express Parcel Volume: The company handled an aggregate express parcel volume of 740 million shipments during FY24 across its pan-India network.\n"
        "• Network Reach: As of March 31, 2024, Delhivery covered 18,754 active pin codes across India, maintaining direct delivery presence across all 28 states and union territories.\n"
        "• Active Automated Gateways: Delhivery operated 24 automated mega-gateway sorting hubs nationwide, incorporating automated cross-belt sorters.\n"
        "• Net Loss / Profitability Status: For the full fiscal year FY24, Delhivery reported a consolidated net loss of INR 249 Crore, marking an improvement over the previous year loss."
    )
    rect1 = fitz.Rect(50, 145, 545, 450)
    page1.insert_textbox(rect1, p1_text, fontsize=10, fontname="helv", color=(0.15, 0.15, 0.15), lineheight=1.4)

    p1_notes = (
        "CROSS-DOCUMENT AUDIT NOTES:\n"
        "Note A: The consolidated revenue figure of INR 8,142 Crore exactly matches disclosures in the Delhivery FY24 Annual Report and Q4 Earnings Presentation.\n"
        "Note B: The 740 million parcel volume is consistent with the management discussion report."
    )
    rect1_notes = fitz.Rect(50, 480, 545, 580)
    page1.draw_rect(fitz.Rect(45, 470, 550, 570), color=(0.85, 0.85, 0.9), width=0.8)
    page1.insert_textbox(rect1_notes, p1_notes, fontsize=9, fontname="hebo", color=(0.2, 0.3, 0.5), lineheight=1.3)
    page1.insert_text((50, 800), "Page 1 of 3 | Delhivery Logistics Benchmark Brief", fontsize=8, fontname="helv", color=(0.6, 0.6, 0.6))

    # Page 2: Operational Variances and Conflicting Broker Estimates (Contradiction Test)
    page2 = doc.new_page(width=595, height=842)
    page2.insert_text((50, 70), "SECTION 2: INFRASTRUCTURE & DISPUTED AUDIT ESTIMATES", fontsize=10, fontname="helv", color=(0.4, 0.4, 0.5))
    page2.insert_text((50, 95), "Infrastructure Footprint and Parcel Volume Audit Discrepancies", fontsize=15, fontname="hebo", color=(0.1, 0.1, 0.2))
    page2.draw_line((50, 105), (545, 105), color=(0.8, 0.8, 0.8), width=1)

    p2_text = (
        "2. WAREHOUSING INFRASTRUCTURE AND LOGISTICS METRICS\n\n"
        "The following operational metrics detail logistics infrastructure deployment across automated mega-facilities:\n\n"
        "• Total Operational Infrastructure Area: As of March 31, 2024, Delhivery operated approximately 18.5 million square feet of total logistics and warehousing infrastructure across India.\n"
        "• Delivery Service Centers: The company maintained 2,880 active delivery service centers (fulfillment and pickup hubs) at the close of the financial year.\n"
        "• Alternative Logistics Audit Note: A third-party logistics consulting estimate from Nexus Trans-Audit pegged Delhivery's FY24 express parcel volume at 685 million shipments, which directly contradicts the 740 million parcel count reported in official company filings.\n"
        "• Full Year Profit Claim: Contrary to the statutory audit report, preliminary retail investor circulated notes inaccurately stated that Delhivery recorded a positive net profit of INR 115 Crore for full year FY24, conflicting with the statutory reported net loss of INR 249 Crore."
    )
    rect2 = fitz.Rect(50, 125, 545, 460)
    page2.insert_textbox(rect2, p2_text, fontsize=10, fontname="helv", color=(0.15, 0.15, 0.15), lineheight=1.4)

    page2.draw_rect(fitz.Rect(45, 480, 550, 600), color=(0.9, 0.8, 0.8), width=0.8)
    p2_box = (
        "AUDIT CLASSIFICATION FOR VERITY REASONING ENGINE:\n"
        "• Corroboration target: Pin code count (18,754) and operating revenue (INR 8,142 Cr).\n"
        "• Contradiction target: Parcel shipment volume stated as 685 million vs 740 million in official reports.\n"
        "• Contradiction target: FY24 Net Income stated as positive profit INR 115 Cr vs statutory loss INR 249 Cr."
    )
    page2.insert_textbox(fitz.Rect(50, 490, 545, 590), p2_box, fontsize=9, fontname="hebo", color=(0.6, 0.1, 0.1), lineheight=1.3)
    page2.insert_text((50, 800), "Page 2 of 3 | Delhivery Logistics Benchmark Brief", fontsize=8, fontname="helv", color=(0.6, 0.6, 0.6))

    # Page 3: Contextual Reconciliation Cases (Standalone vs Consolidated & Q4 vs FY24)
    page3 = doc.new_page(width=595, height=842)
    page3.insert_text((50, 70), "SECTION 3: CONTEXTUAL RECONCILIATIONS & QUARTERLY BREAKDOWNS", fontsize=10, fontname="helv", color=(0.4, 0.4, 0.5))
    page3.insert_text((50, 95), "Quarterly Adjusted EBITDA and Standalone vs Consolidated Figures", fontsize=15, fontname="hebo", color=(0.1, 0.1, 0.2))
    page3.draw_line((50, 105), (545, 105), color=(0.8, 0.8, 0.8), width=1)

    p3_text = (
        "3. ACCOUNTING AND RECONCILIATION DIFFERENTIALS\n\n"
        "Apparent numerical discrepancies between reporting releases can be reconciled through accounting perimeter and temporal boundaries:\n\n"
        "• Q4 FY24 Standalone vs FY24 Full-Year Revenue: For the single fourth quarter (Q4 FY24), Delhivery recorded revenue of INR 2,076 Crore, whereas the full fiscal year FY24 aggregated revenue reached INR 8,142 Crore. The figures do not contradict because Q4 represents a three-month sub-period of the annual twelve-month cycle.\n"
        "• Adjusted EBITDA: Consolidated Adjusted EBITDA for FY24 stood positive at INR 127 Crore (1.6% margin), whereas Q4 FY24 Adjusted EBITDA was INR 102 Crore. This reflects positive margin expansion weighted toward the second half of the year.\n"
        "• Team Strength / Headcount: Total registered corporate and contractual workforce at peak season was 57,000 personnel, whereas permanent full-time payroll employees were reported at 23,400. This variance is explained by seasonal gig and partner delivery associates added during festival peak demands.\n"
        "• Net Debt Status: The company remained net cash positive with total cash and financial investments exceeding INR 5,200 Crore as of March 31, 2024."
    )
    rect3 = fitz.Rect(50, 125, 545, 480)
    page3.insert_textbox(rect3, p3_text, fontsize=10, fontname="helv", color=(0.15, 0.15, 0.15), lineheight=1.4)

    page3.draw_rect(fitz.Rect(45, 500, 550, 620), color=(0.8, 0.9, 0.8), width=0.8)
    p3_box = (
        "CONTEXTUAL RECONCILIATION TARGETS FOR VERITY:\n"
        "• Scope difference: Q4 FY24 Revenue (INR 2,076 Cr) vs Full Year FY24 Revenue (INR 8,142 Cr) -> Temporal Scope.\n"
        "• Accounting difference: Total workforce (57,000 peak) vs Permanent staff (23,400) -> Employment Definition.\n"
        "• Both figures are factually valid when evaluated with their appropriate contextual scopes."
    )
    page3.insert_textbox(fitz.Rect(50, 510, 545, 610), p3_box, fontsize=9, fontname="hebo", color=(0.1, 0.4, 0.2), lineheight=1.3)
    page3.insert_text((50, 800), "Page 3 of 3 | Delhivery Logistics Benchmark Brief", fontsize=8, fontname="helv", color=(0.6, 0.6, 0.6))

    doc.save(str(output_path))
    doc.close()
    print(f"Sample PDF created successfully at: {output_path}")

if __name__ == "__main__":
    out = Path(__file__).resolve().parent.parent / "data" / "delhivery_industry_benchmark_sample.pdf"
    out.parent.mkdir(exist_ok=True)
    generate_sample_pdf(out)
