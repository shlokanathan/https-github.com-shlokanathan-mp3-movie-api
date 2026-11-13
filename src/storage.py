# src/storage.py
import logging
import sqlite3

import pandas as pd

from .database import get_connection, initialize_database

logger = logging.getLogger(__name__)
MOVIE_COLUMNS = ["title", "release_year", "rating", "genre"]


def _to_sql_value(value):
    """Convert a pandas/NumPy value to a Python value SQLite can store."""
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        return value.item()
    return value


class MovieStorage:
    def __init__(self, db_path="data/movies.db"):
        self.db_path = db_path
        initialize_database(self.db_path)

    def save(self, df):
        """Replace all movie rows in one transaction."""
        movies = df.reindex(columns=MOVIE_COLUMNS)
        rows = [
            tuple(_to_sql_value(value) for value in row)
            for row in movies.itertuples(index=False, name=None)
        ]

        connection = get_connection(self.db_path)
        try:
            connection.execute("DELETE FROM movies")
            connection.executemany(
                "INSERT INTO movies (title, release_year, rating, genre) "
                "VALUES (?, ?, ?, ?)",
                rows,
            )
            connection.commit()
        except sqlite3.Error as error:
            connection.rollback()
            logger.error(f"Failed to store movies in SQLite: {error}")
            raise
        finally:
            connection.close()

        logger.debug(f"Stored movies in SQLite: rows={len(rows)}")

    def get(self):
        """Return the four movie columns as a DataFrame, ordered by id."""
        connection = get_connection(self.db_path)
        try:
            rows = connection.execute(
                "SELECT title, release_year, rating, genre FROM movies ORDER BY id"
            ).fetchall()
        finally:
            connection.close()

        df = pd.DataFrame([tuple(row) for row in rows], columns=MOVIE_COLUMNS)
        logger.debug(f"Retrieved movies from SQLite: rows={len(df)}")
        return df

    def select_columns(self, columns, limit=5):
        """Return id plus the requested movie columns, ordered by id."""
        if not columns:
            logger.error("Select at least one column")
            raise ValueError("Select at least one column")

        for column in columns:
            if column not in MOVIE_COLUMNS:
                logger.error(f"Unsupported column: {column}")
                raise ValueError(f"Unsupported column: {column}")

        selected_columns = ", ".join(["id"] + columns)
        connection = get_connection(self.db_path)
        try:
            rows = connection.execute(
                f"SELECT {selected_columns} FROM movies ORDER BY id LIMIT ?",
                (limit,),
            ).fetchall()
            records = [dict(row) for row in rows]
            logger.debug(
                f"Selected movie columns: columns={columns}, rows={len(records)}"
            )
            return records
        finally:
            connection.close()

    def count_movies(self):
        """Return the number of stored movies using SQL COUNT(*)."""
        connection = get_connection(self.db_path)
        try:
            count = connection.execute("SELECT COUNT(*) FROM movies").fetchone()[0]
            logger.debug(f"Counted movies: total={count}")
            return count
        finally:
            connection.close()

    def query_movies(self, columns, min_rating, limit):
        """Return selected fields from matching movies using SQL."""
        if not columns:
            logger.error("Select at least one column")
            raise ValueError("Select at least one column")

        for column in columns:
            if column not in MOVIE_COLUMNS:
                logger.error(f"Unsupported column: {column}")
                raise ValueError(f"Unsupported column: {column}")

        selected_columns = ", ".join(["id"] + columns)
        connection = get_connection(self.db_path)
        try:
            rows = connection.execute(
                f"SELECT {selected_columns} FROM movies "
                "WHERE rating >= ? "
                "ORDER BY rating DESC, id ASC "
                "LIMIT ?",
                (min_rating, limit),
            ).fetchall()
            records = [dict(row) for row in rows]
            logger.debug(
                f"Queried movies: columns={columns}, rows={len(records)}"
            )
            return records
        finally:
            connection.close()
