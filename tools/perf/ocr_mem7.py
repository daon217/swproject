import sys, resource, cv2, time
from paddleocr import PaddleOCR
mode = sys.argv[1]
ocr = PaddleOCR(lang='korean', use_angle_cls=False, use_gpu=False, cpu_threads=4, rec_batch_num=1, show_log=False)
rss = lambda: resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024
img = cv2.imread('/img/page4.jpg')
same = img[150:182, 40:700]
for i in range(1, 121):
    crop = same if mode == 'same' else img[150:182, 40:40 + 60 + 9*(i % 3)]   # 'three': only 3 widths
    ocr.text_recognizer([crop])
    if i in (1, 10, 40, 120): print(f'{mode} runs={i} peak {rss():.0f} MiB', flush=True)
