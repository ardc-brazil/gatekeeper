import json
import requests

f = open('datasets.json')
data = json.load(f)
for i in data:
    del i["id"]
    c = {"name": i["name"]}
    del i["name"]
    c["data"] = i
    r = requests.post('http://ec2-34-194-118-180.compute-1.amazonaws.com/api/datasets/', json=c)
    print(r.status_code)

f.close()