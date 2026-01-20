# Gatekeeper Documentation

This directory contains technical documentation for the Gatekeeper service.

## Structure

```
docs/
├── README.md           # This file
└── rfcs/               # Request for Comments (design documents)
    └── 001-*.md        # RFC documents
```

## RFCs

RFCs (Request for Comments) document significant architectural decisions and feature implementations.

| RFC | Title | Status |
|-----|-------|--------|
| [001](rfcs/001-dataset-pagination-fulltext-search.md) | Dataset Pagination and Full-Text Search | Implemented |

## Contributing

When adding a new RFC:

1. Create a new file in `docs/rfcs/` with the format `NNN-short-description.md`
2. Use the next available number
3. Update this README with the new RFC entry
