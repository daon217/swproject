# 학교 LLM(gemma-4-26b)으로 압축 방식 정확도 비교. 저장소 루트(Recommend Pipeline 폴더)에서 실행:
#   powershell -ExecutionPolicy Bypass -File services\recommendation\bench\run_bench.ps1
# API 키는 이 창에서만 쓰는 환경변수로 넣습니다 (파일에 저장 안 함).
if (-not $env:SUNMOON_API_KEY) {
  $sec = Read-Host "SUNMOON_API_KEY (hidden)" -AsSecureString
  $env:SUNMOON_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec))
}
py -m pip install -q pydantic toon-format
# LLMLingua-2 비교용 (torch 포함, 처음 실행 때 압축 모델 약 700MB 다운로드). 실험 끝나면: py -m pip uninstall llmlingua torch transformers
py -m pip install -q llmlingua
py -m services.recommendation.bench.compare_compression --llm local --pace 2.5 --note "gemma-4-26b 1회차"
