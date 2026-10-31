from app import app


def test_offline_page_contains_new_arcade_and_not_dino_game():
    response = app.test_client().get("/offline")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Snake and Flappy Bird offline arcade" in body
    assert "dino_game.html" not in body


def test_game_page_contains_snake_and_flappy_bird():
    body = app.test_client().get("/game").get_data(as_text=True)
    assert "Snake" in body
    assert "Flappy Bird" in body


def test_service_worker_precaches_game():
    body = app.test_client().get("/sw.js").get_data(as_text=True)
    assert "'/game'" in body
