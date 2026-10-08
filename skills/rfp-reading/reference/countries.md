# Countries

## Allowed countries

These are the 43 country columns of the SAP Best Practice catalogue - the only codes the ledger
accepts in `rfp_profile.countries`, `capabilities[].countries` and `timeline.waves[].countries`.

| Code | Country | Code | Country | Code | Country |
|---|---|---|---|---|---|
| AE | United Arab Emirates | GB | United Kingdom | PH | Philippines |
| AT | Austria | HK | Hong Kong | PL | Poland |
| AU | Australia | HU | Hungary | PT | Portugal |
| BE | Belgium | ID | Indonesia | RO | Romania |
| BR | Brazil | IE | Ireland | RU | Russia |
| CA | Canada | IN | India | SA | Saudi Arabia |
| CH | Switzerland | IT | Italy | SE | Sweden |
| CN | China | JP | Japan | SG | Singapore |
| CZ | Czech Republic | KR | South Korea | SK | Slovakia |
| DE | Germany | LU | Luxembourg | TH | Thailand |
| DK | Denmark | MX | Mexico | TR | Turkey |
| ES | Spain | MY | Malaysia | TW | Taiwan |
| FI | Finland | NL | Netherlands | US | United States |
| FR | France | NO | Norway | ZA | South Africa |
|  |  | NZ | New Zealand |  |  |

Common RFP spellings: KSA -> SA; UAE -> AE; UK, Great Britain, England, Scotland, Wales,
Northern Ireland -> GB; USA, U.S., United States of America -> US; Republic of Korea, Korea (South)
-> KR; Czechia -> CZ; Turkiye / Türkiye -> TR; Holland -> NL.

## Which countries qualify

Extract a country when the RFP indicates that the country is relevant to the SAP implementation,
transformation, migration, rollout, localization, integration, or other requested SAP scope.

Do NOT extract a country merely because it appears in:

- general company background,
- export/customer information,
- generic business operations,
- vendor office information,
- SAP/vendor office locations,
- server or hosting locations,
- generic global references,
- an existing system belonging to a separate affiliate, subsidiary, or intercompany trading partner
  that the in-scope country's process only transacts with (e.g. an intercompany purchase order,
  billing, or goods movement) - that partner's own country is not itself in scope unless the RFP
  separately states that country is also being implemented. The integration work itself is still
  captured as a capability under whichever country is actually performing it (see "Third-party /
  non-SAP systems" in capability-extraction.md); this bullet only affects which country the
  relationship is attached to, never whether the integration is extracted at all,
- the client's own office or head-office location mentioned only for project execution, travel,
  or delivery logistics, not as a place where SAP is being deployed,

unless the surrounding RFP context indicates that the country is part of the requested SAP scope.

Use the complete document and your judgment rather than relying only on keyword matching.

## The country gate

A module may only be attached to a country that has already qualified above. If a country appears
merely as a mention (company background, generic reference, or incidental keyword proximity),
attach NO modules to it. This precondition overrides every "always extract", "mandatory" and "must
not be omitted" instruction anywhere in this skill: those mandates govern only WHETHER a module is
a valid SAP module, never WHETHER a merely-mentioned country becomes in scope. When a module keyword
appears near a country that is not itself in SAP scope, attach the module to the country that is
actually performing the work - never promote the mentioned country into scope on the strength of a
module keyword alone.

Every country you write must qualify on its own SAP-scope merits, independent of any single module
keyword. If the only reason a country appears is a nearby module keyword, remove it entirely.

## Scope type per country

- `in_scope`: the country is part of the requested SAP scope.
- `optional_scope`: the country's SAP scope is explicitly offered as an option ("optional",
  "priced separately as an option", "at the client's discretion").
- When a country is in scope through one statement and optional through another, it is `in_scope`;
  individual optional capabilities for it are marked `optional_scope` on the capability rows.
- Countries whose SAP scope is explicitly OUT OF SCOPE, EXCLUDED or NOT REQUIRED are not written.

## Unsupported countries

If the RFP clearly identifies a country as part of the SAP scope but that country is NOT present in
the list above, put its name (as the RFP spells it) in `rfp_profile.unsupported_countries` and add a
quote showing it is in scope to `rfp_profile.evidence`. Do NOT invent a country code - for example,
Egypt has no code here. Do NOT place an unsupported country in `rfp_profile.countries` or in any
capability's `countries`.

In the timeline, a wave that delivers an unsupported country keeps it: record the country as a unit
with `kind: "country"` and `iso: "OTHER:<name>"` (e.g. `OTHER:Egypt`) and reference it from the
wave's `unit_ids`. Never drop or shorten a wave because one of its countries is unsupported -
whether a country can be serviced is decided later, not while reading.
