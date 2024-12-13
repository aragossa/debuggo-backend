import google.generativeai as genai
import os


class GeminiAPI():
    def __init__(self):
        self.__gemini_api_key = 'AIzaSyBdaeZU_rNW7PEI9tszlIl_UOn_frEKw_U'



    def get_locator(self, element_type, element_name, html_code, text_prompt):
        genai.configure(api_key=self.__gemini_api_key)

        if not text_prompt:
            text_prompt = (f"""Find on in this html code the best locator fo the {element_name} {element_name} and give me xpath locator to find it. Example of response:
            Give me just xpath expression
    {html_code}""")



        model = genai.GenerativeModel("gemini-2.0-flash-exp")

        response = model.generate_content(text_prompt)

        return response


