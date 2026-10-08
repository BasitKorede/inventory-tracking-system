CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL CHECK(role IN ('admin','storekeeper','viewer'))
);
CREATE TABLE IF NOT EXISTS suppliers(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT UNIQUE NOT NULL,
  phone TEXT
);
CREATE TABLE IF NOT EXISTS items(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  sku TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL,
  category TEXT NOT NULL CHECK(category IN ('Raw Material','Finished Good')),
  unit TEXT NOT NULL,
  reorder_level REAL NOT NULL DEFAULT 0,
  qty REAL NOT NULL DEFAULT 0 CHECK(qty >= 0),
  unit_cost REAL NOT NULL DEFAULT 0,
  location TEXT
);
CREATE TABLE IF NOT EXISTS bom(
  product_id INTEGER NOT NULL REFERENCES items(id),
  material_id INTEGER NOT NULL REFERENCES items(id),
  qty_per_unit REAL NOT NULL CHECK(qty_per_unit > 0),
  PRIMARY KEY(product_id, material_id)
);
CREATE TABLE IF NOT EXISTS transactions(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  item_id INTEGER NOT NULL REFERENCES items(id),
  type TEXT NOT NULL CHECK(type IN ('RECEIPT','ISSUE','PRODUCTION_USE','PRODUCTION_OUTPUT','ADJUSTMENT')),
  qty REAL NOT NULL,
  balance_after REAL NOT NULL,
  reference TEXT,
  supplier_id INTEGER REFERENCES suppliers(id),
  user_id INTEGER REFERENCES users(id),
  ts TEXT NOT NULL DEFAULT (datetime('now'))
);
