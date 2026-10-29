from app.domain.discovery import distance_km


def test_haversine_handles_antimeridian_and_antipodes():
    assert 22 < distance_km(0, 179.9, 0, -179.9) < 23
    assert 20000 < distance_km(0, 0, 0, 180) < 20020
    assert distance_km(90, 0, 90, 180) < 1e-8
