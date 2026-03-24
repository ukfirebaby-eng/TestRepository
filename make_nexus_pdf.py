"""
Generates a large test PDF for Diamond Miner: Nexus Digital Transformation Programme.

Deliberately embeds:
  - 6 structural contradictions  (REQUIRES + BLOCKS paradoxes)
  - 4 hub nodes                  (Identity Platform, Core Database, Network Upgrade, Compliance Authority)
  - 4 schedule conflicts         (negative slack between STARTS_AFTER pairs)
  - Dense temporal metadata      (ISO 8601 dates throughout)
"""
import fitz

# ---------------------------------------------------------------------------
# Document content
# Each section: heading + body paragraph(s).  Longer bodies = more chunks.
# ---------------------------------------------------------------------------

SECTIONS = [
    # ── TITLE ───────────────────────────────────────────────────────────────
    {
        "heading": "Nexus Enterprise Digital Transformation Programme\nMaster Programme Charter — Version 3.0",
        "body": None,
        "is_title": True,
    },

    # ── 1. EXECUTIVE SUMMARY ────────────────────────────────────────────────
    {
        "heading": "1. Executive Summary",
        "body": (
            "The Nexus Programme is the largest technology transformation initiative ever undertaken "
            "by the organisation. It replaces five legacy systems with a unified cloud-native architecture "
            "spanning Identity, Data, Network, AI, and Compliance domains. "
            "The programme is structured across four sequential phases: Foundation (February 2026 to June 2026), "
            "Integration (May 2026 to September 2026), Validation (July 2026 to November 2026), and "
            "Production Deployment (October 2026 to March 2027). "
            "Total programme budget is £47.2 million across 22 months. "
            "The programme is governed by the Nexus Steering Board, reporting to the Chief Technology Officer. "
            "All phase gates require sign-off from the Compliance Authority and the Security Certification Body "
            "before any production-affecting activity may proceed. "
            "This charter is effective from 1 February 2026 and supersedes all prior programme documentation."
        ),
    },

    # ── 2. PROGRAMME OBJECTIVES ─────────────────────────────────────────────
    {
        "heading": "2. Programme Objectives and Strategic Alignment",
        "body": (
            "The Nexus Programme delivers against four strategic pillars endorsed by the Board of Directors "
            "in the 2025 Technology Strategy Review. "
            "Pillar 1 — Unified Identity: Every internal system and customer-facing service must authenticate "
            "through a single Identity Platform, replacing seven disparate login mechanisms and eliminating "
            "the password synchronisation failures that caused three production incidents in 2025. "
            "Pillar 2 — Data Consolidation: All transactional and analytical workloads must be served from "
            "a single Core Database cluster, eliminating the twelve point-to-point data feeds currently "
            "maintained by the Database Administration Team. "
            "Pillar 3 — Infrastructure Modernisation: The ageing on-premises network must be replaced by a "
            "fully resilient Network Infrastructure Upgrade, enabling Cloud Migration and the retirement of "
            "the primary data centre lease which expires on 31 December 2026. "
            "Pillar 4 — Intelligent Automation: An AI Platform fed by a governed Training Data Repository "
            "must be operational by Q4 2026, enabling the Machine Learning Pipeline that the Product "
            "organisation has committed to three enterprise customers in binding SLAs."
        ),
    },

    # ── 3. PROGRAMME GOVERNANCE ──────────────────────────────────────────────
    {
        "heading": "3. Programme Governance Structure",
        "body": (
            "The Nexus Steering Board has ultimate authority over scope, budget, and schedule. "
            "It meets fortnightly and produces the Programme Authority Notice consumed by the Compliance "
            "Authority at each phase gate. "
            "The Compliance Authority requires the Programme Authority Notice before opening any phase gate "
            "review. The Compliance Authority produces the Gate Approval Certificate consumed by every "
            "delivery workstream as the prerequisite for production activity. "
            "The Security Certification Body operates independently of the Nexus Steering Board and "
            "requires a completed penetration test report before issuing the Security Certification. "
            "The Security Certification is required by Cloud Migration, by Production Deployment, and by "
            "the AI Platform go-live. "
            "The Data Protection Officer produces the GDPR Compliance Sign-Off required by the Training "
            "Data Repository before any personal data may be ingested for model training. "
            "The Change Advisory Board requires a completed impact assessment from each workstream "
            "before scheduling any change in the production change window. "
            "Programme-level risks are owned by the Programme Director, who reports to the "
            "Nexus Steering Board at each fortnightly session."
        ),
    },

    # ── 4. IDENTITY DOMAIN ────────────────────────────────────────────────
    {
        "heading": "4. Identity Domain — Workstream A",
        "body": (
            "The Identity Platform is the central authentication and authorisation broker for all "
            "Nexus programme workstreams. It provides OAuth 2.0, SAML 2.0, and OpenID Connect endpoints "
            "consumed by every downstream application. "
            "The SSO Module requires Identity Platform to be deployed and health-checked before any "
            "user-facing application may be connected. "
            "The MFA Gateway requires Identity Platform to be operational because all second-factor "
            "challenges are routed through the Identity Platform token service. "
            "The HR Integration Service requires Identity Platform so that employee provisioning and "
            "deprovisioning events are propagated to all connected systems within the SLA of four hours. "
            "The Finance Integration Module requires Identity Platform for role-based access control "
            "enforcement on all financial transactions above £10,000. "
            "The Customer Portal requires Identity Platform because unauthenticated access to customer "
            "account data is prohibited under the organisation's data classification policy. "
            "The Audit System requires Identity Platform to capture a complete authentication event log "
            "for the mandatory 7-year retention period required by the Financial Conduct Authority. "
            "Identity Platform is therefore the highest-centrality node in the programme dependency graph: "
            "six separate workstreams cannot proceed until it is live. "
            "The Identity Platform is scheduled to be deployed and signed off by 1 April 2026."
        ),
    },

    # ── 5. IDENTITY CONTRADICTION ─────────────────────────────────────────
    {
        "heading": "5. Identity Domain — Open Conflict: Privacy Board Objection",
        "body": (
            "The Privacy Board has formally objected to the Identity Platform architecture on the grounds "
            "that centralising all authentication events in a single platform creates a high-value target "
            "for data exfiltration and violates the data minimisation principle of the UK GDPR. "
            "The Privacy Board blocks Identity Platform deployment until a privacy impact assessment "
            "is reviewed and approved, a process estimated to take between 60 and 90 days from submission. "
            "The SSO Module requires Identity Platform, and the Identity Platform deployment is blocked "
            "by the Privacy Board. The MFA Gateway requires Identity Platform, which is blocked. "
            "The HR Integration Service requires Identity Platform, which the Privacy Board blocks. "
            "The Finance Integration Module requires Identity Platform; the Privacy Board blocks it. "
            "The Customer Portal requires Identity Platform, which remains blocked. "
            "This constitutes a cascading structural conflict: every workstream that requires Identity "
            "Platform is transitively blocked by the Privacy Board's objection. "
            "The Nexus Steering Board is aware of this conflict. As of the date of this charter, "
            "no resolution or escalation path has been agreed. The programme schedule assumes "
            "Identity Platform deployment proceeds on 1 April 2026, which is inconsistent with the "
            "Privacy Board's stated timeline. "
            "Resolution options include federated identity (rejected by Security Certification Body "
            "as insufficiently auditable) or a phased privacy review (not yet scheduled)."
        ),
    },

    # ── 6. DATA DOMAIN ────────────────────────────────────────────────────
    {
        "heading": "6. Data Domain — Workstream B",
        "body": (
            "The Core Database cluster is a PostgreSQL 16 active-active deployment across three "
            "availability zones, replacing Oracle 11g instances running on hardware that reaches "
            "end-of-support on 30 June 2026. "
            "The Analytics Engine requires Core Database because all analytical queries are issued "
            "directly against the production replica set; a separate analytical database was rejected "
            "as a cost overrun in the 2025 budget review. "
            "The Reporting Module requires Core Database for its nightly batch extract jobs that "
            "populate the executive dashboards consumed by the Nexus Steering Board. "
            "The Customer Portal requires Core Database to retrieve and persist customer account "
            "records in real time. "
            "The API Gateway requires Core Database for request routing rules and rate-limit configuration "
            "stored in the operations schema. "
            "The Archive System requires Core Database because the archival policy engine reads "
            "retention metadata from the Core Database catalogue table. "
            "Data migration from Oracle 11g to PostgreSQL 16 is scheduled to begin on 1 April 2026 "
            "and complete on 31 July 2026. "
            "Core Database cluster provisioning begins on 1 February 2026 and must be complete "
            "by 31 March 2026 so that migration tooling can be validated before the migration window opens."
        ),
    },

    # ── 7. DATA DOMAIN CONTRADICTION ─────────────────────────────────────
    {
        "heading": "7. Data Domain — Open Conflict: Data Centre Decommission",
        "body": (
            "Cloud Migration requires Data Centre Decommission to proceed on schedule, because "
            "the cloud hosting costs and the data centre lease cannot be carried concurrently beyond "
            "31 December 2026 without breaching the programme budget envelope. "
            "Data Centre Decommission requires all production workloads to have been migrated to "
            "cloud infrastructure and validated before the facility access is surrendered. "
            "However, the Compliance Authority blocks Data Centre Decommission because the on-premises "
            "audit trail — stored on data centre-local storage arrays — must remain accessible for a "
            "minimum of 12 months following the end of the last financial year covered by the audit. "
            "The Compliance Authority's position is that decommissioning the data centre before "
            "31 March 2027 would breach statutory record-keeping obligations. "
            "Cloud Migration requires Data Centre Decommission, but the Compliance Authority "
            "blocks Data Centre Decommission. This is a direct structural conflict. "
            "The data centre lease expiry on 31 December 2026 creates a hard cost forcing function "
            "that the Compliance Authority objection does not accommodate. "
            "The Legal team has been asked to advise on whether cloud-replicated audit logs satisfy "
            "the statutory requirement. No response has been received as of the charter date."
        ),
    },

    # ── 8. NETWORK DOMAIN ────────────────────────────────────────────────
    {
        "heading": "8. Network Domain — Workstream C",
        "body": (
            "The Network Infrastructure Upgrade replaces the organisation's flat 10GbE LAN with a "
            "fully segmented 100GbE spine-and-leaf topology with software-defined networking control. "
            "The upgrade is scheduled to begin on 1 March 2026 and complete by 31 May 2026. "
            "Cloud Migration requires Network Infrastructure Upgrade because the direct-connect "
            "circuits to the cloud provider require the new spine switches to be in place. "
            "Video Conferencing Platform requires Network Infrastructure Upgrade because the existing "
            "network cannot sustain the QoS policies required for 4K video across 40 concurrent rooms. "
            "Secure Remote Access requires Network Infrastructure Upgrade because the zero-trust NAC "
            "policy enforcement points are integrated into the new spine-and-leaf control plane. "
            "VPN Gateway requires Network Infrastructure Upgrade because the IPsec tunnel termination "
            "capacity is physically hosted on the new spine switches. "
            "The Network Infrastructure Upgrade is therefore a hub node: four separate workstreams "
            "are blocked until it completes. Any delay to the network upgrade propagates to "
            "Cloud Migration, Video Conferencing, Secure Remote Access, and VPN Gateway simultaneously. "
            "The network team has flagged a 15% risk of a 4-week delay due to supplier lead times "
            "on the 100GbE line cards, which are currently on a 14-week order cycle."
        ),
    },

    # ── 9. NETWORK CONTRADICTION ─────────────────────────────────────────
    {
        "heading": "9. Network Domain — Open Conflict: Security Certification Hold",
        "body": (
            "The Security Certification Body requires a completed penetration test of the new "
            "network architecture before issuing the Security Certification that permits Cloud Migration. "
            "The penetration test requires the Network Infrastructure Upgrade to be fully installed "
            "and operational before the test environment can be stood up. "
            "Cloud Migration requires Security Certification, and Security Certification requires "
            "the penetration test, and the penetration test requires Network Infrastructure Upgrade. "
            "However, the Security Certification Body blocks Cloud Migration until certification is issued, "
            "and the Security Certification Body has stated it will not issue certification based on "
            "a partial or simulated network environment. "
            "The programme schedule assumes Cloud Migration begins on 1 June 2026. "
            "The Security Certification Body's earliest available penetration test slot is 15 June 2026, "
            "after the Network Infrastructure Upgrade completes on 31 May 2026. "
            "The penetration test and remediation cycle is estimated at 6 to 8 weeks, meaning "
            "Security Certification cannot be issued before 10 August 2026 at the earliest. "
            "Cloud Migration requires Security Certification; the Security Certification Body blocks "
            "Cloud Migration until certification is issued. The scheduled Cloud Migration start date "
            "of 1 June 2026 is therefore unachievable given the Security Certification Body's constraints. "
            "This conflict has not been escalated to the Nexus Steering Board."
        ),
    },

    # ── 10. AI DOMAIN ────────────────────────────────────────────────────
    {
        "heading": "10. AI Domain — Workstream D",
        "body": (
            "The AI Platform is a GPU-accelerated model training and inference cluster deployed on "
            "cloud infrastructure. It exposes a managed API consumed by the Machine Learning Pipeline "
            "and the BI Reporting Suite's predictive analytics module. "
            "The AI Platform requires the Training Data Repository to be populated with at least "
            "18 months of historical transaction data before the first model training run can produce "
            "results within the accuracy thresholds committed to enterprise customers. "
            "The Machine Learning Pipeline requires AI Platform because all feature engineering, "
            "model training, and inference serving is delegated to the platform's managed runtime. "
            "The BI Reporting Suite requires the Data Warehouse, and the Data Warehouse requires "
            "Core Database as its source-of-record feed. "
            "The AI Platform is scheduled to be operational by 1 August 2026. "
            "The Training Data Repository population is scheduled to begin on 1 May 2026 and "
            "complete by 31 July 2026. "
            "The Machine Learning Pipeline first production run is scheduled for 1 September 2026. "
            "Three enterprise customers have contracted for ML Pipeline outputs from 1 October 2026, "
            "creating a hard external deadline that cannot be moved without triggering penalty clauses "
            "totalling £3.2 million."
        ),
    },

    # ── 11. AI CONTRADICTION ─────────────────────────────────────────────
    {
        "heading": "11. AI Domain — Open Conflict: GDPR Training Data Block",
        "body": (
            "The Training Data Repository requires GDPR Compliance Sign-Off from the Data Protection "
            "Officer before any personal data may be ingested. The repository contains customer "
            "transaction records, browsing behaviour, and support interaction logs — all of which "
            "are classified as personal data under the UK GDPR definition. "
            "The GDPR Compliance Framework blocks Training Data Repository population until a lawful "
            "basis for processing has been established, a Records of Processing Activities entry has "
            "been created, and a Data Protection Impact Assessment has been signed off by the "
            "Data Protection Officer. "
            "The Data Protection Officer has estimated the DPIA review and sign-off process will take "
            "a minimum of 10 weeks from the date of submission. The DPIA has not yet been submitted "
            "as of the date of this charter. "
            "The AI Platform requires Training Data Repository. The GDPR Compliance Framework blocks "
            "Training Data Repository. Therefore the AI Platform cannot meet its 1 August 2026 "
            "go-live date unless the DPIA is submitted immediately and the Data Protection Officer "
            "prioritises its review. "
            "The Machine Learning Pipeline requires AI Platform, meaning the 1 September 2026 "
            "first production run is also at risk. "
            "The enterprise customer penalty exposure of £3.2 million is directly contingent on "
            "resolving this GDPR compliance conflict before 1 July 2026."
        ),
    },

    # ── 12. INFRASTRUCTURE DOMAIN ─────────────────────────────────────────
    {
        "heading": "12. Infrastructure Domain — Workstream E",
        "body": (
            "The infrastructure workstream decommissions the legacy on-premises estate and migrates "
            "all workloads to the contracted cloud provider. "
            "The Disaster Recovery System requires the Primary Production System to be the source "
            "of replication; DR cannot be stood up until the Primary Production System has been "
            "migrated to cloud and health-checked. "
            "Disaster Recovery System provisioning is scheduled to begin on 1 July 2026 and "
            "complete by 31 August 2026. "
            "Primary Production System cloud migration is scheduled to begin on 1 June 2026 and "
            "complete by 30 June 2026. "
            "The Container Orchestration platform requires the DevOps Pipeline to be operational "
            "because all containerised workload deployments are managed through the CI/CD toolchain. "
            "The DevOps Pipeline requires the API Gateway to be deployed before pipeline jobs "
            "can push artefacts to the container registry. "
            "The Service Mesh requires Container Orchestration because all inter-service mTLS "
            "is managed by the service mesh control plane running inside the cluster. "
            "Load Balancer Cluster requires API Gateway to be deployed and traffic routing rules "
            "to be configured before any external traffic can be admitted to the platform. "
            "The infrastructure workstream is on the critical path for 14 of the 22 delivery "
            "milestones in the programme schedule."
        ),
    },

    # ── 13. INFRASTRUCTURE CONTRADICTION ──────────────────────────────────
    {
        "heading": "13. Infrastructure Domain — Open Conflict: SLA Uptime Block",
        "body": (
            "The Primary Production System migration to cloud requires a maintenance window during "
            "which the primary database is in read-only mode for an estimated 4 to 6 hours. "
            "The SLA Compliance obligation requires 99.95% monthly uptime for the Primary Production "
            "System, which permits a maximum of 21.6 minutes of unplanned downtime per month. "
            "The SLA Compliance obligation blocks Primary Production System Shutdown because a "
            "4-to-6-hour maintenance window would consume 1,100% of the monthly downtime allowance "
            "in a single event, triggering SLA breach penalties estimated at £180,000 per hour. "
            "Cloud Migration requires the Primary Production System to be migrated, which requires "
            "a shutdown window, which the SLA Compliance obligation blocks. "
            "Disaster Recovery System requires Primary Production System to be on cloud infrastructure, "
            "meaning the DR go-live is also transitively blocked. "
            "The Infrastructure team has proposed a blue-green migration approach that would reduce "
            "the downtime window to under 5 minutes, but this approach requires a second cloud "
            "environment licence costing £240,000 that has not been approved in the programme budget. "
            "The Nexus Steering Board has not been presented with this trade-off."
        ),
    },

    # ── 14. API AND INTEGRATION DOMAIN ────────────────────────────────────
    {
        "heading": "14. API and Integration Domain — Workstream F",
        "body": (
            "The Unified API Layer consolidates 23 legacy point-to-point integrations into a single "
            "managed API gateway, reducing integration maintenance effort from 3.4 FTE to 0.8 FTE annually. "
            "The Unified API Layer requires Legacy API Deprecation to be completed because the legacy "
            "endpoints and the new Unified API Layer cannot coexist on the same hostname without "
            "routing conflicts that would make end-to-end tracing impossible. "
            "The API Gateway requires Core Database for its configuration store, as described in "
            "Workstream B. "
            "The Third-Party Integration Framework connects 14 external vendors to the organisation's "
            "APIs under contractual arrangements that reference specific legacy endpoint URLs. "
            "The Third-Party Integration Framework blocks Legacy API Deprecation because vendor contracts "
            "contain clause 7.4 which requires 12 months' written notice before any endpoint URL change. "
            "The earliest any vendor contract permits endpoint migration is 1 March 2027. "
            "The Unified API Layer requires Legacy API Deprecation, and the Third-Party Integration "
            "Framework blocks Legacy API Deprecation. This is a direct structural conflict. "
            "The programme schedule assumes Legacy API Deprecation completes by 30 September 2026, "
            "which is 18 months before the contractual notice period permits it. "
            "Legal has been asked to review clause 7.4 but has not yet provided an opinion."
        ),
    },

    # ── 15. CHANGE MANAGEMENT ─────────────────────────────────────────────
    {
        "heading": "15. Change Management and Communications",
        "body": (
            "The Change Management workstream supports all five delivery workstreams with stakeholder "
            "communications, training delivery, and adoption measurement. "
            "The HR Integration Service deployment requires the Change Management training programme "
            "to have been delivered to all 4,200 employees before the new HR portal goes live. "
            "The Customer Portal requires a customer communications campaign to have been completed "
            "at least 30 days before launch, informing customers of the new login experience. "
            "The Change Advisory Board requires impact assessments from all workstreams before "
            "scheduling any production change. "
            "The Communications team produces the customer communications campaign material consumed "
            "by the Customer Portal pre-launch checklist. "
            "The Training team produces the employee training programme consumed by the HR Integration "
            "Service deployment checklist. "
            "Change Management activities begin on 1 February 2026 and run continuously through "
            "to programme close on 31 March 2027. "
            "A change readiness survey is scheduled for 1 May 2026 and must be completed before "
            "the Integration Phase begins. Change readiness score must be above 70% for the "
            "Integration Phase gate to open."
        ),
    },

    # ── 16. SCHEDULE: PHASE 1 ─────────────────────────────────────────────
    {
        "heading": "16. Phase 1 — Foundation Schedule (February 2026 to June 2026)",
        "body": (
            "Phase 1 Foundation begins on 1 February 2026 and is scheduled to end on 30 June 2026. "
            "Key milestones and their committed dates are as follows. "
            "Core Database cluster provisioning: start 1 February 2026, end 31 March 2026. "
            "Network Infrastructure Upgrade: start 1 March 2026, end 31 May 2026. "
            "Identity Platform deployment: start 1 March 2026, end 1 April 2026. "
            "Data Encryption Module delivery: start 1 February 2026, end 15 March 2026. "
            "Security Audit of Identity Platform: start 15 April 2026, end 30 June 2026. "
            "Privacy Board impact assessment review: start 1 February 2026, end 30 April 2026. "
            "Phase 1 gate review is scheduled for 1 July 2026 and requires all Foundation milestones "
            "to be complete and signed off by the Compliance Authority. "
            "Phase 2 Integration begins on 1 May 2026 and must start after Phase 1 Foundation ends. "
            "Phase 1 ends on 30 June 2026. Phase 2 starts on 1 May 2026. "
            "Phase 2 must start after Phase 1 ends, but Phase 2 is scheduled to start 60 days "
            "before Phase 1 ends. This represents 60 days of negative slack on the phase boundary."
        ),
    },

    # ── 17. SCHEDULE: PHASE 2 ─────────────────────────────────────────────
    {
        "heading": "17. Phase 2 — Integration Schedule (May 2026 to September 2026)",
        "body": (
            "Phase 2 Integration begins on 1 May 2026 and is scheduled to end on 30 September 2026. "
            "Key milestones within Phase 2 are as follows. "
            "API Gateway deployment: start 1 May 2026, end 31 May 2026. "
            "Load Balancer Cluster configuration: start 1 June 2026, end 15 June 2026. "
            "Data Migration (Oracle to PostgreSQL): start 1 April 2026, end 31 July 2026. "
            "User Acceptance Testing: start 1 June 2026, end 31 August 2026. "
            "Training Data Repository population: start 1 May 2026, end 31 July 2026. "
            "Change Readiness Survey: scheduled 1 May 2026. "
            "Integration Testing: start 1 June 2026, end 31 August 2026. "
            "User Acceptance Testing must start after Data Migration ends. "
            "Data Migration ends on 31 July 2026. User Acceptance Testing starts on 1 June 2026. "
            "User Acceptance Testing must start after Data Migration ends, but it is scheduled "
            "to start 60 days before Data Migration ends. This is 60 days of negative slack. "
            "Integration Testing must start after the API Gateway is deployed. "
            "API Gateway deployment ends 31 May 2026 and Integration Testing starts 1 June 2026; "
            "this dependency has zero slack and is on the critical path."
        ),
    },

    # ── 18. SCHEDULE: PHASE 3 ─────────────────────────────────────────────
    {
        "heading": "18. Phase 3 — Validation Schedule (July 2026 to November 2026)",
        "body": (
            "Phase 3 Validation begins on 1 July 2026 and is scheduled to end on 30 November 2026. "
            "Key milestones within Phase 3 are as follows. "
            "Disaster Recovery System provisioning: start 1 July 2026, end 31 August 2026. "
            "Security Certification penetration test: start 15 June 2026, end 15 August 2026. "
            "Security Certification issuance: start 15 August 2026, end 15 November 2026. "
            "Go-Live Rehearsal: start 1 July 2026, end 31 August 2026. "
            "Regulatory Approval Gate review: scheduled 1 October 2026. "
            "Production Deployment go-live: start 1 October 2026, end 31 March 2027. "
            "Production Deployment must start after Security Certification is issued. "
            "Security Certification is not issued until 15 November 2026. "
            "Production Deployment is scheduled to start on 1 October 2026. "
            "Production Deployment must start after Security Certification ends, but is scheduled "
            "to start 45 days before Security Certification is complete. This is 45 days of negative slack. "
            "Go-Live Rehearsal must start after Integration Testing ends. "
            "Integration Testing ends on 31 August 2026. Go-Live Rehearsal starts on 1 July 2026. "
            "Go-Live Rehearsal must start after Integration Testing ends, but starts 61 days before "
            "Integration Testing ends. This is 61 days of negative slack on this dependency."
        ),
    },

    # ── 19. RISK REGISTER ─────────────────────────────────────────────────
    {
        "heading": "19. Programme Risk Register",
        "body": (
            "Risk R-01 (Critical): Privacy Board blocks Identity Platform deployment. "
            "The Privacy Board objection to the Identity Platform architecture, if not resolved by "
            "1 April 2026, will cascade to SSO Module, MFA Gateway, HR Integration Service, "
            "Finance Integration Module, Customer Portal, and Audit System — six workstreams blocked. "
            "Probability: High. Impact: Critical. Owner: Chief Privacy Officer. "
            "Due date: Resolution required by 15 March 2026. "
            "Risk R-02 (Critical): GDPR Framework blocks Training Data Repository. "
            "If the DPIA is not submitted by 1 April 2026, the AI Platform cannot be operational "
            "by 1 August 2026, triggering Machine Learning Pipeline delays and the £3.2 million "
            "enterprise customer penalty exposure. "
            "Probability: High. Impact: Critical. Owner: Data Protection Officer. "
            "Due date: DPIA submission required by 1 April 2026. "
            "Risk R-03 (High): SLA Compliance blocks Primary Production System migration. "
            "The 4-to-6-hour maintenance window required for cloud migration conflicts with "
            "the 99.95% uptime SLA. Without the blue-green migration budget of £240,000, "
            "Cloud Migration and Disaster Recovery are both at risk. "
            "Probability: Medium. Impact: High. Owner: Infrastructure Director. "
            "Due date: Budget decision required by 1 March 2026. "
            "Risk R-04 (High): Compliance Authority blocks Data Centre Decommission. "
            "The statutory record-keeping obligation may prevent Data Centre Decommission before "
            "31 March 2027, breaching the budget envelope by an estimated £480,000 in extended "
            "lease costs. "
            "Probability: Medium. Impact: High. Owner: General Counsel. "
            "Due date: Legal advice required by 1 March 2026. "
            "Risk R-05 (High): Third-Party Integration Framework blocks Legacy API Deprecation. "
            "Vendor clause 7.4 requires 12 months notice; earliest migration is 1 March 2027, "
            "19 months after the planned 30 September 2026 deprecation date. "
            "Probability: High. Impact: High. Owner: Vendor Management Director. "
            "Due date: Clause 7.4 renegotiation or waiver required by 1 April 2026. "
            "Risk R-06 (Medium): Security Certification Body blocks Cloud Migration. "
            "Earliest certification issuance is 10 August 2026, making the 1 June 2026 Cloud "
            "Migration start date unachievable. "
            "Probability: High. Impact: Medium. Owner: Security Director. "
            "Due date: Certification timeline confirmed by 1 February 2026. "
            "Risk R-07 (Medium): Network supplier lead time delay. "
            "100GbE line cards on 14-week order cycle; 15% risk of 4-week delay impacting "
            "Cloud Migration, Video Conferencing, Secure Remote Access, and VPN Gateway. "
            "Probability: Low. Impact: Medium. Owner: Network Procurement Manager. "
            "Due date: Order confirmation required by 1 January 2026."
        ),
    },

    # ── 20. RESOURCE PLAN ─────────────────────────────────────────────────
    {
        "heading": "20. Resource Allocation and Capacity Plan",
        "body": (
            "The programme requires 87 internal FTE and 34 contractor roles across 22 months. "
            "The Database Administration Team (8 FTE) is fully allocated to Core Database provisioning "
            "from 1 February 2026 to 31 March 2026, then to Data Migration from 1 April 2026 "
            "to 31 July 2026, then to Integration Testing support from 1 August 2026 to "
            "31 August 2026. The Database Administration Team has zero contingency capacity during "
            "these periods. Any unplanned work arriving from the Analytics Engine or Reporting Module "
            "during Data Migration will require explicit reprioritisation by the Nexus Steering Board. "
            "The Security Team (6 FTE) is allocated to Data Encryption Module from 1 February 2026 "
            "to 15 March 2026, to Security Audit from 15 April 2026 to 30 June 2026, and to "
            "penetration test support from 15 June 2026 to 15 August 2026. "
            "The Security Team requires the Data Encryption Module to be complete before Security "
            "Audit begins. The Data Encryption Module produces the encryption key manifest that "
            "Security Audit requires. "
            "The Security Team is therefore self-blocking: if the Data Encryption Module slips "
            "beyond 15 April 2026, the Security Team's own Security Audit window is compressed. "
            "The Network Engineering Team (12 FTE) is allocated exclusively to Network Infrastructure "
            "Upgrade from 1 March 2026 to 31 May 2026, with no capacity for other work. "
            "The AI/ML Team (10 FTE) begins Training Data Repository setup on 1 May 2026 and "
            "transitions to AI Platform deployment from 1 July 2026. "
            "The DevOps Team (9 FTE) provisions the CI/CD pipeline from 1 April 2026 and the "
            "Container Orchestration platform from 1 May 2026."
        ),
    },

    # ── 21. BUDGET ────────────────────────────────────────────────────────
    {
        "heading": "21. Programme Budget Summary",
        "body": (
            "Total approved programme budget: £47,200,000. "
            "Phase 1 Foundation: £12,400,000 (budget release date: 1 February 2026). "
            "Phase 2 Integration: £15,800,000 (budget release date: 1 May 2026). "
            "Phase 3 Validation: £9,600,000 (budget release date: 1 July 2026). "
            "Phase 4 Production Deployment: £9,400,000 (budget release date: 1 October 2026). "
            "Budget release for each phase requires the Nexus Steering Board approval and "
            "the Compliance Authority Gate Approval Certificate. "
            "The Nexus Steering Board produces the budget release authorisation consumed by the "
            "Finance Integration Module's cost centre allocation process. "
            "Unresolved risks carry a combined expected value of £7,840,000 against a contingency "
            "reserve of £3,200,000, leaving a residual exposure of £4,640,000 that is not "
            "currently funded in the approved budget. "
            "The blue-green migration option (Risk R-03) costs £240,000 and is not in the budget. "
            "The extended data centre lease (Risk R-04) costs up to £480,000 and is not in the budget. "
            "The enterprise customer SLA penalties (Risk R-02) are £3.2 million and are not insured. "
            "The vendor API contract renegotiation (Risk R-05) carries legal costs estimated at £120,000."
        ),
    },

    # ── 22. DEPENDENCY MAP ────────────────────────────────────────────────
    {
        "heading": "22. Full Programme Dependency Map",
        "body": (
            "The following relationships are the formal programme dependency register. "
            "SSO Module REQUIRES Identity Platform. "
            "MFA Gateway REQUIRES Identity Platform. "
            "HR Integration Service REQUIRES Identity Platform. "
            "Finance Integration Module REQUIRES Identity Platform. "
            "Customer Portal REQUIRES Identity Platform. "
            "Audit System REQUIRES Identity Platform. "
            "Privacy Board BLOCKS Identity Platform. "
            "Analytics Engine REQUIRES Core Database. "
            "Reporting Module REQUIRES Core Database. "
            "Customer Portal REQUIRES Core Database. "
            "API Gateway REQUIRES Core Database. "
            "Archive System REQUIRES Core Database. "
            "Data Warehouse REQUIRES Core Database. "
            "Cloud Migration REQUIRES Network Infrastructure Upgrade. "
            "Video Conferencing Platform REQUIRES Network Infrastructure Upgrade. "
            "Secure Remote Access REQUIRES Network Infrastructure Upgrade. "
            "VPN Gateway REQUIRES Network Infrastructure Upgrade. "
            "AI Platform REQUIRES Training Data Repository. "
            "Machine Learning Pipeline REQUIRES AI Platform. "
            "BI Reporting Suite REQUIRES Data Warehouse. "
            "Disaster Recovery System REQUIRES Primary Production System. "
            "Container Orchestration REQUIRES DevOps Pipeline. "
            "Service Mesh REQUIRES Container Orchestration. "
            "Load Balancer Cluster REQUIRES API Gateway. "
            "Unified API Layer REQUIRES Legacy API Deprecation. "
            "Cloud Migration REQUIRES Security Certification. "
            "Compliance Authority BLOCKS Data Centre Decommission. "
            "GDPR Compliance Framework BLOCKS Training Data Repository. "
            "SLA Compliance BLOCKS Primary Production System Shutdown. "
            "Third-Party Integration Framework BLOCKS Legacy API Deprecation. "
            "Security Certification Body BLOCKS Cloud Migration. "
            "Cloud Migration REQUIRES Data Centre Decommission. "
            "Production Deployment REQUIRES Security Certification. "
            "Production Deployment REQUIRES Integration Testing. "
            "Integration Testing REQUIRES API Gateway. "
            "Regulatory Hold BLOCKS Production Deployment. "
            "DevOps Pipeline REQUIRES API Gateway."
        ),
    },

    # ── 23. TEMPORAL DEPENDENCY MAP ───────────────────────────────────────
    {
        "heading": "23. Temporal Dependency and Schedule Sequence Register",
        "body": (
            "The following STARTS_AFTER relationships are recorded in the programme schedule. "
            "Phase 2 Integration STARTS_AFTER Phase 1 Foundation. "
            "Phase 1 Foundation ends on 2026-06-30. Phase 2 Integration starts on 2026-05-01. "
            "Phase 2 starts before Phase 1 ends: negative slack of 60 days. "
            "User Acceptance Testing STARTS_AFTER Data Migration. "
            "Data Migration ends on 2026-07-31. User Acceptance Testing starts on 2026-06-01. "
            "UAT starts before Data Migration ends: negative slack of 60 days. "
            "Production Deployment STARTS_AFTER Security Certification. "
            "Security Certification ends on 2026-11-15. Production Deployment starts on 2026-10-01. "
            "Production Deployment starts before Security Certification ends: negative slack of 45 days. "
            "Go-Live Rehearsal STARTS_AFTER Integration Testing. "
            "Integration Testing ends on 2026-08-31. Go-Live Rehearsal starts on 2026-07-01. "
            "Go-Live Rehearsal starts before Integration Testing ends: negative slack of 61 days. "
            "Machine Learning Pipeline STARTS_AFTER AI Platform. "
            "AI Platform ends on 2026-08-01. Machine Learning Pipeline starts on 2026-09-01. "
            "This dependency has positive slack of 31 days. "
            "Disaster Recovery System STARTS_AFTER Primary Production System cloud migration. "
            "Primary Production System migration ends on 2026-06-30. "
            "Disaster Recovery System starts on 2026-07-01. Positive slack of 1 day. "
            "Network Infrastructure Upgrade must complete before Cloud Migration begins. "
            "Network Infrastructure Upgrade ends 2026-05-31. Cloud Migration starts 2026-06-01. "
            "Zero slack on this dependency — any network delay directly delays cloud migration."
        ),
    },

    # ── 24. COMPLIANCE FRAMEWORK ─────────────────────────────────────────
    {
        "heading": "24. Regulatory and Compliance Framework",
        "body": (
            "The programme is subject to the following regulatory instruments, each imposing "
            "mandatory constraints on programme activities. "
            "UK GDPR (2018): governs all processing of personal data. The GDPR Compliance Framework "
            "blocks Training Data Repository population until DPIA sign-off is received. "
            "Financial Services and Markets Act: requires the Audit System to retain a 7-year "
            "authentication log accessible at all times. The Audit System requires Identity Platform. "
            "Network and Information Systems Regulations (NIS): requires Secure Remote Access and "
            "VPN Gateway to use approved cryptographic standards. Both require Network Infrastructure Upgrade. "
            "ISO 27001 certification: the Security Certification Body requires evidence of ISO 27001 "
            "compliance before issuing Security Certification for Cloud Migration. "
            "The Compliance Authority produces the Gate Approval Certificate at four programme checkpoints: "
            "Foundation Gate (1 July 2026), Integration Gate (1 October 2026), "
            "Validation Gate (1 December 2026), and Production Gate (1 January 2027). "
            "Each Gate Approval Certificate requires a completed assurance package from the Security Team "
            "and a Programme Authority Notice from the Nexus Steering Board. "
            "Regulatory Hold is automatically invoked if any gate is missed or any open compliance finding "
            "is not remediated within 30 days of being raised. "
            "Regulatory Hold blocks Production Deployment, blocks API Gateway deployment, "
            "and blocks Legacy System Shutdown simultaneously."
        ),
    },

    # ── 25. TECHNICAL ARCHITECTURE ────────────────────────────────────────
    {
        "heading": "25. Target State Technical Architecture",
        "body": (
            "The target architecture is a fully cloud-native microservices platform hosted on the "
            "contracted hyperscaler across three regions: UK South (primary), UK West (secondary), "
            "and EU West (compliance-mandated data residency). "
            "The Identity Platform hosts the OAuth 2.0 authorisation server, the OIDC provider, "
            "and the SAML 2.0 bridge required for legacy application federation. "
            "The Core Database cluster runs PostgreSQL 16 with Citus horizontal sharding, "
            "a read replica set for the Analytics Engine, and a change-data-capture stream "
            "feeding the Data Warehouse via Apache Kafka. "
            "The Network Infrastructure Upgrade provisions BGP route reflectors, EVPN-VXLAN overlays, "
            "and 100GbE spine switches with SR-IOV NIC passthrough for GPU workloads in the AI cluster. "
            "The AI Platform runs on a dedicated GPU node pool with A100 instances, managed by "
            "the Container Orchestration platform and exposed via the Unified API Layer. "
            "The Service Mesh provides mutual TLS, circuit breaking, and distributed tracing "
            "across all microservices, feeding telemetry to the BI Reporting Suite. "
            "The DevOps Pipeline integrates with the Container Orchestration platform to provide "
            "GitOps-driven deployment, policy-as-code enforcement, and automated security scanning "
            "for every container image before it reaches the production registry."
        ),
    },

    # ── 26. VENDOR MANAGEMENT ─────────────────────────────────────────────
    {
        "heading": "26. Vendor and Contract Management",
        "body": (
            "The programme engages 14 external vendors under a mix of fixed-price and time-and-materials "
            "contracts. The Third-Party Integration Framework manages the API endpoint commitments "
            "made to each vendor under their respective master service agreements. "
            "Vendor contract clause 7.4 requires 12 months' written notice before any API endpoint URL "
            "change. This clause directly conflicts with the Legacy API Deprecation milestone. "
            "The Unified API Layer requires Legacy API Deprecation; the Third-Party Integration "
            "Framework blocks Legacy API Deprecation. "
            "Vendor renegotiation is in progress for 3 of the 14 vendors. The remaining 11 vendors "
            "have not been approached. The Vendor Management Director has estimated that renegotiation "
            "will take 6 months per vendor. This is incompatible with the 30 September 2026 "
            "Legacy API Deprecation date. "
            "The cloud provider contract was signed on 1 December 2025 for a 36-month term "
            "commencing 1 February 2026, at a total committed spend of £18,400,000. "
            "The GPU node pool for the AI Platform carries a minimum commitment of £2,400,000 "
            "per year regardless of utilisation, meaning the AI Platform cost is incurred from "
            "1 February 2026 even if the platform is not operational by its scheduled date."
        ),
    },

    # ── 27. DATA GOVERNANCE ───────────────────────────────────────────────
    {
        "heading": "27. Data Governance and Classification",
        "body": (
            "All data assets processed by the Nexus Programme are classified under the organisation's "
            "four-tier data classification scheme: Public, Internal, Confidential, and Restricted. "
            "The Training Data Repository contains customer transaction records classified as Restricted "
            "under the data classification scheme. "
            "The GDPR Compliance Framework requires that Restricted data may not be used for AI model "
            "training without explicit data subject consent or an alternative lawful basis. "
            "The Data Protection Officer has not yet identified a lawful basis for processing the "
            "Training Data Repository contents for model training. "
            "The Data Warehouse contains Internal and Confidential data fed from Core Database. "
            "The BI Reporting Suite requires the Data Warehouse and must implement role-based access "
            "control enforced by the Identity Platform. "
            "The Archive System retains Confidential and Restricted data for the mandatory retention "
            "periods defined by the data classification policy: 7 years for financial records, "
            "3 years for operational records, and 1 year for system event logs. "
            "The Archive System requires Core Database for its retention metadata catalogue. "
            "The Audit System requires Identity Platform to associate all data access events with "
            "authenticated user identities for the forensic audit trail required by regulators."
        ),
    },

    # ── 28. SECURITY FRAMEWORK ────────────────────────────────────────────
    {
        "heading": "28. Security Architecture and Controls",
        "body": (
            "The programme's security architecture is governed by the Security Framework produced "
            "by the Security Team and approved by the Security Certification Body. "
            "The Data Encryption Module produces the encryption key manifest consumed by the "
            "Security Audit and required by the Identity Platform's token signing infrastructure. "
            "Security Audit requires Data Encryption Module to be complete and the key manifest "
            "to be available before the audit scope can be confirmed. "
            "The Security Certification Body requires Security Audit sign-off as a prerequisite "
            "for issuing Security Certification for Cloud Migration. "
            "Zero-trust network access is enforced by Secure Remote Access, which requires "
            "Network Infrastructure Upgrade for its NAC policy enforcement points. "
            "All inter-service communication is encrypted at the transport layer by the Service Mesh, "
            "which requires Container Orchestration to be operational. "
            "The MFA Gateway enforces step-up authentication for all Restricted data access, "
            "requiring Identity Platform to be healthy. "
            "Penetration testing is scheduled to begin 15 June 2026 against the full cloud environment, "
            "after Network Infrastructure Upgrade completes on 31 May 2026. "
            "Security Certification is expected by 15 November 2026, assuming a 3-month remediation "
            "cycle following the penetration test."
        ),
    },

    # ── 29. ACCEPTANCE CRITERIA ────────────────────────────────────────────
    {
        "heading": "29. Phase Gate Acceptance Criteria",
        "body": (
            "Foundation Gate (1 July 2026) acceptance criteria: "
            "Core Database cluster provisioned and health-checked. "
            "Network Infrastructure Upgrade complete and signed off by Network Engineering Team. "
            "Identity Platform deployed (subject to Privacy Board resolution). "
            "Data Encryption Module delivered and key manifest generated. "
            "Security Audit completed and report signed off by Security Team. "
            "Privacy Board impact assessment complete and decision recorded. "
            "Compliance Authority Gate Approval Certificate issued. "
            "Integration Gate (1 October 2026) acceptance criteria: "
            "API Gateway deployed and traffic routing validated. "
            "Load Balancer Cluster configured and tested under load. "
            "Data Migration complete and data integrity verified. "
            "User Acceptance Testing complete with defect count below threshold. "
            "Integration Testing complete and system validation report signed off. "
            "Training Data Repository populated (subject to GDPR sign-off). "
            "Change Readiness Survey score above 70%. "
            "Validation Gate (1 December 2026) acceptance criteria: "
            "Disaster Recovery System operational and DR test passed. "
            "Security Certification issued by Security Certification Body. "
            "Go-Live Rehearsal completed successfully. "
            "Regulatory Approval Gate review passed. "
            "Production Gate (1 January 2027) acceptance criteria: "
            "All Foundation, Integration, and Validation gate criteria confirmed still met. "
            "Production Deployment plan approved by Change Advisory Board. "
            "Compliance Authority final Gate Approval Certificate issued."
        ),
    },

    # ── 30. CLOSURE CRITERIA ──────────────────────────────────────────────
    {
        "heading": "30. Programme Closure and Benefits Realisation",
        "body": (
            "The programme will be formally closed when all of the following conditions are met: "
            "All phase gate criteria are confirmed as met and documented in the programme closure report. "
            "Production Deployment is complete and the system has been in stable production operation "
            "for a minimum of 30 days without a severity-1 incident. "
            "All legacy systems have been decommissioned or formally handed over to sustain teams. "
            "Data Centre Decommission is complete or an approved deferral plan is in place. "
            "All vendor transitions under the Third-Party Integration Framework are complete "
            "or contractual waivers for Legacy API Deprecation are in place. "
            "Benefits realisation review is scheduled for 1 April 2027 and will assess whether "
            "the committed benefits of £14,600,000 annualised cost reduction have been achieved. "
            "The Identity Platform unified authentication is expected to deliver £2,800,000 per year "
            "by eliminating password reset incidents and identity administration overhead. "
            "The Core Database consolidation is expected to deliver £4,200,000 per year by retiring "
            "Oracle licensing and the 12 point-to-point data feed maintenance contracts. "
            "The Network Infrastructure Upgrade and Cloud Migration together are expected to deliver "
            "£7,600,000 per year by retiring the data centre lease and reducing network operations staffing. "
            "Programme closure is targeted for 31 March 2027. "
            "This charter was approved by the Nexus Steering Board on 1 February 2026. "
            "Document owner: Programme Director. Review cycle: monthly."
        ),
    },
]


# ---------------------------------------------------------------------------
# PDF renderer
# ---------------------------------------------------------------------------

def make_pdf(output_path: str):
    doc = fitz.open()
    font_regular = "helv"
    font_bold = "hebo"
    margin = 72
    page_width = 595
    page_height = 842
    text_width = page_width - 2 * margin

    def new_page():
        p = doc.new_page(width=page_width, height=page_height)
        return p, margin

    page, y = new_page()

    for section in SECTIONS:
        heading = section["heading"]
        body = section.get("body")
        is_title = section.get("is_title", False)

        # ── Title block ──────────────────────────────────────────────────
        if is_title:
            y += 60
            for line in heading.split("\n"):
                rc = page.insert_textbox(
                    fitz.Rect(margin, y, page_width - margin, y + 50),
                    line,
                    fontname=font_bold,
                    fontsize=16,
                    color=(0.9, 0.95, 1.0),
                    align=fitz.TEXT_ALIGN_CENTER,
                )
                y += 36
            y += 40
            # Horizontal rule
            page.draw_line((margin, y), (page_width - margin, y), color=(0.3, 0.5, 0.8), width=1)
            y += 20
            continue

        # ── Page break check for heading ─────────────────────────────────
        if y > page_height - 160:
            page, y = new_page()

        # ── Section heading ──────────────────────────────────────────────
        page.insert_textbox(
            fitz.Rect(margin, y, page_width - margin, y + 28),
            heading,
            fontname=font_bold,
            fontsize=12,
            color=(0.05, 0.25, 0.55),
        )
        y += 26

        # ── Underline ────────────────────────────────────────────────────
        page.draw_line((margin, y), (margin + 200, y), color=(0.05, 0.25, 0.55), width=0.5)
        y += 10

        # ── Body text ────────────────────────────────────────────────────
        if body:
            # Split into sentences at ". " boundaries for paragraph variety
            sentences = body.replace(". ", ".\n").split("\n")
            for sentence in sentences:
                words = sentence.split()
                line_buf = []
                for word in words:
                    line_buf.append(word)
                    test_line = " ".join(line_buf)
                    if len(test_line) * 5.3 >= text_width:
                        if y > page_height - 55:
                            page, y = new_page()
                        page.insert_text(
                            (margin, y),
                            " ".join(line_buf[:-1]),
                            fontname=font_regular,
                            fontsize=10.5,
                            color=(0.1, 0.1, 0.1),
                        )
                        y += 15
                        line_buf = [word]
                if line_buf:
                    if y > page_height - 55:
                        page, y = new_page()
                    page.insert_text(
                        (margin, y),
                        " ".join(line_buf),
                        fontname=font_regular,
                        fontsize=10.5,
                        color=(0.1, 0.1, 0.1),
                    )
                    y += 15

        y += 20  # section gap

    doc.save(output_path)
    print(f"Saved: {output_path}  ({doc.page_count} pages, {len(SECTIONS)} sections)")
    doc.close()


if __name__ == "__main__":
    make_pdf("nexus_programme_charter.pdf")
