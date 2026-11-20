"""Organisation evidence collector. Network scope excludes mail and contact discovery."""
import datetime as dt
import hashlib
import json
import os
import re
import sys
import time
import unicodedata
from html.parser import HTMLParser
from urllib import error, parse, request, robotparser

AGENT = "OrgEvidenceCollector/1.0"
API = "https://recherche-entreprises.api.gouv.fr/search"
DIRECTORY = "https://data.economie.gouv.fr/api/explore/v2.1/catalog/datasets/activateurs-france-num/records"
class Closed(Exception):
    pass

class Withdrawn(Closed):
    pass

class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None

net = request.build_opener(NoRedirect())
robots, last, cache = {}, {}, {}

def fetch(url, body=None, headers=None):
    u = parse.urlsplit(url)
    if u.scheme != "https" or u.username or u.password or u.port not in (None,443):
        raise Closed()
    for attempt in range(2):
        time.sleep(max(0, 1.25 - (time.monotonic() - last.get(u.hostname,0))))
        last[u.hostname] = time.monotonic()
        req = request.Request(url, data=body, headers={"User-Agent":AGENT, **(headers or {})})
        try:
            with net.open(req, timeout=14) as res:
                data = res.read(3_000_001)
                if len(data)>3_000_000: raise Closed()
                return data
        except error.HTTPError as e:
            if attempt or e.code not in (502,503,504) or body is not None: raise
            time.sleep(2)

class Page(HTMLParser):
    def __init__(self,data):
        super().__init__(convert_charrefs=True)
        self.parts,self.links,self.skip=[],[],0
        self.websites=[]
        self.anchor=None
        self.feed(data)
        self.text=" ".join(" ".join(self.parts).split())
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag in ("script","style"): self.skip+=1
        if tag=="a" and attrs.get("href"):
            self.links.append(attrs["href"]); self.anchor=attrs["href"]
    def handle_endtag(self,tag):
        if tag=="a": self.anchor=None
        if tag in ("script","style"): self.skip=max(0,self.skip-1)
    def handle_data(self,data):
        if not self.skip: self.parts.append(data)
        if self.anchor and "site internet" in data.casefold(): self.websites.append(self.anchor)

def page(url):
    if url in cache: return cache[url]
    u=parse.urlsplit(url)
    origin="https://"+u.netloc
    if origin not in robots:
        rp=robotparser.RobotFileParser()
        try: rp.parse(fetch(origin+"/robots.txt").decode().splitlines())
        except error.HTTPError as exc:
            if exc.code!=404: raise
            rp.parse([])
        robots[origin]=rp
    rp=robots[origin]
    delay=rp.crawl_delay(AGENT) or 0
    if not rp.can_fetch(AGENT,url) or delay>10: raise Closed()
    if delay: time.sleep(delay)
    cache[url]=Page(fetch(url).decode("utf-8","replace"))
    return cache[url]

def norm(v):
    return " ".join(unicodedata.normalize("NFKC",v).casefold().split())

def owned(url,domain):
    host=parse.urlsplit(url).hostname or ""
    return url.startswith("https://") and (host==domain or host.endswith("."+domain))

def verify(c,now):
    siren=c["siren"]
    if not re.fullmatch(r"\d{9}",siren): raise Closed()
    api=API+"?"+parse.urlencode({"q":siren,"per_page":1,"minimal":"true","include":"siege"})
    matches=json.loads(fetch(api))["results"]
    org=next((x for x in matches if x["siren"]==siren),{})
    if org.get("etat_administratif")!="A" or org.get("statut_diffusion")!="O" or org.get("siege",{}).get("statut_diffusion_etablissement")!="O" or org.get("opposition_diffusion_commerciale") is not False: raise Withdrawn()
    if not owned(c["legal_url"],c["domain"]): raise Closed()
    legal=norm(page(c["legal_url"]).text)
    if norm(c["legal_snippet"]) not in legal or siren not in re.sub(r"[\s.]","",c["legal_snippet"]): raise Closed()
    proofs=[]
    for s in c["signals"]:
        if not owned(s["url"],c["domain"]): raise Closed()
        if norm(s["term"]) in norm(page(s["url"]).text):
            proof={k:s[k] for k in ("type","fact","term","url","published_at")}
            proof["observed_at"]=now
            proofs.append(proof)
    if not proofs: raise Closed()
    row={k:c[k] for k in ("siren","name","domain","legal_url","legal_snippet","fit","discovery_url","hypothesis","unknowns")}
    return dict(row,legal_name=org["nom_complet"],api_url=api,api_status="A",commercial_opposition=False,diffusion="O",siege_diffusion="O",api_checked_at=now,signals=proofs)

def open_candidate(url,name,source):
    # Only first-party pages with explicit reusable licensing qualify for automatic discovery.
    domain=parse.urlsplit(url).hostname
    if not domain or not re.fullmatch(r"(?:[a-z0-9-]+\.)+[a-z]{2,}",domain): return
    domain=domain.removeprefix("www.")
    if domain in ("linkedin.com","facebook.com","instagram.com","youtube.com","x.com","francenum.gouv.fr"): return
    if not owned(url,domain): return
    root=page(url)
    licenses=("https://creativecommons.org/licenses/by/","https://creativecommons.org/publicdomain/zero/")
    if not any(link.startswith(licenses) for link in root.links): return
    text=norm(root.text)
    if "saas" not in text or not any(t in text for t in ("entreprises","professionnels","b2b")): return
    links=[parse.urljoin(url,a) for a in root.links]
    legal_url=next((a for a in links if owned(a,domain) and re.search(r"mentions[-_/ ]legales|legal-notice",a,re.I)),None)
    if not legal_url: return
    match=re.search(r"\bSIREN\s*[:n° ]*([0-9]{3}[ .]?[0-9]{3}[ .]?[0-9]{3})\b",page(legal_url).text,re.I)
    if not match: return
    siren=re.sub(r"\D","",match[1])
    signals=[]
    for term,kind in (("équipe support","support"),("customer success","customer_success"),("parcours d’onboarding","onboarding")):
        if term in text: signals.append(dict(type=kind,term=term,url=url,published_at=None,fact="La présentation de "+name+" mentionne « "+term+" »."))
    if not signals: return
    return dict(name=name,siren=siren,domain=domain,legal_url=legal_url,legal_snippet=match[0],signals=signals,discovery_url=source,fit="L’éditeur présente un logiciel SaaS à destination des professionnels.",unknowns=["Volume de retours","Décision à éclairer","Accord du contact"],hypothesis="Pertinence pour une analyse des retours à qualifier.")
    
def discover(config,now):
    query={"limit":8,"select":"nom_de_la_structure,lien_url_site_france_num","order_by":"identifiant_de_la_structure"}
    total=json.loads(fetch(DIRECTORY+"?limit=1&select=identifiant_de_la_structure"))["total_count"]
    query["offset"]=(dt.date.fromisoformat(now[:10]).toordinal()*8)%max(total,1)
    rows=json.loads(fetch(DIRECTORY+"?"+parse.urlencode(query)))["results"]
    result=[]
    for row in rows:
        source=row["lien_url_site_france_num"]
        if not owned(source,"francenum.gouv.fr"): continue
        try: directory_page=page(source); links=directory_page.links
        except (Closed,error.URLError): continue
        for site in directory_page.websites[:1]:
            try: candidate=open_candidate(site,row["nom_de_la_structure"],source)
            except (Closed,error.URLError): continue
            if candidate: result.append(candidate)
        for domain,policy in config.get("discovery_domains",{}).items():
            if any(owned(link,domain) for link in links): result.append(dict(policy,discovery_url=source))
    return result

def collect(config,now):
    rows={}
    withdrawn=[]
    for candidate in config.get("watch",[]):
        if candidate["siren"] in rows: continue
        try: row=verify(candidate,now)
        except Withdrawn:
            withdrawn.append(candidate["siren"])
            continue
        rows[row["siren"]]=row
        if len(rows)==20: break
    if not rows and not withdrawn: raise Closed()
    return list(rows.values()),withdrawn

def main():
    now=dt.datetime.now(dt.timezone.utc).isoformat()
    rows,withdrawn=collect(json.loads(os.environ["SOURCE_CONFIG"]),now)
    digest=hashlib.sha256(json.dumps([rows,withdrawn],sort_keys=True).encode()).hexdigest()
    payload=json.dumps({"run_id":digest,"companies":rows,"withdrawn":withdrawn}).encode()
    dest=os.environ["DEPOSIT_URL"]
    if not dest.endswith("/api/ingest"): raise Closed()
    headers={"Content-Type":"application/json","OAI-Sites-Authorization":"Bearer "+os.environ["SITE_SERVICE"],"X-Radar-Key":os.environ["DEPOSIT_KEY"]}
    result=json.loads(fetch(dest,payload,headers))
    if "replayed" not in result: raise Closed()

if __name__=="__main__":
    try: main()
    except Exception:
        print("Collecte interrompue. Diagnostic opérationnel privé.",file=sys.stderr)
        sys.exit(1)
    print("Dépôt accepté.")

