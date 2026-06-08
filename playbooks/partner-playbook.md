# Partner Playbook: How a GSI or Hyperscaler Resells This

> The take-home brief asks for "a working automation." This document
> answers a different question: **what would it take to turn this into a
> productized partner offering?** That's the muscle Cognition's
> Partner-Deployed Engineering team is being built around, and it's the
> reason the Playbook (`playbooks/cve_remediation_v1.md`) is the most
> important artifact in this repo — not the orchestrator code.

---

## The opportunity

Enterprise engineering organizations sit on **hundreds of known CVEs in
production code** at any given time. The work to remediate them is:

- **Repetitive but non-trivial.** Each fix is read-the-changelog →
  bump → patch breaks → run tests → open PR. Same pattern, different
  package, every time.
- **Hard to staff.** Senior engineers don't want it; juniors can't
  always be trusted to triage breaking changes.
- **Currently outsourced to humans** at GSI rates: Infosys and Cognizant
  both sell "Application Security Managed Services" engagements that
  bill out at $120–$200/hr. A 500-CVE backlog at 4 hours per CVE is a
  **$300K–$400K engagement**, with thin margins because it's labor.

**Devin changes the unit economics.** A Devin session at production-grade
performance does this work for a small multiple of an ACU. The partner
who packages this *first* captures the margin.

---

## The packaged offering

### Name
**CVE Burndown-as-a-Service** *(working title)*

### Pitch (one paragraph)
> *We will clear your top-priority CVE backlog in 90 days. Each
> vulnerability gets a dedicated remediation pull request, opened
> against your repo, ready for your security and engineering teams to
> review. You pay a fixed price per merged PR, with a transparent
> dashboard showing throughput, latency, and consumption. We bring the
> Devin Playbook, the orchestrator, the dashboard, and one Cognition-
> certified SE; you bring the repo access and the reviewers.*

### Commercial structure

| Component | Owner | Mechanics |
|---|---|---|
| Engagement contract | GSI (e.g. Infosys) | Fixed-price or per-PR; 90-day SOW |
| Customer relationship | GSI | Already exists — this rides existing MSAs |
| Devin consumption | Cognition | Pass-through ACU billing to GSI |
| Reference architecture | Cognition Partner-Deployed Eng | This repo |
| Customer-specific tuning | GSI partner SE | Forks the repo, modifies the Playbook |
| Reviewer / merger | Customer | The one thing we don't replace |

### Why this works for each party

**For the customer's CISO:** measurable security debt reduction with a
clear $-per-CVE-resolved unit cost. The dashboard answers the board's
"what are we doing about CVEs?" question with numbers.

**For the GSI:** higher-margin work than humans-on-keyboards. Reuses
existing customer relationships. Cognition-certified Playbooks become a
defensible IP layer; the GSI builds a library across customers (CVE
Burndown, Test Coverage Lift, Java Upgrade, COBOL Modernization — all
the use cases on Devin's existing landing page).

**For Cognition:** consumption revenue. Marquee logos on hyperscaler
marketplaces (AWS, Azure). A **proven playbook** the Partner Eng team
can hand to the next GSI with confidence — closing the gap identified
in the strategy review.

**For the hyperscaler:** marketplace SKU with measurable customer ROI;
co-sell opportunity; pulls more workloads (the customer's repo, the
Devin org, the orchestrator) into their cloud.

---

## What gets reused vs. customized per customer

| Asset | Reused as-is | Customized per customer |
|---|---|---|
| `orchestrator/` Python code | ✅ | Container deployment target only |
| `playbooks/cve_remediation_v1.md` | Starting point | Forked per customer (their code style, test commands, branch policy) |
| `dashboard/app.py` | ✅ | Cost-model env vars only |
| `.github/workflows/` | Template | Different trigger (their CI, their schedule) |
| Devin Knowledge entries | — | Customer-specific (coding standards, repo conventions, who-owns-what) |
| Service user + RBAC config | Template | Per customer Devin org |

The Playbook is the most customer-specific piece — and the most
defensible because it's the **codified expertise** of the partner SE.
Two GSIs running the same orchestrator with different Playbooks deliver
genuinely different work product.

---

## Rollout plan in a real engagement

**Week 0 — Discovery (3 days, partner SE on-site).**
- Inventory the customer's CVE backlog (Snyk, Dependabot, internal scans).
- Identify the top three repos by criticality.
- Customize the Playbook: branch naming, PR template, test commands,
  reviewers, branch protection rules, lockfile regen commands.
- Stand up a customer-dedicated Devin org and service users.

**Weeks 1–2 — Pilot (10 CVEs, supervised).**
- Run the orchestrator against one repo in `DEVIN_MOCK=0` mode but with
  the partner SE manually approving each Devin session before it spawns.
- Measure: what % of sessions produce a mergeable PR? What's the median
  time-to-PR? Where does the Playbook need to be tightened?
- The Playbook gets ~3-5 revisions in this phase. That's expected and
  good.

**Weeks 3–10 — Burndown.**
- Switch to autonomous mode. Nightly scans, scheduled sessions, PRs
  landing in the morning for the customer's reviewers.
- Weekly reporting via the dashboard. Monthly executive readout to the
  CISO.

**Week 11 — Handover.**
- Customer team is trained on the orchestrator and Playbook.
- Optionally: customer continues running it themselves on the same
  Devin consumption contract, or contracts the partner for ongoing
  managed-service operation.

---

## Why this maps to Cognition's stated gap

From the strategy review with the Partner team:

> *"Cognition has achieved some marketplace wins and early customer
> successes through hyperscalers, but lacks systematized processes or
> proven playbooks. The goal over the next year is to prioritize wins,
> prove them out, and convert them into scalable processes."*

This repo is one such systematized process. The pattern generalizes —
swap the scanner for `coverage.py` and the Playbook for a test-writing
SOP and you have **Test Coverage Lift-as-a-Service**. Swap them for a
Java migration scanner and a JDK-upgrade SOP and you have **Java
Modernization-as-a-Service**. Each Playbook is one document and one
fork of this orchestrator away.

That's what "scalable partnership motions" looks like in code.

---

## Open questions for the Cognition team

1. **Playbook IP.** Should customer-specific Playbook forks live in
   Cognition's GitHub, the partner's, or the customer's? Affects who
   owns the IP and how reusable the assets are across engagements.
2. **ACU pricing transparency.** Do partners get visibility into ACU
   spend per customer for accurate gross-margin reporting? The current
   Metrics API supports this; just want to confirm the commercial wrap.
3. **Marketplace listings.** Is the right go-to-market here a Cognition
   listing co-branded with Infosys/Cognizant, or a partner-listed SKU
   that uses Devin under the hood? Different deal sizes, different
   discount mechanics.
4. **Reference customer.** What's the right first deployment — a logo
   we already have a foothold at, or net-new through a GSI?

These are the conversations I'd want to have with Jake and the team
once Day 1 lands.
