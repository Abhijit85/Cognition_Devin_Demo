# Loom Script — 5-minute Devin CVE Remediation Pitch

> **Audience.** VP of Engineering + senior ICs at a hypothetical
> enterprise customer evaluating Devin. They are technical, they are
> skeptical, they have seen demos.
> **Tone.** Confident, specific, no jargon-as-drama. The numbers do the
> work.
> **Total budget: 5:00.**

---

## 0:00–0:45 — What (the problem)

> "Hi, I'm Abhi. In the next five minutes I'll show you an
> event-driven automation I built on Devin that closes the CVE backlog
> on a real codebase — Apache Superset — and I'll show you why this
> wouldn't be practical with anything other than an autonomous coding
> agent.
>
> Here's the problem. Every enterprise engineering org I've worked with
> sits on a hundred to a thousand known CVEs in production code at any
> given time. The work to fix them is repetitive but not trivial — read
> the changelog, bump the dep, fix the breaks, run tests, open a PR.
> Same pattern, every time. Today this work either doesn't get done, or
> it gets outsourced to a GSI at a hundred and fifty bucks an hour.
> Neither of those is a good answer."

*(Cue: screen-share the dashboard at <http://localhost:8501> showing
the four headline metrics already populated from a prior run. The "$
saved" number is the hook.)*

---

## 0:45–2:30 — How (the demo)

> "Let me show you the system in action. I have a fork of Apache
> Superset here" — *show the GitHub fork* — "and the orchestrator
> running locally."
>
> "Three things can trigger this system: a GitHub Action on a nightly
> cron, a webhook when someone files an issue with the
> `devin-remediate` label, or a manual curl. They all converge on the
> same workflow. Let me trigger one now."

```bash
$ python scripts/demo_seed.py --watch
```

> "What just happened: the scanner ran `pip-audit` against Superset's
> requirements files, found six vulnerable dependencies, and for each
> one it" — *flip to the GitHub fork's Issues tab* — "filed a
> structured GitHub issue, then called Devin's v3 sessions API with a
> versioned Playbook."

*(Click into one of the Devin session URLs and let it stream for ~15
seconds — you want the evaluators to see the agent doing the work.)*

> "This is the key piece. The orchestrator's workflow logic is small
> — under a thousand lines of Python. It doesn't reimplement coding
> intelligence, retrieval, sandboxing, any of that. It glues events to
> Devin sessions and reports on the result. The smart work happens in
> Devin, guided by this Playbook."

*(Flip to `playbooks/cve_remediation_v1.md` in the editor.)*

> "This file is the asset. It's a versioned standard operating
> procedure: how to verify a CVE, branch, bump the dep, handle
> lockfiles, run tests, open the PR. It lives in source control, gets
> reviewed in pull requests, and gets synced to Devin via a single
> bootstrap script. When the customer says 'we want PRs to follow our
> conventional-commits format,' that's a one-line edit here, not a code
> change."

*(Flip back to the dashboard, scroll to the in-flight table.)*

> "And here's the answer to the question every engineering leader asks
> a vendor: 'how do I know it's working?' Findings discovered. Sessions
> in flight. PRs open. Time-to-PR. ACU consumption pulled live from
> Devin's metrics API. Dollar value saved versus the human-engineer
> baseline. Every number traces back to either Devin or this repo."

---

## 2:30–3:45 — Why Devin specifically

> "Now: why couldn't I have built this with a code-completion tool or
> a more traditional bot?
>
> Two reasons.
>
> **First, the unit of work.** Each CVE is hours of focused engineering
> — read the upstream changelog, figure out if the breaking change
> affects this codebase, fix it, run the suite, fix the test breaks
> caused by the upgrade. That's a session, not a completion. Devin
> being autonomous means I can spawn thirty of these in parallel and
> walk away. A completion tool would still need a human in the loop for
> each one, which puts you right back to GSI economics.
>
> **Second, the primitives.** Look at what the orchestrator code is and
> isn't doing. It's not running sandboxes. It's not managing git
> branches. It's not invoking compilers or test runners. All of that
> happens inside the Devin session because Devin exposes Playbooks,
> Sessions, Tags, and Metrics as first-class primitives. That's why
> this integration is thin glue, not a framework. A real
> partner integration *should* look like this — thin, declarative, and
> easy to clone for the next customer."

*(Switch to the docker-compose.yml and `devin_client.py` briefly to
make the point visually — the client is one file, the orchestrator
endpoints are a few dozen lines each.)*

---

## 3:45–5:00 — When / Next steps

> "Finally, where this goes next.
>
> In a real customer engagement, this isn't a one-off automation. It's
> a productizable offering. Imagine an Infosys or a Cognizant pitching
> 'CVE Burndown-as-a-Service' to their existing enterprise customers:
> fixed price, ninety days, dedicated PR per CVE, this dashboard as the
> reporting surface. Infosys owns the customer relationship and the
> reviewer-side handover; Cognition runs the consumption; the
> Playbook is the codified expertise.
>
> The reason that's interesting is that the same architecture handles
> any *other* high-volume, repetitive engineering pattern. Swap the
> scanner for coverage.py and the Playbook for a test-writing SOP, and
> you have Test Coverage Lift-as-a-Service. Swap them for a Java
> migration scanner and a JDK-upgrade SOP, and you have Java
> Modernization. Each new offering is one Playbook and one fork of this
> orchestrator. That's how a partner-led motion scales — not by
> closing one-off custom engagements, but by templating them.
>
> The repo and the partner playbook write-up are linked in the
> submission. Happy to dive deeper on any part of this in a follow-up
> conversation. Thanks for your time."

---

## Production tips

- **Record in three takes max.** Quality over polish.
- **Have the dashboard pre-populated** with 5-10 sessions before you
  start recording — don't try to demo a cold start.
- **Keep the Devin session window open in a tab** for the live-session
  moment in the How section. If the agent is mid-PR while you record,
  even better.
- **Don't read this script word-for-word.** Internalize the four beats
  (problem, demo, why-Devin, partner-future) and the timings.
- **The closing 75 seconds is the part most candidates won't have.**
  Don't rush it.

## Beats to hit (cue card)

1. CVE backlogs are a real, expensive, neglected problem.
2. Trigger → orchestrator → Devin sessions → PRs. Live demo.
3. The Playbook is the asset, not the code.
4. Dashboard answers "is this working?" with numbers.
5. Devin's primitives are why this is 500 LOC not 5000.
6. This is a *template* for a GSI-resold offering. Same shape for the
   next ten use cases.
