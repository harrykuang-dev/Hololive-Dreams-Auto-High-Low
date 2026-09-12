import cv2
import numpy as np
from PIL import Image

# 1. 读取原图
img = cv2.imread('icon.png')
h, w = img.shape[:2]

# 2. 创建 floodFill 专用掩膜（高宽各增加 2 像素）
mask = np.zeros((h + 2, w + 2), np.uint8)

# 3. 从四个角落向内蔓延检测背景白色（容差设为 18，兼容抗锯齿轻微杂色）
floodflags = 4 | (255 << 8) | cv2.FLOODFILL_MASK_ONLY
for pt in [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)]:
    cv2.floodFill(img, mask, pt, (0, 0, 0), loDiff=(18, 18, 18), upDiff=(18, 18, 18), flags=floodflags)

# 4. 生成 Alpha 透明通道（外部背景为 0，角色主体为 255）
bg_mask = mask[1:h+1, 1:w+1]
alpha = np.where(bg_mask == 255, 0, 255).astype(np.uint8)

# 5. 合成 RGBA 图像并保存
b, g, r = cv2.split(img)
rgba = cv2.merge([b, g, r, alpha])
cv2.imwrite('icon_transparent.png', rgba)

# 6. 一步直接生成适配 Windows 的多尺寸 ICO 文件
pil_img = Image.fromarray(cv2.cvtColor(rgba, cv2.COLOR_BGRA2RGBA))
pil_img.save('icon.ico', format='ICO', sizes=[(256,256), (128,128), (64,64), (48,48), (32,32), (16,16)])

print("✅ 已生成透明底 PNG (icon_transparent.png) 和适配图标 (icon.ico)")