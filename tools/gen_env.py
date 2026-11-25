"""격리 검증용 env 파일 2개를 만든다(비밀번호·토큰은 매번 무작위). 저장소 밖(예: 임시 폴더)에 만들 것.

python gen_env.py <출력폴더>
  verify.env     : 호스트에서 docker compose 에 넘김 (DB_PORT=55433)
  verify-in.env  : DB 컨테이너 네트워크를 공유하는 테스트 컨테이너용 (DB_PORT=5432)
"""
import secrets, sys
from pathlib import Path

out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
secret_names = ["POSTGRES_PASSWORD", "MEMBER_OWNER_PASSWORD", "MEMBER_APP_PASSWORD", "CATALOG_OWNER_PASSWORD",
                "CATALOG_APP_PASSWORD", "SUPPORT_OWNER_PASSWORD", "SUPPORT_APP_PASSWORD", "COLLECTOR_TOKEN",
                "ANALYSIS_WORKER_TOKEN", "WORKSPACE_TOKEN", "BILLING_TEST_TOKEN"]
values = {k: secrets.token_urlsafe(32) for k in secret_names}
values |= {"API_PORT": "58000", "APP_ENV": "development", "BILLING_MODE": "mock", "MOCK_PAYMENT_OUTCOME": "succeeded",
           "AFFILIATE_URL_HOSTS": "store.example.test", "CATALOG_URL_HOSTS": "store.example.test",
           "CATALOG_CURRENCIES": "KRW,USD,AUD,EUR,INR,GBP,JPY,CNY", "CATALOG_PRICE_RATIO": "10"}
for name, port in (("verify.env", "55433"), ("verify-in.env", "5432")):
    (out / name).write_text("\n".join(f"{k}={v}" for k, v in (values | {"DB_PORT": port}).items()) + "\n", encoding="utf-8")
print("written:", out / "verify.env", out / "verify-in.env")
