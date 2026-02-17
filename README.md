## Setup
./scripts/setup.sh
source venv/bin/activate

## Run Control Plane
uvicorn control-plane.main:app --reload

## Run Data Plane
uvicorn data-plane.stream_server:app --reload
