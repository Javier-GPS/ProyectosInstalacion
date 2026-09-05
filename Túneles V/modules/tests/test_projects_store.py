import os


def test_project_store_round_trip(tmp_path, monkeypatch):
    monkeypatch.setenv("TUNNEL_PROJECTS_DB", os.fspath(tmp_path / "projects.sqlite3"))
    import modules.projects_store as store

    store.DB_PATH = tmp_path / "projects.sqlite3"
    created = store.create_project({"project_name": "Túnel de prueba", "client": "SALVI"})
    assert created["id"]
    assert created["project_name"] == "Túnel de prueba"
    assert store.list_projects()[0]["client"] == "SALVI"

    updated = store.update_project(created["id"], {"project_name": "Túnel actualizado"})
    assert updated["project_name"] == "Túnel actualizado"
    assert store.delete_project(created["id"])
    assert store.list_projects() == []

