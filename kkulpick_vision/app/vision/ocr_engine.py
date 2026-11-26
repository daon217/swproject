"""
[ocr_engine.py]
PaddleOCR(`lang='korean'`) 모델을 워커 프로세스당 단 한 번만 메모리에 로드하는 싱글톤(Singleton) 엔진과,
1) Phase 1 메타데이터 Fallback용 최대 면적 바운딩 박스 상품명 추출
2) Phase 2 앵커(Anchor) 키워드 탐색 및 Y좌표 반환
3) 전처리된 ROI 이미지에서 정규표현식(Regex) 기반 성분표 정제 로직을 담당합니다.
"""

import logging
import re
import threading
from typing import Any, List, Optional, Tuple
import numpy as np

from app.config import settings

logger = logging.getLogger(__name__)


# 한 글자로 표기되는 알레르기 원료(성분표의 '밀', '게' 등). 1글자 노이즈 제거에서 제외한다(#62).
ALLERGEN_SINGLE_CHARS = frozenset({"밀", "게", "잣", "굴", "깨", "콩"})
# '…산'으로 끝나지만 원산지가 아닌 성분(아황산류는 알레르기 표시 대상).
ACID_INGREDIENTS = frozenset({"아황산", "구연산", "젖산", "초산", "사과산", "주석산", "인산", "호박산", "규산", "빙초산"})


class OCRSingletonEngine:
    """
    [PaddleOCR 싱글톤 패턴]
    PaddleOCR 한국어 모델은 Detection + Recognition 가중치를 포함해 메모리를 많이 점유하고
    초기화 시간이 길기 때문에, 매 프레임마다 재생성하면 심각한 병목과 OOM이 발생합니다.
    워커 프로세스 시작 시(또는 최초 호출 시) 단 1회만 메모리에 로드하여 재사용합니다.
    """

    _instance: Optional["OCRSingletonEngine"] = None
    _lock: threading.Lock = threading.Lock()

    def __new__(cls) -> "OCRSingletonEngine":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if getattr(self, "_initialized", False):
            return
        with self._lock:
            if getattr(self, "_initialized", False):
                return
            self._ocr_model = None
            self._load_model()
            self._initialized = True

    def _load_model(self) -> None:
        """
        OCR 한국어 엔진을 메모리에 로드합니다.
        - Windows 환경에서는 상주형 Windows Native 한국어 OCR 데몬(Windows.Media.Ocr)을 우선 활성화하여
          매 프레임 추론 속도를 ~1,500ms에서 ~70ms(20배 이상 단축)로 가속합니다.
        - Linux/Docker 환경이거나 `VISION_FORCE_PADDLE=1`이 지정된 경우에는 PaddleOCR 싱글톤을 로드합니다.
        """
        import os
        import sys

        self._use_windows_native_ocr = False
        self._win_ocr_proc = None
        self._win_ocr_lock = threading.Lock()

        if sys.platform == "win32" and os.getenv("VISION_FORCE_PADDLE", "0") != "1":
            try:
                self._use_windows_native_ocr = True
                self._ocr_model = None
                self._ensure_win_ocr_daemon()
                logger.info(
                    "[OCRSingletonEngine] Windows Native 한국어 OCR 상주 워커(Windows.Media.Ocr, ~70ms/frame) 활성화 완료."
                )
                return
            except Exception as win_exc:
                logger.warning(f"[OCRSingletonEngine] Windows Native OCR 데몬 초기화 실패 ({win_exc}), PaddleOCR로 전환합니다.")
                self._use_windows_native_ocr = False

        try:
            from paddleocr import PaddleOCR

            cpu_threads = min(8, os.cpu_count() or 4)
            logger.info(f"[OCRSingletonEngine] PaddleOCR (lang='korean', threads={cpu_threads}) 모델을 메모리에 로드합니다...")
            # use_angle_cls=False: 쇼핑몰 상세페이지는 정방향 텍스트이므로 방향 분류기를 꺼서 추론 속도 향상
            self._ocr_model = PaddleOCR(
                lang="korean",
                use_angle_cls=False,
                use_gpu=False,
                cpu_threads=cpu_threads,
                det_limit_side_len=settings.OCR_DET_LIMIT_SIDE,
                rec_batch_num=settings.REC_BATCH_NUM,
                show_log=False,
            )
            self._fix_recognition_width(self._ocr_model)
            logger.info("[OCRSingletonEngine] PaddleOCR 싱글톤 로드 완료.")
        except Exception as exc:
            logger.warning(
                f"[OCRSingletonEngine] PaddleOCR DLL 로드 제한 감지 ({exc}). "
                "Windows Native 한국어 OCR 상주 워커(Windows.Media.Ocr, lang='ko')로 자동 전환합니다."
            )
            self._ocr_model = None
            self._use_windows_native_ocr = True

    @staticmethod
    def _fix_recognition_width(ocr_model) -> None:
        """
        [메모리 증가 방지 #66] PaddleOCR 인식기는 배치마다 가장 긴 줄의 비율(max_wh_ratio)로 입력 폭을 정한다.
        줄 폭이 매번 달라 새 입력 모양이 계속 생기고, Paddle은 모양마다 잡은 메모리를 반환하지 않는다.
        입력 폭을 REC_WIDTH_RATIOS 중 하나(기본 2가지)로만 정해 입력 모양 수를 고정한다.
        측정: 폭이 다른 120줄 7.0GiB → 0.70GiB, 페이지 처리도 가변 폭보다 빠르다(28.6s → 13.2s).
        REC_BATCH_NUM=1이므로 줄마다 자기 길이에 맞는 크기를 고른다.
        """
        recognizer = getattr(ocr_model, "text_recognizer", None)
        if recognizer is None or not hasattr(recognizer, "resize_norm_img"):
            logger.warning("[OCRSingletonEngine] 인식기 구조가 예상과 달라 입력 폭을 고정하지 못했습니다.")
            return
        original = recognizer.resize_norm_img
        ratios = sorted(float(x) for x in settings.REC_WIDTH_RATIOS.split(",") if x.strip())

        def fixed_width(img, max_wh_ratio):
            h, w = img.shape[:2]
            own = w / max(h, 1)
            return original(img, next((r for r in ratios if own <= r), ratios[-1]))

        recognizer.resize_norm_img = fixed_width

    @staticmethod
    def _to_fixed_canvas(image: np.ndarray) -> Tuple[np.ndarray, float]:
        """
        [메모리 증가 방지 #66] 검출 입력을 항상 OCR_CANVAS_WIDTH × OCR_CANVAS_HEIGHT로 맞춘다.
        더 크면 비율을 유지해 축소하고(확대는 하지 않음), 남는 오른쪽·아래는 흰색으로 채운다.
        채움은 오른쪽·아래에만 하므로 좌표는 scale로 나누기만 하면 원래 이미지 좌표가 된다.
        """
        import cv2

        if image.ndim == 2:
            image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        canvas_w, canvas_h = settings.OCR_CANVAS_WIDTH, settings.OCR_CANVAS_HEIGHT
        h, w = image.shape[:2]
        scale = min(canvas_w / w, canvas_h / h, 1.0)
        if scale < 1.0:
            image = cv2.resize(image, (max(1, int(w * scale)), max(1, int(h * scale))), interpolation=cv2.INTER_AREA)
        canvas = np.full((canvas_h, canvas_w, 3), 255, dtype=np.uint8)
        canvas[: image.shape[0], : image.shape[1]] = image
        return canvas, scale

    def _ensure_win_ocr_daemon(self):
        """
        Windows Native OCR 사용 시 매번 powershell.exe 프로세스를 새로 띄우지 않고(350ms 절약),
        단일 상주 PowerShell 워커 프로세스를 띄워 stdin/stdout 파이프로 50~80ms 내에 즉시 추론합니다.
        """
        import subprocess

        if self._win_ocr_proc is not None and self._win_ocr_proc.poll() is None:
            return self._win_ocr_proc

        ps_daemon_script = """
[Console]::InputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Globalization.Language, Windows.Foundation, ContentType = WindowsRuntime]

$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
})[0]
function Await($WinRtTask, $ResultType) {
    $asTask = $asTaskGeneric.MakeGenericMethod($ResultType)
    $netTask = $asTask.Invoke($null, @($WinRtTask))
    $netTask.Wait(-1) | Out-Null
    return $netTask.Result
}
$lang = New-Object Windows.Globalization.Language('ko')
$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($lang)

while ($null -ne ($imgPath = [Console]::In.ReadLine())) {
    $imgPath = $imgPath.Trim()
    if ([string]::IsNullOrEmpty($imgPath)) { continue }
    try {
        $file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($imgPath)) ([Windows.Storage.StorageFile])
        $stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
        $decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
        $bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
        $result = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
        $lines = @()
        foreach ($line in $result.Lines) {
            $minX = 999999; $minY = 999999; $maxX = 0; $maxY = 0
            foreach ($word in $line.Words) {
                $r = $word.BoundingRect
                if ($r.X -lt $minX) { $minX = $r.X }
                if ($r.Y -lt $minY) { $minY = $r.Y }
                if (($r.X + $r.Width) -gt $maxX) { $maxX = $r.X + $r.Width }
                if (($r.Y + $r.Height) -gt $maxY) { $maxY = $r.Y + $r.Height }
            }
            $lines += @{
                text = ($line.Words | ForEach-Object { $_.Text }) -join ''
                text_spaced = $line.Text
                x1 = $minX; y1 = $minY; x2 = $maxX; y2 = $maxY
            }
        }
        $stream.Dispose()
        [Console]::Out.WriteLine((ConvertTo-Json -InputObject @($lines) -Compress))
        [Console]::Out.Flush()
    } catch {
        [Console]::Out.WriteLine("[]")
        [Console]::Out.Flush()
    }
}
"""
        self._win_ocr_proc = subprocess.Popen(
            ["powershell", "-NoProfile", "-Command", ps_daemon_script],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        return self._win_ocr_proc

    def _run_windows_native_ocr(
        self, image: np.ndarray
    ) -> List[Tuple[List[List[float]], str, float]]:
        """
        Windows 10/11 내장 WinRT 한국어 OCR 엔진(Windows.Media.Ocr)을 상주 워커로 호출하여
        각 줄(Line)의 실제 바운딩 박스 4점 좌표([[x1,y1], [x2,y2], [x3,y3], [x4,y4]])와
        인식된 한글 텍스트를 PaddleOCR와 동일한 포맷으로 초고속 반환합니다.
        """
        import json
        import os
        import tempfile
        import cv2

        with tempfile.NamedTemporaryFile(suffix=".bmp", delete=False) as tmp_file:
            tmp_path = tmp_file.name

        try:
            cv2.imwrite(tmp_path, image)
            with self._win_ocr_lock:
                proc = self._ensure_win_ocr_daemon()
                assert proc.stdin is not None and proc.stdout is not None
                proc.stdin.write(tmp_path + "\n")
                proc.stdin.flush()
                stdout_str = proc.stdout.readline().strip()

            if not stdout_str:
                return []

            raw_lines = json.loads(stdout_str)
            if isinstance(raw_lines, dict):
                raw_lines = [raw_lines]

            parsed_items: List[Tuple[List[List[float]], str, float]] = []
            for item in raw_lines:
                if not item:
                    continue
                x1, y1 = float(item.get("x1", 0)), float(item.get("y1", 0))
                x2, y2 = float(item.get("x2", 0)), float(item.get("y2", 0))
                box = [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]
                text = str(item.get("text_spaced") or item.get("text") or "").strip()
                if text:
                    parsed_items.append((box, text, 0.95))
            return parsed_items
        except Exception as exc:
            logger.error(f"[WindowsNativeOCR] 추론 오류: {exc}")
            return []
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass

    def run_ocr(self, image: np.ndarray) -> List[Tuple[List[List[float]], str, float]]:
        """
        PaddleOCR를 실행하고 결과를 표준화된 리스트로 반환합니다.
        Returns:
            List of (box_points, text, confidence)
            box_points: [[x1, y1], [x2, y2], [x3, y3], [x4, y4]]
        """
        if getattr(self, "_use_windows_native_ocr", False):
            return self._run_windows_native_ocr(image)

        if self._ocr_model is None:
            self._load_model()
            if getattr(self, "_use_windows_native_ocr", False):
                return self._run_windows_native_ocr(image)
            if self._ocr_model is None:
                return []

        canvas, scale = self._to_fixed_canvas(image)
        raw_result: Any = self._ocr_model.ocr(canvas, cls=False)
        del canvas
        parsed_items: List[Tuple[List[List[float]], str, float]] = []

        if not raw_result:
            return parsed_items

        # PaddleOCR는 페이지 단위 리스트 [ [ [box, (text, score)], ... ] ] 형태로 반환
        lines = raw_result[0] if isinstance(raw_result, list) and len(raw_result) > 0 else []
        if not lines:
            return parsed_items

        for line in lines:
            if not line or len(line) < 2:
                continue
            box = [[float(x) / scale, float(y) / scale] for x, y in line[0]]
            text_info = line[1]
            if isinstance(text_info, (list, tuple)) and len(text_info) >= 2:
                text = str(text_info[0]).strip()
                score = float(text_info[1])
                if text:
                    parsed_items.append((box, text, score))

        return parsed_items

    @staticmethod
    def calculate_bbox_area(box: List[List[float]]) -> float:
        """
        4점 바운딩 박스 좌표 [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]로부터
        가로(Width) × 세로(Height) 면적을 계산합니다.
        """
        xs = [pt[0] for pt in box]
        ys = [pt[1] for pt in box]
        width = max(xs) - min(xs)
        height = max(ys) - min(ys)
        return float(max(0.0, width) * max(0.0, height))

    def extract_largest_text_as_product_name(self, first_frame_image: np.ndarray) -> Optional[str]:
        """
        [Phase 1: 메타데이터 Vision Fallback]
        프론트엔드에서 안티 크롤링 등으로 인해 product_name을 보내지 못한 경우,
        0초 차 최상단 화면(first_frame_image)을 스캔하여
        바운딩 박스 면적(Width × Height)이 가장 큰 텍스트를 상품명으로 추출합니다.
        """
        ocr_items = self.run_ocr(first_frame_image)
        if not ocr_items:
            return None

        best_text: Optional[str] = None
        max_area: float = -1.0

        for box, text, score in ocr_items:
            # 신뢰도가 너무 낮거나 1글자 노이즈인 경우 제외
            if score < 0.5 or len(text.strip()) < 2:
                continue
            area = self.calculate_bbox_area(box)
            if area > max_area:
                max_area = area
                best_text = text.strip()

        if best_text:
            best_text = re.sub(r"(?<=[가-힣])\s+(?=[가-힣])", "", best_text)
            # 한국어 OCR에서 중량 표기 '120g'의 소문자 'g'가 숫자 '9'로 오인식되는 흔한 패턴 보정
            best_text = re.sub(r"(\b\d{2,4})9\b", r"\1g", best_text)
        return best_text

    def find_anchor_and_initial_ingredients(
        self,
        tiles: List[Tuple[int, np.ndarray]],
        anchor_keywords: List[str] = settings.ANCHOR_KEYWORDS,
    ) -> Tuple[Optional[int], List[str]]:
        """
        [Phase 2 초고속 1-Pass 최적화]
        타일링된 이미지 블록들을 순회하며 앵커 키워드('원재료명', '영양정보', '성분명' 등)의
        Global Y 좌표를 찾음과 동시에, 이미 1차 스캔에서 인식된 앵커 하단(y ~ y + ROI_CROP_HEIGHT) 텍스트로
        성분 추출을 즉시 시도합니다.
        선명한 일반 상세페이지의 경우 2차 ROI 크롭 + CLAHE 재추론(OCR 2회차)을 생략하여 속도를 2배 이상 단축합니다.
        """
        normalized_anchors = [kw.replace(" ", "") for kw in anchor_keywords]

        for y_offset, tile_img in tiles:
            ocr_items = self.run_ocr(tile_img)
            for box, text, _ in ocr_items:
                normalized_text = text.replace(" ", "")
                if any(anchor in normalized_text for anchor in normalized_anchors):
                    min_y_in_tile = min(pt[1] for pt in box)
                    global_anchor_y = int(y_offset + min_y_in_tile)
                    logger.info(
                        f"[Anchor Found] 키워드 매칭 텍스트='{text}', Global Y={global_anchor_y}px"
                    )
                    # 동일 타일 내 앵커 Y좌표 하단(ROI_CROP_HEIGHT 범위) 텍스트를 즉시 수집
                    roi_top = min_y_in_tile - settings.ROI_TOP_PADDING
                    roi_bottom = min_y_in_tile + settings.ROI_CROP_HEIGHT
                    roi_items = [
                        item for item in ocr_items
                        if item[2] >= 0.45 and roi_top <= min(pt[1] for pt in item[0]) <= roi_bottom
                    ]
                    roi_items.sort(key=lambda item: (min(pt[1] for pt in item[0]), min(pt[0] for pt in item[0])))
                    fast_ingredients = self.clean_ingredient_text("\n".join(t for _, t, _ in roi_items))
                    return global_anchor_y, fast_ingredients

        return None, []

    def find_anchor_y_coordinate(
        self,
        tiles: List[Tuple[int, np.ndarray]],
        anchor_keywords: List[str] = settings.ANCHOR_KEYWORDS,
    ) -> Optional[int]:
        """
        [Phase 2: 1차 스캔 및 앵커(Anchor) 키워드 탐색]
        타일링된 이미지 블록들을 순회하며 '원재료명', '영양정보', '성분명', '원재료 및 함량' 등의
        앵커 키워드가 포함되어 있는지 검사합니다.
        발견 즉시 원본 이미지 기준의 Y 좌표(상단 Y)를 반환합니다.
        """
        anchor_y, _ = self.find_anchor_and_initial_ingredients(tiles, anchor_keywords)
        return anchor_y

    def extract_and_clean_ingredients(self, enhanced_roi: np.ndarray) -> List[str]:
        """
        [Phase 2: 2차 정밀 추출 및 정규표현식(Regex) 후처리]
        CLAHE 및 샤프닝 전처리가 완료된 ROI 이미지에서 텍스트를 추출하고,
        불필요한 안내 문구/특수문자/원산지/비율 표기를 제거한 뒤
        쉼표(,) 및 줄바꿈 기준으로 분리하여 중복 없는 성분 리스트(List[str])를 반환합니다.
        """
        ocr_items = self.run_ocr(enhanced_roi)
        if not ocr_items:
            return []

        # Y 좌표(위->아래), X 좌표(좌->우) 순으로 정렬하여 문맥 순서 보장
        ocr_items.sort(key=lambda item: (min(pt[1] for pt in item[0]), min(pt[0] for pt in item[0])))

        raw_lines = [text for _, text, score in ocr_items if score >= 0.45]
        combined_text = "\n".join(raw_lines)

        return self.clean_ingredient_text(combined_text)

    @staticmethod
    def clean_ingredient_text(raw_text: str) -> List[str]:
        """
        정규표현식(Regex) 기반 성분 텍스트 정제 파이프라인:
        1. 앵커 타이틀(원재료명 및 함량, 전성분 등) 제거
        2. 괄호 안의 원산지/함량 비율(예: (미국산), (국산 10%), [밀]) 제거 또는 정제
        3. 퍼센트 수치(12.5%) 및 불필요한 특수기호 제거
        4. 쉼표(,), 가운뎃점(·), 슬래시(/), 줄바꿈(\n) 기준으로 토큰 분리
        5. 노이즈 불용어 제거 및 순서 보존 중복 제거(Deduplication)
        """
        if not raw_text or not raw_text.strip():
            return []

        text = raw_text

        # 1. 앵커 헤더 문구 제거
        header_pattern = r"(원재료명\s*및\s*함량|원재료\s*및\s*함량|원재료명|영양정보|전성분|성분명|원료명|및\s*함량)\s*[:：]?"
        text = re.sub(header_pattern, ",", text)

        # 1-1. 한국어 OCR에서 닫는 괄호+쉼표 '), '가 '기 '로 오인식되는 패턴(예: '소맥분(미국산기 ' -> '소맥분(미국산), ') 보정
        text = re.sub(r"\(([^(),]{1,25}?)기(?=\s|,|$)", r"(\1),", text)
        text = re.sub(r"([가-힣]{2,10}(?:산|우유|대두|밀|계란|땅콩))기(?=\s|,|$)", r"(\1),", text)

        # 2. 괄호 내부 처리:
        #    - 알레르기 핵심 원료(우유, 대두, 밀, 땅콩, 계란, 난류, 새우, 게, 메밀, 호두, 잣, 아몬드, 복숭아, 토마토, 돼지고기, 쇠고기, 닭고기, 오징어, 조개류)가
        #      괄호 안에 표기된 경우(예: 버터(우유), 레시틴(대두)) 추천/알레르기 엔진이 감지할 수 있도록 쉼표 토큰으로 보존합니다.
        #    - 원산지(미국산, 호주산, 국내산, 국산 등) 및 단순 부연설명 괄호는 제거합니다.
        #    (#62) 괄호 안을 지우지 않고 쉼표로 풀어 펼친다. '(밀:미국산)'·'(대두유)'·'(우유, 대두)'처럼 가장 흔한 표기가
        #    통째로 사라지던 문제. 원산지·함량 조각은 아래 불용어·원산지 규칙이 걸러낸다.
        text = re.sub(r"[()\[\]{}]", ",", text)

        # 3. 함량 퍼센트 수치(예: 15.2%, 100%) 제거
        text = re.sub(r"\d+(?:\.\d+)?\s*%", "", text)

        # 4. 구분자 통일: 줄바꿈, 가운뎃점(·, •), 세미콜론(;), 콜론(:) 등을 쉼표(,)로 변환
        text = re.sub(r"[\n\r•·;:/|]+", ",", text)
        # 문장 끝 마침표도 구분자('밀 함유. 같은 제조시설…'이 한 토큰으로 붙어 '밀'을 놓치던 문제, #62)
        text = re.sub(r"\.(?=\s|$)", ",", text)
        # 쉼표가 블러로 유실되어 한글 성분명 뒤에 영문 접두 성분(예: L-글루탐산나트륨)이 공백으로 이어진 경우 분리
        text = re.sub(r"(?<=[가-힣])\s+(?=[A-Za-z]\s*-)", ",", text)

        # 5. 한글, 영문, 숫자, 하이픈(-, L-글루탐산나트륨 등 보존), 쉼표(,), 공백 외 특수문자 제거
        text = re.sub(r"[^가-힣a-zA-Z0-9,\-\s]", " ", text)

        # 6. 토큰 분리 및 정제
        stopwords = {
            "함유", "포함", "외", "기타", "기준", "일일영양성분", "영양성분",
            "나트륨", "탄수화물", "당류", "지방", "트랜스지방", "포화지방", "콜레스테롤", "단백질",
            "미국산", "호주산", "국내산", "국산", "중국산", "독일산", "말레이시아산",
        }

        cleaned_ingredients: List[str] = []
        seen = set()

        for token in text.split(","):
            # 다중 공백 압축 및 양끝 하이픈/공백 제거
            item = re.sub(r"\s+", " ", token).strip(" -_.")
            # OCR 엔진이 한글 음절 사이에 불필요한 공백을 삽입한 경우(예: "소 맥 분" -> "소맥분") 보정
            item = re.sub(r"(?<=[가-힣])\s+(?=[가-힣])", "", item)
            if not item:
                continue

            # 숫자만으로 이루어진 토큰이나 1글자 노이즈 제외. 단 한 글자 알레르기 원료(밀·게·잣·굴·깨·콩)는 보존(#62)
            if item.isdigit() or (len(item) < 2 and item not in ALLERGEN_SINGLE_CHARS):
                continue

            # 원산지 단독 토큰이나 불용어 제외. '아황산'·'구연산' 같은 성분은 원산지가 아니다(#62)
            if item in stopwords or (item.endswith("산") and len(item) <= 4 and item not in ACID_INGREDIENTS):
                continue

            # 머리말('알레르기 유발물질 …')만 떼고 남은 원료는 보존한다. '같은 제조시설에서 땅콩 사용' 같은 혼입 표시는
            # 그대로 남겨 추천 쪽이 알레르기로 판정하게 한다(지우면 경고가 사라진다, #62). 상담 안내 문구만 버린다.
            if "소비자" in item:
                continue
            item = re.sub(r"알레르기\s*(?:유발\s*물질|정보|표시)?|유발\s*물질", "", item).strip(" -_.")
            if not item or (len(item) < 2 and item not in ALLERGEN_SINGLE_CHARS):
                continue

            if item not in seen:
                seen.add(item)
                cleaned_ingredients.append(item)

        return cleaned_ingredients


# 모듈 레벨 헬퍼: 워커 프로세스 어디서든 싱글톤 인스턴스를 즉시 획득
def get_ocr_engine() -> OCRSingletonEngine:
    return OCRSingletonEngine()

