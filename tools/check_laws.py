# 국가법령정보센터 현행(및 시행예정) 버전을 확인해 data/updates.json 의 changes 에 새 버전을 기록하고 checked_at 을 갱신합니다.
# 사용: python3 check_laws.py data/updates.json
# 환경변수 LAW_OC(국가법령정보센터 Open API 인증키)가 있으면 API를, 없으면 웹페이지를 읽어 확인합니다.
import json, os, re, sys, time, datetime as dt, urllib.request, urllib.parse

KST = dt.timezone(dt.timedelta(hours=9))
NOW = dt.datetime.now(KST)
OC = os.environ.get("LAW_OC", "").strip()
UA = {"User-Agent": "Mozilla/5.0 (JB-FX-Guide daily check)"}

# (updates.json baseline 키, 국가법령정보센터 정식 명칭, 종류)
TARGETS = [
    ("외국환거래법", "외국환거래법", "law"),
    ("외국환거래법 시행령", "외국환거래법 시행령", "law"),
    ("외국환거래규정", "외국환거래규정", "admrul"),
    ("외국인투자 촉진법", "외국인투자 촉진법", "law"),
    ("외국인투자 촉진법 시행령", "외국인투자 촉진법 시행령", "law"),
    ("외국인투자 촉진법 시행규칙", "외국인투자 촉진법 시행규칙", "law"),
    ("금융회사등의 해외진출에 관한 규정", "금융회사등의 해외진출에 관한 규정", "admrul"),
    ("금융회사등의 해외진출에 관한 규정 시행세칙", "금융회사등의 해외진출에 관한 규정 시행세칙", "admrul"),
]


def get(url, tries=3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:
            if i == tries - 1:
                raise
            time.sleep(2 ** (i + 1))


def ymd(s):
    """'20261203' 또는 '2026. 12. 3.' → '2026.12.3'"""
    s = re.sub(r"\D", " ", str(s)).split()
    if len(s) == 1 and len(s[0]) == 8:
        s = [s[0][:4], s[0][4:6], s[0][6:]]
    if len(s) < 3:
        return None
    return f"{int(s[0])}.{int(s[1])}.{int(s[2])}"


def as_list(x):
    return x if isinstance(x, list) else ([x] if x else [])


def page_url(name, kind, encoded=False):
    p = ("법령/" if kind == "law" else "행정규칙/") + name
    return "https://www.law.go.kr/" + (urllib.parse.quote(p) if encoded else p)


# ---------- 방법 1: Open API (LAW_OC 있을 때) ----------
def via_api(name, kind):
    out = []
    if kind == "law":
        for nw in ("3", "2"):  # 3=현행, 2=시행예정
            q = urllib.parse.urlencode({"OC": OC, "target": "law", "type": "JSON", "query": name, "nw": nw, "display": 20})
            j = json.loads(get("https://www.law.go.kr/DRF/lawSearch.do?" + q))
            for it in as_list(j.get("LawSearch", {}).get("law")):
                if re.sub(r"\s", "", it.get("법령명한글", "")) != re.sub(r"\s", "", name):
                    continue
                out.append({"number": str(it.get("공포번호", "")).strip(),
                            "version": f"{it.get('법령구분명', '')} 제{it.get('공포번호')}호 ({ymd(it.get('공포일자'))} 공포)",
                            "effective": ymd(it.get("시행일자"))})
    else:
        q = urllib.parse.urlencode({"OC": OC, "target": "admrul", "type": "JSON", "query": name, "display": 20})
        j = json.loads(get("https://www.law.go.kr/DRF/lawSearch.do?" + q))
        for it in as_list(j.get("AdmRulSearch", {}).get("admrul")):
            if re.sub(r"\s", "", it.get("행정규칙명", "")) != re.sub(r"\s", "", name):
                continue
            if it.get("현행연혁구분") and it.get("현행연혁구분") not in ("현행", "시행예정"):
                continue
            out.append({"number": str(it.get("발령번호", "")).strip(),
                        "version": f"{it.get('소관부처명', '')}{it.get('행정규칙종류', '')} 제{it.get('발령번호')}호 ({ymd(it.get('발령일자'))} 발령)",
                        "effective": ymd(it.get("시행일자"))})
    return out


# ---------- 방법 2: 웹페이지 (키 없을 때) ----------
def via_web(name, kind):
    html = get(page_url(name, kind, encoded=True))
    if kind == "law":
        m = re.search(r"lsInfoP\.do\?lsiSeq=(\d+)[^\"'<>]*?efYd=(\d{8})", html)
        if not m:
            raise RuntimeError("lsInfoP 링크를 찾지 못함")
        d = get(f"https://www.law.go.kr/LSW/lsInfoP.do?lsiSeq={m.group(1)}&efYd={m.group(2)}&chrClsCd=010202&urlMode=lsInfoP&ancYnChk=0")
        h = re.search(r"\[\s*시행\s*([\d.\s]+?)\s*\]\s*\[\s*([가-힣]+)\s*제\s*([\d-]+)\s*호\s*,\s*([\d.\s]+?)\s*,", d)
        if not h:
            raise RuntimeError("시행일·번호를 읽지 못함")
        return [{"number": h.group(3), "version": f"{h.group(2)} 제{h.group(3)}호 ({ymd(h.group(4))} 공포)",
                 "effective": ymd(h.group(1))}]
    m = re.search(r"admRulInfoP\.do\?admRulSeq=(\d+)", html)
    if not m:
        raise RuntimeError("admRulInfoP 링크를 찾지 못함")
    d = get(f"https://www.law.go.kr/LSW/admRulInfoP.do?admRulSeq={m.group(1)}&chrClsCd=010201")
    n = re.search(r"([가-힣]+(?:고시|훈령|예규|공고|세칙))\s*제\s*([\d-]+)\s*호", d)
    e = re.search(r"시행\s*(\d{4}\.\s*\d{1,2}\.\s*\d{1,2}\.?)", d)
    if not n:
        raise RuntimeError("발령번호를 읽지 못함")
    return [{"number": n.group(2), "version": f"{n.group(1)} 제{n.group(2)}호",
             "effective": ymd(e.group(1)) if e else None}]


def num(s):
    m = re.search(r"제\s*([\d-]+)\s*호", s or "")
    return m.group(1) if m else None


def main(path):
    data = json.load(open(path, encoding="utf-8"))
    base = data.get("baseline", {})
    changes = data.setdefault("changes", [])
    known = {(c.get("law"), num(c.get("version"))) for c in changes}
    today = NOW.date()
    new, errors = [], []

    for key, name, kind in TARGETS:
        try:
            found = via_api(name, kind) if OC else via_web(name, kind)
            if not found and OC:
                found = via_web(name, kind)
        except Exception as e:
            errors.append(f"{key}: {e}")
            continue
        if not found:
            errors.append(f"{key}: 결과 없음")
            continue
        for f in found:
            n = f["number"]
            if not n or n == num(base.get(key)) or (key, n) in known:
                continue
            eff = f.get("effective")
            try:
                future = eff and dt.date(*map(int, eff.split("."))) > today
            except Exception:
                future = False
            item = {
                "law": key,
                "version": f["version"],
                "effective": eff,
                "detected_at": today.isoformat(),
                "status": "공포(시행 전)" if future else "시행",
                "summary": f"국가법령정보센터에 새 버전({f['version']}, {eff} 시행)이 게시되었습니다. 개정 요지는 원문 확인 후 반영 예정입니다.",
                "details": "",
                "sources": [page_url(name, kind)],
                "fulltext_pending": True,
            }
            changes.append(item)
            known.add((key, n))
            new.append(f"- {key}: {f['version']} / 시행 {eff} ({item['status']})")
            print("새 버전:", new[-1])

    for e in errors:
        print("확인 실패:", e)

    # 하나라도 확인했으면 checked_at 갱신
    if len(errors) < len(TARGETS):
        data["checked_at"] = NOW.strftime("%Y-%m-%d %H:%M KST")
        tmp = path + ".tmp"
        json.dump(data, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        json.load(open(tmp, encoding="utf-8"))
        os.replace(tmp, path)

    gh_out = os.environ.get("GITHUB_OUTPUT")
    if gh_out and new:
        with open(gh_out, "a", encoding="utf-8") as fh:
            fh.write("new_changes<<EOF\n" + "\n".join(new) + "\nEOF\n")

    if errors:
        sys.exit(1)  # 일부라도 확인 못 하면 작업을 실패로 표시해 알림이 가게 함


if __name__ == "__main__":
    main(sys.argv[1])
