from __future__ import annotations


def test_sales_page_renders(logged_client):
    response = logged_client.get("/operations?type=sale")
    assert response.status_code == 200
    assert "Operations" in response.text
    assert "Ventes" in response.text


def test_sale_form_renders(logged_client):
    response = logged_client.get("/operations/sales/new")
    assert response.status_code == 200
    assert "Lignes de vente" in response.text or "Ajouter une ligne" in response.text
