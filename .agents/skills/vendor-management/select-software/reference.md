# select-software: reference

Not loaded by default. The criteria catalogue, the script's input formats with the full
fictional example, the sources, and why the method is shaped as it is. Ledgerly, Tallybook
and Receiptwise are invented; any resemblance to a real product is accidental.

## Criteria catalogue

### Quality wants: ISO/IEC 25010:2023

The nine product-quality characteristics, as plain questions to score against. The 2023
edition replaced *usability* with **interaction capability** and *portability* with
**flexibility**, and added **safety**.

| Characteristic | Ask |
| --- | --- |
| Functional suitability | Does it do the whole job, correctly, without needless steps? |
| Performance efficiency | Is it fast enough at our volume, within the plan's limits? |
| Compatibility | Does it work alongside and exchange data with the systems we already run? |
| Interaction capability | Can our actual users learn and use it unaided, including users with access needs? |
| Reliability | Is it available when we need it, and does it recover cleanly? What does the service commitment say? |
| Security | Who can see what, how is access controlled, is activity logged, and what assurance is there? |
| Maintainability | Can it be configured and changed by the people we have, without breaking things? |
| Flexibility | Will it adapt as we grow or change, and can it be replaced or moved? |
| Safety | Can a failure or misuse cause harm to people, money or legal standing, and is that guarded? |

### Commercial wants

The standard covers the product, not the supplier or the deal. Add these:

| Want | Ask |
| --- | --- |
| Vendor viability | How long trading, how funded, how many customers like us? Will it exist at the end of the horizon? |
| Exit and data portability | Can we get all our data out, in a usable form, without the vendor's help? At what cost? |
| Implementation effort | Who sets it up, how long, how much of our staff time? |
| Support | Hours, channels, response commitments, and what the references say about it |
| Contract terms | Term length, notice period, price rises on renewal, liability, data processing terms |
| Roadmap credibility | Has the vendor shipped what it promised before? Judge past delivery, not the published roadmap |

### Generic musts

Used when no `selection-criteria` companion is set. Each needs a yes/no answer and evidence.

- Meets the budget ceiling at the needed scale and tier.
- Holds data where the business is required to hold it, under a data processing agreement.
- Supports the sign-in method the business requires.
- Connects to each system named as required in step 1.
- Meets any accessibility, regulatory or sector rule that applies to the business.

## Input formats

### `score`

```json
{
  "decision": "Select an expense-management tool for a 40-person team",
  "musts": [{"id": "sso"}, {"id": "data-residency"}],
  "wants": [
    {"id": "interaction-capability", "weight": 10},
    {"id": "integration", "weight": 8},
    {"id": "exit-portability", "weight": 6},
    {"id": "vendor-viability", "weight": 5}
  ],
  "options": [
    {"name": "Ledgerly",
     "musts": [{"id": "sso", "pass": true, "evidence": "SAML tested in trial tenant"},
               {"id": "data-residency", "pass": true, "evidence": "DPA clause 4, EU region"}],
     "scores": {"interaction-capability": {"score": 4, "source": "verified", "evidence": "5 of 6 testers finished a claim unaided"},
                "integration": {"score": 4, "source": "verified", "evidence": "accounting sync ran in trial"},
                "exit-portability": {"score": 3, "source": "vendor-stated", "evidence": "CSV export only, per sales"},
                "vendor-viability": {"score": 4, "source": "verified", "evidence": "filed accounts, 6 years trading"}}},
    {"name": "Tallybook",
     "musts": [{"id": "sso", "pass": true, "evidence": "SAML tested in trial tenant"},
               {"id": "data-residency", "pass": true, "evidence": "DPA annex B"}],
     "scores": {"interaction-capability": {"score": 3, "source": "verified", "evidence": "3 of 6 testers finished unaided"},
                "integration": {"score": 3, "source": "verified", "evidence": "sync needs a middleware plan"},
                "exit-portability": {"score": 5, "source": "verified", "evidence": "full API export tested"},
                "vendor-viability": {"score": 2, "source": "verified", "evidence": "seed-funded, 2 years trading"}}},
    {"name": "Receiptwise",
     "musts": [{"id": "sso", "pass": false, "evidence": "SSO only on enterprise tier, above budget ceiling"},
               {"id": "data-residency", "pass": true, "evidence": "DPA clause 7"}]}
  ]
}
```

| Field | Rule |
| --- | --- |
| `musts[].id` | unique; may be empty when there are no musts. Every option answers each one |
| `wants[].id` | unique, at least one; every score key must be one of these |
| `wants[].weight` | whole number 1 to 10 |
| `options[].name` | unique |
| `options[].musts[].id` | a declared must, answered once. One left unanswered counts as `null` |
| `options[].musts[].pass` | `true`, `false` or `null`; `false` needs non-empty text `evidence` |
| `options[].scores.<want>.score` | whole number 0 to 5 |
| `options[].scores.<want>.source` | required: `verified` or `vendor-stated` |

An eliminated option needs no `scores`. `decision` and `evidence` on scores are carried for
the person reading the file; the script does not check them.

### `ahp`

```json
{
  "criteria": ["interaction-capability", "integration", "exit-portability", "vendor-viability"],
  "matrix": [
    [1, 2, 3, 3],
    [0.5, 1, 2, 2],
    [0.3333, 0.5, 1, 1],
    [0.3333, 0.5, 1, 1]
  ]
}
```

`matrix[i][j]` is how much more important criterion `i` is than `j`, on Saaty's 1 to 9
scale (1 equal, 3 moderately, 5 strongly, 7 very strongly, 9 extremely). The diagonal is 1
and `matrix[j][i]` must be the reciprocal of `matrix[i][j]`, within 1%. Two to ten criteria;
group more into a hierarchy and run each level. Weights are the principal eigenvector, found
by power iteration; the consistency ratio uses Saaty's random index.

### `tco`

```json
{
  "currency": "GBP",
  "horizon_years": 3,
  "options": [
    {"name": "Ledgerly", "lines": [
      {"item": "Setup and data migration", "category": "go-live", "amounts": [4000, 0, 0]},
      {"item": "Licences, 40 seats", "category": "run", "amounts": [7200, 7560, 7940]},
      {"item": "Admin time, 2 hours a week", "category": "internal-time", "amounts": [3100, 3100, 3100]},
      {"item": "Export and archive at exit", "category": "exit", "amounts": [0, 0, 1500]}
    ]},
    {"name": "Tallybook", "lines": [
      {"item": "Setup", "category": "go-live", "amounts": [1500, 0, 0]},
      {"item": "Middleware for accounting sync", "category": "run", "amounts": [2400, 2400, 2400]},
      {"item": "Licences, 40 seats", "category": "run", "amounts": [6000, 6600, 7260]},
      {"item": "Admin time, 3 hours a week", "category": "internal-time", "amounts": [4650, 4650, 4650]}
    ]}
  ]
}
```

`amounts` has exactly one number per year of the horizon, each zero or more. `currency` is a
label; the script does no conversion, so put every option in one currency. A duplicate is
detected by item name, ignoring case and surrounding spaces; two differently named lines for
the same cost are not caught.

## Error messages

Every input problem exits 2 with one line on stderr, `error: <message>`, where `<where>`
is a path into the input such as `options[1].musts[0]`. Fix the named field and run again.

| Message | Fix |
| --- | --- |
| `cannot read <file>` / `<file> is not valid JSON: <reason>` / `<file> must hold a JSON object` | check the path, then the JSON; the top level is an object |
| `<where> must be an object` / `<where> has no '<key>'` | each entry is an object with that key |
| `<where>.<key> must be a whole number`, `must be text` or `must be an object` | give the field the type in the input rules above |
| `<where>.<key> must be a list` | `musts`, `wants`, `options` and `lines` are arrays, even with one entry |
| `input.wants is empty: weight at least one want before scoring` / `input.options is empty` | add them; nothing can be ranked without both |
| `<where>.weight is <n>; weights run 1 to 10` / `<where> is <n>; scores run 0 to 5` | bring the number into range |
| `want '<id>' is listed twice` / `must '<id>' is listed twice` / `option '<name>' is listed twice` / `a criterion is listed twice` | merge or rename the duplicate |
| `<where> answers '<id>', which is not a declared must` | declare it in the top-level `musts`, or fix the id |
| `<where> answers '<id>' twice` | keep one answer per must per option |
| `<where>.evidence must be text` | write the evidence as a string |
| `<where> fails with no evidence; an elimination cites its evidence` | add what showed the must failed, or set `pass` to `null` |
| `<where>.pass must be true, false or null` | use the JSON literal, not `"yes"` or `1` |
| `<where>.scores must be an object keyed by want id` | `scores` maps want id to a score entry |
| `<where> scores '<id>', which is not a weighted want` | add the want with a weight, or drop the score |
| `<where>.source must be one of verified, vendor-stated; every score says where it came from` | mark each score's source |
| `ahp needs at least two criteria` / `ahp supports at most 10 criteria; group them into a hierarchy` | resize the comparison |
| `matrix must be <n> by <n>, one row and column per criterion` | one row and one column per criterion, in the same order |
| `matrix[i][j] must be a positive number` / `matrix[i][i] must be 1: a criterion equals itself` | fix that cell |
| `matrix[i][j] and matrix[j][i] are not reciprocals` | make one the inverse of the other, such as 3 and 0.3333 |
| `input.horizon_years must be at least 1` | give a horizon of one year or more |
| `<where>.category must be one of go-live, run, support, upgrade, exit, internal-time` | file the line under one of those |
| `<where> has <n> amounts; the horizon is <n> years` | one amount per year of the horizon |
| `<where>.amounts[k] must be a number of zero or more` | record a credit as a lower cost, not a negative line |

Exit 3 with `internal error: <type>: <message>` is a defect in the script, not the input.

## Thresholds, and why

| Threshold | Value | Why |
| --- | --- | --- |
| Close call | leader less than 10% ahead | scores are structured judgement on a 0 to 5 scale; a smaller gap is inside the noise of one rater's reading |
| Sensitivity | each weight moved by 2, clamped to 1 to 10 | a 2-point disagreement on a 10-point weight is common between two reasonable people |
| Vendor claims | the leader's vendor-stated scores each cut by 1 | a vendor's own claim is the score most likely to be one point generous; a lead that cannot absorb that rests on the vendor's word |
| AHP consistency | ratio above 0.1 | Saaty's own limit for acceptable inconsistency |

The checks run in a fixed order: `TIE`, then `CLOSE_CALL`, then `FRAGILE`. A close call that
is also fragile reports `CLOSE_CALL`, and `flips` still lists the weight changes.

## Failure modes

- **Starting from a favourite.** Weights set after scoring, or musts written to rule a rival
  out. Fix weights first, and give every elimination its evidence.
- **Reading the analyst map as the answer.** A market leader can be wrong for a 40-person
  team.
- **Scoring the brochure.** A total built from vendor-stated scores is the vendor's ranking.
- **Licence-only cost.** Staff time, migration and exit usually change the order.
- **Skipping step 2.** Buying a product for the one thing that makes the business different,
  or building a commodity nobody will thank you for.
- **Recommending on `INCOMPLETE`.** A missing must is a question, not a pass.

## Sources

- ISO/IEC 25010:2023, *Systems and software Quality Requirements and Evaluation (SQuaRE) —
  Product quality model*. https://www.iso.org/standard/78176.html
- ISO/IEC 25040:2024, *SQuaRE — Quality evaluation framework*: define, design, plan,
  execute and conclude an evaluation, including choosing among products.
  https://www.iso.org/standard/83467.html
- C. H. Kepner and B. B. Tregoe, *The New Rational Manager*, chapter 4, "Decision Analysis":
  musts, weighted wants, adverse consequences.
- T. L. Saaty, *The Analytic Hierarchy Process*, McGraw-Hill, 1980.
- A. S. Jadhav and R. M. Sonar, "Evaluating and selecting software packages: A review",
  *Information and Software Technology* 51(3), 2009: AHP is the most used technique, and
  there is no shared generic criteria list. https://doi.org/10.1016/j.infsof.2008.09.003
- Gartner, "How Markets and Vendors Are Evaluated in Gartner Magic Quadrants": a Magic
  Quadrant focuses the search but does not align requirements to a vendor.
  https://www.gartner.com/en/documents/3956304
- Gartner, Critical Capabilities methodology: products scored 1 to 5 against weighted use
  cases. https://www.gartner.com/en/research/methodologies/research-methodologies-gartner-critical-capabilities
- Gartner, "Defining Gartner Total Cost of Ownership" (G00131837, 2005), and "How to Manage
  Rising Software Costs": whole-of-life cost, a chart of accounts, no double counting.
  https://www.gartner.com/smarterwithgartner/how-to-manage-rising-software-costs
- Forrester, The Forrester Wave methodology: differentiating, weighted criteria from
  questionnaires, demos and reference customers.
  https://www.forrester.com/policies/forrester-wave-methodology/
- S. Wardley, *Wardley Maps* (Creative Commons): evolution from genesis to commodity, and
  build or buy by stage. https://medium.com/wardleymaps
- Thoughtworks, Technology Radar FAQ: Adopt, Trial, Assess, Caution, and Trial only after
  production use. https://www.thoughtworks.com/radar/faq

## Changing this skill

Run `python3 scripts/score_options.py --selftest` after any edit to the script. If a
threshold changes, regenerate the samples in SKILL.md by running the script on the inputs
above, rather than editing them by hand.
