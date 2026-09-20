# Demo corpus — sources and licences

This directory holds the demo corpus: openly licensed text the **public** deployment may
serve. It exists because the product's real corpus is a student's own textbook, which
cannot be redistributed (see `docs/adr/ADR-001-licensing-boundary.md`).

All text below is from Wikipedia, licensed **CC BY-SA 4.0**, retrieved 2026-09-20.
Attribution is repeated in each file's header. Re-fetch with `python scripts/fetch_demo_corpus.py`.

| file | article | licence | retrieved | chars | sha256 |
|---|---|---|---|---|---|
| `reflection-of-light.txt` | [Reflection (physics)](https://en.wikipedia.org/wiki/Reflection_%28physics%29) | CC BY-SA 4.0 | 2026-09-20 | 1739 | `089b7b20dd49637e` |
| `refraction.txt` | [Refraction](https://en.wikipedia.org/wiki/Refraction) | CC BY-SA 4.0 | 2026-09-20 | 4091 | `3bdd9a23838c6d88` |
| `electric-current.txt` | [Electric current](https://en.wikipedia.org/wiki/Electric_current) | CC BY-SA 4.0 | 2026-09-20 | 4058 | `b6d931b6ce505702` |
| `ohms-law.txt` | [Ohm's law](https://en.wikipedia.org/wiki/Ohm%27s_law) | CC BY-SA 4.0 | 2026-09-20 | 4039 | `da716fb83c928aae` |
| `magnetic-field.txt` | [Magnetic field](https://en.wikipedia.org/wiki/Magnetic_field) | CC BY-SA 4.0 | 2026-09-20 | 4034 | `0add876f378a01d2` |
| `chemical-reaction.txt` | [Chemical reaction](https://en.wikipedia.org/wiki/Chemical_reaction) | CC BY-SA 4.0 | 2026-09-20 | 2856 | `edc8b44f433b3a5a` |
| `acid-base-reaction.txt` | [Acid–base reaction](https://en.wikipedia.org/wiki/Acid%E2%80%93base_reaction) | CC BY-SA 4.0 | 2026-09-20 | 4185 | `affff3ea470dbb02` |
| `human-eye.txt` | [Human eye](https://en.wikipedia.org/wiki/Human_eye) | CC BY-SA 4.0 | 2026-09-20 | 3929 | `e7a71e3f3ef68d65` |
| `photoreceptor-cell.txt` | [Photoreceptor cell](https://en.wikipedia.org/wiki/Photoreceptor_cell) | CC BY-SA 4.0 | 2026-09-20 | 2348 | `1f5f583862ac3022` |
| `trigonometric-functions.txt` | [Trigonometric functions](https://en.wikipedia.org/wiki/Trigonometric_functions) | CC BY-SA 4.0 | 2026-09-20 | 4160 | `cc7fb549da88146b` |
| `quadratic-equation.txt` | [Quadratic equation](https://en.wikipedia.org/wiki/Quadratic_equation) | CC BY-SA 4.0 | 2026-09-20 | 3769 | `d1ec468237951db9` |
| `circle.txt` | [Circle](https://en.wikipedia.org/wiki/Circle) | CC BY-SA 4.0 | 2026-09-20 | 3739 | `1a30595abdf11294` |
| `similar-triangles.txt` | [Similarity (geometry)](https://en.wikipedia.org/wiki/Similarity_%28geometry%29) | CC BY-SA 4.0 | 2026-09-20 | 3999 | `04b1d17b0c11a154` |
| `probability-theory.txt` | [Probability theory](https://en.wikipedia.org/wiki/Probability_theory) | CC BY-SA 4.0 | 2026-09-20 | 3034 | `da57194cb0f7fc68` |

## What this corpus is not

- It is **not** NCERT textbook content, and it is not a substitute for the student's own
  copy of their book. Coverage is partial and the wording is not the syllabus wording.
- It is **not** aligned page-by-page to any book; the Class 10 hooks above are for orientation.
