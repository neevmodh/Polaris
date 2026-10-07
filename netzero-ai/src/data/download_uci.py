import os, zipfile, requests
URL='https://archive.ics.uci.edu/static/public/235/individual+household+electric+power+consumption.zip'
os.makedirs('data/raw',exist_ok=True)
r=requests.get(URL,timeout=120); r.raise_for_status()
z='data/raw/uci_power.zip'; open(z,'wb').write(r.content)
with zipfile.ZipFile(z) as f: f.extractall('data/raw/uci')
print('saved and extracted UCI household dataset')
