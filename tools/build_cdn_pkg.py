#!/usr/bin/env python3
"""Claude 버전용 공개 데이터 묶음(npm 패키지)을 만든다.
Claude 아티팩트는 외부 서버에 fetch 할 수 없지만, unpkg.com·cdn.jsdelivr.net/npm 의 스크립트는 불러올 수 있다.
그래서 매일 고시환율(data/rates.json)과 법령 점검 결과(data/updates.json)를 fxdata.js 한 파일로 묶어 npm 에 올린다.
공개 정보만 담는다(고객·직원 정보 없음).
사용: python3 tools/build_cdn_pkg.py <출력 폴더> <패키지 이름>
"""
import json, sys, os, hashlib, datetime
out, name = sys.argv[1], sys.argv[2]
os.makedirs(out, exist_ok=True)
rates = json.load(open("data/rates.json", encoding="utf-8"))
upd = json.load(open("data/updates.json", encoding="utf-8"))
body = json.dumps({"rates": rates, "updates": upd}, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
h = hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]
now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
js = ("/* 서울외국환중개 최초고시 매매기준율 · 외환 법령 현행 버전 점검 결과 (공개 정보) */\n"
      f"window.__FXDATA={body[:-1]},\"built_at\":\"{now:%Y-%m-%d %H:%M} KST\",\"hash\":\"{h}\"}};\n")
open(os.path.join(out, "fxdata.js"), "w", encoding="utf-8").write(js)
pkg = {"name": name, "version": f"{now.year}.{now.month * 100 + now.day}.{now.hour * 100 + now.minute}",
       "description": "Daily KRW reference exchange rates (Seoul Money Brokerage first fixing) and FX regulation version check results.",
       "main": "fxdata.js", "files": ["fxdata.js"], "license": "UNLICENSED", "fxhash": h}
json.dump(pkg, open(os.path.join(out, "package.json"), "w"), indent=2)
print(pkg["version"], h)
