# Label notes (cache_cases.yaml is frozen — corrections would be documented here, not edited in the file)

After the sweep, every label was re-read against the per-case similarities and the MySQL answers.
No labeling mistake was found: all 10 near-miss cases have a correct answer different from the cached one (checked against
MySQL before the sweep), all 10 paraphrases ask for the same fact about the same route, and no unrelated case is transit-related.

Observation, not a relabel: case C28 ("Accident-Collision" vs the cached "Safety Hazard" question for route R-0050) is the
lowest-similarity near-miss (0.853) because the route is identical and only the category word differs; it is still correctly
labeled should-miss (6 vs 11 incidents).
