import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
import csv

path = "/home/machvision/Downloads/11.csv"

car_data = {i: {'x': [], 'y': [], 'z': []} for i in range(6)}  # IDs 0-5

with open(path, 'r') as csvfile:
    csv_reader = csv.reader(csvfile)
    next(csv_reader)  # skip header
    for row in csv_reader:
        car_id = int(row[1])
        if 0 <= car_id <= 5:
            car_data[car_id]['x'].append(float(row[2])) 
            car_data[car_id]['y'].append(float(row[4])) 
            car_data[car_id]['z'].append(float(row[3])) 

fig = plt.figure()
ax = fig.add_subplot(111, projection='3d')

colors = ['red', 'blue', 'green', 'orange', 'purple', 'cyan']
for car_id in range(6):
    ax.scatter(
        car_data[car_id]['x'],  # X axis
        car_data[car_id]['y'],  # Y axis (vertical)
        car_data[car_id]['z'],  # Z axis (depth)
        s=10,
        color=colors[car_id],
        label=f'Car {car_id}'
    )

ax.set_title('Car Positions by ID (3D)')
ax.set_xlabel('X Position')
ax.set_ylabel('Z Position (vertical)')
ax.set_zlabel('Y Position (depth)')

ax.legend(markerscale=2)
plt.savefig('car_positions_3d.png', dpi=300)
plt.show()
plt.close()

