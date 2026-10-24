"""Generate four fictional supplier proposals (2-4 pages each) for the same procurement request.

    python scripts/generate_sample_pdfs.py

All companies, people, prices and references are invented. Each proposal deliberately has different
strengths, weaknesses, prices, schedules, evidence quality and missing information.
"""
from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

OUT_DIR = Path(__file__).resolve().parent.parent / "sample_rfps"

RFP_TITLE = "RFP-2026-017: Enterprise Order-to-Cash Integration Platform"
CLIENT = "Meridian Foods Pvt Ltd (fictional)"

SUPPLIERS = {
    # ------------------------------------------------------------------ Apex Systems
    "Apex_Systems": {
        "name": "Apex Systems",
        "accent": "#1f3a5f",
        "sections": [
            ("1. Executive Summary and Understanding of the Requirement", [
                "Apex Systems is pleased to respond to " + RFP_TITLE + " issued by " + CLIENT + ". We understand that "
                "Meridian needs a single integration platform that connects its SAP S/4HANA ERP, the warehouse management "
                "system, the CRM and the government e-invoicing portal so that an order is captured, fulfilled, invoiced and "
                "reconciled without manual re-keying. Peak load is approximately 2,500 orders per hour during festival "
                "season, and finance requires a complete audit trail for every document.",
                "Our proposal, ApexConnect, is an API-first integration platform built on a microservices architecture. It "
                "combines deep SAP expertise with an enterprise-grade security posture. We are not the cheapest option; we "
                "are offering the most technically robust and most secure solution, with a delivery schedule of nine months.",
            ]),
            ("2. Proposed Solution and Technical Approach", [
                "Architecture: ApexConnect runs as containerised microservices on Kubernetes across three availability zones "
                "(multi-AZ), providing high availability with automatic failover and a 99.95% platform availability target. "
                "Services scale horizontally through auto-scaling policies driven by queue depth and CPU.",
                "Integration: all systems exchange data through an event bus based on Apache Kafka, with REST APIs and webhooks "
                "exposed for the CRM and the e-invoicing portal. SAP connectivity uses certified BAPI and IDoc interfaces "
                "(SAP S/4HANA and ECC-compatible). We define a canonical data model for order, delivery and invoice, and we "
                "provide a field-level mapping workbook for every interface, signed off by Meridian before build.",
                "Scalability evidence: in a recent load test, the platform sustained 6,000 transactions per hour with 400 "
                "concurrent API sessions and a median processing latency of 1.8 seconds. The test report will be shared "
                "during technical due diligence.",
            ]),
            ("3. Implementation Approach, Timeline and Team", [
                "The programme runs for nine months in four phases: Phase 1 Discovery and Design (6 weeks), Phase 2 Build "
                "(14 weeks), Phase 3 Integration Testing and UAT (10 weeks) and Phase 4 Go-live and Stabilisation (6 weeks). "
                "Milestones are M1 Design sign-off (week 6), M2 Build complete (week 20), M3 UAT sign-off (week 30) and "
                "M4 Go-live (week 36).",
                "The core team comprises a project manager, a solution architect and eight engineers. Governance is through "
                "a fortnightly project review. The detailed resourcing plan and the formal risk register will be provided after "
                "contract award. Key risks we foresee are SAP interface change requests and data quality in legacy masters.",
            ]),
            ("4. Price Table and Assumptions", []),
            ("5. Security, Compliance and Risk Controls", [
                "Apex Systems is certified to ISO/IEC 27001 and holds a SOC 2 Type II report covering the ApexConnect "
                "platform. An independent penetration test is performed every year and after every major release, with "
                "findings tracked under our vulnerability management process.",
                "Data is encrypted with AES-256 at rest and TLS 1.3 in transit. Access is controlled through role-based access "
                "control (RBAC) with least privilege, mandatory multi-factor authentication and SSO integration. Every "
                "transaction is written to an immutable audit trail that is streamed to a SIEM. Customer data is hosted in "
                "the India region to satisfy data residency, and our processes align with the DPDP Act. Disaster recovery "
                "targets are an RTO of 4 hours and an RPO of 15 minutes, tested twice a year. We operate a documented "
                "incident response plan with a 1-hour notification commitment.",
            ]),
            ("6. Support Model, Experience and References", [
                "Standard support is provided in business hours (09:00 to 18:00 IST, Monday to Friday) with a 99.9% service "
                "level (SLA) on production availability. 24x7 coverage for Priority 1 incidents is available as an optional "
                "add-on priced separately. Service credits apply for SLA breaches.",
                "Apex has delivered three similar integration programmes for manufacturing and FMCG clients over the last "
                "five years. References: Ms. R. Kulkarni, CIO, Suryoday Beverages (fictional); Mr. A. Fernandes, Head of IT, "
                "Konkan Agro Foods (fictional).",
            ]),
        ],
        "price_table": [
            ("Platform licence (3 years)", "ApexConnect core, Kafka, 5 environments", "165.0"),
            ("Implementation services", "Design, build, testing, go-live", "180.0"),
            ("SAP and CRM connectors", "BAPI/IDoc and REST connectors", "45.0"),
            ("Training and documentation", "40 user-days, admin certification", "12.0"),
            ("Support (3 years)", "Business-hours support, SLA 99.9%", "78.0"),
        ],
        "price_total": "480.0",
        "assumptions": [
            "Fixed price for implementation; changes handled through the change request process at the agreed rate card.",
            "Payment terms: 20% on design sign-off, 30% on build complete, 30% on UAT sign-off, 20% on go-live.",
            "24x7 Priority 1 coverage is optional and is quoted separately at INR 22 lakh over three years.",
            "Prices exclude GST and are valid for 90 days.",
        ],
    },
    # ------------------------------------------------------------------ BrightPath Tech
    "BrightPath_Tech": {
        "name": "BrightPath Tech",
        "accent": "#c2571a",
        "sections": [
            ("1. Executive Summary", [
                "BrightPath Tech is delighted to respond to " + RFP_TITLE + " from " + CLIENT + ". We offer the lowest price "
                "in the market and the fastest delivery: a complete order-to-cash integration live in five months. Our "
                "lean delivery model lets us pass the savings directly to Meridian.",
                "We understand that Meridian wants its ERP, warehouse, CRM and invoicing systems to work together. Our "
                "solution uses a lightweight integration layer and standard connectors to achieve this quickly.",
            ]),
            ("2. Proposed Solution", [
                "BrightPath Flow is a generic integration layer that uses standard connectors for the ERP, the CRM and the "
                "invoicing portal. We follow industry best practices for integration design. The solution is hosted on a "
                "single cloud region and can be scaled by adding servers when required.",
                "Data mapping will be done by our consultants during the build. We do not currently publish performance "
                "benchmark results.",
            ]),
            ("3. Implementation Plan", [
                "We will deliver in five months using two phases: Phase 1 Build (3 months) and Phase 2 Testing and Go-live "
                "(2 months). A team of five engineers led by a delivery lead will carry out the work. Milestones are build "
                "complete in month 3 and go-live in month 5. A detailed project schedule and a risk log will be shared at "
                "project kick-off.",
            ]),
            ("4. Price Table and Assumptions", []),
            ("5. Security and Compliance", [
                "BrightPath follows industry best practices for security. Data is protected using TLS in transit and "
                "encrypted storage. Our ISO 27001 certification is in progress and is planned for the second quarter of "
                "next year. Penetration testing and disaster recovery arrangements are planned for after go-live.",
            ]),
            ("6. Support and Experience", [
                "Support is provided by email only during business hours with a best-effort response. BrightPath was "
                "recently established in 2022 and has completed one similar project, for a regional distributor. A "
                "reference for that project is available on request.",
            ]),
        ],
        "price_table": [
            ("Platform subscription (3 years)", "BrightPath Flow, 2 environments", "70.0"),
            ("Implementation services", "Build, testing, go-live", "95.0"),
            ("Connectors and training", "Standard connectors, 10 user-days", "20.0"),
            ("Support (3 years)", "Email support, business hours", "25.0"),
        ],
        "price_total": "210.0",
        "assumptions": [
            "Fixed all-inclusive price for the scope described; the total contract price includes all listed items.",
            "Payment terms: 40% on kick-off, 40% on build complete, 20% on go-live.",
            "Prices exclude GST. Custom connectors beyond the standard set are not included.",
        ],
    },
    # ------------------------------------------------------------------ NexaWorks
    "NexaWorks": {
        "name": "NexaWorks",
        "accent": "#1b7f5c",
        "sections": [
            ("1. Executive Summary and Understanding of the Requirement", [
                "NexaWorks submits this proposal for " + RFP_TITLE + " from " + CLIENT + ". Meridian needs reliable, auditable "
                "order-to-cash flow across SAP S/4HANA, the warehouse management system, the CRM and the e-invoicing "
                "portal, handling peaks of about 2,500 orders per hour. We understand that the business risk lies in the "
                "cutover period, so our proposal emphasises disciplined delivery and strong post-go-live support.",
                "NexaWorks offers a balanced solution: solid architecture, certified security, a fair price (INR 340 lakh "
                "over three years) and a seven-month programme with a delivery and support model that we consider the "
                "strongest in this competition.",
            ]),
            ("2. Proposed Solution and Technical Approach", [
                "NexaFlow is built on a microservices architecture deployed on Kubernetes with auto-scaling and multi-AZ "
                "failover. Integration uses REST APIs and webhooks plus a Kafka-based event bus, and SAP integration uses "
                "BAPI and IDoc interfaces. A canonical data model and field-level mapping documents are produced for each "
                "interface. Load tests are run against a target of 4,000 transactions per hour before go-live.",
            ]),
            ("3. Implementation Plan, Timeline, Team and Milestones", [
                "Delivery is organised into five phases over seven months: Phase 1 Mobilisation and Discovery (4 weeks), "
                "Phase 2 Design (4 weeks), Phase 3 Build in three two-week sprints per module (12 weeks), Phase 4 "
                "Integration Testing and UAT (6 weeks) and Phase 5 Cutover, Go-live and Hypercare (4 weeks plus 8 weeks of "
                "hypercare). Milestones are M1 Mobilisation (week 4), M2 Design sign-off (week 8), M3 Build complete "
                "(week 20), M4 UAT sign-off (week 26) and M5 Go-live (week 30).",
                "Team and governance: a team of 14 full-time specialists, including a project manager, a solution architect, "
                "a test lead and a change manager. A RACI matrix is agreed in week 1, and a monthly steering committee with "
                "Meridian sponsors reviews progress. Knowledge transfer and role-based training are scheduled in the last "
                "eight weeks.",
                "Risk plan: we maintain a risk register with owners and mitigation actions; the eight initial risks are SAP "
                "interface changes, data quality, key-user availability, performance at peak, integration environment delays, "
                "scope creep, cutover window overruns and resistance to change. A documented cutover plan includes a "
                "rollback procedure and contingency window, rehearsed twice before go-live.",
            ]),
            ("4. Price Table and Assumptions", []),
            ("5. Security, Compliance and Risk Controls", [
                "NexaWorks is ISO/IEC 27001 certified and has a SOC 2 Type I report, with the Type II audit window under way. "
                "An annual penetration test is performed by an external firm. Data is encrypted with AES-256 at rest and TLS "
                "1.2 or higher in transit, with role-based access control, multi-factor authentication and audit logs "
                "retained for 12 months. Data is hosted in the India region. Disaster recovery targets are an RTO of 8 hours "
                "and an RPO of 30 minutes.",
            ]),
            ("6. Support Model, Experience and References", [
                "NexaWorks provides 24x7 support with a named Technical Account Manager. Priority 1 incidents (Severity 1) "
                "receive a 15-minute response time and a 4-hour resolution target; the platform SLA is 99.9% with service "
                "credits for any breach. A customer satisfaction (CSAT) score of 4.6 out of 5 was recorded over the last "
                "four quarters.",
                "We have delivered six similar integration projects over the last four years. References: Mr. S. Iyer, "
                "VP Operations, Godavari Dairy (fictional); Ms. P. Menon, CIO, Malabar Spices (fictional); Mr. D. Shetty, "
                "Head of IT, Western Grains (fictional).",
            ]),
        ],
        "price_table": [
            ("Platform licence (3 years)", "NexaFlow core, Kafka, 4 environments", "110.0"),
            ("Implementation services", "Mobilisation to hypercare", "135.0"),
            ("SAP and CRM connectors", "BAPI/IDoc and REST connectors", "30.0"),
            ("Training and knowledge transfer", "30 user-days", "10.0"),
            ("Support (3 years)", "24x7 support, named TAM, SLA 99.9%", "55.0"),
        ],
        "price_total": "340.0",
        "assumptions": [
            "Fixed price for implementation and hypercare; changes follow the change request process.",
            "Payment terms: 15% on mobilisation, 25% on design sign-off, 30% on UAT sign-off, 30% on go-live.",
            "The price is all-inclusive of 24x7 support. Prices exclude GST and are valid for 120 days.",
        ],
    },
    # ------------------------------------------------------------------ Orbit Digital
    "Orbit_Digital": {
        "name": "Orbit Digital",
        "accent": "#6a3d9a",
        "sections": [
            ("1. Executive Summary and Understanding of the Requirement", [
                "Orbit Digital thanks " + CLIENT + " for the opportunity to respond to " + RFP_TITLE + ". With more than "
                "fifteen years of experience delivering enterprise integration programmes, Orbit brings a depth of "
                "experience and customer trust that few providers can match. We understand Meridian's goal of connecting "
                "ERP, warehouse, CRM and invoicing systems into a seamless order-to-cash flow.",
            ]),
            ("2. Proposed Solution", [
                "Orbit proposes its OrbitHub integration platform, a proven product used across our client base. The "
                "platform provides an architecture based on reusable adapters and a central orchestration engine.",
                "The detailed integration approach for the ERP, the warehouse system and the e-invoicing portal will be "
                "finalised during the discovery phase. The list of connectors to be used is to be confirmed once the "
                "interface inventory is available, and performance targets will be defined with Meridian during design.",
            ]),
            ("3. Implementation Approach and Timeline", [
                "Orbit proposes delivery in approximately eight months in four phases: Phase 1 Discovery (6 weeks), "
                "Phase 2 Build (16 weeks), Phase 3 Testing and UAT (8 weeks) and Phase 4 Go-live (4 weeks). Orbit will "
                "assign a project manager and ten consultants, and a steering committee will meet monthly. Detailed "
                "milestones will be agreed at project kick-off. A risk register will be maintained throughout the project.",
            ]),
            ("4. Price Table and Assumptions", []),
            ("5. Security and Compliance", [
                "Orbit Digital is ISO/IEC 27001 certified. Data is encrypted in transit using TLS 1.2 and at rest. Users "
                "authenticate with multi-factor authentication and access is role-based. Audit logs are maintained for "
                "administrative actions. Details of penetration testing and disaster recovery targets can be shared on "
                "request.",
            ]),
            ("6. Support Model, Relevant Experience and References", [
                "Orbit provides 24x7 support through a global service desk with a 99.9% SLA and service credits. Priority 1 "
                "incidents receive a 30-minute response time. A customer satisfaction (CSAT) score of 4.5 out of 5 and a "
                "client retention rate of 94% have been maintained over the last three years.",
                "Orbit has completed 14 similar integration projects for manufacturing, retail and FMCG clients since 2009. "
                "Named references: Mr. V. Rao, CIO, Deccan Retail (fictional), Ms. N. Das, Director IT, Eastern Biscuits "
                "(fictional); Mr. K. Joshi, VP Technology, Coastal Foods (fictional); Ms. L. Pinto, Head of IT, Highland "
                "Tea Co. (fictional); Mr. T. Bose, CTO, Prime Dairy (fictional).",
            ]),
        ],
        "price_table": [
            ("Platform licence (3 years)", "OrbitHub core", "105.0"),
            ("Implementation services", "Estimated; subject to scoping", "150.0"),
            ("Connectors and training", "Quantity to be confirmed", "25.0"),
            ("Support (3 years)", "24x7 global service desk", "40.0"),
        ],
        "price_total": "320.0",
        "assumptions": [
            "Implementation effort is an estimate and is subject to scoping after discovery.",
            "Payment terms to be agreed in the contract. Prices exclude GST.",
        ],
    },
}


def build_pdf(key: str, spec: dict) -> Path:
    accent = colors.HexColor(spec["accent"])
    ss = getSampleStyleSheet()
    body = ParagraphStyle("body", parent=ss["Normal"], fontName="Helvetica", fontSize=10.5, leading=15.5, spaceAfter=8)
    h1 = ParagraphStyle("h1", parent=ss["Heading2"], fontName="Helvetica-Bold", fontSize=13, textColor=accent,
                        spaceBefore=16, spaceAfter=6)
    title = ParagraphStyle("title", parent=ss["Title"], fontName="Helvetica-Bold", fontSize=20, textColor=accent,
                           alignment=0, spaceAfter=2)
    sub = ParagraphStyle("sub", parent=ss["Normal"], fontSize=10, textColor=colors.HexColor("#444444"), spaceAfter=2)
    bullet = ParagraphStyle("bullet", parent=body, leftIndent=12, bulletIndent=2, spaceAfter=2)

    path = OUT_DIR / f"{key}_RFP_Response.pdf"
    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=18 * mm,
                            bottomMargin=18 * mm, title=f"{spec['name']} - RFP response (synthetic)",
                            author=spec["name"] + " (fictional)")

    def footer(canvas, _doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.grey)
        canvas.drawString(20 * mm, 10 * mm, f"{spec['name']} | Response to RFP-2026-017 | Synthetic classroom data - fictional")
        canvas.drawRightString(A4[0] - 20 * mm, 10 * mm, f"Page {_doc.page}")
        canvas.restoreState()

    story = [Paragraph(spec["name"], title),
             Paragraph("Proposal in response to " + RFP_TITLE, sub),
             Paragraph("Submitted to: " + CLIENT, sub), Spacer(1, 6)]

    for heading, paras in spec["sections"]:
        story.append(Paragraph(heading, h1))
        for p in paras:
            story.append(Paragraph(p, body))
        if heading.startswith("4."):
            rows = [["Item", "Description", "3-year cost (INR lakh)"]]
            rows += [list(r) for r in spec["price_table"]]
            rows.append(["Total", "Total contract price (3 years)", spec["price_total"]])
            t = Table(rows, colWidths=[55 * mm, 75 * mm, 40 * mm])
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), accent), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9), ("ALIGN", (2, 0), (2, -1), "RIGHT"),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#bbbbbb")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor("#f3f3f3")]),
                ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]))
            story += [t, Spacer(1, 6), Paragraph("<b>Assumptions</b>", body)]
            story += [Paragraph(a, bullet, bulletText="-") for a in spec["assumptions"]]
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return path


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for key, spec in SUPPLIERS.items():
        print("wrote", build_pdf(key, spec))


if __name__ == "__main__":
    main()
