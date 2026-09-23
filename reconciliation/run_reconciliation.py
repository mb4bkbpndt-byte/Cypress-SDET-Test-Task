import csv
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parent

TABLES = {
    "our_records": (
        "data/recon_our_records.csv",
        ("payment_id", "ref", "corridor", "amount", "currency", "status", "created_at"),
    ),
    "partner_statement": (
        "data/recon_partner_statement.csv",
        ("ref", "amount", "currency", "status", "settled_at"),
    ),
}

SCHEMA = """
CREATE TABLE our_records (
    payment_id TEXT NOT NULL,
    ref TEXT NOT NULL,
    corridor TEXT NOT NULL,
    amount INTEGER NOT NULL,
    currency TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE partner_statement (
    ref TEXT NOT NULL,
    amount INTEGER NOT NULL,
    currency TEXT NOT NULL,
    status TEXT NOT NULL,
    settled_at TEXT NOT NULL
);
"""


def load_table(connection: sqlite3.Connection, table: str) -> int:
    filename, columns = TABLES[table]
    with (ROOT / filename).open(newline="", encoding="utf-8-sig") as source:
        reader = csv.DictReader(source)
        if tuple(reader.fieldnames or ()) != columns:
            raise ValueError(f"Unexpected columns in {filename}: {reader.fieldnames}")
        rows = list(reader)

    values = []
    for row in rows:
        if not row["ref"]:
            raise ValueError(f"Empty ref in {filename}")
        values.append(tuple(int(row[column]) if column == "amount" else row[column]
                            for column in columns))

    placeholders = ", ".join("?" for _ in columns)
    connection.executemany(
        f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})",
        values,
    )
    return len(values)


def read_queries() -> list[tuple[str, str]]:
    source = (ROOT / "reconcile.sql").read_text(encoding="utf-8")
    queries = []
    for section in source.split("-- query: ")[1:]:
        name, sql = section.split("\n", 1)
        queries.append((name.strip(), sql.strip()))
    if len(queries) != 7:
        raise ValueError("Expected seven named queries in reconcile.sql")
    return queries


def main() -> None:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.executescript(SCHEMA)
    counts = {table: load_table(connection, table) for table in TABLES}
    print(f"Loaded: our_records={counts['our_records']}, "
          f"partner_statement={counts['partner_statement']}")

    for name, sql in read_queries():
        rows = [dict(row) for row in connection.execute(sql)]
        print(f"\n{name} ({len(rows)})")
        for row in rows:
            print(row)


if __name__ == "__main__":
    main()
