"""Ingestion: PDF -> page-accurate text -> section-anchored chunks with provenance.

Modules:
    extract_structure  heading/section skeleton of a textbook (structure only, ships in the repo)
    extract_text       page text for the retrieval corpus (book text: corpus/ only)
    repair_titles      rebuild titles the PDF's duplicate text layer fragmented
    chunk              section-anchored chunking with page provenance
    cli                the end-to-end driver
"""
