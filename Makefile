.PHONY: db-up db-down backend frontend bridge dev

# Start PostgreSQL in Docker
db-up:
	docker compose up -d
	@echo "Waiting for PostgreSQL..."
	@until docker compose exec db pg_isready -U pedalmind > /dev/null 2>&1; do sleep 1; done
	@echo "PostgreSQL ready on localhost:5432"

# Stop PostgreSQL
db-down:
	docker compose down

# Install backend deps and start API server
backend:
	@test -f backend/.env || cp backend/.env.example backend/.env
	cd backend && pip install -r requirements.txt -q && python run.py

# Install frontend deps and start dev server
frontend:
	cd frontend && npm install --legacy-peer-deps -q && npm run dev

# Run the bridge to import historical activities
# Usage: make bridge TOKEN=<jwt_token>
bridge:
	cd backend && python -c "import sys; sys.path.insert(0,'..'); exec(open('../garmin_sync/bridge.py').read())" $(TOKEN)

# Start everything for development (db + backend + frontend)
dev: db-up
	@test -f backend/.env || cp backend/.env.example backend/.env
	@echo "Starting backend and frontend..."
	@(cd backend && pip install -r requirements.txt -q && python run.py) & \
	(cd frontend && npm install --legacy-peer-deps -q && npm run dev) & \
	wait
