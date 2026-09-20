# Test fixtures

`synthetic_chunks.jsonl` is written by hand for this repository, in my own words, and is **not**
textbook text. No NCERT (or any other) book text is stored in the repository — see
`docs/adr/ADR-001-licensing-boundary.md` and the gitignore rules for `corpus/`.

It exists so retrieval, ranking, refusal and the API can be tested before (and without) anyone's
real book being ingested. It is deliberately small: six chunks, two synthetic subjects, three
sections, one `math_heavy` page.

| chunk id | subject | chapter | section | page | what it is for |
|---|---|---|---|---|---|
| `fixture-science-1-1.1-2` | fixture-science | 1 | 1.1 | 2 | balancing a reaction statement |
| `fixture-science-1-1.2-8` | fixture-science | 1 | 1.2 | 8 | silver chloride turning grey in light |
| `fixture-science-1-1.2-9` | fixture-science | 1 | 1.2 | 9 | the same section, a different topic (light-driven change in leaves) |
| `fixture-science-2-2.1-20` | fixture-science | 2 | 2.1 | 20–21 | home-made indicators; the only chunk containing "turmeric" |
| `fixture-maths-1-1.1-5` | fixture-maths | 1 | 1.1 | 5 | solutions of a quadratic statement, `math_heavy: true` |
| `fixture-maths-1-1.2-6` | fixture-maths | 1 | 1.2 | 6 | distance between two points |

Chunks 2 and 3 share a section and both mention light, which is what makes the ranking test
meaningful: a question about the grey silver salt must beat the leaf passage, not merely return
"something from §1.2".

The refusal tests use questions from outside this corpus entirely (Class 12 calculus), because the
refusal path has to be tested against material that genuinely is not there.
