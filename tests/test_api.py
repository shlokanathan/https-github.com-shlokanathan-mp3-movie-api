import pytest

from src import MovieStorage
import main

ORIGINAL_TITLES = [
    "Movie A", "Movie B", "Movie B", "Movie C", "Movie D",
    "Movie D", "Movie E", "Movie F", "Movie G", "Movie H",
    "Movie I", "Movie J", "Movie K", "Movie L", "Movie M",
    "Movie N", "Movie O", "Movie P", "Movie Q", "Movie R",
]


def test_movies_persist(client, test_storage, uploaded_movies):
    other_storage = MovieStorage(test_storage.db_path)

    df = other_storage.get()
    assert other_storage.count_movies() == 20
    assert len(df) == 20
    assert list(df.columns) == ["title", "release_year", "rating", "genre"]
    assert list(df["title"]) == ORIGINAL_TITLES

    stored_ids = [
        record["id"] for record in other_storage.select_columns(["title"], limit=100)
    ]
    response = client.get("/movies", params={"limit": 100})
    assert response.status_code == 200
    api_ids = [record["id"] for record in response.json()["data"]]

    assert stored_ids == list(range(1, 21))
    assert api_ids == list(range(1, 21))


def test_cache_and_processing(client, uploaded_movies, processing_body):
    # Populate the cache for two different limits.
    first = client.get("/movies", params={"limit": 100})
    assert first.status_code == 200
    assert main.cache.get(100) == first.json()

    single = client.get("/movies", params={"limit": 1})
    assert single.status_code == 200
    assert main.cache.get(1) == single.json()

    # Repeating limit=100 returns the same response.
    repeat = client.get("/movies", params={"limit": 100})
    assert repeat.status_code == 200
    assert repeat.json() == first.json()

    # Processing replaces the data and clears every cached limit.
    response = client.post("/movies/process", json=processing_body)
    assert response.status_code == 200
    report = response.json()
    assert report["validation_rows_removed"] == 0
    assert report["cleaning_report"] == {
        "rows_before": 20,
        "rows_after": 16,
        "rows_removed": 4,
        "columns_before": 4,
        "columns_after": 4,
        "columns_removed": 0,
    }
    assert main.cache.get(100) is None
    assert main.cache.get(1) is None

    # The next retrieval reads the processed rows and caches them.
    response = client.get("/movies", params={"limit": 100})
    assert response.status_code == 200
    body = response.json()
    assert body["total_rows"] == 16
    titles = [record["title"] for record in body["data"]]
    assert titles == [f"Movie {letter}" for letter in "ABCDEFGHIJKLMNOP"]
    assert [record["id"] for record in body["data"]] == list(range(1, 17))
    assert main.cache.get(100) == body


def test_cache_hit_skips_database(client, uploaded_movies, monkeypatch):
    first = client.get("/movies", params={"limit": 100})
    assert first.status_code == 200
    expected = first.json()

    def fail_if_called(*args, **kwargs):
        pytest.fail("The database was queried on a cache hit")

    monkeypatch.setattr(main.storage, "select_columns", fail_if_called)
    monkeypatch.setattr(main.storage, "count_movies", fail_if_called)

    second = client.get("/movies", params={"limit": 100})
    assert second.status_code == 200
    assert second.json() == expected
