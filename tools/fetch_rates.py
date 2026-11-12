# 서울외국환중개 일별 최초고시 매매기준율을 받아 data/rates.json 에 합칩니다.
# 사용: python3 tools/fetch_rates.py data/rates.json
import json, sys, os, re, time, datetime as dt, urllib.request, concurrent.futures as cf
URL = "http://www.smbs.biz/Flash/TodayExRate_flash.jsp?tr_date={}"
UNITS = {"JPY": 100, "IDR": 100, "VND": 100}
KST = dt.timezone(dt.timedelta(hours=9))
path = sys.argv[1]
def get(d):
    for i in range(3):
        try:
            with urllib.request.urlopen(URL.format(d.isoformat()), timeout=30) as r:
                txt = r.read().decode("utf-8", "replace")
            break
        except Exception:
            if i == 2: raise
            time.sleep(5)
    return d.isoformat(), {k: float(v.replace(",", "")) for k, v in re.findall(r"&([A-Z]{3})=([\d,\.]+)", txt)}
today = dt.datetime.now(KST).date()
data = json.load(open(path, encoding="utf-8"))
rates = data.get("rates", {})
days = [today - dt.timedelta(days=i) for i in range(11)]
days = [d for d in days if d.weekday() < 5]
with cf.ThreadPoolExecutor(4) as ex:
    for k, v in ex.map(get, days):
        if len(v) >= 30: rates[k] = v
        elif not v.get("USD"): rates.pop(k, None)
keep = sorted(rates)[-420:]
rates = {k: rates[k] for k in keep}
data = {"source": "서울외국환중개(주) 일별 최초고시 매매기준율 및 재정된 매매기준율",
 "source_url": "http://www.smbs.biz/ExRate/TodayExRate.jsp",
 "note": "원화 기준 고시율. JPY·IDR·VND는 100단위 기준. 미화 환산은 해당 통화의 재정된 매매기준율 ÷ 미화 매매기준율로 계산",
 "units": UNITS, "updated_at": dt.datetime.now(KST).strftime("%Y-%m-%d %H:%M KST"),
 "latest": keep[-1], "rates": rates, "partial": None}
json.dump(data, open(path, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
lt = keep[-1]; print("latest", lt, "USD", rates[lt]["USD"], "count", len(rates[lt]), "dates", len(rates))
usd = rates[lt]["USD"]
if not (900 <= usd <= 2500) or len(rates[lt]) < 30:
    sys.exit(f"이상값: USD {usd}, 통화 수 {len(rates[lt])}")
