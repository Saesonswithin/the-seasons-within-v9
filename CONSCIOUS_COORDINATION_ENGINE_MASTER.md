# The Seasons Within — Conscious Coordination Engine Master Specification

This file is the build contract for the intelligence layer under the approved The Seasons Within visual design.

## Core rule

**CALCULATE → STRUCTURE → COMPARE → INTERPRET → WRITE → VALIDATE → CREATE LISTENING SCRIPT → SPEAK**

Never generate a report by `sign → generic paragraph`, and never turn a questionnaire answer into a lightly reworded paragraph.

Member-facing language uses **Lunar / Lunar Cycle / Current Season Within**. Internal astronomy may use the technical beginning-of-cycle Sun–Lunar conjunction.

## Four separate coordination jobs

1. **Natal Foundation — permanent.** Swiss Ephemeris/provider calculations store exact longitudes for Sun, Lunar, Mercury, Venus, Mars, Jupiter, Saturn, Uranus, Neptune and Pluto. Rising, houses and house cusps are used only when birth time is reliable. Natal aspects and element balance are stored as deterministic evidence.
2. **Personal Planetary Coordination — Lunar-cycle/monthly.** Seven different functions: Sun, Lunar, Mercury, Venus, Mars, Jupiter and Saturn. Each has a calculated Coordination score, a separate Activation score, structured evidence, a written report, a separate listening script and report-version identity.
3. **What Deserves Your Attention — daily.** Today’s Lunar contacts, other current contacts, current monthly activation, owner-private structured Journal themes and recent daily continuity determine the highest-activation domains. The daily writer operates inside the larger Lunar cycle.
4. **Two-person Conscious Coordination.** When another member views a profile, the numbers belong to **viewer + profile owner**. They are calculated from chart-to-chart synastry plus both permitted self-reported profiles. Private Journal material is never used in pair coordination.

## Coordination is not Activation

**Coordination** represents relative ease/integration in the configured reflective model.

**Activation** represents how strongly a function is emphasized/relevant now.

A lower Coordination score with a high Activation score does not mean the member is “bad” at that function. It means the function may require more conscious effort during the current period.

No qualifying aspect uses a neutral flow baseline of **65** and Activation **0**.

### Major aspect configuration

| Aspect | Angle | Orb | Flow target | Activation |
|---|---:|---:|---:|---:|
| Conjunction | 0° | 8° | .70 | 1.00 |
| Sextile | 60° | 6° | .82 | .65 |
| Square | 90° | 7° | .48 | .95 |
| Trine | 120° | 7° | .88 | .70 |
| Opposition | 180° | 8° | .45 | .95 |

Orb strength is `1 - orb/max_orb`. A loose aspect moves toward the neutral flow baseline while an exact aspect carries the full configured target.

## Personal monthly Planetary Coordination

Each planet uses:

- 35% current astrological coordination
- 30% psychological coordination
- 20% natal integration
- 15% current-life/Journal integration

Journal theme **relevance** may increase Activation. Journal language does not automatically prove high or low integration; without validated evidence, integration remains neutral.

### Current-sky weights by target function

| Target | Cycle Point | Sun | Mercury | Venus | Mars | Jupiter | Saturn |
|---|---:|---:|---:|---:|---:|---:|---:|
| Sun | .30 | .10 | .10 | .08 | .12 | .15 | .15 |
| Lunar | .35 | .08 | .08 | .10 | .12 | .10 | .17 |
| Mercury | .25 | .10 | .20 | .06 | .15 | .10 | .14 |
| Venus | .22 | .08 | .08 | .20 | .14 | .12 | .16 |
| Mars | .22 | .08 | .10 | .05 | .23 | .10 | .22 |
| Jupiter | .20 | .08 | .08 | .08 | .10 | .26 | .20 |
| Saturn | .20 | .08 | .08 | .06 | .12 | .16 | .30 |

## Personal Overall Coordination

The current Lunar-cycle Overall Coordination uses:

- Sun .15
- Lunar .20
- Mercury .15
- Venus .12
- Mars .13
- Jupiter .10
- Saturn .15

The natal chart remains permanent; the monthly snapshot can change with the next Lunar cycle, profile updates and permitted current-life context.

## Current Season Within

Python selects the symbolic season from structured monthly evidence; AI does not choose it.

- **Spring — Renewal:** beginnings, experimentation, emerging intention, rebuilding, curiosity.
- **Summer — Expansion & Connection:** expression, visibility, creativity, relationships, outward movement.
- **Autumn — Reflection & Release:** discernment, boundaries, reassessment, simplifying, letting go.
- **Winter — Restoration & Inner Listening:** recovery, reduced stimulation, integration, solitude, preparation.

The Current Season Within is a Lunar-cycle orientation, not a weather/calendar season and not the same job as the daily attention report.

## Daily clock

Daily domain activation uses the configured starting model:

- 50% today’s Lunar-to-natal activation
- 20% other current-planet activation
- 15% current monthly activation
- 10% current Journal-theme relevance
- 5% recent-report continuity

The engine ranks all seven functions, then the report writer interprets the primary and secondary functions. Recent daily reports are retrieved so the next day can develop a theme rather than repeat it.

## Journal privacy architecture

Raw private Journal bodies stay private. Report writers receive a structured owner-private packet containing:

- current theme names
- normalized theme strengths/relevance
- theme counts
- continuity fingerprint

Reports must never say “Your Journal says…” unless the member explicitly asks for Journal analysis. Pair coordination never receives private Journal material.

## Two-person coordination

Each planetary domain begins with:

- 55% chart-to-chart planetary coordination
- 45% psychological/behavioral coordination

Synastry uses actual longitude/aspect/orb calculations and cross-chart pairs, not zodiac-sign shortcuts. Directional cross-pairs are evaluated in both directions where appropriate.

### Relationship-type Overall weights

**Romantic / Love**: Sun .10, Lunar .22, Mercury .16, Venus .18, Mars .14, Jupiter .07, Saturn .13.

**Friendship**: Sun .10, Lunar .18, Mercury .22, Venus .14, Mars .10, Jupiter .16, Saturn .10.

**Family**: Sun .10, Lunar .24, Mercury .20, Venus .12, Mars .14, Jupiter .05, Saturn .15.

**Business**: Sun .13, Lunar .08, Mercury .22, Venus .08, Mars .16, Jupiter .14, Saturn .19.

**Retreat**: Sun .08, Lunar .20, Mercury .14, Venus .10, Mars .10, Jupiter .18, Saturn .20.

The same two people may therefore have different Overall Coordination percentages for different relationship/coordination contexts.

## Wheel behavior

- Self view: the member’s seven-function Planetary Coordination wheel, using the same factual natal longitudes shown on the seven Journal cards.
- The self wheel is birthday-centered: the member’s exact natal Sun longitude is placed at 12 o’clock. The zodiac sectors and all seven planetary glyphs rotate by the same Sun-derived offset, so changing the member’s birth information changes the wheel orientation without changing any calculated sign, degree or planet-to-planet angle.
- Other-member view: viewer + member comparison wheel.
- Planet positions use exact stored zodiac longitude.
- Cross-chart aspect lines come from the reusable aspect engine.
- The self wheel excludes outer planets, Rising and houses so it cannot conflict with the seven-function member experience.
- The comparison wheel may draw reliable house cusps only when supported by exact birth time/location; missing reliable birth time never invents Rising or houses.

## Structured report generation

For substantial reports, the language model is asked for structured JSON before formatting prose. Planetary reports use planet-specific human-domain headings and require multiple evidence sources. The model is not allowed to invent scores.

Quality checks reject:

- repeated/canned report text
- excessive generic spiritual filler
- reports that only restate questionnaire wording
- reports that depend on a single sign or one isolated fact

Exact normalized hashes and semantic-similarity checks protect against duplicate or near-duplicate reports.

## Audio

Each substantial written report has a separate listening script that preserves the report’s meaning without reading webpage headings verbatim. Report identity includes the report type, period/cycle key and report version; the audio key is derived from the exact report context/text so changed reports receive changed audio identity.

## Stored architecture

The build includes persistent tables/equivalents for:

- natal_charts
- planet_positions
- natal_aspects
- lunar_cycles
- member_lunar_cycles
- transit_snapshots
- transit_aspects
- psychological_profiles
- psychological_dimensions
- journal_theme_snapshots
- planetary_coordination_snapshots
- daily_attention_reports
- coordination_reports
- report_embeddings
- member_pair_coordination
- member_pair_planetary_scores

The approved visual application remains the shell around this engine. Intelligence changes must not resurrect removed pricing, duplicate profiles, old Retreat placement, or other retired UI.

## AI Communication Connection — implemented after visual approval

The member-facing communication layer is connected after deterministic scoring:

1. Personal Lunar-cycle snapshot calculates seven Planetary Coordination scores and separate Activation scores.
2. Personal Coordination Profile category percentages are derived from those same monthly seven-function calculations; questionnaire completion is not used as the visible score.
3. Daily What Deserves Your Attention ranks daily activation inside the current Lunar cycle and generates a separate daily report.
4. Current Season Within is selected by the deterministic season engine from the current Lunar-cycle evidence, then AI explains that selected season without changing it.
5. Another member's profile uses the viewer-to-member pair engine. The viewer sees pair percentages and pair reports, never the profile owner's personal self percentages.
6. Pair evidence uses chart-to-chart relationships plus both permitted psychological/behavioral profiles and excludes both members' private Journal text from pair reports.
7. AI report generation uses OpenAI Responses API Structured Outputs with a strict JSON schema, then formats validated sections into member-facing prose.
8. The deterministic coordination score and separate activation score are supplied to AI as fixed evidence; AI is explicitly forbidden to invent or change either number.
9. Every substantial written reflection receives a separate listening script; the listening script preserves meaning but is not a verbatim reading of visible headings/text.
10. Speech is generated server-side through the configured OpenAI speech endpoint. No browser speech synthesis is used.
11. The main My Journal page no longer depends on successful AI generation to decide the season or whether daily/monthly sections can render. Evidence-bound fallbacks prevent a permanent "temporarily unavailable" member experience when generation or uniqueness checks fail.
12. Cached monthly reports are tied to the Lunar-cycle key; daily reports are tied to the calendar date; pair reports are tied to the two member profiles and relationship context fingerprint.


## FINAL REVIEW CORRECTIONS — 2026-08-19

- Do not neutral-pad missing evidence into every visible percentage. Missing evidence lowers confidence; it does not force cards toward 65–75%.
- Monthly personal and pair scores combine only available evidence using explicit confidence. Coordination and Activation remain separate.
- All seven monthly Planetary Coordination reports must always return a written report. AI failure or uniqueness exhaustion falls back to deterministic evidence-bound communication; it must never leave six cards as “temporarily unavailable.”
- Listening scripts are separate from written reports. Spoken-generation failure cannot invalidate the written report. Audio is generated once, cached persistently, and tied to the exact coordination report identity/version/script.
- Collapsed Planetary Coordination cards display Coordination only. Activation remains in the evidence/report system and may be explained in the written reflection rather than appearing as a second collapsed-card percentage.
- The seven planetary audio files are prepared sequentially, retried and validated before the browser receives them so concurrent first-load generation cannot leave every player at 0:00 / 0:00.
- Daily What Deserves Your Attention is ranked from today’s real Lunar/current-planet activation inside the monthly cycle, current structured life themes, and recent report continuity. Recent repetition reduces novelty weight rather than reinforcing the same domain indefinitely.
- The Conscious Coordination Profile wheel is the visual Wheel Planetary Coordination: only Sun, Lunar, Mercury, Venus, Mars, Jupiter and Saturn, taken from the exact same calculated longitudes powering Your Planetary Coordination. Its orientation is member-specific and birthday-centered, with the natal Sun at 12 o’clock. Zodiac sectors and glyphs use the same Sun-derived transform. Do not mix outer planets, houses or ASC into this seven-function personal wheel.
