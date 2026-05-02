from __future__ import annotations


def test_client_history_print_renders(logged_client, first_client_id):
    response = logged_client.get(f"/contacts/clients/{first_client_id}/print-history")
    assert response.status_code == 200
    assert "Historique client" in response.text


def test_purchase_print_page_renders(logged_client, first_purchase_id):
    response = logged_client.get(f"/print/purchase/{first_purchase_id}")
    assert response.status_code == 200
    assert "ACH-000001" in response.text
    assert "0771214948 / 0553183302" in response.text
    assert "Imprimer la page" in response.text


def test_purchase_print_pdf_downloads(logged_client, first_purchase_id):
    response = logged_client.get(f"/print/purchase/{first_purchase_id}?format=pdf")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")
