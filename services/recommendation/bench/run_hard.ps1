# 5차: 어려운 데이터셋(헷갈리는 식품 44개, 질의 13개)으로 학교 LLM 정확도 비교. 저장소 루트에서 실행:
#   powershell -ExecutionPolicy Bypass -File services\recommendation\bench\run_hard.ps1
# LLMLingua-2 는 3·4차 결과(압축 약 1초, 정보 9% 손실, 정확도 이득 없음)로 제외. 설치 필요 없음.
if (-not $env:SUNMOON_API_KEY) {
  $sec = Read-Host "SUNMOON_API_KEY (hidden)" -AsSecureString
  $env:SUNMOON_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec))
}
py -m pip install -q pydantic toon-format
py -m services.recommendation.bench.compare_compression --dataset hard --llm local --pace 2.5 --methods json toon compact compact8 --note "5차 hard gemma-4-26b"
