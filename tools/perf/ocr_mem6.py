import sys, resource, cv2, math, time
from paddleocr import PaddleOCR
bucket, batch = int(sys.argv[1]), int(sys.argv[2])
ocr = PaddleOCR(lang='korean', use_angle_cls=False, use_gpu=False, cpu_threads=4, rec_batch_num=batch, show_log=False)
cls = type(ocr.text_recognizer)
print('recognizer class module:', cls.__module__, flush=True)
if bucket:
    orig = cls.resize_norm_img
    cls.resize_norm_img = lambda self, img, r: orig(self, img, math.ceil(r / bucket) * bucket)
rss = lambda: resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024
img = cv2.imread('/img/page4.jpg')
crops = [img[150:182, 40:40 + 60 + 9*k] for k in range(120)]   # 120 lines, all different widths
t = time.time()
for i in range(0, 120, 30):
    ocr.text_recognizer(crops[i:i+30])
    print(f'bucket={bucket} batch={batch} lines={i+30} peak {rss():.0f} MiB {time.time()-t:.1f}s', flush=True)
