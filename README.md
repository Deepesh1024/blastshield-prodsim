# BlastShield — Production Failure Simulator

> **AWS AI for Bharat Hackathon** • Simulates real production failures on your Python code using deterministic drills + Amazon Bedrock (Claude 3.5 Sonnet).

---

## 🏗️ Architecture

```
POST /scan (code or zip)
     │
     ├── extract.py     → parse files, detect endpoints
     ├── drills.py      → concurrency / latency / chaos
     ├── edge_cases.py  → 10 extreme input tests per endpoint
     ├── curl_runner.py → 20-40 concurrent simulated requests
     │
     └── bedrock.py     → ONE Claude 3.5 Sonnet call
                           → outage story, timeline, patches
```

## 🚀 Local Development

### Prerequisites
- Python 3.11+
- AWS credentials configured (for Bedrock) — optional, falls back gracefully

### Setup
```bash
cd blastshield-agent
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Run locally
```bash
uvicorn app.main:app --reload --port 8000
```

### Test with raw code
```bash
curl -X POST http://localhost:8000/scan \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d 'code=from+fastapi+import+FastAPI%0Aapp+%3D+FastAPI()%0A%40app.get("/health")%0Adef+health():%0A++++return+{"status":+"ok"}'
```

### Test with zip upload
```bash
# Create example zip first
cd examples/sample_project && zip -r ../sample_project.zip *.py && cd ../..

curl -X POST http://localhost:8000/scan \
  -F "file=@examples/sample_project.zip"
```

### Interactive docs
Open [http://localhost:8000/docs](http://localhost:8000/docs) for the Swagger UI.

---

## ☁️ Deploy to AWS Lambda

### Prerequisites
- Node.js 18+ (for Serverless Framework)
- AWS credentials with Lambda + API Gateway + Bedrock access

### Deploy
```bash
npm install -g serverless
npm install --save-dev serverless-python-requirements
sls deploy
```

### Test deployed endpoint
```bash
# Replace with your actual API Gateway URL
API_URL="https://xxxxxxxx.execute-api.us-east-1.amazonaws.com"

curl -X POST "$API_URL/scan" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d 'code=from+fastapi+import+FastAPI%0Aapp+%3D+FastAPI()%0A%40app.post("/create")%0Adef+create_order(data:+dict):%0A++++orders.append(data)%0A++++return+{"id":+len(orders)}'

curl -X POST "$API_URL/scan" \
  -F "file=@examples/sample_project.zip"
```

---

## 📋 API Contract

### `POST /scan`

**Input** (one of):
- Form field: `code=<python source>`
- Multipart file: `file=<zipfile>`

**Response**:
```json
{
  "overall_score": 23,
  "files": [{"file": "app.py", "lines": 45}],
  "endpoints": [{"file": "app.py", "method": "POST", "path": "/create", "function": "create_order"}],
  "drills": {
    "concurrency": [...],
    "latency": [...],
    "chaos": [...]
  },
  "edge_cases": [...],
  "curl_results": [...],
  "bedrock_story": {
    "timeline": "...",
    "propagation": "...",
    "outage_scenario": "...",
    "blast_radius": "...",
    "explanation": "...",
    "patches": "..."
  }
}
```

---

## 📁 File Structure

```
app/
  main.py              # FastAPI app factory
  api/
    scan.py            # POST /scan endpoint
  core/
    extract.py         # Unpack zip + extract code + detect endpoints
    drills.py          # Concurrency, latency, chaos drills
    edge_cases.py      # Input stress tests (10 cases per endpoint)
    curl_runner.py     # Simulated concurrent endpoint tests
  ai/
    bedrock.py         # boto3 Bedrock client + retry logic
    prompt.py          # Build Bedrock JSON prompt
handler.py             # Mangum Lambda wrapper
serverless.yml         # Serverless Framework config
requirements.txt       # Python dependencies
```

---

## 🛡️ Safety

- **Fallback**: If Bedrock fails → static fallback JSON is returned
- **Time-bounded**: Entire scan runs under 4 seconds
- **No crashes**: All exceptions caught at the endpoint level
- **Stateless**: No DB, no S3, no queues — pure in-memory
- **Lambda-safe**: No subprocesses, no monkeypatching
