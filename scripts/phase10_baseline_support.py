"""Reusable read-only baseline table digest, no migrations or connections to providers."""
from pathlib import Path
import sqlite3
from services.windows_native.contracts import digest

def tables(path):
    with sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True) as con:
        con.row_factory=sqlite3.Row
        assert con.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        return {r['name']:{'ddl':r['sql'],'rows':len(values),'sha256':digest(values)}
                for r in con.execute("SELECT name,sql FROM sqlite_master WHERE type='table' ORDER BY name")
                for values in [[dict(v) for v in con.execute('SELECT * FROM "'+r['name']+'" ORDER BY rowid')]]}
