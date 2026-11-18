# 압축 속도만 측정 (LLM 호출 없음, 키 필요 없음, 요청 제한 없음). 저장소 루트에서:
#   powershell -ExecutionPolicy Bypass -File services\recommendation\bench\run_speed.ps1
py -m services.recommendation.bench.compare_compression --repeat 20 --note "압축 속도만 (LLM 없음)"
