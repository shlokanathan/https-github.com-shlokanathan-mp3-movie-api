# MP3 Movie API

This FastAPI application stores one movie collection in SQLite, lets clients filter it with SQL, cleans it with the MP1 data pipeline, and caches repeated retrievals. `main.py` defines the endpoints, `src/database.py` creates connections and the `movies` table, and `src/storage.py` holds `MovieStorage`, which saves, reads, counts, and queries movies using SQL. `src/models.py` defines the request and response models, `src/middleware.py` logs each request with an ID and timing, and `data_pipeline/` contains the reused validation and cleaning functions. `POST /upload` checks that a CSV has exactly the columns `title`, `release_year`, `rating`, and `genre` and at least one row, then replaces the stored collection in a single transaction. `GET /movies` returns up to `limit` rows plus the total count, and `GET /movies/search` filters by minimum rating and sorts by rating using SQL. `POST /movies/process` loads the stored movies, validates and cleans them, and saves the result back to SQLite, so the data survives a server restart. `src/cache.py` provides `MovieCache`, which keeps each `GET /movies` response in FakeRedis for 90 seconds under a key such as `movies:limit:100`. After any successful upload or processing save, the whole cache is cleared, so the next retrieval reads fresh data from the database.

## Commands

Start the API from the repository root:

```bash
python -m uvicorn main:app --reload
```

Then open http://127.0.0.1:8000/docs.

Run the tests:

```bash
python -m pytest tests -v
```

## Sample Processing Request

After uploading `fixtures/sample_movies.csv`, send `POST /movies/process` with:

```json
{
  "validation": {
    "required_columns": ["title", "release_year", "rating", "genre"],
    "numeric_columns": ["release_year", "rating"]
  },
  "processing": {
    "remove_duplicates": true,
    "missing": {"enabled": true, "axis": "rows"},
    "outliers": {
      "enabled": true,
      "columns": ["rating"],
      "method": "iqr",
      "threshold": 1.5
    }
  }
}
```

Expected result:

```json
{
  "validation_rows_removed": 0,
  "cleaning_report": {
    "rows_before": 20,
    "rows_after": 16,
    "rows_removed": 4,
    "columns_before": 4,
    "columns_after": 4,
    "columns_removed": 0
  }
}
```

The duplicate rows for Movie B and Movie D and the low-rating outliers Movie Q and Movie R are removed, leaving 16 movies.
