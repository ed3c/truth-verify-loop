#!/usr/bin/env bash
# tv-preverify.sh — web-era T0 pre-verifier for the truth-verify loop.
# Mechanically gate claims.jsonl / verdicts.jsonl BEFORE any judge (Fable/Opus) token.
# Disk-anchor sibling: kb-ingest/verify-claims.sh (repo-wiki era). Same discipline:
#   HARD failure => exit 1, bounce to the author (extractor/worker), ZERO judge cost.
#   ADVISORY     => reported, never fails the pass (a dead source != a false claim).
#
# Modes:
#   --claims   <claims.jsonl> --article <article.md>              [--report F]
#     H1' schema : each line has claim_id/type/text_quote/source_span; type in
#                  {TYPE_A,TYPE_B,TYPE_C,TYPE_D}; claim_id unique.            (HARD)
#     H2' quote  : text_quote (ws-normalized) is a fixed-string substring of the
#                  article; paraphrase-as-quote => FAIL.                       (HARD)
#   --verdicts <verdicts.jsonl> --claims <claims.jsonl> --run-id <id> [--report F]
#     H3' evidence : TYPE_A/B with verdict SUPPORTED|REFUTED must carry evidence[].url;
#                    fetch each url (curl, timeout+UA, cached under runs/<id>/cache/);
#                    ws-normalized evidence[].quote must fixed-string-match the fetched
#                    (tag-stripped) page.
#                      fetch fail (net/4xx/5xx)     => ADVISORY "UNRESOLVED" (not HARD).
#                      fetch ok but quote absent    => HARD FAIL (fabrication suspicion).
#     H4' contract : TYPE_C => reasoning_chain non-empty; TYPE_D => evidence AND
#                    reasoning_chain both null AND verdict==OPINION.           (HARD)
#
# Contract SSOT: truth-verify/contracts/tv-extract.prompt.md (claims side),
#                truth-verify/contracts/tv-verify.prompt.md  (verdicts side, slice 04),
#                docs/plans/2026-07-05-truth-verify-loop/CONTEXT.md §4 (locked schema).
# Zero deps: POSIX sh/awk/sed/tr/grep + curl. No jq, no assoc arrays (macOS bash 3.2).
set -uo pipefail

# --- args -------------------------------------------------------------------
CLAIMS=""; VERDICTS=""; ARTICLE=""; RUNID=""; REPORT=""
while [ $# -gt 0 ]; do
  case "$1" in
    --claims)   CLAIMS="${2:?--claims needs a file}";   shift 2 ;;
    --verdicts) VERDICTS="${2:?--verdicts needs a file}"; shift 2 ;;
    --article)  ARTICLE="${2:?--article needs a file}";  shift 2 ;;
    --run-id)   RUNID="${2:?--run-id needs an id}";       shift 2 ;;
    --report)   REPORT="${2:?--report needs a path}";     shift 2 ;;
    *) echo "FATAL: unknown arg: $1" >&2; exit 2 ;;
  esac
done

if [ -n "$VERDICTS" ]; then MODE=verdicts; else MODE=claims; fi

TAB="$(printf '\t')"
UA="Mozilla/5.0 (compatible; truth-verify-T0/1.0; +local pre-verifier)"

norm() { tr -s '[:space:]' ' ' | sed 's/^ //; s/ $//'; }

# html_to_text: best-effort tag strip for evidence-quote matching (see design note).
# Not a browser: no JS, no CSS layout, greedy script/style removal, few entities only.
# html_to_text:python3 stdlib HTMLParser(沿 slice 02 fixture 執行者驗證過的抽文法)。
# 前身 sed 版的 `s/<script...>.*<\/script>//` 貪婪 .* 在單行 Next.js 頁(280KB、多對 script)
# 上從第一個 <script> 吃到最後一個 </script> → 整頁清空 → 14/14 evidence 偽 FAIL
# (2026-07-05 baseline-01 實測;小頁單對 script 測試測不出)。python3 已是 t0 工具鏈依賴。
html_to_text() {
  python3 -c '
import sys, html
from html.parser import HTMLParser
class P(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.out = []
    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1
    def handle_endtag(self, tag):
        if tag in ("script", "style") and self.skip > 0:
            self.skip -= 1
    def handle_data(self, data):
        if not self.skip:
            self.out.append(data)
p = P()
p.feed(sys.stdin.read())
# "".join(非 " ".join):行內節點貼緊(footnote [3] 不變 [ 3 ]),文件原生空白由 data 保留
# ——對齊 slice 02 fixture 抽取器的正規化慣例(canonical 正文即 worker 引用錨)。
sys.stdout.write("".join(p.out))
' | norm
}

# ---------------------------------------------------------------------------
# Shared awk library: escape-aware JSON string reader.
#   js(s,i)   : i points at the OPENING quote of a JSON string in s; decodes it
#               into global RET, sets global NEXT to just past the closing quote.
#               handles \" \\ \/ \n \t \r \uXXXX(->space). Escaped quotes never
#               terminate, so markers like "url":" can't appear inside a value.
#   jstr(l,k) : value of top-level string key k in line l; RET=value, returns 1;
#               returns 0 (RET="") if key absent or value not a string (null).
#               Tolerates whitespace after the colon (json.dumps default emits
#               `"k": "` — a literal-marker match here misreported 35/35 rows as
#               missing claim_id, tracer03 2026-07-05; parser tolerance beats
#               contract admonition).
# Emitted once as a here-string prelude, reused by both modes.
# ---------------------------------------------------------------------------
AWKLIB='
function js(s,i,   out,c,c2){ i++; out="";
  while(i<=length(s)){ c=substr(s,i,1);
    if(c=="\\"){ c2=substr(s,i+1,1);
      if(c2=="n"||c2=="t"||c2=="r"){ out=out" " } else if(c2=="u"){ out=out" "; i+=4 }
      else { out=out c2 } i+=2 }
    else if(c=="\""){ NEXT=i+1; RET=out; return }
    else { out=out c; i++ } }
  NEXT=i; RET=out }
function jstr(l,k,   q,p,i,c){ q="\"" k "\":"; p=index(l,q);
  if(p==0){ RET=""; return 0 }
  i=p+length(q);
  while(i<=length(l)){ c=substr(l,i,1); if(c==" "||c=="\t") i++; else break }
  if(substr(l,i,1)!="\""){ RET=""; return 0 }
  js(l, i); return 1 }
function jvpos(s,k,   q,p,i,c){ q="\"" k "\":"; p=index(s,q); if(p==0) return 0
  i=p+length(q);
  while(i<=length(s)){ c=substr(s,i,1); if(c==" "||c=="\t") i++; else break }
  if(substr(s,i,1)!="\"") return 0; return i }
function jnull(l,k,   q,p,i,c){ q="\"" k "\":"; p=index(l,q); if(p==0) return 0
  i=p+length(q);
  while(i<=length(l)){ c=substr(l,i,1); if(c==" "||c=="\t") i++; else break }
  return substr(l,i,4)=="null" }
'
# jvpos/jnull:jstr 同族的空白容忍 helper。判官 round-1(2026-07-05)實測:--verdicts 模式三處
# raw index() 硬編零空白 pattern,對 json.dumps 預設輸出 H3'=14/H4'=18 全偽陽性,evidence
# fetch 迴圈整輪未執行——與 tracer03 的 jstr() 同一 bug 家族,本次一併清掉。

TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT

# ===========================================================================
# MODE: --claims  (H1' schema, H2' verbatim quote)
# ===========================================================================
if [ "$MODE" = claims ]; then
  [ -n "$CLAIMS" ]  || { echo "FATAL: --claims requires a claims.jsonl" >&2; exit 2; }
  [ -f "$CLAIMS" ]  || { echo "FATAL: claims file not found: $CLAIMS" >&2; exit 2; }
  [ -f "$ARTICLE" ] || { echo "FATAL: --article file not found: $ARTICLE" >&2; exit 2; }
  REPORT="${REPORT:-./preverify-claims.md}"
  : > "$TMP/h1"; : > "$TMP/h2"; : > "$TMP/rows"

  # H1' schema + emit rows (cid TAB type TAB ws-normalized-quote) for H2'
  awk "$AWKLIB"'
    $0 ~ /^[[:space:]]*$/ { next }
    { nb++; line=$0
      okid=jstr(line,"claim_id");   cid=RET
      oktp=jstr(line,"type");       typ=RET
      okq =jstr(line,"text_quote"); q=RET
      oksp=jstr(line,"source_span");sp=RET
      if(!okid||cid==""){ print "- line " nb ": missing/empty claim_id" > H1; next }
      if(!oktp||typ==""){ print "- " cid ": missing/empty type" > H1 }
      else if(typ!="TYPE_A"&&typ!="TYPE_B"&&typ!="TYPE_C"&&typ!="TYPE_D"){
        print "- " cid ": type not in {TYPE_A..D}: \"" typ "\"" > H1 }
      if(!okq ||q ==""){ print "- " cid ": missing/empty text_quote" > H1 }
      if(!oksp||sp==""){ print "- " cid ": missing/empty source_span" > H1 }
      if(seen[cid]++){    print "- " cid ": duplicate claim_id" > H1 }
      gsub(/[ \t\r\n]+/," ",q); sub(/^ /,"",q); sub(/ $/,"",q)
      if(q!="") print cid "\t" typ "\t" q > ROWS
    }
    END{ print nb+0 > NC }
  ' H1="$TMP/h1" ROWS="$TMP/rows" NC="$TMP/nc" "$CLAIMS"

  # H2' verbatim: normalized quote must be a fixed-string substring of the article
  nart="$(norm < "$ARTICLE")"
  while IFS="$TAB" read -r cid typ q; do
    [ -n "$q" ] || continue
    case "$nart" in
      *"$q"*) : ;;
      *) echo "- $cid: text_quote NOT verbatim in article: \"$q\"" >> "$TMP/h2" ;;
    esac
  done < "$TMP/rows"

  nb=$(cat "$TMP/nc" 2>/dev/null || echo 0)
  nrows=$(wc -l < "$TMP/rows" | tr -d ' ')
  h1=$(wc -l < "$TMP/h1" | tr -d ' '); h2=$(wc -l < "$TMP/h2" | tr -d ' ')
  hard=$((h1 + h2)); verdict=PASS; [ "$hard" -gt 0 ] && verdict=FAIL
  {
    echo "# T0 pre-verify (claims) — $(basename "$CLAIMS") vs $(basename "$ARTICLE")"
    echo
    echo "Hard: H1' schema=$h1 · H2' quotes=$h2 → **$verdict**"
    echo "Seen: claims=$nb · quotes-checked=$nrows"
    if [ -s "$TMP/h1" ]; then echo; echo "## H1' schema"; cat "$TMP/h1"; fi
    if [ -s "$TMP/h2" ]; then echo; echo "## H2' verbatim quote"; cat "$TMP/h2"; fi
  } > "$REPORT"
  echo "PREVERIFY mode=claims claims=$nb schema_bad=$h1 quotes=$nrows quote_bad=$h2 verdict=$verdict report=$REPORT"
  [ "$verdict" = PASS ]
  exit
fi

# ===========================================================================
# MODE: --verdicts  (H3' evidence fetch+match, H4' contract completeness)
# ===========================================================================
[ -n "$CLAIMS" ]   || { echo "FATAL: --verdicts also needs --claims (for type lookup)" >&2; exit 2; }
[ -f "$VERDICTS" ] || { echo "FATAL: verdicts file not found: $VERDICTS" >&2; exit 2; }
[ -f "$CLAIMS" ]   || { echo "FATAL: claims file not found: $CLAIMS" >&2; exit 2; }
[ -n "$RUNID" ]    || { echo "FATAL: --verdicts requires --run-id (cache dir)" >&2; exit 2; }
REPORT="${REPORT:-./preverify-verdicts.md}"
: > "$TMP/h1"; : > "$TMP/h3"; : > "$TMP/h4"; : > "$TMP/adv"; : > "$TMP/vrows"

TV_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CACHE="$TV_ROOT/runs/$RUNID/cache"
mkdir -p "$CACHE"

# awk two-file join: build type[cid] from claims, then check verdicts.
# evseg(line): substring of the evidence array, bounded by the next top-level key
#   ,"reasoning_chain" (locked field order, CONTEXT §4). Escaped quotes make the
#   bound robust even if order drifts; markers can't occur inside a JSON string.
# next_pair(): consume SEG, emit URL/QUOTE of the next evidence object; 0 when none.
awk "$AWKLIB"'
  function evseg(line,   a,seg,b){ a=index(line,"\"evidence\":"); if(a==0) return "";
    seg=substr(line,a); b=index(seg,"\"reasoning_chain\""); if(b>1) seg=substr(seg,1,b-1);
    return seg }
  function next_pair(   iu,iq){
    iu=jvpos(SEG,"url"); if(iu==0) return 0
    js(SEG, iu); URL=RET; SEG=substr(SEG,NEXT)
    iq=jvpos(SEG,"quote")
    if(iq>0){ js(SEG, iq); QUOTE=RET; SEG=substr(SEG,NEXT) }
    else { QUOTE="" }
    return 1 }
  NR==FNR{ if($0 ~ /^[[:space:]]*$/) next
           jstr($0,"claim_id"); c=RET; jstr($0,"type"); t=RET
           if(c!="") type[c]=t; next }
  $0 ~ /^[[:space:]]*$/ { next }
  { line=$0; nv++
    jstr(line,"claim_id"); cid=RET
    jstr(line,"verdict");  vd=RET
    if(cid==""){ print "- line " FNR ": verdict missing claim_id" > H1; next }
    tp = (cid in type) ? type[cid] : ""
    if(tp==""){ print "- " cid ": claim_id not present in claims.jsonl" > H1 }
    rc_null = jnull(line,"reasoning_chain")
    jstr(line,"reasoning_chain"); rc=RET
    ev_null = jnull(line,"evidence")
    # H4 contract completeness
    if(tp=="TYPE_C" && (rc_null||rc=="")){
      print "- " cid ": TYPE_C requires non-empty reasoning_chain" > H4 }
    if(tp=="TYPE_D"){
      if(!ev_null){ print "- " cid ": TYPE_D evidence must be null" > H4 }
      if(!rc_null){ print "- " cid ": TYPE_D reasoning_chain must be null" > H4 }
      if(vd!="OPINION"){ print "- " cid ": TYPE_D verdict must be OPINION (got " vd ")" > H4 }
    }
    # H3 evidence rows (only where a URL is contractually required)
    if((tp=="TYPE_A"||tp=="TYPE_B") && (vd=="SUPPORTED"||vd=="REFUTED")){
      SEG=evseg(line); n=0
      while(next_pair()){ n++
        gsub(/[ \t\r\n]+/," ",URL); gsub(/[ \t\r\n]+/," ",QUOTE)
        print cid "\t" URL "\t" QUOTE > VROWS }
      if(n==0){ print "- " cid ": " tp " " vd " has no evidence[].url" > H3 }
    }
  }
  END{ print nv+0 > NV }
' H1="$TMP/h1" H3="$TMP/h3" H4="$TMP/h4" VROWS="$TMP/vrows" NV="$TMP/nv" \
  "$CLAIMS" "$VERDICTS"

# H3' fetch + match (bash side; curl per url, cache, tag-strip, fixed-string).
nvrows=0
while IFS="$TAB" read -r cid url quote; do
  [ -n "$url" ] || continue
  nvrows=$((nvrows+1))
  key="$(printf '%s' "$url" | cksum | tr -cd '0-9')"
  cf="$CACHE/$key.html"
  if [ ! -s "$cf" ]; then
    if curl -fsSL --max-time 20 -A "$UA" "$url" > "$cf.part" 2>/dev/null; then
      mv "$cf.part" "$cf"
    else
      rm -f "$cf.part"
      echo "- $cid: UNRESOLVED (fetch failed, source unreachable/4xx/5xx): $url" >> "$TMP/adv"
      continue
    fi
  fi
  q="$(printf '%s' "$quote" | norm)"
  if [ -z "$q" ]; then
    echo "- $cid: empty evidence quote for $url" >> "$TMP/h3"; continue
  fi
  ntext="$(html_to_text < "$cf")"
  case "$ntext" in
    *"$q"*) : ;;
    *) echo "- $cid: evidence quote NOT found in fetched page ($url): \"$q\"" >> "$TMP/h3" ;;
  esac
done < "$TMP/vrows"

nv=$(cat "$TMP/nv" 2>/dev/null || echo 0)
h1=$(wc -l < "$TMP/h1" | tr -d ' '); h3=$(wc -l < "$TMP/h3" | tr -d ' ')
h4=$(wc -l < "$TMP/h4" | tr -d ' '); adv=$(wc -l < "$TMP/adv" | tr -d ' ')
hard=$((h1 + h3 + h4)); verdict=PASS; [ "$hard" -gt 0 ] && verdict=FAIL
{
  echo "# T0 pre-verify (verdicts) — $(basename "$VERDICTS") [run $RUNID]"
  echo
  echo "Hard: H1' link=$h1 · H3' evidence=$h3 · H4' contract=$h4 → **$verdict**"
  echo "Advisory: UNRESOLVED=$adv · verdicts=$nv · evidence-checked=$nvrows"
  if [ -s "$TMP/h1" ];  then echo; echo "## H1' claim link"; cat "$TMP/h1"; fi
  if [ -s "$TMP/h3" ];  then echo; echo "## H3' evidence fetch+match"; cat "$TMP/h3"; fi
  if [ -s "$TMP/h4" ];  then echo; echo "## H4' contract completeness"; cat "$TMP/h4"; fi
  if [ -s "$TMP/adv" ]; then echo; echo "## UNRESOLVED (advisory — dead source, not a false claim)"; cat "$TMP/adv"; fi
} > "$REPORT"
echo "PREVERIFY mode=verdicts verdicts=$nv link_bad=$h1 evid=$nvrows evid_bad=$h3 contract_bad=$h4 unresolved=$adv verdict=$verdict report=$REPORT"
[ "$verdict" = PASS ]
