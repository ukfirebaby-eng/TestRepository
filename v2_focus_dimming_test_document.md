# Orion Payments Modernisation Programme - Test Strategy Pack

## Purpose

This document is a synthetic test input for Diamond Miner. It describes a payments platform migration with deliberate dependency conflicts, schedule risks, fragile hubs, and mitigation choices. It is intended to exercise the V2 graph, selected-evidence panel, focus dimming, report workspace, and risk simulator.

## Executive Intent

Orion Bank will migrate its legacy payments estate into a cloud-native real-time payments platform before the annual peak trading period. The programme must preserve regulatory reporting, customer payment availability, fraud monitoring, treasury settlement, and merchant reconciliation throughout the migration.

The executive commitment is to complete public launch on 30 September 2026, with dress rehearsal on 15 September 2026 and board readiness sign-off on 20 September 2026.

## Major Workstreams

### Network Segmentation Upgrade

The Network Segmentation Upgrade must isolate card-processing, treasury, fraud, and merchant settlement zones. It is owned by Infrastructure Security and is planned to finish on 12 August 2026.

The penetration test cannot start until the Network Segmentation Upgrade is complete. The penetration test is booked for 5 August 2026 because the external testing supplier has limited availability.

### Security Certification

The Security Certification Body will not issue certification until the penetration test is passed and all high-severity findings are remediated. Certification is currently scheduled for 10 August 2026.

Cloud Platform Hardening depends on Security Certification. The Cloud Migration Start Gate also depends on Security Certification.

### Cloud Migration

The Cloud Migration is scheduled to begin on 8 August 2026. It includes payment routing, ledger replication, transaction archive loading, and merchant settlement batch migration.

Cloud Migration cannot safely begin before Security Certification, but the current plan assumes migration begins two days before certification.

### Real-Time Payments Engine

The Real-Time Payments Engine depends on:

- Cloud Migration
- Ledger Replication Service
- Fraud Decisioning API
- Customer Notification Service
- Treasury Settlement Adapter

The Real-Time Payments Engine is scheduled to enter dress rehearsal on 15 September 2026.

### Fraud Decisioning API

The Fraud Decisioning API depends on the Feature Store, Identity Token Service, Device Fingerprint Service, and Sanctions Screening Gateway.

If the Fraud Decisioning API is unavailable, the Real-Time Payments Engine must either reject inbound payments or route them into manual review. Manual review has capacity for only 8% of expected launch-day payment volume.

### Identity Token Service

The Identity Token Service is a shared authentication service used by:

- Customer Mobile App
- Merchant Portal
- Real-Time Payments Engine
- Fraud Decisioning API
- Customer Notification Service
- Operations Console
- Treasury Settlement Adapter

The Identity Token Service currently runs in a single region. Disaster recovery for the Identity Token Service is planned for 25 September 2026, after dress rehearsal and only five days before public launch.

### Ledger Replication Service

The Ledger Replication Service must copy 24 months of transaction history from the Legacy Core Banking System to the cloud ledger. It is scheduled to complete on 1 September 2026.

The Reconciliation Evidence Pack is scheduled to start on 24 August 2026, but it depends on Ledger Replication Service completion and data quality approval.

### Reconciliation Evidence Pack

The Reconciliation Evidence Pack is required by Internal Audit before board readiness sign-off. Internal Audit needs five working days to review the evidence pack.

Board readiness sign-off is scheduled for 20 September 2026. The Reconciliation Evidence Pack cannot be produced until Ledger Replication Service completion, data quality approval, and merchant settlement trial run are complete.

### Merchant Settlement Trial Run

The Merchant Settlement Trial Run is scheduled for 9 September 2026. It depends on:

- Ledger Replication Service
- Treasury Settlement Adapter
- Merchant Portal
- Reconciliation Rules Engine

The Treasury Settlement Adapter is scheduled to complete on 12 September 2026, three days after the Merchant Settlement Trial Run.

### Customer Notification Service

The Customer Notification Service sends payment success, payment failure, fraud hold, refund, and chargeback messages. It depends on Identity Token Service and Message Queue Cluster.

The Message Queue Cluster is maintained by Platform Operations. It has no active-active failover until 18 October 2026.

If Message Queue Cluster fails, the Customer Notification Service cannot send payment status messages, Merchant Portal cannot receive settlement confirmations, and Operations Console cannot alert incident managers.

## Key Dates

| Milestone | Planned Date | Dependency Notes |
| --- | --- | --- |
| Penetration Test Starts | 5 August 2026 | Requires Network Segmentation Upgrade complete |
| Security Certification | 10 August 2026 | Requires passed penetration test |
| Network Segmentation Upgrade Complete | 12 August 2026 | Required before penetration testing |
| Cloud Migration Starts | 8 August 2026 | Requires Security Certification |
| Ledger Replication Complete | 1 September 2026 | Required for reconciliation evidence |
| Reconciliation Evidence Pack Starts | 24 August 2026 | Requires Ledger Replication completion |
| Merchant Settlement Trial Run | 9 September 2026 | Requires Treasury Settlement Adapter |
| Treasury Settlement Adapter Complete | 12 September 2026 | Required before settlement trial |
| Dress Rehearsal | 15 September 2026 | Requires Cloud Migration, Fraud API, Ledger, Notification Service |
| Board Readiness Sign-off | 20 September 2026 | Requires Internal Audit review |
| Identity Token Service DR Complete | 25 September 2026 | Needed before resilient launch |
| Public Launch | 30 September 2026 | Requires sign-off and stable dress rehearsal |

## Dependency Statements

The penetration test is a predecessor of Security Certification.

The Network Segmentation Upgrade is a predecessor of the penetration test.

Security Certification is a predecessor of Cloud Migration.

Cloud Migration is a predecessor of Dress Rehearsal.

Ledger Replication Service is a predecessor of Reconciliation Evidence Pack.

Reconciliation Evidence Pack is a predecessor of Board Readiness Sign-off.

Treasury Settlement Adapter is a predecessor of Merchant Settlement Trial Run.

Merchant Settlement Trial Run is a predecessor of Dress Rehearsal.

Identity Token Service disaster recovery is a predecessor of Public Launch.

## Known Programme Conflicts

### Conflict 1: Certification Before Infrastructure

Security Certification is planned for 10 August 2026, but Network Segmentation Upgrade completes on 12 August 2026. The penetration test is booked for 5 August 2026 even though it requires Network Segmentation Upgrade completion.

The current plan therefore asks the certification process to finish before one of its required security prerequisites is complete.

### Conflict 2: Migration Before Certification

Cloud Migration starts on 8 August 2026, but Security Certification is planned for 10 August 2026 and may be blocked until after Network Segmentation Upgrade completion on 12 August 2026.

The current plan therefore asks migration to begin before certification is available.

### Conflict 3: Reconciliation Before Ledger Completion

Reconciliation Evidence Pack starts on 24 August 2026, but Ledger Replication Service completes on 1 September 2026.

The current plan therefore asks audit evidence production to start before the transaction history has been replicated and approved.

### Conflict 4: Settlement Trial Before Adapter Completion

Merchant Settlement Trial Run is scheduled for 9 September 2026, but Treasury Settlement Adapter completes on 12 September 2026.

The current plan therefore asks the settlement trial to run before the adapter it depends on is complete.

### Conflict 5: Resilience After Launch Readiness

Identity Token Service disaster recovery completes on 25 September 2026. Dress Rehearsal is on 15 September 2026 and Board Readiness Sign-off is on 20 September 2026.

The current plan therefore asks the board to approve readiness before a shared authentication service has disaster recovery.

## Fragility Hubs

### Identity Token Service

Identity Token Service is a single point of failure. If it fails, Customer Mobile App cannot authenticate customers, Merchant Portal cannot authenticate merchants, Real-Time Payments Engine cannot validate payment sessions, Fraud Decisioning API cannot verify device identity, Customer Notification Service cannot send authenticated messages, and Operations Console cannot authorize incident actions.

### Message Queue Cluster

Message Queue Cluster is a single point of failure. If it fails, Customer Notification Service loses outbound messaging, Merchant Portal loses settlement confirmations, Operations Console loses alert delivery, and Fraud Decisioning API cannot publish fraud-hold events.

### Ledger Replication Service

Ledger Replication Service is a single point of failure for reconciliation readiness. If it fails or produces poor-quality data, Reconciliation Evidence Pack cannot start, Internal Audit cannot complete review, Board Readiness Sign-off is blocked, and Public Launch cannot be responsibly approved.

### Treasury Settlement Adapter

Treasury Settlement Adapter is a single point of failure for merchant settlement. If it fails, Merchant Settlement Trial Run cannot prove settlement accuracy, merchant balances cannot be confirmed, and launch exposes the bank to customer-impacting settlement breaks.

## Risk Register

| Risk | Severity | Probability | Description | Mitigation |
| --- | --- | --- | --- | --- |
| Cloud Migration starts before Security Certification | 5 | 4 | Migration begins while security approval is blocked by network and testing prerequisites. | Move migration start to after certification or obtain formal provisional acceptance. |
| Dress Rehearsal occurs before settlement trial evidence | 4 | 4 | Dress rehearsal depends on a settlement trial that currently starts before its adapter is complete. | Reschedule settlement trial after Treasury Settlement Adapter completion. |
| Board signs off before Identity Token Service DR | 5 | 3 | Board readiness may be approved before authentication resilience exists. | Require DR completion or explicit board risk acceptance before sign-off. |
| Audit evidence starts before ledger data exists | 4 | 5 | Reconciliation evidence begins before ledger replication completes. | Move evidence pack start to after replication and data quality approval. |
| Message Queue Cluster outage blocks notifications | 4 | 3 | Notification and alerting services depend on a non-resilient queue. | Add temporary failover queue or reduce launch scope. |

## Recommended Executive Decisions

1. Move Cloud Migration to a date after Security Certification and after Network Segmentation Upgrade completion.
2. Rebook the penetration test after Network Segmentation Upgrade completion or negotiate an emergency supplier slot.
3. Move Reconciliation Evidence Pack to start after Ledger Replication Service completion and data quality approval.
4. Move Merchant Settlement Trial Run to after Treasury Settlement Adapter completion.
5. Require Identity Token Service disaster recovery before Board Readiness Sign-off, or document explicit board acceptance of authentication outage risk.
6. Treat Message Queue Cluster as a launch-critical resilience gap and create a temporary failover path.

## Test Expectations For Diamond Miner

When ingested, this document should produce useful test coverage for:

- Structural friction around migration, certification, audit, and settlement dependencies.
- Timeline friction around tasks scheduled before their prerequisites.
- Fragility hubs around Identity Token Service, Message Queue Cluster, Ledger Replication Service, and Treasury Settlement Adapter.
- Selected Evidence explanations with severity, probability, real-world impact, and recommended actions.
- Focus dimming in 3D Canvas and Analyst Map when selecting a node, risk path, or Critical Attention item.
- Risk Simulator outputs with delay-sensitive nodes and long-tail schedule exposure.
