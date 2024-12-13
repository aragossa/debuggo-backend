import requests

url = "http://127.0.0.1:9000/generate_test_cases_from_data"

# Replace 'your_file_path' with the actual path to the file you want to send.
file_path = "../swagger.json"  # Example: 'test_file.json', 'test_file.yaml', 'test_file.png'


def send_request():


    with open(file_path, 'rb') as file:
        # Create a dictionary with the file to be uploaded.
        files = {'file': (file_path, file)}

        # Make the request to your FastAPI endpoint.
        response = requests.post(url, files=files)

        # Print the response from the server.
        print(response.status_code)
        print(response.text)


if __name__ == '__main__':
    send_request()