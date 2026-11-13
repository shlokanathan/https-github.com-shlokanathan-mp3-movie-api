def test_upload_csv(client, sample_csv_bytes):
    response = client.post(
        "/upload",
        files={"file": ("sample_movies.csv", sample_csv_bytes, "text/csv")}
    )

    assert response.status_code == 200
    assert response.json() == {
        "filename": "sample_movies.csv",
        "rows": 20,
        "columns": 4,
        "column_names": ["title", "release_year", "rating", "genre"],
    }


def test_retrieve_movies(client, uploaded_movies):
    response = client.get("/movies", params={"limit": 2})

    assert response.status_code == 200
    assert response.json() == {
        "data": [
            {"id": 1, "title": "Movie A", "release_year": 2020, "rating": 8.0, "genre": "Drama"},
            {"id": 2, "title": "Movie B", "release_year": 2021, "rating": 8.5, "genre": "Comedy"},
        ],
        "total_rows": 20,
    }


def test_search_movies(client, uploaded_movies):
    response = client.get("/movies/search", params={"min_rating": 8.5, "limit": 2})

    assert response.status_code == 200
    assert response.json() == [
        {"id": 4, "title": "Movie C"},
        {"id": 2, "title": "Movie B"},
    ]

    response = client.get(
        "/movies/search",
        params={"columns": ["title", "rating"], "min_rating": 8.5, "limit": 2},
    )

    assert response.status_code == 200
    assert response.json() == [
        {"id": 4, "title": "Movie C", "rating": 9.0},
        {"id": 2, "title": "Movie B", "rating": 8.5},
    ]


def test_upload_replaces_collection(client, uploaded_movies, sample_csv_bytes):
    response = client.post(
        "/upload",
        files={"file": ("sample_movies.csv", sample_csv_bytes, "text/csv")}
    )

    assert response.status_code == 200
    assert client.get("/movies").json()["total_rows"] == 20


def test_process_and_retrieve(client, uploaded_movies, processing_body):
    response = client.post("/movies/process", json=processing_body)

    assert response.status_code == 200
    report = response.json()
    assert report["validation_rows_removed"] == 0
    assert report["cleaning_report"]["rows_before"] == 20
    assert report["cleaning_report"]["rows_after"] == 16

    response = client.get("/movies")

    assert response.status_code == 200
    body = response.json()
    assert body["total_rows"] == 16
    assert [record["id"] for record in body["data"]] == list(range(1, 17))


def test_unsupported_file_extension(client):
    response = client.post(
        "/upload",
        files={"file": ("movies.txt", b"hello", "text/plain")}
    )

    assert response.status_code == 400
    assert client.get("/health").status_code == 200
