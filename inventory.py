"""Core business logic for the Inventory Tracking System (ITS)."""
import os, sqlite3, csv, io
from werkzeug.security import generate_password_hash, check_password_hash

class InventoryError(Exception):
    pass

def connect(path):
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    return db

def init_db(db, schema_path="schema.sql"):
    with open(schema_path) as f:
        db.executescript(f.read())
    db.commit()

# ---- users ----
def add_user(db, username, password, role):
    db.execute("INSERT INTO users(username,password_hash,role) VALUES(?,?,?)",
               (username, generate_password_hash(password), role))
    db.commit()

def authenticate(db, username, password):
    u = db.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    if u and check_password_hash(u["password_hash"], password):
        return u
    return None

# ---- master data ----
def add_supplier(db, name, phone=""):
    cur = db.execute("INSERT INTO suppliers(name,phone) VALUES(?,?)", (name, phone))
    db.commit()
    return cur.lastrowid

def add_item(db, sku, name, category, unit, reorder_level=0, unit_cost=0, location=""):
    if not sku.strip() or not name.strip():
        raise InventoryError("SKU and name are required.")
    try:
        cur = db.execute(
            "INSERT INTO items(sku,name,category,unit,reorder_level,unit_cost,location)"
            " VALUES(?,?,?,?,?,?,?)",
            (sku.strip().upper(), name.strip(), category, unit, reorder_level, unit_cost, location))
    except sqlite3.IntegrityError:
        raise InventoryError("An item with this SKU already exists.")
    db.commit()
    return cur.lastrowid

def set_bom(db, product_id, material_id, qty_per_unit):
    db.execute("INSERT OR REPLACE INTO bom(product_id,material_id,qty_per_unit) VALUES(?,?,?)",
               (product_id, material_id, qty_per_unit))
    db.commit()

# ---- stock movements ----
def _move(db, item_id, delta, ttype, reference, user_id, supplier_id=None):
    row = db.execute("SELECT qty FROM items WHERE id=?", (item_id,)).fetchone()
    if row is None:
        raise InventoryError("Item not found.")
    new = row["qty"] + delta
    if new < 0:
        raise InventoryError("Insufficient stock: operation would make the balance negative.")
    db.execute("UPDATE items SET qty=? WHERE id=?", (new, item_id))
    db.execute("INSERT INTO transactions(item_id,type,qty,balance_after,reference,supplier_id,user_id)"
               " VALUES(?,?,?,?,?,?,?)", (item_id, ttype, delta, new, reference, supplier_id, user_id))

def _positive(q):
    try:
        q = float(q)
    except (TypeError, ValueError):
        raise InventoryError("Quantity must be a number.")
    if q <= 0:
        raise InventoryError("Quantity must be greater than zero.")
    return q

def receive_stock(db, item_id, qty, user_id, supplier_id=None, reference=""):
    qty = _positive(qty)
    try:
        _move(db, item_id, qty, "RECEIPT", reference, user_id, supplier_id)
        db.commit()
    except Exception:
        db.rollback(); raise

def issue_stock(db, item_id, qty, user_id, reference=""):
    qty = _positive(qty)
    try:
        _move(db, item_id, -qty, "ISSUE", reference, user_id)
        db.commit()
    except Exception:
        db.rollback(); raise

def adjust_stock(db, item_id, counted_qty, user_id, reference="Stock count"):
    counted = float(counted_qty)
    if counted < 0:
        raise InventoryError("Counted quantity cannot be negative.")
    cur = db.execute("SELECT qty FROM items WHERE id=?", (item_id,)).fetchone()
    if cur is None:
        raise InventoryError("Item not found.")
    try:
        _move(db, item_id, counted - cur["qty"], "ADJUSTMENT", reference, user_id)
        db.commit()
    except Exception:
        db.rollback(); raise

def run_production(db, product_id, units, user_id, reference=""):
    """Consume raw materials per the bill of materials and add finished goods atomically."""
    units = _positive(units)
    lines = db.execute("SELECT material_id, qty_per_unit FROM bom WHERE product_id=?",
                       (product_id,)).fetchall()
    if not lines:
        raise InventoryError("No bill of materials defined for this product.")
    try:
        for l in lines:
            _move(db, l["material_id"], -l["qty_per_unit"] * units, "PRODUCTION_USE",
                  reference, user_id)
        _move(db, product_id, units, "PRODUCTION_OUTPUT", reference, user_id)
        db.commit()
    except Exception:
        db.rollback(); raise

# ---- queries / reports ----
def low_stock(db):
    return db.execute("SELECT * FROM items WHERE qty <= reorder_level ORDER BY name").fetchall()

def stock_valuation(db):
    return db.execute("SELECT COALESCE(SUM(qty*unit_cost),0) AS v FROM items").fetchone()["v"]

def ledger(db, item_id=None, limit=200):
    q = ("SELECT t.*, i.sku, i.name, u.username, s.name AS supplier FROM transactions t "
         "JOIN items i ON i.id=t.item_id LEFT JOIN users u ON u.id=t.user_id "
         "LEFT JOIN suppliers s ON s.id=t.supplier_id ")
    args = ()
    if item_id:
        q += "WHERE t.item_id=? "; args = (item_id,)
    q += "ORDER BY t.id DESC LIMIT ?"
    return db.execute(q, args + (limit,)).fetchall()

def stock_csv(db):
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["SKU", "Name", "Category", "Unit", "Qty", "Reorder level", "Unit cost", "Value"])
    for r in db.execute("SELECT * FROM items ORDER BY sku"):
        w.writerow([r["sku"], r["name"], r["category"], r["unit"], r["qty"],
                    r["reorder_level"], r["unit_cost"], r["qty"] * r["unit_cost"]])
    return out.getvalue()

def seed_demo(db):
    """Illustrative demonstration data (NOT real University records)."""
    # Demo passwords come from the environment; the fallbacks are for local demos ONLY.
    add_user(db, "admin", os.environ.get("ITS_ADMIN_PW", "admin123"), "admin")
    add_user(db, "keeper", os.environ.get("ITS_KEEPER_PW", "keeper123"), "storekeeper")
    add_user(db, "viewer", os.environ.get("ITS_VIEWER_PW", "viewer123"), "viewer")
    s1 = add_supplier(db, "Demo Paper Supplies Ltd", "08000000001")
    s2 = add_supplier(db, "Demo Chemicals and Inks Ltd", "08000000002")
    paper = add_item(db, "RM-001", "A4 Paper Reel", "Raw Material", "kg", 200, 650, "Store A")
    ink = add_item(db, "RM-002", "Printing Ink (black)", "Raw Material", "litre", 30, 4200, "Store A")
    glue = add_item(db, "RM-003", "Binding Adhesive", "Raw Material", "litre", 25, 1800, "Store B")
    cover = add_item(db, "RM-004", "Cover Board", "Raw Material", "sheet", 500, 120, "Store B")
    book = add_item(db, "FG-001", "Exercise Book (80 leaves)", "Finished Good", "pcs", 300, 480, "Store C")
    pad = add_item(db, "FG-002", "Writing Pad", "Finished Good", "pcs", 200, 350, "Store C")
    for pid, mid, q in [(book, paper, 0.12), (book, ink, 0.004), (book, glue, 0.003), (book, cover, 1),
                        (pad, paper, 0.08), (pad, ink, 0.002), (pad, glue, 0.002)]:
        set_bom(db, pid, mid, q)
    receive_stock(db, paper, 1500, 2, s1, "GRN-0001")
    receive_stock(db, ink, 120, 2, s2, "GRN-0002")
    receive_stock(db, glue, 80, 2, s2, "GRN-0003")
    receive_stock(db, cover, 4000, 2, s1, "GRN-0004")
    run_production(db, book, 2000, 2, "PO-0001")
    run_production(db, pad, 1000, 2, "PO-0002")
    issue_stock(db, book, 1700, 2, "SO-0001")
    issue_stock(db, ink, 70, 2, "REQ-0001")
