# Inventory Tracking System for a Manufacturing Company

**A case study of the University of Ibadan** — CSC 476 semester project,
Department of Computer Science, Faculty of Science, University of Ibadan.

A web-based system that tracks raw materials and finished goods for a production unit:
receipts, issues, stock counts and production runs are recorded in an append-only ledger;
production deducts raw materials automatically using a bill of materials (BOM);
stock can never go negative; reorder alerts and valuation reports are generated instantly.

## Team

| Name | Matric No. | Role |
|---|---|---|
| Arigbabuwo Basit Korede | E051584 | Team Leader, Lead Developer (backend and business logic) |
| Quadir Baniameen O. | E051579 | Systems Analyst and Database Designer |
| Muhammed Nofisat | E051052 | Documentation and Literature Lead |
| Abia Gift Morris | E050899 | Front-end Developer and Quality Assurance (testing) |

## Features
- Role-based access: administrator, store keeper, viewer
- Item, supplier and bill-of-materials management
- Receive stock (goods received note), issue stock, physical-count adjustment
- Production runs that consume materials by BOM and add finished goods atomically
- Dashboard, reorder alerts, stock ledger with user and time, valuation, CSV export

## Run it locally
```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
python app.py                   # creates its.db with demo data on first run
```
Open http://127.0.0.1:5000 and sign in with a demo account (`admin`, `keeper` or `viewer`).
Demo passwords are in `seed_demo()` in `inventory.py`; override them with the environment variables
`ITS_ADMIN_PW`, `ITS_KEEPER_PW`, `ITS_VIEWER_PW`, and set `ITS_SECRET` (session key) for any real use.
All data in the demo database is illustrative, not real University records.

## Run the tests
```bash
python tests.py        # 23 automated test cases
```

## Project layout
```
app.py          Flask routes, sessions, role checks
inventory.py    business logic (movements, production, reports)
schema.sql      database schema (5 tables, constraints)
templates/      HTML pages        static/  CSS
tests.py        23 test cases     docs/    screenshots and diagrams
```

## Technology
Python 3, Flask, SQLite, HTML/CSS. All free and open source.

## Licence
MIT — see `LICENSE`.
