import os
from functools import wraps
from flask import (Flask, g, render_template, request, redirect, url_for, session,
                   flash, Response, abort)
import inventory as inv

app = Flask(__name__)
app.secret_key = os.environ.get("ITS_SECRET", "dev-only-change-me")
app.config["DB_PATH"] = os.environ.get("ITS_DB", "its.db")

def get_db():
    if "db" not in g:
        g.db = inv.connect(app.config["DB_PATH"])
    return g.db

@app.teardown_appcontext
def close_db(_):
    db = g.pop("db", None)
    if db:
        db.close()

def login_required(roles=None):
    def deco(f):
        @wraps(f)
        def w(*a, **k):
            if "uid" not in session:
                return redirect(url_for("login"))
            if roles and session["role"] not in roles:
                abort(403)
            return f(*a, **k)
        return w
    return deco

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = inv.authenticate(get_db(), request.form["username"], request.form["password"])
        if u:
            session.update(uid=u["id"], user=u["username"], role=u["role"])
            return redirect(url_for("dashboard"))
        flash("Invalid username or password.", "error")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/")
@login_required()
def dashboard():
    db = get_db()
    return render_template("dashboard.html",
        n_items=db.execute("SELECT COUNT(*) c FROM items").fetchone()["c"],
        value=inv.stock_valuation(db), low=inv.low_stock(db),
        recent=inv.ledger(db, limit=8))

@app.route("/items")
@login_required()
def items():
    rows = get_db().execute("SELECT * FROM items ORDER BY sku").fetchall()
    return render_template("items.html", items=rows)

@app.route("/items/new", methods=["GET", "POST"])
@login_required(["admin"])
def item_new():
    if request.method == "POST":
        f = request.form
        try:
            inv.add_item(get_db(), f["sku"], f["name"], f["category"], f["unit"],
                         float(f["reorder_level"] or 0), float(f["unit_cost"] or 0), f["location"])
            flash("Item created.", "ok")
            return redirect(url_for("items"))
        except inv.InventoryError as e:
            flash(str(e), "error")
    return render_template("item_form.html")

def _movement(kind):
    db = get_db()
    if request.method == "POST":
        f = request.form
        try:
            if kind == "receive":
                inv.receive_stock(db, int(f["item_id"]), f["qty"], session["uid"],
                                  int(f["supplier_id"]) if f.get("supplier_id") else None, f["reference"])
            else:
                inv.issue_stock(db, int(f["item_id"]), f["qty"], session["uid"], f["reference"])
            flash("Transaction recorded.", "ok")
            return redirect(url_for("ledger"))
        except inv.InventoryError as e:
            flash(str(e), "error")
    return render_template("movement.html", kind=kind,
        items=db.execute("SELECT * FROM items ORDER BY sku").fetchall(),
        suppliers=db.execute("SELECT * FROM suppliers ORDER BY name").fetchall())

@app.route("/receive", methods=["GET", "POST"])
@login_required(["admin", "storekeeper"])
def receive():
    return _movement("receive")

@app.route("/issue", methods=["GET", "POST"])
@login_required(["admin", "storekeeper"])
def issue():
    return _movement("issue")

@app.route("/production", methods=["GET", "POST"])
@login_required(["admin", "storekeeper"])
def production():
    db = get_db()
    if request.method == "POST":
        try:
            inv.run_production(db, int(request.form["product_id"]), request.form["units"],
                               session["uid"], request.form["reference"])
            flash("Production run recorded; materials deducted and finished goods added.", "ok")
            return redirect(url_for("ledger"))
        except inv.InventoryError as e:
            flash(str(e), "error")
    return render_template("production.html", products=db.execute(
        "SELECT * FROM items WHERE category='Finished Good' ORDER BY name").fetchall())

@app.route("/adjust", methods=["GET", "POST"])
@login_required(["admin"])
def adjust():
    db = get_db()
    if request.method == "POST":
        try:
            inv.adjust_stock(db, int(request.form["item_id"]), request.form["counted"],
                             session["uid"], request.form["reference"] or "Stock count")
            flash("Stock adjusted to counted quantity.", "ok")
            return redirect(url_for("ledger"))
        except inv.InventoryError as e:
            flash(str(e), "error")
        except ValueError:
            flash("Counted quantity must be a number.", "error")
    return render_template("adjust.html", items=db.execute("SELECT * FROM items ORDER BY sku").fetchall())

@app.route("/bom", methods=["GET", "POST"])
@login_required(["admin"])
def bom():
    db = get_db()
    if request.method == "POST":
        try:
            q = float(request.form["qty_per_unit"])
            if q <= 0:
                raise ValueError
            inv.set_bom(db, int(request.form["product_id"]), int(request.form["material_id"]), q)
            flash("Bill of materials line saved.", "ok")
        except ValueError:
            flash("Quantity per unit must be a positive number.", "error")
    rows = db.execute("SELECT p.name AS product, m.name AS material, m.unit, b.qty_per_unit FROM bom b "
                      "JOIN items p ON p.id=b.product_id JOIN items m ON m.id=b.material_id ORDER BY p.name, m.name").fetchall()
    return render_template("bom.html", rows=rows,
        products=db.execute("SELECT * FROM items WHERE category='Finished Good' ORDER BY name").fetchall(),
        materials=db.execute("SELECT * FROM items WHERE category='Raw Material' ORDER BY name").fetchall())

@app.route("/suppliers", methods=["GET", "POST"])
@login_required(["admin"])
def suppliers():
    db = get_db()
    if request.method == "POST":
        try:
            inv.add_supplier(db, request.form["name"].strip(), request.form["phone"])
            flash("Supplier added.", "ok")
        except Exception:
            db.rollback(); flash("Supplier name is required and must be unique.", "error")
    return render_template("suppliers.html", rows=db.execute("SELECT * FROM suppliers ORDER BY name").fetchall())

@app.route("/ledger")
@login_required()
def ledger():
    return render_template("ledger.html", rows=inv.ledger(get_db()))

@app.route("/reports")
@login_required()
def reports():
    db = get_db()
    return render_template("reports.html", low=inv.low_stock(db), value=inv.stock_valuation(db))

@app.route("/reports/stock.csv")
@login_required()
def stock_csv():
    return Response(inv.stock_csv(get_db()), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=stock_report.csv"})

if __name__ == "__main__":
    if not os.path.exists(app.config["DB_PATH"]):
        d = inv.connect(app.config["DB_PATH"]); inv.init_db(d); inv.seed_demo(d); d.close()
    app.run(debug=False, port=5000)
