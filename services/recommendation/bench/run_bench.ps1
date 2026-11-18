# 학교 LLM(gemma-4-26b)으로 압축 방식 정확도 비교. 저장소 루트(Recommend Pipeline 폴더)에서 실행:
#   powershell -ExecutionPolicy Bypass -File services\recommendation\bench\run_bench.ps1
# API 키는 이 창에서만 쓰는 환경변수로 넣습니다 (파일에 저장 안 함).
if (-not $env:SUNMOON_API_KEY) {
  $sec = Read-Host "SUNMOON_API_KEY (hidden)" -AsSecureString
  $env:SUNMOON_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec))
}
py -m pip install -q pydantic toon-format
# LLMLingua-2 도 비교하려면 (torch 포함 수 GB, 처음 실행 때 모델 다운로드):  py -m pip install llmlingua
py -m services.recommendation.bench.compare_compression --llm local --note "gemma-4-26b 1회차"
