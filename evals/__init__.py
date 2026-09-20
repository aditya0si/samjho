"""The samjho evaluation harness: golden question sets, a refusal set, metrics and the gate.

Owned by the eval builder (see docs/CONTRACTS.md §7). Nothing here contains textbook text: the
golden questions are written from the CBSE syllabus structure in ``data/syllabus/class10.json``,
and the corpus itself lives in the gitignored ``corpus/`` directory.

Entry point: ``python -m evals.run_eval`` (see evals/README.md).
"""
