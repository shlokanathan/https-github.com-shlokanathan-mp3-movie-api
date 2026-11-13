import io
import logging
from pathlib import Path
import pandas as pd
from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from data_pipeline import create_cleaning_report, process_data, validate_dataframe
from src import (
    HealthResponse,
    MovieCache,
    MovieStorage,
    MovieUploadInfo,
    MovieDataResponse,
    MovieProcessingReport,
    ProcessConfig,
    log_requests,
    setup_logging,
)
from src.storage import MOVIE_COLUMNS

setup_logging(verbose=True)
logger = logging.getLogger(__name__)

app = FastAPI(title="Movie Database API", version="1.0.0")
app.middleware("http")(log_requests)
storage = MovieStorage()
cache = MovieCache()

@app.get("/health", response_model=HealthResponse)
def health_check():
    """Return the application status and version."""
    return {"status": "ok", "version": app.version}

@app.post("/upload", response_model=MovieUploadInfo)
async def upload_movies(file: UploadFile = File(...)):
    """Read a CSV upload and replace the stored movie collection."""
    suffix = Path(file.filename or "").suffix.lower()
    if suffix != ".csv":
        logger.warning(f"Unsupported file format: {suffix or '(none)'}")
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file format '{suffix or '(none)'}'. Please upload a .csv file.",
        )

    contents = await file.read()
    try:
        df = pd.read_csv(io.BytesIO(contents))
    except pd.errors.EmptyDataError:
        logger.warning(f"Empty CSV upload: {file.filename}")
        raise HTTPException(status_code=400, detail="The uploaded CSV file is empty.")
    except pd.errors.ParserError as e:
        logger.warning(f"Could not parse CSV {file.filename}: {e}")
        raise HTTPException(status_code=400, detail="The uploaded file could not be parsed as CSV.")
    except UnicodeDecodeError:
        logger.warning(f"Could not decode CSV {file.filename}")
        raise HTTPException(status_code=400, detail="The uploaded file is not valid UTF-8 text.")

    if sorted(df.columns) != sorted(MOVIE_COLUMNS):
        logger.warning(f"Unexpected columns in {file.filename}: {list(df.columns)}")
        raise HTTPException(
            status_code=400,
            detail=f"The CSV must contain exactly these columns: {', '.join(MOVIE_COLUMNS)}",
        )

    if df.empty:
        logger.warning(f"No data rows in {file.filename}")
        raise HTTPException(status_code=400, detail="The uploaded CSV has no data rows.")

    df = df[MOVIE_COLUMNS]

    storage.save(df)
    cache.invalidate()
    logger.info(f"Uploaded movies: filename={file.filename}, rows={len(df)}")
    return {
        "filename": file.filename,
        "rows": len(df),
        "columns": len(df.columns),
        "column_names": list(df.columns),
    }

@app.get("/movies", response_model=MovieDataResponse)
def get_movies(limit: int = Query(default=100, ge=1)):
    """Return up to limit stored movies and the total number of movies."""
    cached = cache.get(limit)
    if cached is not None:
        logger.info(f"Cache hit for movies: limit={limit}")
        return cached

    records = storage.select_columns(MOVIE_COLUMNS, limit=limit)
    total_rows = storage.count_movies()
    response = {"data": records, "total_rows": total_rows}

    cache.set(limit, response)
    logger.info(f"Retrieved movies: returned_rows={len(records)}")
    return response

@app.get("/movies/search", response_model=list[dict])
def query_movies(
    columns: list[str] = Query(default=["title"]),
    min_rating: float = Query(default=0, ge=0, le=10),
    limit: int = Query(default=100, ge=1)
):
    """Return selected fields from movies with at least min_rating."""
    try:
        records = storage.query_movies(columns, min_rating, limit)
    except ValueError as error:
        logger.warning(f"Invalid movie search: {error}")
        raise HTTPException(status_code=400, detail=str(error))

    logger.info(
        f"Queried movies: columns={columns}, min_rating={min_rating}, "
        f"returned_rows={len(records)}"
    )
    return records

@app.post("/movies/process", response_model=MovieProcessingReport)
def process_movies(config: ProcessConfig):
    """Validate and process the stored movies using MP1 functions."""
    df = storage.get()
    if df.empty:
        logger.warning("No movies to process")
        raise HTTPException(status_code=400, detail="No movies are stored. Upload a CSV first.")

    config_dict = config.model_dump()
    validation = config_dict["validation"]

    missing_numeric = [col for col in validation["numeric_columns"] if col not in df.columns]
    if missing_numeric:
        logger.warning(f"Numeric columns not found: {missing_numeric}")
        raise HTTPException(
            status_code=400,
            detail=f"Numeric columns not found: {', '.join(missing_numeric)}",
        )

    try:
        validated = validate_dataframe(
            df,
            required_columns=validation["required_columns"],
            numeric_columns=validation["numeric_columns"],
        )
        validation_rows_removed = len(df) - len(validated)
        logger.info(f"Validated movies: rows_removed={validation_rows_removed}")

        validated_copy = validated.copy()
        processed = process_data(validated, config_dict)
        cleaning_report = create_cleaning_report(validated_copy, processed)
    except ValueError as error:
        logger.warning(f"Processing failed: {error}")
        raise HTTPException(status_code=400, detail=str(error))

    storage.save(processed)
    cache.invalidate()
    logger.info(
        f"Processed movies: validation_removed={validation_rows_removed}, "
        f"rows_before={cleaning_report['rows_before']}, rows_after={cleaning_report['rows_after']}"
    )
    return {
        "validation_rows_removed": validation_rows_removed,
        "cleaning_report": cleaning_report,
    }
