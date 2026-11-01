"""노바레지스트 데이터를 ERPNext에 넣는 스크립트.

사용법 (WSL Ubuntu에서):
    python3 nr_load.py check        # 접속 확인
    python3 nr_load.py setup        # 1) 설정·추가 필드·추가 화면
    python3 nr_load.py master       # 2) 기준정보
    python3 nr_load.py tx           # 3) 기초재고 + 2026년 거래 (날짜 순서대로, 중간에 멈추면 다시 실행하면 이어서)
    python3 nr_load.py finish       # 4) 문서번호 자동 채번 복구 + 검증
    python3 nr_load.py all          # 1~4 한 번에

설정은 같은 폴더의 .env 파일에서 읽는다:
    NR_URL=http://localhost:8080
    NR_KEY=...
    NR_SECRET=...
    NR_DATA=./data        (master/, erp/ 폴더가 있는 곳)
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from erp_client import ERP, ERPError  # noqa: E402


def load_env():
    env = {}
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    for k in ["NR_URL", "NR_KEY", "NR_SECRET", "NR_DATA", "NR_HOST"]:
        if os.environ.get(k):
            env[k] = os.environ[k]
    env.setdefault("NR_URL", "http://localhost:8080")
    env.setdefault("NR_DATA", os.path.join(os.path.dirname(os.path.abspath(__file__)), "data"))
    return env


def main():
    stage = sys.argv[1] if len(sys.argv) > 1 else "check"
    until = sys.argv[2] if len(sys.argv) > 2 else None
    env = load_env()
    if not env.get("NR_KEY") or not env.get("NR_SECRET"):
        print("처음 실행이라 ERPNext API 키가 필요해요 (메모장에 복사해 둔 값).")
        env["NR_KEY"] = input("  API Key 붙여넣기 후 엔터: ").strip()
        env["NR_SECRET"] = input("  API Secret 붙여넣기 후 엔터: ").strip()
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
        with open(p, "w", encoding="utf-8") as fp:
            fp.write(f"NR_URL={env['NR_URL']}\nNR_KEY={env['NR_KEY']}\nNR_SECRET={env['NR_SECRET']}\n")
        print("  저장했어요(.env). 다음부터는 묻지 않아요.")
    erp = ERP(env["NR_URL"], env["NR_KEY"], env["NR_SECRET"])
    if env.get("NR_HOST"):
        erp.headers["Host"] = env["NR_HOST"]
    t0 = time.time()
    try:
        user = erp.call("frappe.auth.get_logged_user")
        print(f"접속 성공: {env['NR_URL']} (사용자 {user})")
        if stage == "check":
            return
        if stage in ("setup", "all"):
            import nr_setup
            nr_setup.run(erp)
        if stage in ("master", "all"):
            import nr_master
            nr_master.Master(erp, env["NR_DATA"]).run()
        if stage in ("tx", "all"):
            import nr_tx
            nr_tx.Loader(erp, env["NR_DATA"], user).run(until=until)
        if stage in ("finish", "all"):
            import nr_finish
            nr_finish.run(erp, env["NR_DATA"])
        if stage == "plan":
            import nr_tx
            nr_tx.Loader(erp, env["NR_DATA"], user).build(verbose=True)
    except ERPError as e:
        print("\n[멈춤] ERPNext가 거절했어요:\n  " + str(e))
        print("이 화면을 그대로 보여주세요. 고친 뒤 같은 명령을 다시 실행하면 이어서 진행해요.")
        sys.exit(2)
    finally:
        print(f"(소요 {int(time.time() - t0)}초, API 호출 {erp.calls}회)")


if __name__ == "__main__":
    main()
