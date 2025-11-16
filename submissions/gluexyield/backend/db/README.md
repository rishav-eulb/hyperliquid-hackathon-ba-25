# Vault Data Database

This directory contains the database system for storing vault yield data from GlueX API.

## Structure

```
backend/db/
├── __init__.py              # Package init
├── models.py                # SQLAlchemy database models
├── database.py              # Database connection manager
├── collect_vault_data.py    # Data collection script
├── alembic.ini              # Alembic configuration
├── alembic/                 # Alembic migrations directory
│   ├── versions/            # Migration files
│   └── env.py               # Alembic environment
├── vaults.db                # SQLite database (created after first run)
└── README.md                # This file
```

## Database Schema

### VaultData Table

| Column          | Type     | Description                              |
|-----------------|----------|------------------------------------------|
| id              | Integer  | Primary key (auto-increment)             |
| vault_address   | String   | Vault contract address (indexed)         |
| historical_apy  | Float    | Historical APY percentage                |
| diluted_apy     | Float    | Diluted APY percentage                   |
| tvl             | Float    | Total Value Locked in USD                |
| created_at      | DateTime | Timestamp when record was created        |

## Usage

### 1. Collect Data for All Default Vaults

```bash
cd /Users/rj39/Desktop/NexusNetwork/GLUEX/hackathon
python3 backend/db/collect_vault_data.py
```

This will fetch data for all vaults defined in `backend/config/constants.py`.

### 2. Collect Data for Specific Vaults

```bash
python3 backend/db/collect_vault_data.py --vaults 0xe25514992597786e07872e6c5517fe1906c0cadd 0xcdc3975df9d1cf054f44ed238edfb708880292ea
```

### 3. View Latest Data

```bash
python3 backend/db/collect_vault_data.py --show-data
```

### 4. Custom Amount for Diluted APY

```bash
python3 backend/db/collect_vault_data.py --amount 5000000000000
```

### 5. Specify API Key

```bash
python3 backend/db/collect_vault_data.py --api-key YOUR_API_KEY_HERE
```

Or set the environment variable:

```bash
export GLUEX_API_KEY="your_api_key_here"
python3 backend/db/collect_vault_data.py
```

### 6. Custom Database Path

```bash
python3 backend/db/collect_vault_data.py --db-path /path/to/custom/db.sqlite
```

## Using in Python Code

```python
from backend.db.collect_vault_data import VaultDataCollector
import os

# Initialize collector
api_key = os.getenv('GLUEX_API_KEY')
collector = VaultDataCollector(api_key)

# Collect data for specific vaults
vault_addresses = [
    "0xe25514992597786e07872e6c5517fe1906c0cadd",
    "0xcdc3975df9d1cf054f44ed238edfb708880292ea"
]
collector.collect_vault_data(vault_addresses)

# Get latest data
latest_data = collector.get_latest_data()
for record in latest_data:
    print(f"Vault: {record.vault_address}")
    print(f"  Historical APY: {record.historical_apy:.2f}%")
    print(f"  Diluted APY: {record.diluted_apy:.2f}%")
    print(f"  TVL: ${record.tvl:,.2f}")

# Close connection
collector.close()
```

## Database Migrations

### Create a New Migration

```bash
cd backend/db
python3 -m alembic revision --autogenerate -m "Description of changes"
```

### Apply Migrations

```bash
cd backend/db
python3 -m alembic upgrade head
```

### View Migration History

```bash
cd backend/db
python3 -m alembic history
```

### Rollback One Migration

```bash
cd backend/db
python3 -m alembic downgrade -1
```

## Environment Variables

- `GLUEX_API_KEY`: Your GlueX API key (required)
- `UNIQUE_PID`: Optional unique partner ID for tracking

## Notes

- The database is SQLite-based and stored at `backend/db/vaults.db` by default
- Data is stored with timestamps, allowing historical tracking
- The script handles errors gracefully and continues processing remaining vaults
- All vault addresses are normalized to lowercase for consistency

