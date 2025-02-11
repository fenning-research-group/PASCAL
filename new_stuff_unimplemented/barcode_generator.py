"""
Generates a barcode based on the uid of the sample. Sample UID is generated in maestro.py stop().
"""

import json
import os
from barcode import EAN13
from barcode.writer import ImageWriter


def generate_barcode(json_path):
    with open(json_path, 'r') as f:
        data = json.load()
    if "uid" not in data:
        print("Provided JSON does not contain a UID.")
        return
    uid = data["uid"]
    tray_barcode = EAN13(uid, writer=ImageWriter())
    #saves as png
    file_name = f"{uid}_barcode"
    tray_barcode.save(file_name)
    return file_name

print("Enter sample log JSON path:")
path = input()
while os.path.exists(path) == False:
    print("Invalid file path given, please re-enter:")
    path = input()
output_name = generate_barcode(path)
print(f"Barcode saved as {output_name}.png")