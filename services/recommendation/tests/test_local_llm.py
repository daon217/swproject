import http.server
import json
import threading

from services.recommendation.contracts import CollectedProduct, UserProfile
from services.recommendation.rankers import LocalLLMRanker, render_candidates


def test_local_llm_ranker_against_fake_openai_server():
    seen = {}

    class H(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            seen["path"] = self.path
            seen["body"] = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            reply = '설명 먼저 붙이는 모델: {"picks":[{"id":"c2","reason":"현미 과자"},{"id":"c9","reason":"없는 번호"}]}'
            out = json.dumps({"choices": [{"message": {"content": reply}}],
                              "usage": {"prompt_tokens": 120, "completion_tokens": 30}}).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
            self.wfile.write(out)

        def log_message(self, *a):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        items = [(CollectedProduct.from_dict({"source": "t", "source_listing_id": str(i), "name": n}), 1 - i / 10)
                 for i, n in enumerate(["버터쿠키", "현미 쌀과자"])]
        r = LocalLLMRanker(base_url=f"http://127.0.0.1:{srv.server_address[1]}/v1", model="m")
        picks = r.rank(UserProfile("u"), "현미", items, 3)
        assert picks[0][0] == "t:1" and picks[1][0] == "unknown:c9"
        assert r.last_usage == (120, 30) and seen["path"] == "/v1/chat/completions"
        assert seen["body"]["temperature"] == 0 and "t:1" not in seen["body"]["messages"][1]["content"]
    finally:
        srv.shutdown()


def test_render_formats_share_same_candidates():
    items = [(CollectedProduct.from_dict({"source": "t", "source_listing_id": str(i), "name": f"상품{i}",
                                          "ingredients_raw": "쌀, 소금"}), 1 - i / 100) for i in range(20)]
    ids = [render_candidates(f, UserProfile("u"), "q", items, 3)[2] for f in ("json", "toon", "compact")]
    assert ids[0] == ids[1] == ids[2] and len(ids[0]) == 12
