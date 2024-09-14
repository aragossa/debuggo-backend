from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By

from geminiAPI import GeminiAPI


def test_google_search():
    # Initialize the WebDriver (replace 'chromedriver' with your WebDriver)

    login = 'ilya.ploskovitov@thrivedx.com'
    password = 'QA889noc1!'
    driver = webdriver.Chrome()
    gemini = GeminiAPI()

    # Open Google's homepage
    driver.get("https://lucyqa.lucysecurity.com/admin/login")
    page_source = driver.page_source

    response = gemini.get_locator('field',"email", html_code=page_source)
    email_locator = response.text.replace('`', '')
    print(email_locator)
    driver.find_element(By.XPATH, email_locator).send_keys(login)

    response = gemini.get_locator('field',"password", html_code=page_source)
    password_locator = response.text.replace('`', '')
    print(password_locator)
    driver.find_element(By.XPATH, password_locator).send_keys(password)

    response = gemini.get_locator('button',"Login", html_code=page_source)
    login_locator = response.text.replace('`', '')
    print(login_locator)
    element = driver.find_element(By.XPATH, login_locator).click()

    #
    #
    # # Find the search bar element (by name attribute)
    # search_box = driver.find_element(By.NAME, "q")
    #
    # # Type a search query
    # search_box.send_keys("Selenium automation")
    #
    # # Submit the query (simulate pressing Enter)
    # search_box.send_keys(Keys.RETURN)
    #
    # # Verify the page title contains the search term
    # assert "Selenium automation" in driver.title
    #
    # Close the browser
    driver.quit()

if __name__ == "__main__":
    test_google_search()