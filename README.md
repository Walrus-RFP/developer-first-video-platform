## Setup

### Clone the Repository

```bash
git clone https://github.com/Walrus-RFP/developer-first-video-platform.git
cd developer-first-video-platform
```



### macOS / Linux Setup

Run the setup script:

```bash
./scripts/setup.sh
source venv/bin/activate
```

If you get a permission error:

```bash
chmod +x scripts/setup.sh
./scripts/setup.sh
```

If you see bad interpreter: /bin/bash^M, fix line endings:

```bash
sed -i '' 's/\r$//' scripts/setup.sh
```

---

### Windows Setup (PowerShell)

Create virtual environment:

```bash
python -m venv venv
venv\Scripts\activate
```

Install dependencies:

```bash
pip install -r control-plane\requirements.txt
pip install -r data-plane\requir
ements.txt
```

---

### Run Services

Open two terminals.

Run Control Plane

```bash
uvicorn control_plane.main:app --reload --port 8000
```
Run Data Plane

```bash
uvicorn data_plane.stream_server:app --reload --port 8001
```
