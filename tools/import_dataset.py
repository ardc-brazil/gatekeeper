import json
import requests

f = open('datasets.json')
data = json.load(f)
for i in data:
    del i["id"]
    c = {"name": i["name"]}
    del i["name"]
    c["data"] = i
    r = requests.post('http://localhost:9092/api/v1/datasets/', json=c, headers={'X-Api-Key':'2836396d-7316-4db2-859b-d9047d4b3469', 'X-Api-Secret': '1234'})
    print(r.status_code)

f.close()