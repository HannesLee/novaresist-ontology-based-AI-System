"""작업대 코드 실행기: python -I runner.py <작업 폴더>

code.py의 make(dfs)를 in.pkl 입력으로 실행해 out.pkl에 DataFrame을 쓴다.
"""
import pickle
import sys

import numpy as np  # noqa: F401  (생성 코드에서 사용)
import pandas as pd

d = sys.argv[1]
with open(f"{d}/in.pkl", "rb") as f:
    dfs = pickle.load(f)
ns = {"pd": pd, "np": np}
exec(open(f"{d}/code.py", encoding="utf-8").read(), ns)
out = ns["make"]({k: v.copy() for k, v in dfs.items()})
if isinstance(out, tuple):
    out = out[0]
if isinstance(out, pd.Series):
    out = out.reset_index()
if not isinstance(out, pd.DataFrame):
    raise TypeError(f"make()는 DataFrame을 돌려줘야 합니다 (받은 것: {type(out).__name__})")
out.columns = [str(c) for c in out.columns]
with open(f"{d}/out.pkl", "wb") as f:
    pickle.dump(out, f)
