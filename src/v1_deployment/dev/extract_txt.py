import cv2
import numpy as np
from PIL import Image
from pytesseract import pytesseract
import tempfile
from PIL import Image



image_path = "/home/machvision/Pictures/123.png"
print("image says 27.59\n")

img = cv2.imread(image_path)
norm_img = np.zeros((img.shape[0], img.shape[1]))
img = cv2.normalize(img, norm_img, 0, 255, cv2.NORM_MINMAX)
img = cv2.fastNlMeansDenoisingColored(img, None, 10, 10, 7, 15)

gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
_, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)


text = pytesseract.image_to_string(img)
cv2.imwrite("img.png", img)
print("regular image says: ")
print(text[:-1])

text = pytesseract.image_to_string(gray)
cv2.imwrite("gray.png", gray)
print("\ngray image says: ")
print(text[:-1])

text = pytesseract.image_to_string(thresh)
cv2.imwrite("thresh.png", thresh)
print("\nthresh image says: ")
print(text[:-1])

