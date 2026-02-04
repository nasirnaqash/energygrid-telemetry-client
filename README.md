# EnergyGrid Data Aggregator Solution

A robust Python client for fetching real-time telemetry from 500 solar inverters, navigating strict rate limits and security protocols.

## 📁 Project Structure

```
.
├── energy_grid_client.py   # Main solution (Python)
├── test_energy_grid.py     # Unit tests
├── requirements.txt        # Python dependencies
├── README.md               # This file
├── instructions.md         # Original assignment
└── mock-api/               # Mock API server
    ├── server.js
    ├── package.json
    └── README.md
```

## 🚀 Quick Start

### 1. Prerequisites

- Python 3.8+
- Node.js 14+ (for the mock API server)

### 2. Start the Mock API Server

```bash
# cd mock-api
npm install
npm start
```

You should see:
```
  EnergyGrid Mock API running on port 3000
  Constraints: 1 req/sec, Max 10 items/batch
```

### 3. Run the Client

```bash
# Install Python dependencies
cd solution
pip install -r requirements.txt

# Run the aggregator
python energy_grid_client.py
```

## Architecture & Approach

### Design Principles

The solution follows **clean architecture** with clear separation of concerns:

```
┌─────────────────────────────────────────────────────────────┐
│                  EnergyGridDataAggregator                   │
│                    (Main Orchestrator)                      │
└─────────────────────────────────────────────────────────────┘
                              │
          ┌───────────────────┼───────────────────┐
          ▼                   ▼                   ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│  BatchProcessor │  │ EnergyGridAPI   │  │  DataAggregator │
│  (Orchestration)│  │  Client (HTTP)  │  │  (Analytics)    │
└─────────────────┘  └─────────────────┘  └─────────────────┘
          │                   │
          ▼                   ▼
┌─────────────────┐  ┌─────────────────┐
│   RateLimiter   │  │   Signature     │
│   (Throttle)    │  │   Generator     │
└─────────────────┘  └─────────────────┘
```

### Module Responsibilities

| Module | Responsibility |
|--------|---------------|
| `Config` | Centralized configuration (URLs, limits, tokens) |
| `SignatureGenerator` | MD5 signature: `MD5(URL + Token + Timestamp)` |
| `RateLimiter` | Enforces 1 req/sec with safety buffer |
| `EnergyGridAPIClient` | HTTP communication, headers, session management |
| `BatchProcessor` | Splits into batches, handles retries |
| `DataAggregator` | Combines results, calculates statistics |
| `EnergyGridDataAggregator` | Main orchestrator |

---

## Rate Limiting Strategy

### The Challenge

- **Constraint**: Strictly 1 request per second
- **Penalty**: HTTP 429 on violation
- **Risk**: Network latency can cause timing issues

### Solution: Proactive Rate Limiting with Buffer


**Key decisions:**
1. **Proactive waiting** - We wait *before* requests, not after
2. **50ms buffer** - Accounts for processing time and network jitter
3. **Exponential backoff** - On 429, wait 2^attempt seconds before retry

### Throughput Optimization

With 500 devices and batches of 10:
- **50 batches** required
- **~1.05 seconds** per batch (with buffer)
- **Total time**: ~52-55 seconds (theoretical minimum: 50s)

---

## Security Implementation

### Signature Generation

The API requires: `MD5(URL + Token + Timestamp)`


**Important**: The timestamp must be in **milliseconds** and sent as a string header.

### Headers

Every request includes:
```json
{
    "Content-Type": "application/json",
    "timestamp": "1704067200000",
    "signature": "a1b2c3d4e5f6..."
}
```

---

## Error Handling

### Retry Strategy

| Error Type | Handling |
|------------|----------|
| HTTP 429 | Exponential backoff (2^n seconds), max 3 retries |
| HTTP 401 | No retry - authentication failure |
| HTTP 5xx | Automatic retry via urllib3 |
| Network errors | Exponential backoff, max 3 retries |

### Graceful Degradation

Failed batches are tracked separately with full error context:
- Batch index
- Affected serial numbers
- Error message
- Attempt count

---

## Output

### Console Output

```
============================================================
EnergyGrid Data Aggregator
============================================================

Target: http://localhost:3000/device/real/query
Devices to query: 500

Processing 500 devices in 50 batches
   Rate limit: 1.0s between requests
   Batch size: 10 devices

  [  1/ 50] ✓ Batch 0: 10 devices (attempts: 1)
  [  2/ 50] ✓ Batch 1: 10 devices (attempts: 1)
  ...

============================================================
AGGREGATION SUMMARY
============================================================
  Total devices queried:  500
  Successful queries:     500
  Failed queries:         0
  Online devices:         450
  Offline devices:        50
  Total power output:     1234.56 kW
  Average power/device:   2.47 kW
  Execution time:         53.21 seconds
============================================================
```

### JSON Report

The full report is saved to `telemetry_report.json`:

```json
{
  "summary": {
    "total_devices": 500,
    "successful_queries": 500,
    "failed_queries": 0,
    "online_devices": 450,
    "offline_devices": 50,
    "total_power_kw": 1234.56,
    "average_power_kw": 2.47,
    "execution_time_seconds": 53.21
  },
  "devices": [
    {
      "sn": "SN-000",
      "power": "2.34 kW",
      "status": "Online",
      "last_updated": "2024-01-01T12:00:00.000Z"
    }
  ],
  "errors": []
}
```

---

## Assumptions

1. **Timestamp format**: Milliseconds since epoch (not seconds)
2. **URL in signature**: Uses the path only (`/device/real/query`), not full URL
3. **Rate limit**: Server allows ~50ms tolerance (as per server code)
4. **Batch order**: Order of batches doesn't matter for aggregation
5. **Idempotency**: Re-querying a device on retry is acceptable

---

## Testing

To test the solution:

```bash
# Terminal 1: Start mock server
npm start

# Terminal 2: Run client
cd solution
python energy_grid_client.py
```

---

## Project Structure

```
.
├── server.js              # Mock API server (provided)
├── package.json           # Node.js dependencies
├── instructions.md        # Assignment brief
├── README.md              # Server setup instructions
└── solution/
    ├── energy_grid_client.py   # Main solution
    ├── requirements.txt        # Python dependencies
    └── README.md               # This file
```
