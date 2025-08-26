import os

model = os.popen("getprop ro.product.model").read().strip()
manufacturer = os.popen("getprop ro.product.manufacturer").read().strip()
version = os.popen("getprop ro.build.version.release").read().strip()

print("Model:", model)
print("Manufacturer:", manufacturer)
print("Android Version:", version)
