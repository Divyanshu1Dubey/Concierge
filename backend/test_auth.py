import urllib.request
import json
import urllib.error

if __name__ == '__main__':
    data = json.dumps({'email': 'admin@raleighdentistry.com', 'password': 'admin123'}).encode('utf-8')
    req = urllib.request.Request('http://localhost:8000/api/auth/token/', data=data, headers={'Content-Type': 'application/json'})

    try:
        res = urllib.request.urlopen(req)
        print(res.read().decode())
    except urllib.error.HTTPError as e:
        print(e.read().decode())

