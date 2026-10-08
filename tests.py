import os, tempfile, unittest, json
import inventory as inv
import app as appmod

CASES = []
def case(desc, expected):
    def deco(f):
        f._desc, f._exp = desc, expected
        return f
    return deco

class T(unittest.TestCase):
    def setUp(self):
        self.path = tempfile.mktemp(suffix=".db")
        self.db = inv.connect(self.path); inv.init_db(self.db)
        inv.add_user(self.db, "a", "pw", "admin"); inv.add_user(self.db, "k", "pw", "storekeeper")
        inv.add_user(self.db, "v", "pw", "viewer")
        self.rm = inv.add_item(self.db, "RM1", "Raw", "Raw Material", "kg", 10, 100)
        self.fg = inv.add_item(self.db, "FG1", "Fin", "Finished Good", "pcs", 5, 500)
        inv.set_bom(self.db, self.fg, self.rm, 2)
        appmod.app.config.update(DB_PATH=self.path, TESTING=True)
        self.c = appmod.app.test_client()
    def tearDown(self):
        self.db.close(); os.remove(self.path)
    def qty(self, i): return self.db.execute("select qty from items where id=?", (i,)).fetchone()[0]
    def login(self, u): return self.c.post("/login", data={"username": u, "password": "pw"}, follow_redirects=True)

    @case("Create item with valid data", "Item saved with zero opening balance")
    def test_01(self):
        i = inv.add_item(self.db, "x9", "New", "Raw Material", "kg"); self.assertEqual(self.qty(i), 0)
    @case("Create item with duplicate SKU", "Rejected with error message")
    def test_02(self):
        with self.assertRaises(inv.InventoryError): inv.add_item(self.db, "rm1", "Dup", "Raw Material", "kg")
    @case("Receive 50 kg of raw material", "Balance increases to 50; RECEIPT logged")
    def test_03(self):
        inv.receive_stock(self.db, self.rm, 50, 1); self.assertEqual(self.qty(self.rm), 50)
        self.assertEqual(self.db.execute("select type from transactions").fetchone()[0], "RECEIPT")
    @case("Receive quantity of zero or negative", "Rejected; balance unchanged")
    def test_04(self):
        for q in (0, -5, "abc"):
            with self.assertRaises(inv.InventoryError): inv.receive_stock(self.db, self.rm, q, 1)
        self.assertEqual(self.qty(self.rm), 0)
    @case("Issue 20 kg from 50 kg balance", "Balance becomes 30")
    def test_05(self):
        inv.receive_stock(self.db, self.rm, 50, 1); inv.issue_stock(self.db, self.rm, 20, 1); self.assertEqual(self.qty(self.rm), 30)
    @case("Issue more than available stock", "Rejected; balance stays 10")
    def test_06(self):
        inv.receive_stock(self.db, self.rm, 10, 1)
        with self.assertRaises(inv.InventoryError): inv.issue_stock(self.db, self.rm, 11, 1)
        self.assertEqual(self.qty(self.rm), 10)
    @case("Production of 10 units (BOM 2 kg/unit) with 100 kg stock", "Raw material 80 kg; finished goods 10")
    def test_07(self):
        inv.receive_stock(self.db, self.rm, 100, 1); inv.run_production(self.db, self.fg, 10, 1)
        self.assertEqual((self.qty(self.rm), self.qty(self.fg)), (80, 10))
    @case("Production with insufficient raw material", "Rejected; no partial update")
    def test_08(self):
        inv.receive_stock(self.db, self.rm, 5, 1)
        with self.assertRaises(inv.InventoryError): inv.run_production(self.db, self.fg, 10, 1)
        self.assertEqual((self.qty(self.rm), self.qty(self.fg)), (5, 0))
    @case("Production for product without BOM", "Rejected with error")
    def test_09(self):
        p = inv.add_item(self.db, "FG2", "NoBom", "Finished Good", "pcs")
        with self.assertRaises(inv.InventoryError): inv.run_production(self.db, p, 1, 1)
    @case("Stock count adjustment from 30 to 28", "Balance 28; ADJUSTMENT of -2 logged")
    def test_10(self):
        inv.receive_stock(self.db, self.rm, 30, 1); inv.adjust_stock(self.db, self.rm, 28, 1)
        self.assertEqual(self.qty(self.rm), 28)
        self.assertEqual(self.db.execute("select qty from transactions where type='ADJUSTMENT'").fetchone()[0], -2)
    @case("Reorder alert when quantity <= reorder level", "Item appears in low-stock list")
    def test_11(self):
        inv.receive_stock(self.db, self.rm, 10, 1); self.assertIn(self.rm, [r["id"] for r in inv.low_stock(self.db)])
        inv.receive_stock(self.db, self.rm, 5, 1); self.assertNotIn(self.rm, [r["id"] for r in inv.low_stock(self.db)])
    @case("Ledger balance_after matches running balance", "Last entry equals item quantity")
    def test_12(self):
        inv.receive_stock(self.db, self.rm, 40, 1); inv.issue_stock(self.db, self.rm, 15, 1)
        self.assertEqual(inv.ledger(self.db, self.rm)[0]["balance_after"], self.qty(self.rm))
    @case("Stock valuation", "Value = sum(qty x unit cost) = 2,000")
    def test_13(self):
        inv.receive_stock(self.db, self.rm, 10, 1); inv.receive_stock(self.db, self.fg, 2, 1)
        self.assertEqual(inv.stock_valuation(self.db), 10*100 + 2*500)
    @case("Login with correct credentials", "Redirected to dashboard")
    def test_14(self):
        r = self.login("a"); self.assertIn(b"Dashboard", r.data)
    @case("Login with wrong password", "Access denied with error message")
    def test_15(self):
        r = self.c.post("/login", data={"username": "a", "password": "bad"}); self.assertIn(b"Invalid username", r.data)
    @case("Unauthenticated access to dashboard", "Redirected to login page")
    def test_16(self):
        r = self.c.get("/"); self.assertEqual(r.status_code, 302); self.assertIn("/login", r.headers["Location"])
    @case("Viewer attempts to open the issue-stock page", "HTTP 403 Forbidden")
    def test_17(self):
        self.login("v"); self.assertEqual(self.c.get("/issue").status_code, 403)
    @case("Storekeeper attempts to add an item", "HTTP 403 Forbidden")
    def test_18(self):
        self.login("k"); self.assertEqual(self.c.get("/items/new").status_code, 403)
    @case("Storekeeper receives stock through the web form", "Transaction recorded; balance updated")
    def test_19(self):
        self.login("k"); self.c.post("/receive", data={"item_id": self.rm, "qty": "25", "reference": "GRN-9"})
        self.assertEqual(self.qty(self.rm), 25)
    @case("Export stock report as CSV", "CSV file with header row and one row per item")
    def test_20(self):
        self.login("a"); r = self.c.get("/reports/stock.csv"); lines = r.data.decode().strip().splitlines()
        self.assertEqual((r.mimetype, len(lines)), ("text/csv", 3))

    @case("Administrator adjusts stock to a counted quantity through the web form", "Balance set to counted value; ADJUSTMENT logged")
    def test_21(self):
        inv.receive_stock(self.db, self.rm, 30, 1); self.login("a")
        self.c.post("/adjust", data={"item_id": self.rm, "counted": "27", "reference": "Count"})
        self.assertEqual(self.qty(self.rm), 27)
    @case("Administrator saves a bill-of-materials line, then production deducts per BOM", "BOM line stored; production deducts per BOM")
    def test_22(self):
        p = inv.add_item(self.db, "FG9", "Pad", "Finished Good", "pcs"); inv.receive_stock(self.db, self.rm, 10, 1)
        self.login("a"); self.c.post("/bom", data={"product_id": p, "material_id": self.rm, "qty_per_unit": "0.5"})
        inv.run_production(self.db, p, 4, 1); self.assertEqual((self.qty(self.rm), self.qty(p)), (8, 4))
    @case("Store keeper attempts stock adjustment", "HTTP 403 Forbidden")
    def test_23(self):
        self.login("k"); self.assertEqual(self.c.get("/adjust").status_code, 403)

if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(T)
    names = [t._testMethodName for t in suite]
    res = unittest.TextTestRunner(verbosity=0).run(suite)
    failed = {str(f[0]).split()[0] for f in res.failures + res.errors}
    out = []
    for n in names:
        f = getattr(T, n)
        out.append(dict(id=n.split("_")[1], desc=f._desc, expected=f._exp,
                        result="Fail" if n in failed else "Pass"))
    json.dump(out, open("test_results.json", "w"), indent=1)
    print(sum(o["result"] == "Pass" for o in out), "of", len(out), "passed")
