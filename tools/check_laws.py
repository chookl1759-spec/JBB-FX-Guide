# 국가법령정보센터 현행(및 시행예정) 버전을 확인해 data/updates.json 의 changes 에 새 버전을 기록하고 checked_at 을 갱신합니다.
# 사용: python3 check_laws.py data/updates.json
# 환경변수 LAW_OC(국가법령정보센터 Open API 인증키)가 있으면 API를, 없으면 웹페이지를 읽어 확인합니다.
#
# 버전 식별:
#   - 법령·고시는 발령(공포)번호 "제2026-110호"로 구분합니다.
#   - 금융감독원 시행세칙처럼 발령번호가 없는 행정규칙은 발령일자로 구분합니다(내부 식별자 "D20240130").
# 종료 코드:
#   - 일부 법령을 확인하지 못해도 읽어 온 법령은 반영하고 0으로 끝냅니다(GitHub 경고로만 표시).
#   - 대상 법령을 하나도 확인하지 못했을 때만 1로 끝냅니다.
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
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(2 ** (i + 1))


def ymd(s):
    """'20261203' 또는 '2026. 12. 3.' → '2026.12.3'"""
    s = re.sub(r"\D", " ", str(s or "")).split()
    if len(s) == 1 and len(s[0]) == 8:
        s = [s[0][:4], s[0][4:6], s[0][6:]]
    if len(s) < 3:
        return None
    return f"{int(s[0])}.{int(s[1])}.{int(s[2])}"


def date_id(d):
    """'2024.1.30' → 'D20240130' (발령번호가 없는 행정규칙의 버전 식별자)"""
    d = ymd(d)
    if not d:
        return None
    y, m, dd = d.split(".")
    return f"D{int(y):04d}{int(m):02d}{int(dd):02d}"


def vid(s):
    """버전 문자열에서 식별자를 꺼냅니다: '제2026-110호' → '2026-110', '(2024.1.30 발령' → 'D20240130'"""
    m = re.search(r"제\s*([\d-]+)\s*호", s or "")
    if m:
        return m.group(1)
    m = re.search(r"(\d{4}\.\s*\d{1,2}\.\s*\d{1,2})\.?\s*발령", s or "")
    return date_id(m.group(1)) if m else None


def make_admrul(kind, number, issued, effective, rev=""):
    """행정규칙 결과 한 건. 번호가 없으면 발령일자를 식별자로 씁니다."""
    kind = re.sub(r"\s+", "", kind or "")
    issued = ymd(issued)
    if number:
        version = f"{kind} 제{number}호" + (f" ({issued} 발령)" if issued else "")
        ident = number
    else:
        if not issued:
            raise RuntimeError("발령번호·발령일자를 모두 읽지 못함")
        version = f"{kind} ({issued} 발령{', ' + rev.strip() if rev and rev.strip() else ''})"
        ident = date_id(issued)
    return {"number": ident, "version": version, "effective": ymd(effective)}


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
            n = re.sub(r"[^\d-]", "", str(it.get("발령번호", "") or ""))
            out.append(make_admrul(f"{it.get('소관부처명', '')}{it.get('행정규칙종류', '')}", n or None,
                                   it.get("발령일자"), it.get("시행일자"), it.get("제개정구분명", "")))
    return out


# 행정규칙 본문 머리말:
#   [시행 2026. 11. 2.] [재정경제부고시 제2026-110호, 2026. 10. 30., 일부개정]
#   [시행 2024. 1. 31.] [금융감독원세칙 , 2024. 1. 30., 일부개정]   ← 발령번호 없음
ADM_HEAD = re.compile(
    r"\[\s*시행\s*(?P<eff>\d{4}\.\s*\d{1,2}\.\s*\d{1,2}\.?)\s*\]\s*"
    r"\[\s*(?P<kind>[가-힣A-Za-z·\s]+?)\s*(?:제\s*(?P<num>[\d-]+)\s*호)?\s*,\s*"
    r"(?P<iss>\d{4}\.\s*\d{1,2}\.\s*\d{1,2}\.?)\s*,?\s*(?P<rev>[가-힣\s]*)\]")


def parse_admrul_head(text):
    t = re.sub(r"<[^>]+>", " ", text).replace("&nbsp;", " ")
    t = re.sub(r"\s+", " ", t)
    m = ADM_HEAD.search(t)
    if m:
        return make_admrul(m.group("kind"), m.group("num"), m.group("iss"), m.group("eff"), m.group("rev"))
    # 예전 방식(머리말을 못 찾았을 때): 고시·훈령·예규·공고·세칙 + 제○호
    n = re.search(r"([가-힣]+(?:고시|훈령|예규|공고|세칙))\s*제\s*([\d-]+)\s*호", t)
    e = re.search(r"시행\s*(\d{4}\.\s*\d{1,2}\.\s*\d{1,2}\.?)", t)
    if n:
        return make_admrul(n.group(1), n.group(2), None, e.group(1) if e else None)
    raise RuntimeError("발령번호·발령일자를 읽지 못함")


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
    return [parse_admrul_head(d)]


def main(path):
    data = json.load(open(path, encoding="utf-8"))
    base = data.setdefault("baseline", {})
    changes = data.setdefault("changes", [])
    known = {(c.get("law"), vid(c.get("version"))) for c in changes}
    today = NOW.date()
    new, errors, checked, registered = [], [], [], []

    for key, name, kind in TARGETS:
        try:
            found = []
            if OC:
                try:
                    found = via_api(name, kind)
                except Exception as e:
                    print(f"API 확인 실패, 웹페이지로 재시도: {key}: {e}")
            if not found:
                found = via_web(name, kind)
        except Exception as e:
            errors.append(f"{key}: {e}")
            continue
        found = [f for f in found if f.get("number")]
        if not found:
            errors.append(f"{key}: 결과 없음")
            continue
        checked.append(key)

        # 기준 버전이 아직 없으면(처음 확인하는 법령) 지금 버전을 기준으로 등록만 하고 '새 버전'으로 알리지 않음
        if key not in base:
            f0 = found[0]
            base[key] = f0["version"] + (f" ({f0['effective']} 시행)" if f0.get("effective") and "시행" not in f0["version"] else "")
            registered.append(f"- {key}: {base[key]}")
            print("기준 버전 등록:", registered[-1])
            continue

        for f in found:
            n = f["number"]
            if n == vid(base.get(key)) or (key, n) in known:
                continue
            eff = f.get("effective")
            try:
                future = bool(eff) and dt.date(*map(int, eff.split("."))) > today
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

    print(f"확인 완료 {len(checked)}/{len(TARGETS)}건")
    for e in errors:
        print("확인 실패:", e)
        print(f"::warning title=법령 확인 실패::{e}")  # GitHub Actions 화면에 경고로 표시 (작업은 계속)

    # 하나라도 확인했으면 읽어 온 결과를 저장하고 checked_at 갱신
    if checked:
        data["checked_at"] = NOW.strftime("%Y-%m-%d %H:%M KST")
        tmp = path + ".tmp"
        json.dump(data, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        json.load(open(tmp, encoding="utf-8"))
        os.replace(tmp, path)

    gh_out = os.environ.get("GITHUB_OUTPUT")
    if gh_out:
        with open(gh_out, "a", encoding="utf-8") as fh:
            if new:
                fh.write("new_changes<<EOF\n" + "\n".join(new) + "\nEOF\n")
            if errors:
                fh.write("check_errors<<EOF\n" + "\n".join("- " + e for e in errors) + "\nEOF\n")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write(f"### 법령 개정 점검 {NOW.strftime('%Y-%m-%d %H:%M KST')}\n\n확인 {len(checked)}/{len(TARGETS)}건\n\n")
            for title, rows in (("새 버전", new), ("기준 버전 등록", registered), ("확인 실패", ["- " + e for e in errors])):
                if rows:
                    fh.write(f"**{title}**\n\n" + "\n".join(rows) + "\n\n")

    if not checked:
        sys.exit(1)  # 하나도 확인하지 못했을 때만 실패 처리(사이트 접속 장애 등) → GitHub가 실패 메일 발송


if __name__ == "__main__":
    main(sys.argv[1])
