Setup:
./scripts/setup.sh
source venv/bin/activate

Run control-plane:
uvicorn control-plane.main:app --reload

Run data-plane:
uvicorn data-plane.stream_server:app --reload
