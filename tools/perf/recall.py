"""Ingredient recall through the real engine. Ground truth = replay of make_images.py RNG."""
import random, sys, os, cv2, time, resource
mode = sys.argv[1]
pages = [int(x) for x in sys.argv[2].split(',')]
random.seed(7)
words=['밀가루','설탕','쇼트닝(대두유)','정제소금','버터(우유)','전분','혼합분유(우유, 대두)','팜유','계란','땅콩','호두','젖산','향료','정제수','물엿','코코아분말']
sizes=[(1280,800),(1366,900),(1440,1600),(1920,1080),(1280,2600),(1600,3400),(1100,700),(1920,4200)]
truth=[]
for i,(w,h) in enumerate(sizes):
    y=140
    while y<h-300:
        [random.choice(words) for _ in range(8)]; y+=40
    truth.append(random.sample(words,10))
from app.vision import ocr_engine as oe
from app.vision.preprocessor import split_into_horizontal_tiles
if mode == 'original':
    oe.OCRSingletonEngine._to_fixed_canvas = staticmethod(lambda img: (img, 1.0))
    oe.OCRSingletonEngine._fix_recognition_width = staticmethod(lambda m: None)
eng = oe.get_ocr_engine()
clean = oe.OCRSingletonEngine.clean_ingredient_text
tot_hit = tot_exp = 0; t = time.time()
for i in pages:
    img = cv2.imread(f'/img/page{i}.jpg')
    _, got = eng.find_anchor_and_initial_ingredients(split_into_horizontal_tiles(img))
    exp = set(clean(', '.join(truth[i])))
    hit = len(exp & set(got)); tot_hit += hit; tot_exp += len(exp)
    print(f'  page{i}: {hit}/{len(exp)}', flush=True)
print(f'{mode} {os.getenv("OCR_DET_LIMIT_SIDE","736")}: recall {tot_hit}/{tot_exp} = {tot_hit/tot_exp:.0%} {time.time()-t:.0f}s peak {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024:.0f}MiB', flush=True)
