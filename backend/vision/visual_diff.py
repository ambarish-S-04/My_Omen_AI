from PIL import Image, ImageChops, ImageStat
from typing import Tuple

def calculate_screen_diff_percentage(img1: Image.Image, img2: Image.Image) -> float:
    """
    Calculates the percentage of pixels that changed between two screenshots.
    Useful to verify if a click or typing action actually changed anything on the screen.
    """
    if img1.size != img2.size:
        img2 = img2.resize(img1.size)

    # Convert to grayscale for fast diffing
    gray1 = img1.convert("L")
    gray2 = img2.convert("L")

    diff = ImageChops.difference(gray1, gray2)
    stat = ImageStat.Stat(diff)
    
    # Average pixel difference (0 to 255)
    avg_diff = stat.mean[0]
    percentage = (avg_diff / 255.0) * 100.0
    return round(percentage, 2)
