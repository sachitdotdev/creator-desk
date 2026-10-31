import requests

# Test the endpoint
response = requests.post("http://localhost:8000/api/videos/test_video_id/process")

print(f"Status Code: {response.status_code}")
print(f"Response: {response.text}")