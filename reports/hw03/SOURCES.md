# Corpus Sources - Municipal Transit Incidents (DOMAIN_ID 2)

**Documents:** 8  |  **Total size:** 4,396,156 bytes (4293.1 KB)  |  **Minimum required:** 200 KB

All documents are US federal government publications in the public domain.
Local snapshots live in `data/corpus/`; byte sizes and SHA-256 hashes are in
`reports/hw03/CORPUS_MANIFEST.json`. Re-run `python code/fetch_corpus.py --verify`
to confirm the local files still match their recorded hashes.

## How these snapshots were obtained

`code/fetch_corpus.py` builds the corpus. It downloads each document, converts
it to text, and writes this file plus the manifest in one step.

Any entry whose **Retrieved from** line reads *(hand-saved)* was downloaded in a
browser into `data/corpus_raw/` and converted by the same code path rather than
fetched over the network. The two routes produce identical output: eCFR pages are
tag-stripped and trimmed to the regulation either way, Federal Register documents
are unwrapped from the browser's HTML container, and PDFs are copied byte for byte.
`data/corpus_raw/` holds those originals and is not tracked in git; `data/corpus/`
is the corpus the pipeline reads.

Reproduce with `python code/fetch_corpus.py` (network) or
`python code/fetch_corpus.py --manual-only` (from `data/corpus_raw/`), then
`python code/fetch_corpus.py --verify` to confirm the hashes below.

## 49 CFR Part 673 - Public Transportation Agency Safety Plans

- **Local file:** `data/corpus/ecfr_49cfr673_agency_safety_plans.txt`
- **Publisher:** Electronic Code of Federal Regulations (eCFR)
- **Source URL:** https://www.ecfr.gov/current/title-49/subtitle-B/chapter-VI/part-673
- **Retrieved from:** https://www.ecfr.gov/current/title-49/subtitle-B/chapter-VI/part-673
- **Access date:** 2026-09-21
- **Size:** 38,152 bytes
- **SHA-256:** `7abb2e02081dbecd7b3f6224820ab235b4303d3ad323311495f02f05c94fac34`
- **Why it is in the corpus:** Defines what a transit agency's safety plan must contain, including the safety risk management and safety assurance processes.

## 49 CFR Part 674 - State Safety Oversight

- **Local file:** `data/corpus/ecfr_49cfr674_state_safety_oversight.txt`
- **Publisher:** Electronic Code of Federal Regulations (eCFR)
- **Source URL:** https://www.ecfr.gov/current/title-49/subtitle-B/chapter-VI/part-674
- **Retrieved from:** https://www.ecfr.gov/current/title-49/subtitle-B/chapter-VI/part-674
- **Access date:** 2026-09-21
- **Size:** 38,462 bytes
- **SHA-256:** `f57a0b3665380da241e6c49d781c95e83da83e6aa116d03b66ad1622d218d975`
- **Why it is in the corpus:** Defines how states oversee rail transit safety, including the accident notification and investigation duties after an incident.

## Public Transportation Agency Safety Plans - Final Rule (2024)

- **Local file:** `data/corpus/fr_2024_ptasp_final_rule.txt`
- **Publisher:** Federal Register / Federal Transit Administration
- **Source URL:** https://www.federalregister.gov/d/2024-07514
- **Retrieved from:** 2024-07514
- **Access date:** 2026-09-21
- **Size:** 370,003 bytes
- **SHA-256:** `2bf7cc88b55ccec8e93dde582401f065e6ebb7b2379914d9767473564ba7f40a`
- **Why it is in the corpus:** The final rule preamble; long analytical prose with compliance deadlines and cost estimates.

## Public Transportation Agency Safety Plans - Notice of Proposed Rulemaking (2023)

- **Local file:** `data/corpus/fr_2023_ptasp_proposed_rule.txt`
- **Publisher:** Federal Register / Federal Transit Administration
- **Source URL:** https://www.federalregister.gov/d/2023-08777
- **Retrieved from:** 2023-08777
- **Access date:** 2026-09-21
- **Size:** 114,254 bytes
- **SHA-256:** `94d4df7adafdd365b989db823ac08dba4c648084c5591c3b5440374a5063aeb3`
- **Why it is in the corpus:** The proposal that preceded the final rule; overlaps it heavily, which is useful for producing confidently-scored wrong retrievals.

## National Public Transportation Safety Plan (2024)

- **Local file:** `data/corpus/fr_2024_national_transit_safety_plan.txt`
- **Publisher:** Federal Register / Federal Transit Administration
- **Source URL:** https://www.federalregister.gov/d/2024-07392
- **Retrieved from:** 2024-07392
- **Access date:** 2026-09-21
- **Size:** 71,612 bytes
- **SHA-256:** `915b6603262b20f8b2b4eff950b5b95e26dd4727973ff083042cf4594c4e3ada`
- **Why it is in the corpus:** National safety performance measures for transit, including the fatality, injury, safety-event and reliability measures.

## General Directive 24-1: Required Actions Regarding Assaults on Transit Workers

- **Local file:** `data/corpus/fr_2024_general_directive_24_1_assaults.txt`
- **Publisher:** Federal Register / Federal Transit Administration
- **Source URL:** https://www.federalregister.gov/d/2024-21923
- **Retrieved from:** 2024-21923
- **Access date:** 2026-09-21
- **Size:** 125,339 bytes
- **SHA-256:** `ec2cb20a91c1763c7ff324ec2b0b8f1f8786e8714098110734d2eb5cbe2b09d1`
- **Why it is in the corpus:** A short, highly specific directive; its requirements appear in no other document in the corpus.

## NTSB/RIR-22/07 - Collision Between Sacramento Regional Transit District Light Rail Vehicles

- **Local file:** `data/corpus/ntsb_rir2207_sacramento_light_rail_collision.pdf`
- **Publisher:** National Transportation Safety Board
- **Source URL:** https://www.ntsb.gov/investigations/AccidentReports/Reports/RIR2207.pdf
- **Retrieved from:** https://www.ntsb.gov/investigations/AccidentReports/Reports/RIR2207.pdf
- **Access date:** 2026-09-21
- **Size:** 1,616,498 bytes
- **SHA-256:** `37df3d06966141910455fa168ea9664a19fcad2b9273f82943fae7e8ec0821f4`
- **Why it is in the corpus:** A complete single-incident investigation: date, milepost, injury count and probable cause exist only in this document.

## NTSB/RIR-23/15 - Derailment of Washington Metropolitan Area Transit Authority Train 407

- **Local file:** `data/corpus/ntsb_rir2315_wmata_rosslyn_derailment.pdf`
- **Publisher:** National Transportation Safety Board
- **Source URL:** https://www.ntsb.gov/investigations/AccidentReports/Reports/RIR2315.pdf
- **Retrieved from:** https://www.ntsb.gov/investigations/AccidentReports/Reports/RIR2315.pdf
- **Access date:** 2026-09-21
- **Size:** 2,021,836 bytes
- **SHA-256:** `249c0d2c3f62d470539fde79668b3aec97007760b257360bba718aca16262253`
- **Why it is in the corpus:** A second single-incident investigation with a mechanical (rather than procedural) probable cause, for contrast.
