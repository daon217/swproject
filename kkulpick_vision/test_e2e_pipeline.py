"""
[test_e2e_pipeline.py]
꿀픽(KkulPick) 비전 AI 파이프라인 End-to-End(E2E) 통합 테스트 스크립트입니다.
1) Windows 한글 폰트(맑은 고딕)를 사용하여 실제 쇼핑몰 상세페이지와 유사한
   - 0초 차 최상단 화면 이미지 (sample_first_frame.png: 대제목 "신라면 120g")
   - 스크롤 중 성분표가 포함된 상세페이지 프레임 이미지 (sample_ingredient_frame.png: 앵커 "원재료명 및 함량" + 성분 목록)
   - 성분표가 없는 일반 홍보 이미지 (sample_empty_frame.png: EOF 시나리오 B 검증용)
   를 생성합니다.
2) 실행 중인 FastAPI 서버(http://127.0.0.1:8000)의
   - POST /api/v1/vision/init (product_name 미전송 -> Vision Fallback 유도)
   - POST /api/v1/vision/frame (성분표 프레임 전송 -> HTTP 202 수신)
   - GET  /api/v1/vision/status/{session_id} (폴링하여 최종 JSON 결과 수신)
   전 과정을 실제 호출하고 결과를 출력합니다.
"""

import base64
import json
import os
import time
import httpx
from PIL import Image, ImageDraw, ImageFont

BASE_URL = "http://127.0.0.1:8000/api/v1/vision"
FONT_PATH = "C:/Windows/Fonts/malgunbd.ttf"  # 맑은 고딕 Bold
FONT_REG_PATH = "C:/Windows/Fonts/malgun.ttf"


def create_sample_first_frame(save_path: str) -> str:
    """
    [Phase 1 테스트용 이미지]
    0초 차 최상단 화면: 바운딩 박스 면적이 가장 큰 텍스트로 '신라면 120g'을 배치합니다.
    """
    img = Image.new("RGB", (800, 600), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)

    font_small = ImageFont.truetype(FONT_REG_PATH, 22)
    font_large = ImageFont.truetype(FONT_PATH, 68)

    # 작은 상단 카테고리 문구
    draw.text((50, 60), "무료배송 특가할인", fill=(100, 100, 100), font=font_small)
    # 가장 큰 상품명 타이틀 (바운딩 박스 면적 최대)
    draw.text((50, 160), "신라면 120g", fill=(15, 15, 15), font=font_large)
    # 작은 하단 부가 문구
    draw.text((50, 300), "리뷰 9,999개 평점 4.9", fill=(120, 120, 120), font=font_small)

    img.save(save_path)
    with open(save_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def create_sample_ingredient_frame(save_path: str) -> str:
    """
    [Phase 2 테스트용 이미지]
    세로로 긴 스크롤 상세페이지 이미지(800x1800)를 생성하고,
    중단(Y=750 부근)에 앵커 키워드 '원재료명 및 함량'과 실제 원재료 텍스트를 배치합니다.
    """
    img = Image.new("RGB", (800, 1800), color=(250, 250, 250))
    draw = ImageDraw.Draw(img)

    font_header = ImageFont.truetype(FONT_PATH, 36)
    font_body = ImageFont.truetype(FONT_REG_PATH, 30)

    # 상단 일반 상품 홍보 문구 (앵커 아님)
    draw.text((60, 150), "쫄깃한 면발과 얼큰한 국물의 조화", fill=(60, 60, 60), font=font_body)

    # Y=750 위치에 성분표 박스 및 앵커 키워드 배치
    draw.rectangle([(40, 720), (760, 1180)], outline=(180, 180, 180), width=2, fill=(255, 255, 255))
    draw.text((60, 750), "원재료명 및 함량", fill=(0, 0, 0), font=font_header)
    draw.text(
        (60, 830),
        "소맥분(미국산), 팜유(말레이시아산),",
        fill=(20, 20, 20),
        font=font_body,
    )
    draw.text(
        (60, 900),
        "감자전분, L-글루탐산나트륨",
        fill=(20, 20, 20),
        font=font_body,
    )

    img.save(save_path)
    with open(save_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def create_sample_empty_frame(save_path: str) -> str:
    """성분표 앵커가 없는 일반 상세페이지 이미지 (EOF 시나리오 B 테스트용)"""
    img = Image.new("RGB", (800, 800), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    font_body = ImageFont.truetype(FONT_REG_PATH, 30)
    draw.text((60, 200), "본 제품은 엄선된 재료로 정성껏 만들었습니다.", fill=(50, 50, 50), font=font_body)
    img.save(save_path)
    with open(save_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def run_e2e_test() -> None:
    sample_dir = os.path.join(os.path.dirname(__file__), "samples")
    os.makedirs(sample_dir, exist_ok=True)

    first_frame_path = os.path.join(sample_dir, "sample_first_frame.png")
    ingredient_frame_path = os.path.join(sample_dir, "sample_ingredient_frame.png")
    empty_frame_path = os.path.join(sample_dir, "sample_empty_frame.png")

    print("1. 샘플 테스트 이미지 생성 중...")
    first_frame_b64 = create_sample_first_frame(first_frame_path)
    ingredient_frame_b64 = create_sample_ingredient_frame(ingredient_frame_path)
    empty_frame_b64 = create_sample_empty_frame(empty_frame_path)
    print(f"   - 최상단 화면 이미지 생성 완료: {first_frame_path}")
    print(f"   - 성분표 상세 프레임 생성 완료: {ingredient_frame_path}\n")

    session_success = "sess_kkulpick_success_01"
    session_eof = "sess_kkulpick_eof_02"

    with httpx.Client(timeout=30.0) as client:
        # ======================================================================
        # [테스트 1] Phase 1 (Vision Fallback) + Phase 2 (ROI & CLAHE OCR) + Phase 3 (Early Exit 성공)
        # ======================================================================
        print("2. [POST /api/v1/vision/init] 요청 전송 (product_name=None -> Vision Fallback 유도)...")
        init_resp = client.post(
            f"{BASE_URL}/init",
            json={
                "session_id": session_success,
                "product_name": None,
                "price": 1200,
                "first_frame_image": first_frame_b64,
            },
        )
        print(f"   - HTTP Status: {init_resp.status_code}")
        print(f"   - Init 응답: {json.dumps(init_resp.json(), ensure_ascii=False)}\n")

        print("3. [POST /api/v1/vision/frame] 성분표 포함 스크롤 프레임(#1) 전송...")
        frame_resp = client.post(
            f"{BASE_URL}/frame",
            json={
                "session_id": session_success,
                "frame_index": 1,
                "is_last_frame": False,
                "image": ingredient_frame_b64,
            },
        )
        print(f"   - HTTP Status: {frame_resp.status_code}")
        print(f"   - Frame 응답: {json.dumps(frame_resp.json(), ensure_ascii=False)}\n")

        print("4. [GET /api/v1/vision/status/{session_id}] 최종 결과 폴링 중...")
        for _ in range(15):
            status_resp = client.get(f"{BASE_URL}/status/{session_success}")
            result_json = status_resp.json()
            if result_json.get("status") in ("success", "analysis_unavailable"):
                print("\n============================================================")
                print(" [최종 추출 JSON 결과 1: 성분표 추출 성공 (Early Exit + Vision Fallback)]")
                print("============================================================")
                print(json.dumps(result_json, indent=2, ensure_ascii=False))
                break
            time.sleep(1.0)

        # Early Exit 방어 확인
        print("\n5. [Early Exit 방어 검증] 이미 완료된 세션에 후속 프레임(#2) 전송 시:")
        extra_resp = client.post(
            f"{BASE_URL}/frame",
            json={
                "session_id": session_success,
                "frame_index": 2,
                "is_last_frame": False,
                "image": ingredient_frame_b64,
            },
        )
        print(f"   - 응답: {json.dumps(extra_resp.json(), ensure_ascii=False)}\n")

        # ======================================================================
        # [테스트 2] Phase 3 시나리오 B (마지막 프레임 EOF까지 성분표 미발견 -> analysis_unavailable)
        # ======================================================================
        print("6. [시나리오 B (EOF) 검증] 성분표 없는 마지막 프레임(is_last_frame=True) 전송...")
        client.post(
            f"{BASE_URL}/init",
            json={
                "session_id": session_eof,
                "product_name": "신라면 120g",
                "price": 1200,
                "first_frame_image": None,
            },
        )
        client.post(
            f"{BASE_URL}/frame",
            json={
                "session_id": session_eof,
                "frame_index": 0,
                "is_last_frame": True,
                "image": empty_frame_b64,
            },
        )
        for _ in range(15):
            eof_resp = client.get(f"{BASE_URL}/status/{session_eof}").json()
            if eof_resp.get("status") == "analysis_unavailable":
                print("\n============================================================")
                print(" [최종 추출 JSON 결과 2: 분석 불가 시 (EOF / Hard Timeout)]")
                print("============================================================")
                print(json.dumps(eof_resp, indent=2, ensure_ascii=False))
                break
            time.sleep(1.0)


if __name__ == "__main__":
    run_e2e_test()
