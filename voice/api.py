import requests

# Using default reference audio set at startup
response = requests.get(
    "http://127.0.0.1:9880",
    params={"text": "Hello there. who are you? I am Mona", "text_language": "en"},
)

with open("output.wav", "wb") as f:
    f.write(response.content)
