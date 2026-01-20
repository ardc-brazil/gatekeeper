# RFC 001: Dataset Pagination and Full-Text Search

| Status | Implemented |
|--------|-------------|
| Author | DataMap Team |
| Created | 2026-01-19 |
| Updated | 2026-01-19 |

## Summary

This RFC describes the implementation of server-side pagination and PostgreSQL full-text search for the dataset listing endpoint. Previously, the API returned all datasets in a single response, which caused performance issues as the dataset count grew. This change introduces paginated responses with relevance-based search ranking.

## Motivation

### Problem Statement

1. **Performance**: The `/datasets` endpoint returned ALL matching datasets in a single transaction, causing slow response times and high memory usage as the dataset count grew (1,000-10,000 datasets).

2. **Poor Search Quality**: The previous implementation used `ILIKE` on JSONB cast to string, which:
   - Had no relevance ranking
   - Was slow on large datasets
   - Didn't handle accented characters well (common in Portuguese)

3. **No Pagination**: The frontend loaded all datasets into memory, making the UI sluggish.

### Goals

- Implement server-side pagination with configurable page sizes
- Add PostgreSQL full-text search with relevance ranking
- Support accent-insensitive search (e.g., "Sao" matches "São")
- Maintain backward compatibility with existing API consumers

## Technical Design

### Database Changes

#### New Column

Added `search_vector` column to the `datasets` table to store pre-computed searchable text:

```sql
ALTER TABLE datasets ADD COLUMN search_vector TEXT;
```

#### PostgreSQL Extensions

Enabled the `unaccent` extension for accent-insensitive search:

```sql
CREATE EXTENSION IF NOT EXISTS unaccent;
```

#### GIN Index

Created a GIN index for fast full-text search:

```sql
CREATE INDEX idx_datasets_search_vector
ON datasets USING GIN(to_tsvector('simple', coalesce(search_vector, '')));
```

#### Trigger for Auto-Update

A database trigger automatically updates `search_vector` on INSERT/UPDATE:

```sql
CREATE OR REPLACE FUNCTION datasets_search_vector_update() RETURNS trigger AS $$
BEGIN
    NEW.search_vector := unaccent(
        coalesce(NEW.name, '') || ' ' ||
        coalesce(NEW.data->>'category', '') || ' ' ||
        coalesce(NEW.data->>'institution', '') || ' ' ||
        coalesce(NEW.data->>'description', '')
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER datasets_search_vector_trigger
BEFORE INSERT OR UPDATE ON datasets
FOR EACH ROW EXECUTE FUNCTION datasets_search_vector_update();
```

### API Changes

#### Request Parameters

New query parameters added to `GET /datasets`:

| Parameter | Type | Default | Max | Description |
|-----------|------|---------|-----|-------------|
| `page` | int | 1 | - | Page number (1-indexed) |
| `page_size` | int | 10 | 20 | Items per page |

#### Response Schema

The `PagedDatasetGetResponse` now includes pagination metadata:

```json
{
  "content": [...],
  "size": 10,
  "page": 1,
  "page_size": 10,
  "total_count": 150,
  "total_pages": 15,
  "has_next": true,
  "has_previous": false
}
```

| Field | Type | Description |
|-------|------|-------------|
| `content` | array | Dataset objects for current page |
| `size` | int | **Deprecated** - Use `total_count` |
| `page` | int | Current page number |
| `page_size` | int | Items per page |
| `total_count` | int | Total matching datasets |
| `total_pages` | int | Total number of pages |
| `has_next` | bool | Whether next page exists |
| `has_previous` | bool | Whether previous page exists |

### Search Behavior

#### With Search Term (`full_text` parameter)

When a search term is provided:
1. Results are filtered using PostgreSQL full-text search (`@@` operator)
2. Results are ordered by **relevance** (`ts_rank`), then by `created_at DESC`
3. Accent-insensitive matching via `unaccent()` function

Example: Searching "Sao Paulo atmosferico" will match "São Paulo Atmosférico"

#### Without Search Term

When no search term is provided:
- Results are ordered by `created_at DESC` (newest first)

### Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Controller    │────▶│    Service      │────▶│   Repository    │
│                 │     │                 │     │                 │
│ - Validates     │     │ - Adapts        │     │ - FTS query     │
│   page/size     │     │   DB models     │     │ - Pagination    │
│ - Returns       │     │   to domain     │     │ - Relevance     │
│   response      │     │                 │     │   ranking       │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                                                        │
                                                        ▼
                                               ┌─────────────────┐
                                               │   PostgreSQL    │
                                               │                 │
                                               │ - search_vector │
                                               │ - GIN index     │
                                               │ - unaccent()    │
                                               └─────────────────┘
```

### Data Flow

1. **Request**: `GET /datasets?full_text=atmosferico&page=2&page_size=10`

2. **Controller**: Validates pagination params, builds `DatasetQuery`

3. **Service**: Calls repository, adapts results to domain models

4. **Repository**:
   ```python
   # Build tsquery from search term
   search_term = func.plainto_tsquery('simple', func.unaccent('atmosferico'))

   # Filter by full-text match
   query = query.filter(search_vector.op('@@')(search_term))

   # Order by relevance
   query = query.order_by(func.ts_rank(search_vector, search_term).desc())

   # Get total count
   total_count = query.count()

   # Apply pagination
   datasets = query.offset(10).limit(10).all()
   ```

5. **Response**: Returns page 2 with 10 items, relevance-sorted

## Configuration

### Text Search Configuration

Using PostgreSQL's `'simple'` configuration instead of language-specific (e.g., `'english'`, `'portuguese'`):

| Configuration | Stemming | Stop Words | Use Case |
|---------------|----------|------------|----------|
| `'simple'` | No | No | Multi-language, exact matching |
| `'english'` | Yes | Yes | English-only content |
| `'portuguese'` | Yes | Yes | Portuguese-only content |

**Rationale**: Dataset names and metadata can be in any language (primarily Portuguese and English), so `'simple'` provides consistent behavior across languages.

### Searchable Fields

The following fields are indexed in `search_vector`:

| Field | Source |
|-------|--------|
| Dataset name | `datasets.name` |
| Category | `datasets.data->>'category'` |
| Institution | `datasets.data->>'institution'` |
| Description | `datasets.data->>'description'` |

### Adding New Fields

To add new fields to the search index:

1. Update the trigger function:
   ```sql
   CREATE OR REPLACE FUNCTION datasets_search_vector_update() RETURNS trigger AS $$
   BEGIN
       NEW.search_vector := unaccent(
           coalesce(NEW.name, '') || ' ' ||
           coalesce(NEW.data->>'category', '') || ' ' ||
           coalesce(NEW.data->>'institution', '') || ' ' ||
           coalesce(NEW.data->>'description', '') || ' ' ||
           coalesce(NEW.data->>'tags', '')  -- NEW FIELD
       );
       RETURN NEW;
   END;
   $$ LANGUAGE plpgsql;
   ```

2. Re-populate existing records:
   ```sql
   UPDATE datasets SET name = name WHERE name IS NOT NULL;
   ```

## Frontend Integration

### Page Size Options

The frontend provides a dropdown with page size options:

| Option | Description |
|--------|-------------|
| 10 | Default |
| 15 | Medium |
| 20 | Maximum |

### Pagination Behavior

- Changing filters/search resets to page 1
- Changing page size resets to page 1
- Page numbers show smart ellipsis (e.g., `1 ... 4 5 6 ... 10`)

## Migration

### Migration File

`migrations/versions/2026_01_15_1200-add_fulltext_search_to_datasets.py`

### Deployment Steps

1. Run migration: `make ENV_FILE_PATH=<env>.env db-upgrade`
2. The migration automatically:
   - Creates the `unaccent` extension
   - Adds the `search_vector` column
   - Creates the GIN index
   - Creates the trigger
   - Populates `search_vector` for existing records

### Rollback

```bash
make ENV_FILE_PATH=<env>.env db-downgrade
```

This will:
- Drop the trigger
- Drop the trigger function
- Drop the GIN index
- Drop the `search_vector` column

**Note**: The `unaccent` extension is NOT dropped during rollback as other database objects may depend on it.

## Performance Considerations

### Query Performance

| Operation | Before | After |
|-----------|--------|-------|
| List all (1000 datasets) | ~2s | ~100ms (page of 10) |
| Search with ILIKE | O(n) full scan | O(log n) with GIN index |
| Memory usage | All in memory | Page-sized chunks |

### Index Size

The GIN index adds approximately 10-20% overhead to table size, but provides significant query performance improvements.

### Count Query

The `total_count` requires a separate count query. For very large datasets (100k+), consider:
- Caching the count
- Using approximate counts
- Removing count for infinite scroll UIs

## Backward Compatibility

### Deprecated Fields

The `size` field in the response is deprecated but maintained for backward compatibility:

```json
{
  "size": 10,        // Deprecated: number of items in current page
  "total_count": 150 // Use this instead: total matching datasets
}
```

### Default Behavior

Without pagination parameters, the API returns:
- `page=1`
- `page_size=10`

Existing clients that don't send pagination params will receive the first 10 results instead of all results.

## Alternatives Considered

### 1. Elasticsearch

**Pros**: Best search quality, faceted search, suggestions
**Cons**: New infrastructure, data sync complexity, overkill for <100k records

**Decision**: PostgreSQL FTS is sufficient for current scale and avoids infrastructure complexity.

### 2. pg_trgm Extension

**Pros**: Fuzzy matching, typo tolerance
**Cons**: Less effective for phrase search, higher index size

**Decision**: May add later if fuzzy search is needed.

### 3. Cursor-based Pagination

**Pros**: Better for real-time data, no page drift
**Cons**: More complex implementation, harder for page jumps

**Decision**: Offset pagination chosen as users requested page numbers UI.

## Future Improvements

1. **Fuzzy Search**: Add `pg_trgm` extension for typo-tolerant search
2. **Search Highlighting**: Return matched snippets with highlights
3. **Faceted Search**: Return filter counts (e.g., "AEROSOLS (15)")
4. **Search Analytics**: Track popular search terms
5. **Synonyms**: Add synonym support (e.g., "temp" → "temperature")

## References

- [PostgreSQL Full-Text Search Documentation](https://www.postgresql.org/docs/current/textsearch.html)
- [PostgreSQL unaccent Extension](https://www.postgresql.org/docs/current/unaccent.html)
- [GIN Index Documentation](https://www.postgresql.org/docs/current/gin.html)
