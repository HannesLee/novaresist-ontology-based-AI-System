"""ERPNext REST 클라이언트 (Frappe v15/v16). 파이썬 기본 라이브러리만 사용(추가 설치 불필요).

토큰 인증(API Key/Secret)으로 접속해서 문서를 만들고, 제출하고, 취소한다.
실패하면 서버 에러를 보여주고 멈춘다(다시 실행하면 이어서 진행).
"""
import json
import time
import urllib.error
import urllib.parse
import urllib.request


class ERPError(Exception):
    pass


class ERP:
    def __init__(self, url, key, secret, verbose=False):
        self.url = url.rstrip("/")
        self.headers = {
            "Authorization": f"token {key}:{secret}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        # 프록시 설정을 무시하고 직접 접속 (로컬 ERPNext)
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        self.verbose = verbose
        self.calls = 0

    # ---------- 저수준 ----------
    def _req(self, method, path, params=None, data=None):
        url = self.url + urllib.parse.quote(path, safe="/:")
        if params:
            url += "?" + urllib.parse.urlencode(params)
        body = data.encode("utf-8") if isinstance(data, str) else data
        last = None
        for attempt in range(5):
            req = urllib.request.Request(url, data=body, method=method, headers=self.headers)
            try:
                with self.opener.open(req, timeout=600) as r:
                    self.calls += 1
                    txt = r.read().decode("utf-8")
                    return json.loads(txt) if txt else {}
            except urllib.error.HTTPError as e:
                self.calls += 1
                txt = e.read().decode("utf-8", "replace")
                if e.code in (502, 503, 504) or (e.code == 417 and "Deadlock" in txt) or \
                        "QueryTimeoutError" in txt or "Lock wait timeout" in txt:
                    last = f"HTTP {e.code}"
                    time.sleep(3 * (attempt + 1))
                    continue
                raise ERPError(self._explain(e.code, txt))
            except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as e:
                last = e
                time.sleep(3 * (attempt + 1))
        raise ERPError(f"서버 응답 없음 ({self.url}): {last}")

    @staticmethod
    def _explain(code, txt):
        try:
            j = json.loads(txt)
        except Exception:
            return f"HTTP {code}: {txt[:800]}"
        msgs = []
        if j.get("_server_messages"):
            try:
                for m in json.loads(j["_server_messages"]):
                    try:
                        msgs.append(json.loads(m).get("message", m))
                    except Exception:
                        msgs.append(m)
            except Exception:
                msgs.append(j["_server_messages"])
        if j.get("exception"):
            msgs.append(j["exception"])
        if not msgs and j.get("exc"):
            msgs.append(str(j["exc"])[-800:])
        return f"HTTP {code}: " + " | ".join(str(m) for m in msgs)[:1500]

    # ---------- 문서 ----------
    def get(self, doctype, name):
        try:
            return self._req("GET", f"/api/resource/{doctype}/{name}")["data"]
        except ERPError as e:
            if "404" in str(e) or "DoesNotExistError" in str(e):
                return None
            raise

    def exists(self, doctype, name):
        r = self.call("frappe.client.get_value", doctype=doctype, filters={"name": name}, fieldname="name")
        return bool(r)

    def get_list(self, doctype, filters=None, fields=("name",), limit=0, order_by=None):
        params = {"fields": json.dumps(list(fields)), "limit_page_length": limit}
        if filters:
            params["filters"] = json.dumps(filters, ensure_ascii=False)
        if order_by:
            params["order_by"] = order_by
        return self._req("GET", f"/api/resource/{doctype}", params=params)["data"]

    def names(self, doctype, filters=None):
        return {d["name"] for d in self.get_list(doctype, filters=filters)}

    def insert(self, doc):
        return self._req("POST", f"/api/resource/{doc['doctype']}",
                         data=json.dumps(doc, ensure_ascii=False, default=str))["data"]

    def update(self, doctype, name, values):
        return self._req("PUT", f"/api/resource/{doctype}/{name}",
                         data=json.dumps(values, ensure_ascii=False, default=str))["data"]

    def delete(self, doctype, name):
        return self._req("DELETE", f"/api/resource/{doctype}/{name}")

    def submit(self, doc):
        return self.call_post("frappe.client.submit", doc=doc)

    def cancel(self, doctype, name):
        return self.call_post("frappe.client.cancel", doctype=doctype, name=name)

    def set_value(self, doctype, name, field, value=None):
        if isinstance(field, dict):
            return self.call_post("frappe.client.set_value", doctype=doctype, name=name, fieldname=field)
        return self.call_post("frappe.client.set_value", doctype=doctype, name=name, fieldname=field, value=value)

    def set_single(self, doctype, values):
        return self.call_post("frappe.client.set_value", doctype=doctype, name=doctype, fieldname=values)

    # ---------- 메서드 ----------
    def call(self, method, **params):
        p = {k: (json.dumps(v, ensure_ascii=False, default=str) if isinstance(v, (dict, list)) else v)
             for k, v in params.items()}
        return self._req("GET", f"/api/method/{method}", params=p).get("message")

    def call_post(self, method, **data):
        body = {k: (json.dumps(v, ensure_ascii=False, default=str) if isinstance(v, (dict, list)) else v)
                for k, v in data.items()}
        return self._req("POST", f"/api/method/{method}", data=json.dumps(body, ensure_ascii=False)).get("message")
