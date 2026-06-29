cd "c:\Users\guoji\Pictures\cover\coverdesign"
pip install pyinstaller -q
pyinstaller --onefile --windowed --name "CoverGenerator" --icon=Cat.ico --add-data "config-testing.json;." --add-data "cover;cover" --add-data "materials;materials" main-testing.py