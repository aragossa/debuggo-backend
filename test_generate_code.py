from geminiAPI import GeminiAPI


def test_google_search():
    url = 'https://lucyqa.lucysecurity.com/'
    gemini = GeminiAPI()
    text_prompt = f"""I'm QA Engineer and I want to automate login test. Generate a python code to login to this page {url}. give me just the code without any comments from your side"""
    response = gemini.get_locator('field',"email", html_code=None, text_prompt=text_prompt)

    python_code = response.text.replace('`', '')
    if python_code.startswith('python'):
        python_code = python_code.replace('python', '')
    print(python_code)
    exec(python_code)

if __name__ == "__main__":
    test_google_search()