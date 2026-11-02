"""설정: 저장소 최상위의 .env 를 읽는다."""
import os
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _load_env():
    p = ROOT / ".env"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


_load_env()

ERP_URL = os.environ.get("ERP_URL", "http://localhost:8080")
ERP_API_KEY = os.environ.get("ERP_API_KEY", "")
ERP_API_SECRET = os.environ.get("ERP_API_SECRET", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-5-5")
ONTOLOGY_FILE = pathlib.Path(os.environ.get("ONTOLOGY_FILE", ROOT / "ontology" / "ontology.yaml"))
DB_FILE = pathlib.Path(os.environ.get("ONTWIN_DB", ROOT / "data" / "ontwin.db"))
GRAPH_DIR = pathlib.Path(os.environ.get("ONTWIN_GRAPH", ROOT / "data" / "graph"))
DOCS_DIR = pathlib.Path(os.environ.get("ONTWIN_DOCS", ROOT / "erp_seed" / "data" / "docs"))
AS_OF = os.environ.get("ONTWIN_AS_OF", "")  # 평가 때만 기준일 고정 (비우면 오늘)


def erp():
    from app.erp.client import ERP
    return ERP(ERP_URL, ERP_API_KEY, ERP_API_SECRET)
