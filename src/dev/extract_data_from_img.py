# Documentation of tesseract
# https://github.com/tesseract-ocr/tesseract/blob/main/doc/tesseract.1.asc

import cv2
import numpy as np
from PIL import Image
from pytesseract import pytesseract
import tempfile
from PIL import Image
import datetime

# image_path = "/home/machvision/Pictures/screenshot.png"
image_path = "/home/machvision/Documents/ptz_software/src/v1_deployment/dev/screenshot.png"


x1, y1 = 0, 0
x2, y2 = 450, 53


def processing_image_1(img):
    """
    inconsistancy issue with outputting no numbers every once inawhile that isn't clear
    visibly why 
    """
    roi = img[y1:y2, x1:x2]
    norm_roi = np.zeros_like(roi)
    roi = cv2.normalize(roi, norm_roi, 0, 255, cv2.NORM_MINMAX)
    roi = cv2.fastNlMeansDenoisingColored(roi, None, 10, 10, 7, 15)
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    # scaling up made a huge difference in consistancy
    scale = 4
    h, w = gray.shape
    gray_large = cv2.resize(gray, (w*scale, h*scale), interpolation=cv2.INTER_CUBIC)
    _, thresh = cv2.threshold(gray_large, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return thresh

def processing_image_2(img):
    """
    1 is consitantly better than 2. same issue 
    """
    roi = img[y1:y2, x1:x2]
    
    # Convert to grayscale directly
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    
    # Scale up significantly - this is crucial
    scale = 4
    h, w = gray.shape
    gray_large = cv2.resize(gray, (w*scale, h*scale), interpolation=cv2.INTER_CUBIC)
    
    # Simple threshold - often more reliable than complex processing
    _, thresh = cv2.threshold(gray_large, 127, 255, cv2.THRESH_BINARY)
    
    return thresh


def extract_text_from_image(img):
    pre_processed_image = processing_image_1(img)
    text = pytesseract.image_to_string(pre_processed_image)
    return text

def extract_number_from_image(img):
    pre_processed_image = processing_image_1(img)
    config = r'--oem 3 --psm 7 -c tessedit_char_whitelist=0123456789.'
    # pytesseract outputs string 
    number_str = pytesseract.image_to_string(pre_processed_image, config=config).strip()
    try: 
        number = float(number_str)
    except ValueError:
        number = 0.0
    return number

def test_comparison_extract_number_from_image(img):
    # Comparison 1
    pre_processed_image = processing_image_1(img)
    text = pytesseract.image_to_string(pre_processed_image)
    number = extract_numbers_from_text(text)

    now = datetime.datetime.now()
    save_image = Image.fromarray(cv2.cvtColor(pre_processed_image, cv2.COLOR_BGR2RGB))
    timestamp_str = now.strftime("%M_%S_%f")[:-3]  # minute_second_millisecond
    filename = f"{timestamp_str}_{number}_1.png"
    save_image.save(filename)
    print(f"Extracted timestamp Processing 1: {number}")


    config = r'--oem 3 --psm 7 -c tessedit_char_whitelist=0123456789.'
    text = pytesseract.image_to_string(pre_processed_image, config=config)   
    timestamp_str = now.strftime("%M_%S_%f")[:-3]  # minute_second_millisecond
    filename = f"{timestamp_str}_{text}_2.png"
    print(f"Extracted timestamp Processing 2: {text}")

    # Comparison 2 

    # pre_processed_image = processing_image_2(img)
    # text = pytesseract.image_to_string(pre_processed_image)
    # number = extract_numbers_from_text(text)

    # save_image = Image.fromarray(cv2.cvtColor(pre_processed_image, cv2.COLOR_BGR2RGB))
    # timestamp_str = now.strftime("%M_%S_%f")[:-3]  # minute_second_millisecond
    # filename = f"{timestamp_str}_{number}_2.png"
    # save_image.save(filename)
    # print(f"Extracted timestamp Processing 2: {number}")

    return number

def extract_numbers_from_text(text):
    number = ""
    # know length of the string 
    length = len(text)
    # then start from index 0 and if it is number add that to another string then move to next index
    for i in range(length):
        if text[i].isdigit():
            number += text[i]
    if not number:
        return 0
    number = int(number)
    return number


# img = cv2.imread(image_path)
# roi = img[y1:y2, x1:x2]
# norm_roi = np.zeros((roi.shape[0], roi.shape[1]))
# roi = cv2.normalize(roi, norm_roi, 0, 255, cv2.NORM_MINMAX)
# roi = cv2.fastNlMeansDenoisingColored(roi, None, 10, 10, 7, 15)
# gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
# _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

# # text = pytesseract.image_to_string(img)
# # cv2.imwrite("img.png", img)
# # print("regular image says: ")
# # print(text[:-1])

# # text = pytesseract.image_to_string(gray)
# # cv2.imwrite("gray.png", gray)
# # print("\ngray image says: ")
# # print(text[:-1])

# text = pytesseract.image_to_string(thresh)
# cv2.imwrite("thresh.png", thresh)
# print("\nthresh image says: ")
# print(text[:-1])

