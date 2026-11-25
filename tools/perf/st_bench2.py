import time, os, torch
from sentence_transformers import SentenceTransformer
m = SentenceTransformer('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2', device='cpu', revision='e8f8c211226b894fcb81acc59f3b34ba3efd5f42')
texts = [f'벤치 상품 {i} | 브랜드{i%50} | 카테고리{i%20} | product | 설명 {i} 고소한 맛의 간식' for i in range(256)]
for th in (1, 2, 4, 8, os.cpu_count()):
    torch.set_num_threads(th); m.encode(texts[:32])
    t = time.perf_counter(); m.encode(texts, batch_size=32, normalize_embeddings=True); d = time.perf_counter() - t
    print(f'threads={th}: {len(texts)/d:.0f} texts/s', flush=True)
