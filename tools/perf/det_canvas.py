import cv2, glob, numpy as np, resource, time
from paddleocr import PaddleOCR
def canvas(img, W, H):
    h, w = img.shape[:2]; s = min(W/w, H/h, 1.0)
    if s < 1: img = cv2.resize(img, (int(w*s), int(h*s)), interpolation=cv2.INTER_AREA)
    c = np.full((H, W, 3), 255, np.uint8); c[:img.shape[0], :img.shape[1]] = img; return c
pages = [cv2.imread(p)[0:1600] for p in sorted(glob.glob('/img/*.jpg'))]
for name, W, H, lim in [('native(no canvas)',0,0,736), ('canvas1920x1600 det736',1920,1600,736), ('canvas1920x1600 det1280',1920,1600,1280), ('canvas1280x1600 det960',1280,1600,960)]:
    ocr = PaddleOCR(lang='korean', use_angle_cls=False, use_gpu=False, cpu_threads=8, det_limit_side_len=lim, show_log=False)
    t = time.time(); counts = []
    for img in pages:
        x = img if not W else canvas(img, W, H)
        counts.append(len(ocr.ocr(x, rec=False, cls=False)[0] or []))
    print(f'{name}: boxes per page {counts} total={sum(counts)} {time.time()-t:.1f}s peak {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024:.0f}MiB', flush=True)
