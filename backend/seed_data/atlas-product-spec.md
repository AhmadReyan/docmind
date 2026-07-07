# Atlas — Fleet Telemetry Platform: Product Specification

**Document status: Approved v2.3 — March 12, 2026**
**Product owner: D. Ferreira · Engineering lead: M. Szabó**

## 1. Summary

Atlas is a real-time fleet telemetry platform. Customers install the AtlasEdge
device (or integrate an existing OEM feed) in their vehicles; Atlas ingests
position, engine, and sensor data, stores it durably, and exposes dashboards,
alerts, and a query API. Target customers are logistics operators, last-mile
delivery fleets, and municipal vehicle pools running 50 to 50,000 vehicles.

The product promise is simple: **any telemetry event is visible on a customer
dashboard within one second of leaving the vehicle**, and any historical query
over the retention window returns in well under a second.

As of March 2026 Atlas serves **1,900 fleets totaling roughly 310,000 active
vehicles** across two regions (us-east and us-west), processing a sustained
average of 140,000 events per second with a December 2025 peak of 233,000.
Net revenue retention over the trailing twelve months is 127%; the largest
single fleet is 21,400 vehicles. Customer onboarding for fleets under 500
vehicles is self-serve and typically completes in under a week; larger fleets
get a guided rollout with a staged device-installation plan, and the median
Enterprise time-to-first-dashboard is 18 days.

## 2. Architecture

Atlas is composed of six subsystems, deployed per region:

1. **AtlasEdge device / edge agent.** In-vehicle hardware built around a
   Cortex-M7 microcontroller with an **LTE Cat-M1 cellular modem**, GPS sampled
   at **1 Hz**, and a CAN bus interface reading engine RPM, fuel level, battery
   voltage, and fault codes. The agent buffers up to **72 hours of data
   locally** during connectivity gaps and replays it on reconnect.
2. **Ingestion gateway.** Terminates device connections over **MQTT (primary)
   and HTTPS (fallback)**, authenticates devices with per-device X.509
   certificates, validates payloads, and writes them to Kafka.
3. **Stream pipeline.** Kafka topics partitioned by fleet ID feed stream
   processors that deduplicate, enrich with geofence and vehicle metadata, and
   fan out to storage and alerting.
4. **Storage.** A two-tier design: **TimescaleDB is the hot store, holding the
   most recent 90 days** of telemetry for interactive queries; older data is
   compacted into **Parquet files on object storage as the cold store, retained
   for 730 days** (two years). Queries transparently span both tiers.
5. **Query API.** REST API (GraphQL planned — see roadmap) serving dashboards
   and customer integrations, with per-tenant row-level isolation.
6. **Alerting engine.** Evaluates customer-defined rules (speeding, geofence
   exit, engine fault, idle time) against the live stream and delivers
   notifications via webhook, email, and SMS.

## 3. Performance targets (SLOs)

These service level objectives are contractual for the Enterprise tier and
targets for all other tiers:

- **Ingestion throughput: 250,000 events per second per region**, with burst
  capacity to 400,000 events per second for up to 10 minutes.
- **End-to-end freshness: p99 ingest-to-dashboard latency of 800 ms**
  (measured from gateway receipt to dashboard-visible write). p50 target is
  200 ms.
- **Query API latency: p95 of 300 ms** for queries over the hot store; p95 of
  2 s for queries spanning the cold store.
- **Availability: 99.95% monthly uptime SLA for the Enterprise tier**
  (measured at the API gateway); 99.9% target for Starter and Growth.
- Alert delivery: p95 of 5 seconds from triggering event to webhook dispatch.

Missing an Enterprise SLO in a calendar month triggers service credits of 10%
of that month's fees, rising to 30% below 99.0% availability.

## 4. Data retention

| Tier | Hot store | Cold store | Notes |
|---|---|---|---|
| Free trial | 7 days | — | Dashboards only, no API |
| Starter | 90 days | — | Hot store only |
| Growth | 90 days | 365 days | |
| Enterprise | 90 days | 730 days | Custom retention negotiable |

Deleting a vehicle purges its telemetry from the hot store within 24 hours and
from the cold store within 30 days. Customers may request a full data export
before deletion.

## 5. Pricing

- **Starter — $99 per month**: up to **50 vehicles**, dashboards, standard
  alerts, hot-store retention, community support.
- **Growth — $499 per month**: up to **500 vehicles**, everything in Starter
  plus the query API, webhook alerting, cold-store retention (365 days), and
  business-hours support with a 1-business-day response SLA.
- **Enterprise — custom pricing**: designed for **5,000+ vehicles**. Adds
  **SSO/SAML**, custom roles, audit logs, 730-day retention, the 99.95% uptime
  SLA, a dedicated technical account manager, and 24/7 support with a 1-hour
  P1 response SLA. Annual contract required.

Overage: Starter and Growth fleets exceeding their vehicle cap are billed at
**$1.50 per additional vehicle per month** for up to 20% overage, after which
an upgrade is required. AtlasEdge hardware is sold separately at **$89 per
unit** with volume discounts above 1,000 units.

## 6. API limits

The query API enforces per-tenant rate limits by tier:

- **Starter: 100 requests per minute** (API access requires the Growth tier or
  above for production use; Starter limits apply to evaluation keys).
- **Growth: 1,000 requests per minute.**
- **Enterprise: 10,000 requests per minute**, with negotiated burst limits.

Additional limits, all tiers:

- Maximum request payload: **1 MB**; maximum response page size: 10,000 rows.
- **Batch export jobs are capped at 10 GB per job**; larger exports must be
  split by time range.
- **Webhook deliveries are retried 5 times with exponential backoff** (1 s,
  4 s, 16 s, 64 s, 256 s) before being dead-lettered and surfaced in the
  console.
- Rate-limited responses return HTTP 429 with a `Retry-After` header.

API keys are scoped per environment (sandbox/production) and can be rotated
without downtime by running two active keys during a rotation window. Every
key carries a role (read-only, read-write, admin) and an optional vehicle-group
scope, so an integrator can be granted access to a subset of a fleet. All API
calls are recorded in the tenant audit log (Enterprise) with key ID, caller
IP, and request digest, retained for 400 days.

## 7. Security and compliance

All data is encrypted in transit (TLS 1.3) and at rest (AES-256). Device
identity uses per-device X.509 certificates with a 2-year validity and
automated rotation. Atlas is **SOC 2 Type II certified** (report available
under NDA) and GDPR-compliant; EU customer data will remain in the EU region
once it launches (see roadmap). Penetration tests run twice a year through an
external firm, and the platform maintains a public vulnerability disclosure
policy with a 90-day remediation commitment.

## 8. Roadmap

Committed dates (quarters are calendar quarters):

- **Q3 2026 — Predictive maintenance GA.** Failure-risk scoring for engine and
  battery subsystems, trained per vehicle class. Beta ran with 3 design
  partners across 6,400 vehicles.
- **Q4 2026 — EU region launch in Frankfurt.** Full regional isolation:
  ingestion, storage, and processing stay in-region. Required for several
  in-flight Enterprise deals.
- **Q1 2027 — Driver-safety scoring (beta).** Harsh-braking, cornering, and
  speeding scores per driver, with coaching reports. Ships behind a per-fleet
  opt-in due to works-council requirements in the EU.
- **Q2 2027 — API v2 (GraphQL).** Single-endpoint GraphQL API replacing three
  REST resource families; REST v1 remains supported for 24 months after v2 GA.

Exploratory (not committed): video telematics ingestion, fuel-card
reconciliation, and an offline-first mobile app for drivers.

## 9. Data model and event types

Every telemetry record is an **event** with a device ID, fleet ID, timestamp
(device clock, corrected against gateway receipt time), location fix, and a
typed payload. The v2 schema defines five event families:

- **Position events** — GPS fix, heading, speed. Emitted at 1 Hz while moving,
  downsampled to **one event per 30 seconds when stationary** to save
  bandwidth.
- **Engine events** — RPM, coolant temperature, fuel level, odometer, battery
  voltage, read from the CAN bus at 0.2 Hz.
- **Fault events** — OBD-II diagnostic trouble codes, emitted on change with
  full freeze-frame data attached.
- **Trip events** — synthesized server-side: ignition-on opens a trip,
  ignition-off plus a 5-minute debounce closes it. Trips carry distance,
  duration, idle time, and fuel-burn estimates.
- **Custom events** — customer-defined payloads up to 4 KB, sent through the
  same pipeline with schema validation against a customer-registered JSON
  Schema.

Device clock skew beyond 5 minutes flags the event as `time_suspect`; such
events appear in dashboards but are excluded from trip synthesis. All events
are idempotent on (device ID, sequence number), which is what allows the
72-hour offline replay without duplicates.

## 10. Alerting rules

Alert rules are boolean expressions over the live stream, scoped to a fleet,
a vehicle group, or a single vehicle. The rule engine supports:

- **Threshold rules** — e.g. speed above 110 km/h for more than 30 seconds.
- **Geofence rules** — enter/exit/dwell against customer-drawn polygons, up
  to **1,000 geofences per fleet**.
- **Schedule rules** — vehicle movement outside permitted hours.
- **Fault rules** — match on DTC code families, with severity mapping.
- **Compound rules** — AND/OR combinations of the above, max depth 3.

Each rule can notify via webhook, email, or SMS, with per-channel quiet hours
and a **per-rule cooldown (default 15 minutes)** to prevent alert storms. SMS
is metered: 100 messages per month are included on Growth, then billed at
$0.05 per message. Alert history is retained for 13 months on all paid tiers.

### 10.1 Dashboards and console

The web console ships four default dashboards per fleet — live map, fleet
health, utilization, and alert history — each customizable per user with
saved views shareable across the tenant. The live map renders up to **10,000
concurrently moving vehicles** per view using server-side clustering; clicking
through to a vehicle opens a 24-hour timeline with trip playback at up to 32x
speed. Utilization reports (distance, engine hours, idle percentage, fuel
estimate per vehicle per day) can be scheduled as weekly emails in CSV or PDF.
Console access supports role-based permissions on all tiers — owner, admin,
dispatcher, and viewer — with per-vehicle-group visibility restrictions on
Growth and above. Console sessions expire after 12 hours; Enterprise tenants
can shorten this and enforce SSO-only login. The console is available in
English, Spanish, French, and German; localized number and unit formats
(miles/km, gallons/liters) follow per-user settings rather than tenant-wide
defaults, a deliberate choice for cross-border fleets.

## 11. Integrations

Shipping today: **Samsara and Geotab import bridges** (for fleets migrating
mid-contract), a Slack app for alert delivery, webhook signing (HMAC-SHA256
with rotating secrets), and a read-only **Snowflake share** for Enterprise
customers who want telemetry in their own warehouse. A CSV/SFTP nightly export
exists for legacy TMS systems and is deliberately not promoted.

Partner-built integrations are certified through the Atlas Marketplace
program, which requires passing a conformance suite and an annual security
review. Revenue share is 80/20 in the partner's favor for paid marketplace
listings.

## 12. Operations

Each region runs three availability zones with Kafka RF=3 and TimescaleDB
streaming replicas; regional failover is manual by design (data residency
must never fail over across jurisdictions automatically). Error budgets
follow the SLOs in section 3; when the monthly budget is 50% consumed,
feature deploys to that region require SRE sign-off, and at 100% consumed a
change freeze applies until the budget recovers. Deploys are blue/green with
automated rollback on SLO-burn alerts; median deploy-to-production time is
26 minutes. On-call is a weekly rotation across 14 engineers with a P1 page
acknowledgment target of 5 minutes.

## 13. Competitive positioning

Against incumbent telematics suites (Samsara, Geotab, Verizon Connect), Atlas
competes on three axes: **freshness** (sub-second p99 dashboard latency versus
30–120 s refresh cycles typical of incumbents), **API-first design** (every
dashboard capability is available via the public API, which is how the
mid-market integrator channel builds on us), and **transparent pricing**
(published per-tier prices where incumbents quote per-seat custom contracts).
We do not compete on hardware breadth: AtlasEdge supports light and medium
commercial vehicles only, and heavy-equipment support is explicitly ceded to
specialist vendors until at least 2028.

## 14. Out of scope for v2.x

Atlas does not do routing or dispatch optimization, does not sell cellular
connectivity (customers bring their own SIM plans or buy bundled data through
hardware partners), and does not support on-premise deployment. These are
periodically requested and deliberately declined to keep the platform focused.

## 15. Open questions

1. Whether Growth tier should include SSO — sales reports losing mid-market
   deals over it; security argues SSO drives Enterprise upgrades.
2. Cold-store query latency target for the EU region at launch, given smaller
   initial cluster sizing.
3. Whether the 20% overage allowance encourages chronic under-tiering; finance
   is modeling a usage-based alternative for the 2027 pricing review.
