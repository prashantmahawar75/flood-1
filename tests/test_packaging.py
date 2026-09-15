from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_runtime_packaging_files_exist_and_point_to_fastapi_app():
    required = ["requirements.txt", "Dockerfile", "docker-compose.yml", "run.sh", "run.bat", ".env.example", "README_FULLSTACK.md"]
    for name in required:
        assert (ROOT / name).exists(), f"missing {name}"
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "backend.app.main:app" in dockerfile
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    for package in ["fastapi", "uvicorn", "scikit-learn", "httpx", "joblib"]:
        assert package in requirements.lower()


def test_frontend_route_layer_uses_layer_group_for_multiple_polylines():
    js = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
    assert "L.layerGroup()" in js


def test_judge_launchers_start_fullstack_backend_not_old_static_dashboard():
    for name in ["open_dashboard.bat", "ye_kholna_hai_judges_ke_saamne.bat", "ye kholna hai judges ke saamne.sh", "ye kholna hai judges ke saamne.command"]:
        text = (ROOT / name).read_text(encoding="utf-8")
        assert "backend.app.main:app" in text
        assert "dashboard\\pravahai_dashboard.html" not in text
        assert "dashboard/pravahai_dashboard.html" not in text
