import requests

if __name__ == '__main__':
    url = "http://localhost:8000/api/conversations/chat/"
    data = {
        "message": "I need to book a new appointment because my tooth hurts.",
        "name": "Test Patient",
        "email": "test@example.com"
    }
    try:
        response = requests.post(url, json=data)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.json()}")
    except Exception as e:
        print(f"Error: {e}")

