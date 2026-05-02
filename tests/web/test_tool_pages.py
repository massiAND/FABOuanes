from __future__ import annotations

from tests.conftest import extract_csrf


def test_notes_page_renders(logged_client):
    response = logged_client.get("/notes")
    assert response.status_code == 200
    assert "Bloc-note" in response.text


def test_notes_page_can_save_content(logged_client):
    response = logged_client.get("/notes")
    csrf_token = extract_csrf(response.text)
    post = logged_client.post(
        "/notes",
        data={"csrf_token": csrf_token, "action": "save", "content": "Note FastAPI"},
        follow_redirects=False,
    )
    assert post.status_code == 303
    rendered = logged_client.get("/notes")
    assert "Note FastAPI" in rendered.text


def test_pdf_reader_page_renders(logged_client):
    response = logged_client.get("/pdf-reader")
    assert response.status_code == 200
    assert "Lecteur PDF" in response.text


def test_service_worker_route_serves_javascript(client):
    response = client.get("/sw.js")
    assert response.status_code == 200
    assert "javascript" in response.headers.get("content-type", "")
