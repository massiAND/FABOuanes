from __future__ import annotations


def test_admin_panel_renders(logged_client):
    response = logged_client.get("/admin")
    assert response.status_code == 200
    assert "Parametres" in response.text
    assert "Etat du systeme" in response.text


def test_admin_system_status_renders(logged_client):
    response = logged_client.get("/admin/system-status")
    assert response.status_code == 200
    assert "Diagnostic systeme" in response.text


def test_admin_system_status_export(logged_client):
    response = logged_client.get("/admin/system-status/export")
    assert response.status_code == 200
    assert "application/json" in response.headers["content-type"]
    assert "database" in response.json()
