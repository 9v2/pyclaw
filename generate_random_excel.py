import openpyxl
import random

# Create a new workbook
wb = openpyxl.Workbook()
sheet = wb.active
sheet.title = "Random Data"

# Add headers
headers = ["Column A", "Column B", "Column C", "Column D"]
sheet.append(headers)

# Add 10 rows of random data
for _ in range(10):
    row_data = [random.randint(1, 100) for _ in range(len(headers))]
    sheet.append(row_data)

# Save the workbook
file_name = "random_data.xlsx"
wb.save(file_name)
print(f"File '{file_name}' created successfully.")