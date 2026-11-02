"""명령줄: python -m app <명령>

  check     ERP 접속과 정의 파일 검증 (정의의 모든 필드가 ERP에 있는지)
  sync      ERP 전체를 읽어 온톨로지를 만든다
  poll      바뀐 문서만 다시 읽는다
  stats     객체·연결 수
  serve     웹 화면·API·웹훅 서버 (http://localhost:8501)
"""
import sys


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"
    if cmd == "check":
        from app import config
        from app.ontology import schema as sch
        e = config.erp()
        me = e.call("frappe.auth.get_logged_user")
        print(f"ERP 접속: {config.ERP_URL} ({me})")
        s = sch.Schema(sch.load(config.ONTOLOGY_FILE), e)
        probs = s.validate()
        print(f"정의 파일: 객체 {len(s.objects)}종, 읽을 ERP 화면 {len(s.fetch_list())}개")
        print("문제 없음" if not probs else "문제:\n  " + "\n  ".join(probs))
    elif cmd == "sync":
        from app import runtime
        from app.ontology.sync import Sync
        r = runtime.get()
        Sync(store=r["store"], erp=r["erp"], graph=r["graph"], docs=r["docs"]).full()
        print("그래프 DB:", r["graph"].stats)
        _stats()
    elif cmd == "poll":
        from app.ontology.sync import Sync
        print("바뀐 객체", Sync().poll())
    elif cmd == "stats":
        _stats()
    elif cmd == "serve":
        import uvicorn
        uvicorn.run("app.web.server:app", host="0.0.0.0", port=8501)
    else:
        print(__doc__)


def _stats():
    from app import config
    from app.ontology.store import Store
    o, l = Store(config.DB_FILE).counts()
    print("객체:", sum(o.values()))
    for k, v in sorted(o.items()):
        print(f"  {k:12s} {v}")
    print("연결:", sum(l.values()))
    for k, v in sorted(l.items()):
        print(f"  {k:40s} {v}")


if __name__ == "__main__":
    main()
