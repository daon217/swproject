import random
from PIL import Image, ImageDraw, ImageFont
F='/usr/share/fonts/truetype/nanum/NanumGothic.ttf'
random.seed(7)
words=['밀가루','설탕','쇼트닝(대두유)','정제소금','버터(우유)','전분','혼합분유(우유, 대두)','팜유','계란','땅콩','호두','젖산','향료','정제수','물엿','코코아분말']
sizes=[(1280,800),(1366,900),(1440,1600),(1920,1080),(1280,2600),(1600,3400),(1100,700),(1920,4200)]
for i,(w,h) in enumerate(sizes):
    im=Image.new('RGB',(w,h),'white'); d=ImageDraw.Draw(im)
    d.text((40,30),f'고소한 버터 쿠키 {i} 120g',fill='black',font=ImageFont.truetype(F,46))
    y=140
    small=ImageFont.truetype(F,22)
    while y<h-300:
        d.text((40,y),' '.join(random.choice(words) for _ in range(8)),fill=(60,60,60),font=small); y+=40
    d.text((40,h-260),'원재료명 및 함량',fill='black',font=ImageFont.truetype(F,30))
    d.text((40,h-210),', '.join(random.sample(words,10)),fill='black',font=small)
    d.text((40,h-170),'알레르기 유발물질: 밀, 대두, 우유 함유',fill='black',font=small)
    im.save(f'/o/page{i}.jpg',quality=85)
print('ok')
