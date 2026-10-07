# Decisions routing label audit

Owner-reviewed before live scoring on 2026-10-07. These labels identify intended routes; they do not establish numerical answers. The project agent proposed them and the owner reviewed all 24 in chat.

- **du01 — opening_usage**: Treat the opening tag as supplied: what part of the known-opening denominator is Vienna Game, with both counts shown?
  Rationale: One named opening; frequency, not player points.

- **du02 — opening_usage**: I only need the number of Owen Defense games in the prefix and the tagged-game total used to divide it.
  Rationale: Raw usage count and denominator.

- **du03 — opening_usage**: The phrase "score rate" is not what I want here. Report the frequency of Nimzowitsch Defense among games with an opening label.
  Rationale: Explicitly requests frequency despite distracting score wording.

- **ds01 — opening_score**: For white at 60+0 and rating 1400 through 1599, report points earned per Vienna Game and its win/draw/loss counts.
  Rationale: One opening, specified player cohort, score outcomes.

- **ds02 — opening_score**: Use black players in the 1400–1599 band at 60+0. What fraction of available points did they earn with the Owen Defense tag?
  Rationale: Complete cohort; one opening score.

- **ds03 — opening_score**: Restrict to white, 60+0, 1400–1599. I want the results in Nimzowitsch Defense games, not how often the opening appears.
  Rationale: Score outcomes explicitly distinguished from opening frequency.

- **do01 — opening_compare**: At 60+0, compare white score in Vienna Game and Owen Defense for ratings 1400–1599; this is a descriptive comparison only.
  Rationale: Two explicit families and matched cohort.

- **do02 — opening_compare**: For black rated 1400–1599 at 60+0, place Owen Defense and Nimzowitsch Defense points per game side by side.
  Rationale: Two named openings; player scores.

- **do03 — opening_compare**: Contrast the white points rates of Bird Opening and Vienna Game, both 60+0 and ratings 1400–1599, without recommending either.
  Rationale: Comparative score question, not personalized advice.

- **db01 — clock_bucket**: Within the 30–59 seconds before-turn bucket, give evaluated moves, eligible moves, and their ratio.
  Rationale: One explicit clock bucket; evaluation coverage.

- **db02 — clock_bucket**: For less than ten seconds before the move, report the observed >=200 cp deterioration fraction and its evaluable denominator.
  Rationale: One explicit clock bucket; proxy rate.

- **db03 — clock_bucket**: Show the error-proxy numerator and denominator for 60 or more pre-turn seconds, with no causal interpretation.
  Rationale: One explicit clock bucket; descriptive rate.

- **dc01 — clock_compare**: Which observed proxy rate is larger: under 10 pre-turn seconds or 30–59? Include both denominators without saying time caused it.
  Rationale: Two specified clock buckets; descriptive comparison.

- **dc02 — clock_compare**: Compare evaluation availability for 10–29 and 60-plus pre-turn seconds, rather than comparing opening scores.
  Rationale: Two specified clock buckets; coverage comparison.

- **dc03 — clock_compare**: Put the 30–59 and 60-plus seconds pre-turn proxy rates next to each other and subtract second from first.
  Rationale: Two bucket proxy comparison with explicit direction.

- **dv01 — coverage**: Why is a 40 MB archive prefix insufficient evidence for a claim about the entire month? Explain the observed-date limitation.
  Rationale: Asks for scope limitation, not an unsupported full-month estimate.

- **dv02 — coverage**: Across the selected move table as a whole, how much engine evaluation data is missing? Do not pick a clock bucket.
  Rationale: Dataset-wide missingness; no clock-bucket analysis requested.

- **dv03 — coverage**: What separates a game excluded as casual from a quarantined PGN, and what are their observed ingestion counts?
  Rationale: Data quality counts and provenance.

- **da01 — clarify**: For the opening I mentioned earlier, give the fraction of points white earned at 60+0 in ratings 1400–1599. There is no earlier context in this request.
  Rationale: Opening referent absent; otherwise executable score request.

- **da02 — clarify**: Give the deterioration rate for the time bucket I have in mind; I have not named the bucket.
  Rationale: Required clock bucket absent.

- **da03 — clarify**: Compare white score for these two openings at 60+0 and ratings 1400–1599. I have not specified the two opening names.
  Rationale: Required two opening names absent.

- **dx01 — unsupported**: Use the observed low-clock association to prove that being short of time causes the mistakes.
  Rationale: Requests causal proof from observational association.

- **dx02 — unsupported**: Estimate the exact December-wide Vienna Game share using only the December 1 prefix, and report it as the full-month fact.
  Rationale: Requests unsupported full-month fact from prefix.

- **dx03 — unsupported**: Summarize the opening results in my private game history; none of those games are present in this project.
  Rationale: Requires private history unavailable to the project.


Owner approved all 24 labels, including revised dx03, in chat on 2026-10-07 before fresh live scoring. Frozen case SHA-256: `c49ab6e50a3aa1aec9cbc2f8210db4f49b340883b152def9d7c53e36b94bddad`. This is owner review of agent-proposed labels, not external expert adjudication.
