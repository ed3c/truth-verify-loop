#!/usr/bin/env bash
# run-tests.sh — regression suite for tv-preverify.sh. Deterministic, offline where it
# matters (fetch results are seeded into the run cache; no live network for HARD cases).
set -uo pipefail
cd "$(dirname "$0")"
T0=../tv-preverify.sh
PASS=0; FAIL=0
ok(){ PASS=$((PASS+1)); echo "ok   - $1"; }
no(){ FAIL=$((FAIL+1)); echo "FAIL - $1"; }

# ---- html_to_text boundary (source the function out of the script) ----------
# Source out just the norm() (one-liner) and html_to_text() (block) definitions,
# so we unit-test them without running the script's main logic.
eval "$(grep '^norm()' "$T0")"
eval "$(awk '/^html_to_text\(\)/,/^}$/' "$T0")"

got="$(printf '<p>Hello <b>world</b> &amp; friends</p>' | html_to_text)"
[ "$got" = "Hello world & friends" ] && ok "html_to_text strips tags + decodes entity" \
  || no "html_to_text got: [$got]"

got="$(printf '<div>keep <script>var q="ghost";</script>this</div>' | html_to_text)"
case "$got" in *ghost*) no "html_to_text leaked script text: [$got]";; *) ok "html_to_text drops <script> body";; esac

got="$(printf 'A\n  quoted   line\twith\tgaps' | html_to_text)"
[ "$got" = "A quoted line with gaps" ] && ok "html_to_text norm collapses whitespace" \
  || no "html_to_text whitespace got: [$got]"

# 貪婪 wipe 回歸(baseline-01 2026-07-05):單行、兩對 script 夾真內容——sed 貪婪版整頁清空
got="$(printf '<html><head><script>a=1;</script></head><body><p>real content survives</p><script>b=2;</script></body></html>' | html_to_text)"
case "$got" in
  *"real content survives"*) ok "html_to_text single-line multi-script keeps content between" ;;
  *) no "html_to_text greedy-wipe regression got: [$got]" ;;
esac

echo "--- html_to_text: pass=$PASS fail=$FAIL"
# (Task 5 appends H1'/H2'/H3'/H4' end-to-end cases below, then the final tally + exit.)

# ===== H1'/H2' claims-mode cases =====
WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT
printf 'The number 17 is a prime number, and so is 19.\n' > "$WORK/art.md"

# H2' verbatim PASS
printf '%s\n' '{"claim_id":"c-1","type":"TYPE_C","text_quote":"The number 17 is a prime number","source_span":"L1","claim_norm":"17 is prime"}' > "$WORK/good.jsonl"
out="$(bash "$T0" --claims "$WORK/good.jsonl" --article "$WORK/art.md" --report "$WORK/r1.md")"; rc=$?
{ [ $rc -eq 0 ] && printf '%s' "$out" | grep -q 'verdict=PASS'; } \
  && ok "H2' verbatim quote PASSes" || no "H2' PASS case: rc=$rc out=[$out]"

# H2' paraphrase FAIL (not a substring of the article)
printf '%s\n' '{"claim_id":"c-1","type":"TYPE_C","text_quote":"17 and 19 are both primes","source_span":"L1","claim_norm":"17,19 prime"}' > "$WORK/para.jsonl"
out="$(bash "$T0" --claims "$WORK/para.jsonl" --article "$WORK/art.md" --report "$WORK/r2.md")"; rc=$?
{ [ $rc -eq 1 ] && printf '%s' "$out" | grep -q 'quote_bad=1'; } \
  && ok "H2' paraphrase FAILs (quote_bad=1, exit 1)" || no "H2' paraphrase case: rc=$rc out=[$out]"

# H1' bad type FAIL
printf '%s\n' '{"claim_id":"c-1","type":"TYPE_X","text_quote":"The number 17 is a prime number","source_span":"L1","claim_norm":"x"}' > "$WORK/badtype.jsonl"
out="$(bash "$T0" --claims "$WORK/badtype.jsonl" --article "$WORK/art.md" --report "$WORK/r3.md")"; rc=$?
{ [ $rc -eq 1 ] && printf '%s' "$out" | grep -q 'schema_bad=1'; } \
  && ok "H1' bad type FAILs (schema_bad=1)" || no "H1' bad type case: rc=$rc out=[$out]"

# H1'/H2' pretty-JSON tolerance (regression: tracer03 2026-07-05 — json.dumps default
# `": "` spacing was misreported as 35/35 missing claim_id by the literal-marker jstr()).
printf '%s\n' '{"claim_id": "c-1", "type": "TYPE_C", "text_quote": "The number 17 is a prime number", "source_span": "L1", "claim_norm": "17 is prime"}' > "$WORK/pretty.jsonl"
out="$(bash "$T0" --claims "$WORK/pretty.jsonl" --article "$WORK/art.md" --report "$WORK/r4.md")"; rc=$?
{ [ $rc -eq 0 ] && printf '%s' "$out" | grep -q 'schema_bad=0' && printf '%s' "$out" | grep -q 'verdict=PASS'; } \
  && ok "H1' tolerates whitespace after colon (json.dumps default)" || no "H1' pretty-JSON case: rc=$rc out=[$out]"

# ===== H4' contract-mode cases =====
RUNID="test-$$"
printf '%s\n' \
  '{"claim_id":"c-1","type":"TYPE_C","text_quote":"x","source_span":"L1","claim_norm":"x"}' \
  '{"claim_id":"c-2","type":"TYPE_D","text_quote":"y","source_span":"L1","claim_norm":"y"}' > "$WORK/claims.jsonl"

# H4' PASS: TYPE_C has reasoning; TYPE_D all-null + OPINION
printf '%s\n' \
  '{"claim_id":"c-1","verdict":"SUPPORTED","evidence":null,"reasoning_chain":"17 has no divisor other than 1 and itself","verifier":"opus_sub","family":"claude","tokens_out":10}' \
  '{"claim_id":"c-2","verdict":"OPINION","evidence":null,"reasoning_chain":null,"verifier":"opus_sub","family":"claude","tokens_out":5}' > "$WORK/v_ok.jsonl"
out="$(bash "$T0" --verdicts "$WORK/v_ok.jsonl" --claims "$WORK/claims.jsonl" --run-id "$RUNID-ok" --report "$WORK/vr1.md")"; rc=$?
{ [ $rc -eq 0 ] && printf '%s' "$out" | grep -q 'contract_bad=0'; } \
  && ok "H4' contract PASSes (TYPE_C reasoning + TYPE_D null)" || no "H4' PASS case: rc=$rc out=[$out]"

# H4' FAIL: TYPE_C null reasoning; TYPE_D non-null evidence + non-OPINION verdict
printf '%s\n' \
  '{"claim_id":"c-1","verdict":"SUPPORTED","evidence":null,"reasoning_chain":null,"verifier":"opus_sub","family":"claude","tokens_out":10}' \
  '{"claim_id":"c-2","verdict":"SUPPORTED","evidence":[{"kind":"url","url":"http://x","quote":"z"}],"reasoning_chain":null,"verifier":"opus_sub","family":"claude","tokens_out":5}' > "$WORK/v_bad.jsonl"
out="$(bash "$T0" --verdicts "$WORK/v_bad.jsonl" --claims "$WORK/claims.jsonl" --run-id "$RUNID-bad" --report "$WORK/vr2.md")"; rc=$?
# c-1 TYPE_C null reasoning (1) + c-2 TYPE_D evidence-not-null (1) + verdict-not-OPINION (1) = 3
{ [ $rc -eq 1 ] && printf '%s' "$out" | grep -q 'contract_bad=3'; } \
  && ok "H4' contract FAILs (TYPE_C null + TYPE_D evidence/verdict → contract_bad=3)" \
  || no "H4' FAIL case: rc=$rc out=[$out]"

# ===== H3' evidence-mode cases (deterministic via seeded cache) =====
CACHE_ROOT="$(cd "$(dirname "$T0")/.." && pwd)/runs"
printf '%s\n' '{"claim_id":"c-1","type":"TYPE_A","text_quote":"x","source_span":"L1","claim_norm":"x"}' > "$WORK/aclaims.jsonl"

# (a) fetch OK but quote absent => HARD FAIL. Seed cache with a page lacking the quote.
RID_A="test-h3-fabricate-$$"
mkdir -p "$CACHE_ROOT/$RID_A/cache"
FAKE_URL="http://example.invalid/report"
KEY="$(printf '%s' "$FAKE_URL" | cksum | tr -cd '0-9')"
printf '<html><body><p>totally unrelated content here</p></body></html>' > "$CACHE_ROOT/$RID_A/cache/$KEY.html"
printf '%s\n' "{\"claim_id\":\"c-1\",\"verdict\":\"SUPPORTED\",\"evidence\":[{\"kind\":\"url\",\"url\":\"$FAKE_URL\",\"quote\":\"revenue was 4.2 billion\"}],\"reasoning_chain\":null,\"verifier\":\"opus_sub\",\"family\":\"claude\",\"tokens_out\":9}" > "$WORK/v_h3.jsonl"
out="$(bash "$T0" --verdicts "$WORK/v_h3.jsonl" --claims "$WORK/aclaims.jsonl" --run-id "$RID_A" --report "$WORK/vr3.md")"; rc=$?
{ [ $rc -eq 1 ] && printf '%s' "$out" | grep -q 'evid_bad=1'; } \
  && ok "H3' fabricated quote FAILs (fetch ok + quote absent, evid_bad=1)" || no "H3' fabricate case: rc=$rc out=[$out]"
rm -rf "$CACHE_ROOT/$RID_A"

# (b) unreachable source => UNRESOLVED advisory, NOT hard fail (exit 0).
RID_B="test-h3-unreach-$$"
DEAD_URL="http://127.0.0.1:9/nope"
printf '%s\n' "{\"claim_id\":\"c-1\",\"verdict\":\"SUPPORTED\",\"evidence\":[{\"kind\":\"url\",\"url\":\"$DEAD_URL\",\"quote\":\"anything\"}],\"reasoning_chain\":null,\"verifier\":\"opus_sub\",\"family\":\"claude\",\"tokens_out\":9}" > "$WORK/v_dead.jsonl"
out="$(bash "$T0" --verdicts "$WORK/v_dead.jsonl" --claims "$WORK/aclaims.jsonl" --run-id "$RID_B" --report "$WORK/vr4.md")"; rc=$?
{ [ $rc -eq 0 ] && printf '%s' "$out" | grep -q 'unresolved=1' && printf '%s' "$out" | grep -q 'evid_bad=0'; } \
  && ok "H3' dead source is UNRESOLVED advisory (exit 0, not hard fail)" || no "H3' unreachable case: rc=$rc out=[$out]"
rm -rf "$CACHE_ROOT/$RID_B"

# ===== pretty-JSON verdicts regression(judge round-1 2026-07-05:evseg/next_pair/jnull
# 三處 raw marker 對 json.dumps 預設空格 H3'=14/H4'=18 全偽陽性,fetch 迴圈未執行)=====
# (c) pretty H4' PASS:TYPE_C reasoning + TYPE_D all-null,帶 ": " 空格
printf '%s\n' \
  '{"claim_id": "c-1", "verdict": "SUPPORTED", "evidence": null, "reasoning_chain": "17 has no divisor other than 1 and itself", "verifier": "opus_sub", "family": "claude", "tokens_out": 10}' \
  '{"claim_id": "c-2", "verdict": "OPINION", "evidence": null, "reasoning_chain": null, "verifier": "opus_sub", "family": "claude", "tokens_out": 5}' > "$WORK/v_ok_pretty.jsonl"
out="$(bash "$T0" --verdicts "$WORK/v_ok_pretty.jsonl" --claims "$WORK/claims.jsonl" --run-id "$RUNID-okp" --report "$WORK/vr5.md")"; rc=$?
{ [ $rc -eq 0 ] && printf '%s' "$out" | grep -q 'contract_bad=0'; } \
  && ok "H4' pretty-JSON contract PASSes (jnull whitespace tolerance)" || no "H4' pretty case: rc=$rc out=[$out]"

# (d) pretty H3' fabricate:證據迴圈必須在 pretty JSON 下真的執行並抓到捏造
RID_C="test-h3-pretty-$$"
mkdir -p "$CACHE_ROOT/$RID_C/cache"
KEY2="$(printf '%s' "$FAKE_URL" | cksum | tr -cd '0-9')"
printf '<html><body><p>totally unrelated content here</p></body></html>' > "$CACHE_ROOT/$RID_C/cache/$KEY2.html"
printf '%s\n' "{\"claim_id\": \"c-1\", \"verdict\": \"SUPPORTED\", \"evidence\": [{\"kind\": \"url\", \"url\": \"$FAKE_URL\", \"quote\": \"revenue was 4.2 billion\"}], \"reasoning_chain\": null, \"verifier\": \"opus_sub\", \"family\": \"claude\", \"tokens_out\": 9}" > "$WORK/v_h3_pretty.jsonl"
out="$(bash "$T0" --verdicts "$WORK/v_h3_pretty.jsonl" --claims "$WORK/aclaims.jsonl" --run-id "$RID_C" --report "$WORK/vr6.md")"; rc=$?
{ [ $rc -eq 1 ] && printf '%s' "$out" | grep -q 'evid_bad=1'; } \
  && ok "H3' pretty-JSON evidence loop runs + catches fabrication" || no "H3' pretty case: rc=$rc out=[$out]"
rm -rf "$CACHE_ROOT/$RID_C"

echo "=== total: pass=$PASS fail=$FAIL ==="
[ "$FAIL" -eq 0 ]
