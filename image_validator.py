import google.generativeai as genai
from PIL import Image
import google
import json

def is_relevant_content():
    GOOGLE_API_KEY = 'AIzaSyDnnYkKQyBGVM1kE2FitVNGav7aZVeMRDU'

    genai.configure(api_key=GOOGLE_API_KEY)
    # Load your image
    image = Image.open('model/data/login_page.png')

    text_prompt = ("""
                    Act as QA engineer. Visit website https://qa-lucy.thrivedx.io/admin/login and compare it with attached image
                    find as many deviations as possible in UI
                    Use the assumptions that the name may be different and slight deviations in color
                    If you find any issues give me it's locators in the response
                    In the response give expected result (in the attached image) and actual result (the website you visited)
                    You response should be as json:
                    {
                        "issue_1":{
                            "Description": "",
                            "**Expected": "",
                            "Actual": "",
                            "Locator": ""
                        } 
                    }
                    """)

    model = genai.GenerativeModel("gemini-2.5-pro-exp-03-25")
    for i in range(5):
        try:
            response = model.generate_content([text_prompt, image])
            break
        except google.api_core.exceptions.InternalServerError:
            continue
        except google.api_core.exceptions.DeadlineExceeded:
            continue
    try:
        valid_json = response.text.replace("`", "").replace("json", "")
        response_json = json.loads(valid_json)
        print(response_json)

    except ValueError as e:
        print(response.text)
        print(e)
        return False


if __name__ == '__main__':
    is_relevant_content()