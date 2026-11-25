import sys, resource, cv2, time
from paddleocr import PaddleOCR
sizes = [int(x) for x in sys.argv[1].split(',')]
ocr = PaddleOCR(lang='korean', use_angle_cls=False, use_gpu=False, cpu_threads=8, rec_batch_num=1, show_log=False)
rec = ocr.text_recognizer; orig = rec.resize_norm_img
def pick(r):
    for s in sizes:
        if r <= s: return float(s)
    return float(sizes[-1])
rec.resize_norm_img = lambda img, r: orig(img, pick(img.shape[1] / img.shape[0]))
rss = lambda: resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024
img = cv2.imread('/img/page4.jpg')
crops = [img[150:182, 40:40 + 60 + 9*k] for k in range(120)]
t = time.time(); rec(crops); a = time.time() - t
t = time.time(); r = ocr.ocr(img[0:1600], cls=False); b = time.time() - t
print(f'sizes={sizes} 120-distinct-widths peak {rss():.0f}MiB {a:.1f}s | page tile {b:.1f}s lines={len(r[0])} peak {rss():.0f}MiB', flush=True)
