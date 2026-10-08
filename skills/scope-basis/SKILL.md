---
name: scope-basis
description: >-
  Extracts the SAP Basis activities an RFP states (technical landscape set-up and hosting-provider
  coordination, system tiers, clients, transports, connectivity, BTP / Integration Suite / Cloud
  Connector set-up, Fiori Launchpad / Gateway set-up, output, jobs, monitoring, backup, technical
  cutover) into the bid ledger under a strict evidence rule, with scope status and whole man-days
  1-5 for DEV, QA and PRD. Use when building the effort estimate (call 1).
metadata:
  owner: "sap-practice"
  version: "1.0.0"
  ledger_sections: "basis"
---

# SAP Basis scope

Ported from section (E) of the old scope prompt and basis_scope.py.

## Detection procedure (mandatory - an empty section is the most common error)
The first live runs left this section empty or short because the agent read one or two pages and
stopped. So:
1. Read the WHOLE RFP with `read_next_pages` (call it until it says the whole RFP is read). The write
   tool refuses `rows=[]` until you have, and the harness sends you back if you stop early.
2. While reading, note every candidate below with its page. Then grep for each signal word listed
   below as a second pass (`grep(pattern="a|b|c", path="/rfp/")` - case-insensitive).
3. Write what you found in batches of at most 10 rows.
4. `rows=[]` is right only when no signal matched anywhere. Its none_reason must name the signal
   words you searched and the pages you checked, e.g. "read p.1-52; grep 'basis|transport|backup|
   BTP|Cloud Connector|go-live' - no Basis activity stated". A none_reason without this is rejected
   in review.

Signals (grep): `transport`, `backup`, `restore`, `landscape`, `system tier|tiers|DEV|QAS|PRD`,
`hosting|RISE|private cloud|private edition`, `BTP|Integration Suite|CPI|Cloud Connector`,
`Fiori|Launchpad|Gateway`, `output|printing|print`, `job|monitoring`, `go-live|go live|cutover`,
`connection package|capacity`.

Rules 2 and 3 below are met by almost every S/4HANA RFP: an Integration Suite / CPI box in the
integration diagram, Fiori apps in scope, RISE / private-cloud hosting, or stated go-lives each give
one row. An empty Basis section on an S/4HANA implementation RFP is almost always a reading error -
re-check those four signals before you record it empty. A typical S/4HANA private-cloud RFP yields
about 5-8 Basis rows of these kinds: Fiori Launchpad / Gateway set-up, transport management, backup
and recovery coordination, BTP / Integration Suite tenant set-up, landscape tiers / connection
package coordination, technical cutover and go-live support - each only with its RFP evidence.

## What Basis is
The technical administration of the SAP system landscape: system / landscape set-up and coordination
with the hosting provider, additional system tiers, clients, transport management and moving
transports through the landscape, technical connectivity (RFC destinations, SAP Cloud Connector, BTP /
Integration Suite tenant set-up), certificates, Fiori Launchpad / Gateway technical set-up, printing /
output set-up, background jobs, system monitoring and performance, backup and recovery, and technical
cutover / go-live support.

## Never Basis
Functional configuration or business processes, RICEFW / interface development, role and
authorisation design, single sign-on / identity (Secure Login Service, Cloud Identity - Security),
data migration content, testing of business scenarios, training, project management, and the
client's current / legacy landscape.

## STRICT EVIDENCE RULE - list an activity ONLY for one of these
1. The RFP names the Basis activity itself ("Final List of Transports", "Back-up and recovery
   procedures").
2. The RFP puts an SAP technical platform in scope (BTP, Integration Suite / CPI, Cloud Connector,
   Cloud ALM, or hosting tiers / capacity / connection packages): ONE set-up activity each. Business
   applications never qualify (MDG, TM, Ariba, SuccessFactors, GRC, OpenText, Signavio).
3. The RFP states go-lives: ONE "Technical cutover and go-live support" row in total, effort sized by
   their number.
Nothing from general SAP knowledge; when unsure, leave it out. One row per activity - never the same
activity twice in different words. Fiori scope counts only as "Fiori Launchpad / Gateway technical
setup". No evidence -> `rows=[]` with a none_reason.

## Fields
- `activity`: a concise name in the RFP's terms.
- `status`: "Out of Scope" when the RFP gives the activity to someone other than the implementation
  partner - the client's IT team, another vendor, or the hosting provider (e.g. SAP under RISE with
  SAP / S/4HANA Cloud private edition, which runs infrastructure, installation, backups and patching)
  - or excludes it; otherwise "In Scope".
- `dev`, `qa`, `prd`: the partner's effort on the DEV, QA and PRD systems in MAN-DAYS - each a WHOLE
  NUMBER 1-5. Judge from nearby context: the number of systems, tiers, interfaces, apps, entities or
  go-lives stated (1 = a small task, 5 = heavy multi-step work; partner coordination of
  hosting-provider work = 1 - when the landscape is with a hosting provider, backups, tiers, capacity
  and patching are that coordination). null for all three when Out of Scope.
- `evidence`: the exact RFP words stating the activity (verbatim substring), file and page.

## Output
`ledger_write_basis(rows=[...])`. Fix and resend rejected rows.
