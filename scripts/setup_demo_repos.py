#!/usr/bin/env python3
"""
Builds the four (+one) demo-repository scenarios as REAL git repositories,
each with a baseline commit and a "PR" commit on top of it. This lets the
Change Analyzer use a genuine `git diff --name-only <base>..HEAD` instead of
a fake/hardcoded changed-files list.

Safe to re-run: it wipes and recreates scenarios/ from scratch each time.

Usage:
    python3 scripts/setup_demo_repos.py
"""
import os
import shutil
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCENARIOS_DIR = os.path.join(ROOT, "demo-repository", "scenarios")


def write(path: str, content: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        fh.write(content)


def git(repo_dir: str, *args):
    subprocess.run(["git", *args], cwd=repo_dir, check=True, capture_output=True, text=True)


def init_repo(repo_dir: str):
    if os.path.exists(repo_dir):
        shutil.rmtree(repo_dir)
    os.makedirs(repo_dir, exist_ok=True)
    git(repo_dir, "init", "-q")
    git(repo_dir, "config", "user.email", "demo@ramav.local")
    git(repo_dir, "config", "user.name", "RAMAV Demo")


def commit_all(repo_dir: str, message: str):
    git(repo_dir, "add", "-A")
    git(repo_dir, "commit", "-q", "-m", message, "--allow-empty")


# ---------------------------------------------------------------------------
# 1. SAFE — documentation-only change
# ---------------------------------------------------------------------------
def build_safe():
    repo = os.path.join(SCENARIOS_DIR, "safe")
    init_repo(repo)
    write(os.path.join(repo, "docs", "notes.md"), "# Release Notes\n\nInitial release.\n")
    write(os.path.join(repo, "tests", "test_basic.py"), (
        "import unittest\n\n"
        "class TestBasicSanity(unittest.TestCase):\n"
        "    def test_addition(self):\n"
        "        self.assertEqual(1 + 1, 2)\n\n"
        "    def test_string_formatting(self):\n"
        "        self.assertEqual(f\"{'a'}{'b'}\", 'ab')\n\n"
        "if __name__ == '__main__':\n"
        "    unittest.main()\n"
    ))
    commit_all(repo, "baseline")

    write(os.path.join(repo, "docs", "notes.md"), (
        "# Release Notes -- v1.4.1\n\n"
        "This release only updates documentation. No application source code,\n"
        "dependencies, or database access paths were touched.\n\n"
        "## Changes\n"
        "- Clarified the setup instructions in the developer guide.\n"
        "- Fixed a typo in the API usage example.\n"
        "- Added a note about the new `--verbose` flag for the CLI tool.\n\n"
        "No functional behaviour changed in this release.\n"
    ))
    commit_all(repo, "docs: clarify setup instructions, fix typo")


# ---------------------------------------------------------------------------
# 2. SQL INJECTION — vulnerable endpoint added
# ---------------------------------------------------------------------------
def build_sql_injection():
    repo = os.path.join(SCENARIOS_DIR, "sql_injection")
    init_repo(repo)
    write(os.path.join(repo, "app", "routes", "product.py"), (
        '"""Product lookup endpoint -- pre-existing, unchanged in this PR."""\n\n\n'
        "def get_product_by_sku(conn, sku):\n"
        '    """@app.get("/products/<sku>") -- safe, parameterized query."""\n'
        "    cursor = conn.cursor()\n"
        '    cursor.execute("SELECT id, name, price FROM products WHERE sku = ?", (sku,))\n'
        "    return cursor.fetchone()\n"
    ))
    write(os.path.join(repo, "tests", "test_product.py"), (
        "import unittest\nimport sqlite3\nimport sys, os\n"
        "sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))\n"
        "from app.routes.product import get_product_by_sku\n\n"
        "class TestProduct(unittest.TestCase):\n"
        "    def setUp(self):\n"
        "        self.conn = sqlite3.connect(':memory:')\n"
        "        c = self.conn.cursor()\n"
        "        c.execute('CREATE TABLE products (id INTEGER, name TEXT, price REAL, sku TEXT)')\n"
        "        c.execute(\"INSERT INTO products VALUES (1, 'Widget', 9.99, 'SKU1')\")\n"
        "        self.conn.commit()\n\n"
        "    def test_lookup(self):\n"
        "        row = get_product_by_sku(self.conn, 'SKU1')\n"
        "        self.assertEqual(row[1], 'Widget')\n\n"
        "if __name__ == '__main__':\n    unittest.main()\n"
    ))
    write(os.path.join(repo, "requirements.txt"), "flask==3.0.0\n")
    commit_all(repo, "baseline: product lookup endpoint")

    # PR commit: add the vulnerable user lookup endpoint + a test that
    # passes but does NOT cover malicious input.
    write(os.path.join(repo, "app", "routes", "user.py"), (
        '"""User lookup endpoint -- NEW in this PR.\n\n'
        "VULNERABLE: user-controlled `username` is interpolated directly into\n"
        'the SQL string via an f-string instead of a parameterized query.\n"""\n\n\n'
        "def get_user_by_username(conn, username):\n"
        '    """@app.get("/users/<username>") -- looks up a user by username."""\n'
        "    cursor = conn.cursor()\n"
        "    cursor.execute(f\"SELECT id, username, email FROM users WHERE username = '{username}'\")\n"
        "    return cursor.fetchone()\n"
    ))
    write(os.path.join(repo, "tests", "test_user.py"), (
        "import unittest\nimport sqlite3\nimport sys, os\n"
        "sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))\n"
        "from app.routes.user import get_user_by_username\n\n"
        "class TestUser(unittest.TestCase):\n"
        "    def setUp(self):\n"
        "        self.conn = sqlite3.connect(':memory:')\n"
        "        c = self.conn.cursor()\n"
        "        c.execute('CREATE TABLE users (id INTEGER, username TEXT, email TEXT)')\n"
        "        c.execute(\"INSERT INTO users VALUES (1, 'alice', 'alice@example.com')\")\n"
        "        self.conn.commit()\n\n"
        "    def test_lookup_existing_user(self):\n"
        "        row = get_user_by_username(self.conn, 'alice')\n"
        "        self.assertEqual(row[1], 'alice')\n"
        "    # This test only covers the normal/expected lookup path; it does\n"
        "    # not add any adversarial or attacker-supplied-input coverage.\n\n"
        "if __name__ == '__main__':\n    unittest.main()\n"
    ))
    commit_all(repo, "feat: add user lookup endpoint")


# ---------------------------------------------------------------------------
# 3. DISAGREEMENT — regression test fails, but nothing security/quality-wise
# ---------------------------------------------------------------------------
def build_disagreement():
    repo = os.path.join(SCENARIOS_DIR, "disagreement")
    init_repo(repo)
    write(os.path.join(repo, "app", "services", "order.py"), (
        '"""Order pricing service."""\n\n\n'
        "def apply_discount(order_total, is_member):\n"
        '    """Apply the standing 10% member discount."""\n'
        "    if is_member:\n"
        "        return round(order_total * 0.90, 2)\n"
        "    return order_total\n"
    ))
    write(os.path.join(repo, "tests", "test_order_regression.py"), (
        "import unittest\nimport sys, os\n"
        "sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))\n"
        "from app.services.order import apply_discount\n\n"
        "class TestOrderRegression(unittest.TestCase):\n"
        "    def test_member_discount_is_ten_percent(self):\n"
        "        self.assertEqual(apply_discount(100.0, True), 90.0)\n\n"
        "if __name__ == '__main__':\n    unittest.main()\n"
    ))
    commit_all(repo, "baseline: 10% member discount")

    # PR commit changes the discount to 15% -- a legitimate business change,
    # but nobody updated the regression test, so it now fails. Security and
    # Quality see nothing wrong with the code itself.
    write(os.path.join(repo, "app", "services", "order.py"), (
        '"""Order pricing service."""\n\n\n'
        "def apply_discount(order_total, is_member):\n"
        '    """Apply the new 15% member discount (updated pricing policy)."""\n'
        "    if is_member:\n"
        "        return round(order_total * 0.85, 2)\n"
        "    return order_total\n"
    ))
    commit_all(repo, "feat: increase member discount to 15%")


# ---------------------------------------------------------------------------
# 4. REPAIR — same vulnerability as sql_injection, used to demo Repair Agent
# ---------------------------------------------------------------------------
def build_repair():
    repo = os.path.join(SCENARIOS_DIR, "repair")
    init_repo(repo)
    write(os.path.join(repo, "app", "routes", "account.py"), (
        '"""Account lookup endpoint -- pre-existing, unchanged in this PR."""\n\n\n'
        "def get_account_by_id(conn, account_id):\n"
        "    cursor = conn.cursor()\n"
        '    cursor.execute("SELECT id, owner FROM accounts WHERE id = ?", (account_id,))\n'
        "    return cursor.fetchone()\n"
    ))
    write(os.path.join(repo, "tests", "test_account.py"), (
        "import unittest\nimport sqlite3\nimport sys, os\n"
        "sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))\n"
        "from app.routes.account import get_account_by_id\n\n"
        "class TestAccount(unittest.TestCase):\n"
        "    def setUp(self):\n"
        "        self.conn = sqlite3.connect(':memory:')\n"
        "        c = self.conn.cursor()\n"
        "        c.execute('CREATE TABLE accounts (id INTEGER, owner TEXT)')\n"
        "        c.execute(\"INSERT INTO accounts VALUES (1, 'alice')\")\n"
        "        self.conn.commit()\n\n"
        "    def test_lookup(self):\n"
        "        row = get_account_by_id(self.conn, 1)\n"
        "        self.assertEqual(row[1], 'alice')\n\n"
        "if __name__ == '__main__':\n    unittest.main()\n"
    ))
    commit_all(repo, "baseline: account lookup endpoint")

    write(os.path.join(repo, "app", "routes", "invoice.py"), (
        '"""Invoice lookup endpoint -- NEW in this PR.\n\n'
        'VULNERABLE: same class of SQL injection as the sql_injection scenario,\n'
        'used here to demonstrate the Repair Agent + revalidation loop.\n"""\n\n\n'
        "def get_invoice_by_customer(conn, customer_name):\n"
        "    cursor = conn.cursor()\n"
        "    cursor.execute(f\"SELECT id, total FROM invoices WHERE customer = '{customer_name}'\")\n"
        "    return cursor.fetchone()\n"
    ))
    write(os.path.join(repo, "tests", "test_invoice.py"), (
        "import unittest\nimport sqlite3\nimport sys, os\n"
        "sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))\n"
        "from app.routes.invoice import get_invoice_by_customer\n\n"
        "class TestInvoice(unittest.TestCase):\n"
        "    def setUp(self):\n"
        "        self.conn = sqlite3.connect(':memory:')\n"
        "        c = self.conn.cursor()\n"
        "        c.execute('CREATE TABLE invoices (id INTEGER, total REAL, customer TEXT)')\n"
        "        c.execute(\"INSERT INTO invoices VALUES (1, 42.5, 'alice')\")\n"
        "        self.conn.commit()\n\n"
        "    def test_lookup(self):\n"
        "        row = get_invoice_by_customer(self.conn, 'alice')\n"
        "        self.assertEqual(row[1], 42.5)\n\n"
        "if __name__ == '__main__':\n    unittest.main()\n"
    ))
    commit_all(repo, "feat: add invoice lookup endpoint")


# ---------------------------------------------------------------------------
# 5. LOW EVIDENCE — unsupported language, no test runner, generally thin evidence
# ---------------------------------------------------------------------------
def build_low_evidence():
    repo = os.path.join(SCENARIOS_DIR, "low_evidence")
    init_repo(repo)
    write(os.path.join(repo, "README.md"), "# Legacy service (Go)\n")
    commit_all(repo, "baseline")

    write(os.path.join(repo, "cmd", "server", "main.go"), (
        "package main\n\nimport \"fmt\"\n\nfunc main() {\n\tfmt.Println(\"listening\")\n}\n"
    ))
    commit_all(repo, "feat: bootstrap Go server (no Python tooling available for this language)")


def main():
    os.makedirs(SCENARIOS_DIR, exist_ok=True)
    build_safe()
    build_sql_injection()
    build_disagreement()
    build_repair()
    build_low_evidence()
    print("Demo scenarios built at:", SCENARIOS_DIR)


if __name__ == "__main__":
    main()
