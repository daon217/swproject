"""노트북 목업 20개를 Observation v2 JSON으로 만든다(실제 쇼핑몰 데이터 아님).

사용: py services/api/fixtures/make_mock_laptops.py  → services/api/fixtures/mock_laptops_20.json
적재: py tools/catalog.py import --file services/api/fixtures/mock_laptops_20.json
URL은 테스트 전용 호스트 store.example.test(기본 허용)만 쓴다.
"""
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

# (listing_id, variant_key, 이름, 가격(원), 배송비, 재고, 상태, 설명)
LAPTOPS = [
    ("lt-gram14", "i5-16g-512", "LG 그램 14 14Z90S 인텔 코어 울트라5 16GB 512GB", 1349000, 0, "available", "new", "1.1kg 초경량 14인치 노트북"),
    ("lt-gram16", "i7-32g-1t", "LG 그램 16 16Z90S 인텔 코어 울트라7 32GB 1TB", 2099000, 0, "available", "new", "16인치 WQXGA 대화면"),
    ("lt-gram-pro", "i7-16g-512", "LG 그램 프로 16 RTX3050 16GB 512GB", 2390000, 0, "out_of_stock", "new", "외장 그래픽 탑재 그램"),
    ("lt-galaxybook4", "i5-16g-256", "삼성 갤럭시북4 NT750XGR 인텔 코어5 16GB 256GB", 999000, 3000, "available", "new", "15.6인치 FHD 사무용"),
    ("lt-galaxybook4-pro", "u7-16g-512", "삼성 갤럭시북4 프로 14인치 울트라7 16GB 512GB", 1890000, 0, "available", "new", "AMOLED 3K 디스플레이"),
    ("lt-galaxybook4-360", "u5-16g-512", "삼성 갤럭시북4 360 2in1 터치 16GB 512GB", 1490000, 0, "available", "new", "360도 회전 터치 노트북"),
    ("lt-macbook-air13", "m3-8g-256", "애플 맥북 에어 13 M3 8GB 256GB 미드나이트", 1590000, 0, "available", "new", "팬리스 13.6인치"),
    ("lt-macbook-air15", "m3-16g-512", "애플 맥북 에어 15 M3 16GB 512GB 스타라이트", 2290000, 0, "available", "new", "15.3인치 Liquid Retina"),
    ("lt-macbook-pro14", "m3pro-18g-512", "애플 맥북 프로 14 M3 Pro 18GB 512GB", 2990000, 0, "available", "new", "Liquid Retina XDR"),
    ("lt-macbook-pro14-used", "m1pro-16g-512", "애플 맥북 프로 14 M1 Pro 16GB 512GB 중고 A급", 1450000, 4000, "available", "used", "배터리 효율 92% 중고"),
    ("lt-thinkpad-e14", "r5-16g-512", "레노버 씽크패드 E14 Gen5 라이젠5 16GB 512GB", 899000, 0, "available", "new", "비즈니스 키보드"),
    ("lt-thinkpad-x1", "u7-32g-1t", "레노버 씽크패드 X1 카본 Gen12 울트라7 32GB 1TB", 3190000, 0, "available", "new", "1.09kg 카본 섀시"),
    ("lt-ideapad-slim5", "r7-16g-512", "레노버 아이디어패드 슬림5 14 라이젠7 16GB 512GB", 849000, 2500, "available", "new", "가성비 슬림 노트북"),
    ("lt-legion5", "r7-4060-1t", "레노버 리전 5 RTX4060 라이젠7 16GB 1TB 게이밍", 1790000, 0, "available", "new", "165Hz 게이밍 노트북"),
    ("lt-zenbook14", "u5-16g-512", "에이수스 젠북 14 OLED UX3405 울트라5 16GB 512GB", 1290000, 0, "available", "new", "OLED 3K 120Hz"),
    ("lt-vivobook15", "i5-8g-512", "에이수스 비보북 15 X1504 코어i5 8GB 512GB", 649000, 3000, "available", "new", "입문용 15.6인치"),
    ("lt-rog-zephyrus", "r9-4070-1t", "에이수스 ROG 제피러스 G14 RTX4070 라이젠9 32GB 1TB", 2690000, 0, "out_of_stock", "new", "14인치 OLED 게이밍"),
    ("lt-hp-pavilion", "i5-16g-512", "HP 파빌리온 플러스 14 코어 울트라5 16GB 512GB", 1090000, 0, "available", "new", "2.8K OLED"),
    ("lt-hp-victus", "i5-4050-512", "HP 빅터스 15 RTX4050 코어i5 16GB 512GB 게이밍", 1190000, 0, "available", "new", "144Hz 게이밍 입문"),
    ("lt-dell-xps13", "u7-16g-512", "델 XPS 13 9340 울트라7 16GB 512GB", 2190000, 0, "ended", "new", "판매 종료 모델"),
]

FIELDS = ["name", "description", "price", "currency", "shipping_fee", "availability", "url"]


def build(now: datetime):
    rows = []
    for i, (lid, variant, name, price, ship, avail, cond, desc) in enumerate(LAPTOPS):
        observed = (now - timedelta(minutes=len(LAPTOPS) - i)).isoformat()
        rows.append({
            "schema_version": 2, "source": "mock_laptop", "observation_key": f"mock-laptop:{lid}:{variant}:v1",
            "observed_at": observed, "result": "success", "selected_domain": "product",
            "source_listing_id": lid, "variant_key": variant, "condition": cond,
            "name": name, "description": f"[목업] {desc}",
            "price": f"{price}.0000", "currency": "KRW", "shipping_fee": f"{ship}.0000",
            "availability": avail, "url": f"https://store.example.test/laptop/{lid}?v={variant}",
            "field_presence": FIELDS,
        })
    return rows


if __name__ == "__main__":
    out = Path(__file__).with_name("mock_laptops_20.json")
    out.write_text(json.dumps(build(datetime.now(UTC).replace(microsecond=0)), ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    print("wrote", out, "rows", len(LAPTOPS))
