.PHONY: build up down logs test install clean

build:
	docker compose build

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f

test:
	pytest -v

install:
	pip install -r requirements.txt
	pip install -e .

clean:
	docker compose down --rmi local -v
