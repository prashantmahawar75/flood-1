from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"


def test_integrated_frontend_has_required_workflow_controls():
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    for required_id in [
        'id="map"',
        'id="stationSelect"',
        'id="scoreRiskBtn"',
        'id="loadFacilitiesBtn"',
        'id="routeBtn"',
        'id="routeSummary"',
        'id="riskPointsList"',
    ]:
        assert required_id in html
    assert "Leaflet" in html or "leaflet" in html


def test_frontend_calls_backend_ml_facility_and_route_apis():
    js = (FRONTEND / "app.js").read_text(encoding="utf-8")
    assert "/api/risk/predict" in js
    assert "/api/facilities/nearby" in js
    assert "/api/route/safest" in js
    assert "navigator.geolocation" in js
    assert "L.polyline" in js


def test_frontend_escapes_untrusted_osm_labels_before_html_insertion():
    js = (FRONTEND / "app.js").read_text(encoding="utf-8")
    assert "function escapeHtml" in js
    assert "escapeHtml(facility.name)" in js


def test_frontend_normalizes_leaflet_lng_and_rejects_non_finite_coordinates():
    js = (FRONTEND / "app.js").read_text(encoding="utf-8")
    assert "function normalizePoint" in js
    assert "point.lng" in js
    assert "Number.isFinite" in js
    assert "Invalid map coordinates" in js


def test_frontend_explains_degraded_routing_mode_and_provider():
    js = (FRONTEND / "app.js").read_text(encoding="utf-8")
    assert "risk-aware-osrm-alternatives-fallback" in js
    assert "routingProvider" in js
