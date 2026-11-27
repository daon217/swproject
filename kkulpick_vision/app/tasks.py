"""
[tasks.py]
꿀픽(KkulPick) 3-Phase 비전 파이프라인의 핵심 비즈니스 로직을 수행하는 Celery 비동기 태스크 모듈입니다.
- Phase 1: 메타데이터 Vision Fallback (상품명 미수신 시 0초 차 프레임 최대 면적 텍스트 추출)
- Phase 2: 실시간 스트리밍 프레임 타일링 -> 앵커 탐색 -> ROI 크롭 & 메모리 해제 -> CLAHE 전처리 -> 성분 정제
- Phase 3: 조기 종료(Early Exit), 사용자 이탈(EOF), 서버 보호(15프레임 Hard Timeout) 생명주기 제어
"""

import gc
import hashlib
import json
import logging
from typing import Any, Dict, List, Optional
import redis

from app.celery_app import celery_app
from app.config import settings
from app.vision.ocr_engine import classify_product_category, get_ocr_engine
from app.vision.preprocessor import (
    crop_roi_and_release_memory,
    decode_image,
    enhance_roi_for_ocr,
    split_into_horizontal_tiles,
)

logger = logging.getLogger(__name__)

# 워커 및 API 서버에서 공유하는 Redis Connection Pool
redis_pool = redis.ConnectionPool.from_url(
    settings.REDIS_STATE_URL,
    decode_responses=True,
)


def get_redis_client() -> redis.Redis:
    """Redis 클라이언트를 반환합니다."""
    return redis.Redis(connection_pool=redis_pool)


def get_session_key(session_id: str) -> str:
    """Redis Hash 키 네임스페이스 생성"""
    return f"kkulpick:vision:session:{session_id}"


def initialize_session_in_redis(
    session_id: str,
    product_name: Optional[str],
    price: Optional[int],
) -> Dict[str, Any]:
    """
    [Phase 1] `/api/v1/vision/init` 호출 시 Redis에 세션 상태 해시(Hash)를 생성합니다.
    """
    r = get_redis_client()
    key = get_session_key(session_id)

    has_product_name = bool(product_name and product_name.strip())
    source_of_meta = "html_crawler" if has_product_name else "vision_fallback"
    clean_name = product_name.strip() if has_product_name else ""
    category = classify_product_category(clean_name) if clean_name else "unknown"

    # 명확한 일반 상품(비식품·비화장품)은 성분표가 없으므로 15프레임 탐색을 돌리지 않고 즉시 조기 종료한다.
    if category == "general_product":
        session_data = {
            "session_id": session_id,
            "status": "success",
            "frame_count": "0",
            "product_name": clean_name,
            "price": str(price) if price is not None else "",
            "source_of_meta": source_of_meta,
            "product_category": category,
            "ingredients": json.dumps([], ensure_ascii=False),
            "message": "일반 상품(성분표 불필요)으로 판단되어 상품명 확인 후 분석을 즉시 종료했습니다.",
            "early_exit_flag": "1",
        }
    else:
        session_data = {
            "session_id": session_id,
            "status": "processing",
            "frame_count": "0",
            "product_name": clean_name,
            "price": str(price) if price is not None else "",
            "source_of_meta": source_of_meta,
            "product_category": category,
            "ingredients": json.dumps([], ensure_ascii=False),
            "message": "성분표 탐색 중입니다.",
            "early_exit_flag": "0",
        }

    r.hset(key, mapping=session_data)
    r.expire(key, settings.SESSION_TTL_SECONDS)
    return session_data


def finalize_session_state(
    r: redis.Redis,
    session_id: str,
    status: str,
    ingredients: List[str],
    message: str,
) -> None:
    """
    [Phase 3] 세션을 최종 상태(success 또는 analysis_unavailable)로 마감하고,
    남은 대기열의 프레임 태스크들이 즉시 작업을 스킵하도록 `early_exit_flag="1"`을 설정합니다.
    """
    key = get_session_key(session_id)
    # (#64) 마감 경쟁: 늦게 끝난 '성분표 못 찾음'이 먼저 끝난 '성공'을 덮지 않도록 원자적으로 조건부 마감한다.
    # 성공은 항상 기록하고, 실패 마감은 아직 처리 중일 때만 기록한다.
    r.eval(
        """
        local s = redis.call('HGET', KEYS[1], 'status')
        if ARGV[1] ~= 'success' and s and s ~= 'processing' then return 0 end
        redis.call('HSET', KEYS[1], 'status', ARGV[1], 'ingredients', ARGV[2], 'message', ARGV[3], 'early_exit_flag', '1')
        redis.call('EXPIRE', KEYS[1], ARGV[4])
        return 1
        """,
        1, key, status, json.dumps(ingredients, ensure_ascii=False), message, int(settings.SESSION_TTL_SECONDS),
    )


# ==============================================================================
# [Phase 1 Task] 0초 차 최상단 화면 기반 상품명 Vision Fallback 태스크
# ==============================================================================
@celery_app.task(name="app.tasks.extract_metadata_fallback_task")
def extract_metadata_fallback_task(session_id: str, first_frame_b64: str) -> Dict[str, Any]:
    """
    [Phase 1: Fallback 로직]
    프론트엔드에서 안티 크롤링 등으로 `product_name`이 비어 있거나 null로 들어온 경우,
    Celery 워커가 즉시 `first_frame_image`(0초 차 최상단 화면)를 PaddleOCR로 스캔합니다.
    검출된 바운딩 박스들의 면적(Width × Height)을 계산해 가장 큰 글씨를 `product_name`으로 추출하여
    Redis 세션에 업데이트하고 `source_of_meta: "vision_fallback"`으로 기록합니다.
    """
    r = get_redis_client()
    key = get_session_key(session_id)

    if not r.exists(key):
        logger.warning(f"[Phase 1 Fallback] 존재하지 않는 세션입니다: {session_id}")
        return {"session_id": session_id, "updated": False}

    image = decode_image(first_frame_b64)
    if image is None:
        logger.warning(f"[Phase 1 Fallback] 이미지 디코딩 실패: {session_id}")
        return {"session_id": session_id, "updated": False}

    try:
        ocr_engine = get_ocr_engine()
        # 앞 4KB만 해시하면 머리가 같은 다른 캡처(같은 쇼핑몰 화면)에 이전 결과를 재사용한다(#21) -> 전체 해시
        img_hash = hashlib.sha256(first_frame_b64.encode("utf-8", errors="ignore")).hexdigest()
        tiles = split_into_horizontal_tiles(image)
        detected_title = None
        detected_category = "unknown"
        first_tile_items = []

        if tiles:
            tile0_img = tiles[0][1]
            first_tile_items = ocr_engine.run_ocr(tile0_img)
            th, tw = tile0_img.shape[:2]
            detected_title, detected_category, _breadcrumbs = ocr_engine.extract_product_title_and_category(
                first_tile_items, img_width=tw, img_height=th
            )

        # 명확한 일반 상품(노트북·가전·패션·가구 등)은 성분표 탐색 없이 즉시 조기 종료(Early Exit)
        if detected_category == "general_product":
            r.hset(
                key,
                mapping={
                    "init_frame_hash": img_hash,
                    "init_cached_ingredients": "[]",
                    "product_name": detected_title or "",
                    "source_of_meta": "vision_fallback",
                    "product_category": detected_category,
                },
            )
            finalize_session_state(
                r=r,
                session_id=session_id,
                status="success",
                ingredients=[],
                message="일반 상품(성분표 불필요)으로 판단되어 상품명 추출 후 즉시 분석을 종료했습니다.",
            )
            logger.info(
                f"[Phase 1 일반 상품 조기 종료] session={session_id}, 상품명='{detected_title}'"
            )
            return {
                "session_id": session_id,
                "product_name": detected_title,
                "product_category": detected_category,
                "source_of_meta": "vision_fallback",
                "updated": bool(detected_title),
                "early_exit": True,
            }

        # [통합 스캔 캐시] 동일 프레임 안에 앵커 키워드(원재료명 등)까지 함께 있는지 즉시 검사하여
        # 뒤이어 동일한 이미지로 POST /frame이 호출될 때 중복 OCR을 100% 생략하도록 캐싱합니다.
        anchor_ys, cached_ingredients = ocr_engine.find_all_anchors_and_initial_ingredients(
            tiles, precomputed_first_tile=first_tile_items
        )
        del tiles

        # 만약 1차 타일 스캔에서 앵커는 찾았는데 정밀 성분이 부족하면 후보 앵커들에 대해 ROI CLAHE 보정 수행
        if anchor_ys and not cached_ingredients:
            for cand_y in anchor_ys[:3]:
                roi_image = crop_roi_and_release_memory(
                    full_image=image.copy(),
                    anchor_y=cand_y,
                    crop_height=settings.ROI_CROP_HEIGHT,
                )
                try:
                    enhanced_roi = enhance_roi_for_ocr(roi_image, use_adaptive_binarization=False)
                    cached_ingredients = ocr_engine.extract_and_clean_ingredients(enhanced_roi)
                    del enhanced_roi
                    if not cached_ingredients:
                        bin_roi = enhance_roi_for_ocr(roi_image, use_adaptive_binarization=True)
                        cached_ingredients = ocr_engine.extract_and_clean_ingredients(bin_roi)
                        del bin_roi
                finally:
                    del roi_image
                if cached_ingredients:
                    break

        cache_mapping: Dict[str, str] = {
            "init_frame_hash": img_hash,
            "init_cached_ingredients": json.dumps(cached_ingredients, ensure_ascii=False),
            "product_category": detected_category,
        }

        if detected_title:
            cache_mapping["product_name"] = detected_title
            cache_mapping["source_of_meta"] = "vision_fallback"
            r.hset(key, mapping=cache_mapping)
            logger.info(
                f"[Phase 1 Fallback 완료] session={session_id}, 추출된 상품명='{detected_title}'"
            )
            return {
                "session_id": session_id,
                "product_name": detected_title,
                "source_of_meta": "vision_fallback",
                "updated": True,
            }
        else:
            cache_mapping["source_of_meta"] = "vision_fallback"
            r.hset(key, mapping=cache_mapping)
            return {"session_id": session_id, "updated": False}
    finally:
        # 0초 차 프레임 이미지 메모리 즉시 해제
        del image
        gc.collect()


# ==============================================================================
# [Phase 2 & 3 Task] 실시간 스트리밍 프레임 분석 및 조기 종료/타임아웃 제어 태스크
# ==============================================================================
def _scan_frame(frame_holder: list) -> List[str]:
    """프레임 1장에서 성분표를 찾아 정제된 성분 목록을 돌려준다(못 찾으면 빈 목록). 예외는 호출한 쪽이 처리한다(#64).
    원본 이미지는 리스트로 받아 꺼낸다: 호출한 쪽이 참조를 쥐고 있으면 ROI만 남기고 원본을 일찍 해제하는 설계(#66)가 깨진다."""
    full_image = frame_holder.pop()
    extracted_ingredients: List[str] = []
    ocr_engine = get_ocr_engine()

    # 3-1. 세로로 긴 이미지를 가로 블록 단위로 분할 (Tiling)
    tiles = split_into_horizontal_tiles(full_image)

    # 3-2. 1차 스캔: 다중 앵커 Y좌표 탐색 + 표 경계 기반 즉시 성분 추출 시도 ('상세설명 참조' 앵커 자동 우회)
    anchor_ys, fast_ingredients = ocr_engine.find_all_anchors_and_initial_ingredients(tiles)

    # 타일 참조 리스트 정리
    del tiles

    if anchor_ys:
        if len(fast_ingredients) >= 2:
            extracted_ingredients = fast_ingredients
            del full_image
            gc.collect()
        else:
            # 3-3. 최대 3개의 앵커 후보에 대해 순차적으로 ROI 크롭 및 CLAHE/이진화 2차 정밀 추출 수행
            candidates = anchor_ys[:3]
            for i, cand_y in enumerate(candidates):
                is_last_cand = i == len(candidates) - 1
                src_img = full_image if is_last_cand else full_image.copy()
                if is_last_cand:
                    full_image = None
                roi_image = crop_roi_and_release_memory(
                    full_image=src_img,
                    anchor_y=cand_y,
                    crop_height=settings.ROI_CROP_HEIGHT,
                )
                try:
                    enhanced_roi = enhance_roi_for_ocr(roi_image, use_adaptive_binarization=False)
                    extracted_ingredients = ocr_engine.extract_and_clean_ingredients(enhanced_roi)
                    if not extracted_ingredients:
                        binarized_roi = enhance_roi_for_ocr(roi_image, use_adaptive_binarization=True)
                        extracted_ingredients = ocr_engine.extract_and_clean_ingredients(binarized_roi)
                        del binarized_roi
                    del enhanced_roi
                finally:
                    del roi_image
                    gc.collect()
                if extracted_ingredients:
                    if full_image is not None:
                        del full_image
                        full_image = None
                        gc.collect()
                    break
    else:
        # 앵커가 없는 프레임도 즉시 메모리에서 해제
        del full_image
        gc.collect()
    return extracted_ingredients


@celery_app.task(name="app.tasks.process_frame_task")
def process_frame_task(
    session_id: str,
    frame_index: int,
    is_last_frame: bool,
    image_b64: str,
) -> Dict[str, Any]:
    """
    [Phase 2 & Phase 3 통합 파이프라인]
    1. 작업 전 Redis에서 세션의 현재 `status`를 확인해 이미 종료된 세션(`success` 또는 `analysis_unavailable`)이면 즉시 스킵(Early Exit).
    2. `frame_count`를 원자적(HINCRBY)으로 1 증가시키고 15프레임 도달 여부를 체크.
    3. OpenCV 가로 타일링 -> PaddleOCR 1차 스캔으로 앵커 키워드 탐색.
    4. 앵커 발견 시 하단 500px ROI 크롭 및 원본 이미지 메모리 즉시 해제 -> CLAHE 전처리 -> 성분 정규식 정제.
    5. 시나리오 A(성공), 시나리오 B(EOF 이탈), 시나리오 C(15프레임 Hard Timeout)에 따라 생명주기 마감.
    """
    r = get_redis_client()
    key = get_session_key(session_id)

    # --------------------------------------------------------------------------
    # [Step 1] 조기 종료(Early Exit) 사전 검사
    # 이미 앞선 프레임에서 성분표를 찾았거나 타임아웃된 세션이면 이미지 디코딩조차 하지 않고 즉시 스킵
    # --------------------------------------------------------------------------
    session_state = r.hgetall(key)
    if not session_state:
        logger.warning(f"[Phase 2] 세션 정보가 없습니다 ({session_id}). 작업을 건너뜁니다.")
        return {"session_id": session_id, "skipped": True, "reason": "session_not_found"}

    current_status = session_state.get("status", "processing")
    early_exit_flag = session_state.get("early_exit_flag", "0")

    if current_status != "processing" or early_exit_flag == "1":
        logger.info(
            f"[Phase 3 Early Exit Skip] 이미 종료된 세션({current_status})입니다. "
            f"session={session_id}, frame_index={frame_index} 스킵."
        )
        return {"session_id": session_id, "skipped": True, "reason": f"already_{current_status}"}

    # --------------------------------------------------------------------------
    # [Step 2] 프레임 카운트 원자적 증가 및 Hard Timeout(15프레임) 초과 검사
    # --------------------------------------------------------------------------
    current_frame_count: int = int(r.hincrby(key, "frame_count", 1))

    # 이미 15프레임을 초과하여 들어온 잔여 큐 작업인 경우 즉시 차단 (시나리오 C 방어)
    if current_frame_count > settings.MAX_FRAME_LIMIT:
        finalize_session_state(
            r=r,
            session_id=session_id,
            status="analysis_unavailable",
            ingredients=[],
            message="성분표를 찾지 못해 알레르기 분석이 불가합니다.",
        )
        logger.warning(
            f"[Phase 3 Hard Timeout] 15프레임 한도 초과 (현재 {current_frame_count}장). 강제 종료: {session_id}"
        )
        return {"session_id": session_id, "status": "analysis_unavailable", "reason": "hard_timeout"}

    # --------------------------------------------------------------------------
    # [Step 3] 이미지 디코딩 및 OpenCV 타일링 + 1차 앵커 탐색
    # --------------------------------------------------------------------------
    frame_hash = hashlib.sha256(image_b64.encode("utf-8", errors="ignore")).hexdigest() if image_b64 else ""
    extracted_ingredients: List[str] = []

    # [초고속 캐시 히트] 만약 Phase 1(init)에서 이미 동일 프레임 이미지를 스캔했다면
    # 이미지 디코딩 및 중복 OCR을 100% 생략(0ms)하고 캐싱된 성분 결과를 즉시 사용합니다!
    if frame_hash and session_state.get("init_frame_hash") == frame_hash:
        try:
            extracted_ingredients = json.loads(session_state.get("init_cached_ingredients", "[]"))
        except Exception:
            extracted_ingredients = []
        logger.info(f"[Phase 2 Fast Cache Hit] init 프레임과 동일 이미지 감지 -> 중복 OCR 생략 (session={session_id})")
        full_image = None
    else:
        full_image = decode_image(image_b64)

    try:
        if full_image is not None:
            frame_holder, full_image = [full_image], None
            extracted_ingredients = _scan_frame(frame_holder)
    except Exception:
        # (#64) OCR 중 예외가 나도 세션이 '처리 중'에 멈추지 않게 이 프레임을 '못 찾음'으로 보고 아래 마감 규칙을 따른다.
        logger.exception(f"[Phase 2] 프레임 처리 실패: session={session_id}, frame_index={frame_index}")
        extracted_ingredients = []
        full_image = None
        gc.collect()


    # --------------------------------------------------------------------------
    # [Step 4] Phase 3 생명주기 제어 (시나리오 A / B / C 판정)
    # --------------------------------------------------------------------------

    # [시나리오 A: 정상 발견 - Early Exit]
    if len(extracted_ingredients) > 0:
        finalize_session_state(
            r=r,
            session_id=session_id,
            status="success",
            ingredients=extracted_ingredients,
            message="성분표 추출이 완료되었습니다.",
        )
        logger.info(
            f"[Phase 3 시나리오 A - Early Exit 성공] session={session_id}, "
            f"frame_index={frame_index}, 추출 성분 수={len(extracted_ingredients)}"
        )
        return {
            "session_id": session_id,
            "status": "success",
            "ingredients": extracted_ingredients,
        }

    # [Phase 2 동적 메타데이터/카테고리 보완]
    # 초기(0초) 화면이 대형 배너여서 상품명/품목이 미분류('unknown')였더라도, 스크롤 중 상품명이나
    # 비식품 상품정보제공고시(갑피/밑창/방문설치/정격전압 등)가 확인되면 즉시 반영 및 일반 상품 조기 종료 수행
    if session_state.get("product_category", "unknown") in ("", "unknown"):
        try:
            eng = get_ocr_engine()
            tls = getattr(eng, "_tls", None)
            scan_info = getattr(tls, "last_scan_info", None) if tls is not None else None
            if scan_info:
                if tls is not None:
                    tls.last_scan_info = None
                cur_title = session_state.get("product_name") or ""
                tw, th = scan_info.get("tile0_size", (0, 0))
                t0_items = scan_info.get("tile0_items") or []
                new_title = None
                breadcrumbs: List[str] = []
                if not cur_title and t0_items and tw > 0 and th > 0:
                    new_title, _, breadcrumbs = eng.extract_product_title_and_category(
                        t0_items, img_width=tw, img_height=th
                    )
                dyn_cat = classify_product_category(
                    cur_title or new_title,
                    breadcrumbs=breadcrumbs,
                    page_texts=scan_info.get("all_texts") or [],
                )
                updates: Dict[str, str] = {}
                if not cur_title and new_title:
                    updates["product_name"] = new_title
                if dyn_cat != "unknown":
                    updates["product_category"] = dyn_cat
                if updates:
                    r.hset(key, mapping=updates)
                if dyn_cat == "general_product":
                    finalize_session_state(
                        r=r,
                        session_id=session_id,
                        status="success",
                        ingredients=[],
                        message="스크롤 화면에서 일반 상품(성분표 불필요)으로 확인되어 분석을 즉시 종료했습니다.",
                    )
                    logger.info(
                        f"[Phase 2 동적 일반 상품 조기 종료] session={session_id}, frame_index={frame_index}"
                    )
                    return {
                        "session_id": session_id,
                        "status": "success",
                        "ingredients": [],
                        "reason": "dynamic_general_product_exit",
                    }
        except Exception:
            logger.debug("[Phase 2] 동적 카테고리 보완 스킵", exc_info=True)

    # [시나리오 B: 사용자 이탈/방치 - EOF]
    # 요청의 is_last_frame == True인데 현재 프레임에서도 성분표를 찾지 못한 경우 즉시 중단
    if is_last_frame:
        finalize_session_state(
            r=r,
            session_id=session_id,
            status="analysis_unavailable",
            ingredients=[],
            message="성분표를 찾지 못해 알레르기 분석이 불가합니다.",
        )
        logger.info(
            f"[Phase 3 시나리오 B - EOF 종료] 마지막 프레임(index={frame_index})까지 성분표 미발견: {session_id}"
        )
        return {
            "session_id": session_id,
            "status": "analysis_unavailable",
            "reason": "eof_reached",
        }

    # [시나리오 C: 서버 보호 - Hard Timeout (15프레임 도달)]
    # frame_count가 15장(15프레임)에 도달할 때까지 성분표를 찾지 못하면 강제 종료
    if current_frame_count >= settings.MAX_FRAME_LIMIT:
        finalize_session_state(
            r=r,
            session_id=session_id,
            status="analysis_unavailable",
            ingredients=[],
            message="성분표를 찾지 못해 알레르기 분석이 불가합니다.",
        )
        logger.warning(
            f"[Phase 3 시나리오 C - 15프레임 Hard Timeout] 15장 도달 성분표 미발견 강제 종료: {session_id}"
        )
        return {
            "session_id": session_id,
            "status": "analysis_unavailable",
            "reason": "max_frames_15_timeout",
        }

    # 아직 탐색 중 (다음 프레임 대기)
    return {
        "session_id": session_id,
        "status": "processing",
        "frame_count": current_frame_count,
    }

