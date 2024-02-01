import asyncio
import os
import openai
import json
import re
import requests
import logging
import pyperclip
from pyppeteer import launch
from telegram import Bot, Update
from telegram.ext import *
from quickstart import AIsolve
from dotenv import load_dotenv
from datetime import datetime



load_dotenv()


TOKEN = os.environ['TOKEN']
HOSTUSER = os.environ['HOSTUSER']
HOSTPASS = os.environ['HOSTPASS']
browser = None
status = None
hprofile_pic = None  # Global variable to store the profile picture
allowed_users = []
GET_INPUT, SHANNONGRAM_UPDATE = range(2)

current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def decode_emoji_sequence(sequence: str) -> str:
    def replace_unicode_escapes(match):
        return bytes(match.group(0), 'ascii').decode('unicode_escape')
    
    return re.sub(r'\\U[a-fA-F0-9]{8}|\\u[a-fA-F0-9]{4}', replace_unicode_escapes, sequence)




async def get_chat_id(update, context):
    chat_id = update.message.chat.id
    await update.message.reply_text(f"Chat ID: {chat_id}")

async def add_user(update, context):
    # Ensure only you (the admin) can add users
    if update.message.from_user.id == 1402836486:
        username_to_add = context.args[0]  # Assuming you use the command like "/adduser <username>"
        if username_to_add and username_to_add not in allowed_users:
            allowed_users.append(username_to_add)
            await update.message.reply_text(f"User {username_to_add} added to the whitelist.")
        else:
            await update.message.reply_text(f"User {username_to_add} is already in the whitelist.")
    else:
        await update.message.reply_text("You are not authorized to add users.")

async def remove_user(update, context):
    # Ensure only you (the admin) can remove users
    if update.message.from_user.id == 1402836486:
        username_to_remove = context.args[0]  # Assuming you use the command like "/removeuser <username>"
        if username_to_remove and username_to_remove in allowed_users:
            allowed_users.remove(username_to_remove)
            await update.message.reply_text(f"User {username_to_remove} removed from the whitelist.")
        else:
            await update.message.reply_text(f"User {username_to_remove} is not in the whitelist.")
    else:
        await update.message.reply_text("You are not authorized to remove users.")

async def log_to_group(update: Update, context: CallbackContext, message: str):
    user = update.message.from_user  # This gets the user who sent the message
    group_chat_id = '-4010528128'  # Replace this with the ID of your group chat
    await context.bot.send_message(chat_id=group_chat_id, text=message)

def download_image(url, filename):
    response = requests.get(url)
    with open(filename, 'wb') as file:
        file.write(response.content)

def query_openai(user_message, captions):
    system_message_content = (
        f"If I had a table of 3x3 images (or maybe 4x4 if i dont mention enough then its 3x3) described in simple captions, "
        f"first row is caption 1-3, second row is caption 4-6, and last row is caption 7-9, "
        f"and then I was tasked to answer the question {user_message}, "
        f"tell me the exact captions that match or answer this prompt correctly in numbers "
        f"simply return the numbers in plaintext separated by commas and wrap them within {{}} FIRST AT THE TOP OF YOUR RESPONSE, "
        f"DO NOT SAY ANYTHING AFTER. MAKE SURE THE COMMA SEPARATED NUMBERS ARE THE FIRST THING YOU SAY. "
        f"Here are the captions: "
        f"1: {captions[0]}, 2: {captions[1]}, 3: {captions[2]}, "
        f"4: {captions[3]}, 5: {captions[4]}, 6: {captions[5]}, "
        f"7: {captions[6]}, 8: {captions[7]}, 9: {captions[8]}"
        f"10: {captions[10]}, 11: {captions[11]}, 12: {captions[12]}"
    )
    response = openai.ChatCompletion.create(
    model="gpt-3.5-turbo",
    messages=[
        {
            "role": "system",
            "content": system_message_content
        },
        {
            "role": "user",
            "content": user_message
        }
    ]
    )
    gpt3_response = response['choices'][0]['message']['content'].strip()
    numbers_match = re.search(r'\{([\d,]+)\}', gpt3_response)
    if numbers_match:
        numbers_list = numbers_match.group(1).split(',')
        numbers_array = [int(number.strip()) for number in numbers_list]
    else:
        numbers_array = []
    return numbers_array

async def get_image_urls_from_payload_class(page):
    """Get all image URLs from elements with the class 'rc-imageselect-payload'."""
    image_urls = await page.evaluate('''() => {
        const images = document.querySelectorAll('.rc-imageselect-payload img');
        return Array.from(images).map(img => img.src);
    }''')
    return image_urls

async def process_images(page):
    try:
        for _ in range(3):
            await page.keyboard.press('Tab')
            await asyncio.sleep(1)
            
        await page.keyboard.press('Enter')
        await asyncio.sleep(1)
        await page.keyboard.down('Control')
        await page.keyboard.press('A')
        await page.keyboard.up('Control')
        await asyncio.sleep(1)
        await page.keyboard.down('Control')
        await page.keyboard.press('C')
        await page.keyboard.up('Control')

        user_message = pyperclip.paste()
        print(user_message) 
        image_urls = await get_image_urls_from_payload_class(page)

        if not image_urls:
            print("Unexpected number of images: 0")
            return

        # If you want to check the number of images and perform a specific action based on that:
        num_images = len(image_urls)
        if num_images not in [9, 12]:
            print(f"Unexpected number of images: {num_images}")
            return

        # Analyze the image URLs
        captions = AIsolve(image_urls)

        # Cleanup: Delete the temporary files
        for image_path in image_paths:
            os.remove(image_path)

        return captions
        response_numbers = query_openai(user_message, captions)
        if not response_numbers:  # Exit the loop if no matching images
            return "FAILED CAPTCHA"

        # Map the response to corresponding buttons:
        tab_indexes_to_click = [number + 3 for number in response_numbers]
        for index in tab_indexes_to_click:
            await page.click(f'td[tabindex="{index}"]')
            await asyncio.sleep(1)  # Wait for 1 second between clicks

        # Press tab 10 times and then enter
        page.click('#recaptcha-verify-button')
        await asyncio.sleep(5)

        if '/challenge' in page.url():
            return "SUCCESS"
        else:
            return "NO CHALLENGE IN URL"

    except Exception as e:
        print(f"Error: {str(e)}")
        return "ERROR"
    return "END OF FUNCTION"

async def login_to_instagram(update, context, page=None):   
    try:
        # If page is not provided as an argument, create a new one in the existing browser context.
        if not page:
            global browser
            browser = await launch(headless=False)  # Set headless to True if you want it to run in background

            page = await browser.newPage()

        # Open Browser
        await page.goto('https://instagram.com')
        await asyncio.sleep(5)

        # Simulate the tab presses and type in user and pass
        for _ in range(2):
            await page.keyboard.press('Tab')
            await asyncio.sleep(0.5)
        await page.keyboard.type(HOSTUSER)

        await page.keyboard.press('Tab')
        await page.keyboard.type(HOSTPASS)

        for _ in range(2):
            await page.keyboard.press('Tab')
            await asyncio.sleep(0.5)

        await page.keyboard.press('Enter')
        await page.waitForNavigation()

        await asyncio.sleep(2)
        current_url = page.url


        if "/challenge" in current_url:
            try:
                # Define your captcha selector
                # captcha_selector = '.rc-image-tile-33[src^="https://www.google.com/recaptcha/api2/payload?p="]'
                captcha_selector = 'recaptcha-checkbox goog-inline-block recaptcha-checkbox-unchecked rc-anchor-checkbox'
                # Wait for the captcha selector to appear for a defined timeout
                await asyncio.sleep(6)                
                if captcha_selector:
                    status = await process_images(page)  

                else:
                    await update.message.reply_text("Captcha element found but couldn't be selected.")
                    status = "CAPTCHA_ERROR"

            except TimeoutError:
                # If the captcha element doesn't appear in the given timeout, handle accordingly.
                await update.message.reply_text("Timeout while waiting for the captcha.")
                status = "CAPTCHA_TIMEOUT"


        if "accounts/suspended/" in current_url:
            status = "SUSPENDED ACCOUNT"

        else:
            if not "/challenge" in current_url:
                status = "SUCCESS"
                for _ in range(10):
                    await page.keyboard.press('Tab')
                    await asyncio.sleep(0.5)

                await page.keyboard.press('Enter')
                await asyncio.sleep(1)
                await page.keyboard.press('Enter')
            else:
                print("Unknown scenario encountered.")
                status = "UNKNOWN"


        # Add your checks for GlobalBanKeys and GlobalRetryKeys here



        print(f"Login status determined: {status}")  # <-- Add this line
        return status
    except Exception as e:
        # Here, you can log the exception or print it for debugging purposes.
        print(f"An error occurred: {e}")

async def close_browser(update: Update, context: CallbackContext):
    global browser
    if browser is not None:
        await browser.close()
        status = None
    else:
        await update.message.reply_text("Browser instance not initialized.")

async def bang_command(update, context):
    user = update.message.from_user.username
    if user not in allowed_users:
        await update.message.reply_text("You are not authorized to use this bot.")
        return
    if user in allowed_users: 
        print(f"Status retrieved in bang_command: {context.user_data.get('status')}")  

        global browser
        if context.user_data.get('status') == "SUCCESS":
            await update.message.reply_text("Please enter the target username or link:")
            return GET_INPUT
        else:
            await update.message.reply_text("You are not logged in.")
            return ConversationHandler.END

async def click_checkbox_via_js(page1):
    await page1.waitForSelector('input[type="checkbox"]', timeout=5000)  # Ensure the checkbox is present on the page

    # JavaScript code to find the checkbox and click it
    click_js = """
    (function() {
        const checkbox = document.querySelector('input[type="checkbox"]');
        if (checkbox) {
            checkbox.click();
            return 'Checkbox clicked';
        }
        return 'Checkbox not found';
    })();
    """

    result = await page1.evaluate(click_js)
    print(result)  # This will either print "Checkbox clicked" or "Checkbox not found"

async def set_zip_code_via_js(page1, zip_codee):
    await page1.waitForSelector('input[type="text"][name="zip code"]', timeout=5000)  # Ensure the input is present on the page

    # JavaScript code to find the input and set its value
    set_value_js = f"""
    (function() {{
        const zipInput = document.querySelector('input[type="text"][name="zip code"]');
        if (zipInput) {{
            zipInput.value = '{zip_codee}';
            return 'Value set';
        }}
        return 'Input not found';
    }})();
    """

    result = await page1.evaluate(set_value_js)
    print(result)  # This will either print "Value set" or "Input not found"

async def click_options_via_js(page):
    await page.waitForSelector('div[role="button"][tabindex="0"] > div > svg[aria-label="Options"]', timeout=5000)  # Ensure the "Options" parent div is present on the page

    # JavaScript code to find the parent "Options" div and click it
    click_js = """
    (function() {
        const svgElement = document.querySelector('div[role="button"][tabindex="0"] > div > svg[aria-label="Options"]');
        if (svgElement) {
            const parentDiv = svgElement.closest('div[role="button"]');
            const clickEvent = new MouseEvent('click', {
                'view': window,
                'bubbles': true,
                'cancelable': true
            });
            parentDiv.dispatchEvent(clickEvent);
            return 'Options clicked';
        }
        return 'Options not found';
    })();
    """

    result = await page.evaluate(click_js)
    print(result)  # This will either print "Options clicked" or "Options not found"

async def resetinsta_command(update, context):
    user = update.message.from_user.username
    if user not in allowed_users:
        await update.message.reply_text("You are not authorized to use this bot.")
        return
    if user in allowed_users: 
        global browser1
        if context.user_data.get('status') == "SUCCESS":
            await resetinsta(update, context)
        else:
            await update.message.reply_text("You are not logged in.")
            return ConversationHandler.END



async def set_profile_pic(update, context):
    user_id = update.message.from_user.id
    if context.user_data.get('status') == "awaiting_photo":
        if update.message.photo:
            # Get the highest resolution photo from the update
            photo_file = await update.message.photo[-1].photo_file
            
            # Generate a unique filename
            filename = f"{user_id}.jpg"
            # Download the photo
            await photo_file.download_to_drive(custom_path=filename)
            
            # Reset the state for the user and inform them
            del context.user_data['status']  # Clear the status
            await update.message.reply_text("Profile picture updated!")
        else:
            await update.message.reply_text("That's not a photo. Please send a photo or cancel the operation.")
    else:
        await update.message.reply_text("Please send the profile picture you want to set. Send a photo.")
        context.user_data[status] = 'awaiting_photo'

async def resetinsta(update, context):
    status = "pending"
    profile_pic_changed = False
    bio_changed = False
    full_name_changed = False
    category_changed = False
    load_dotenv()
    biography1 = "Official account of Marco Giampaolo .\nItalian manager \\U0001F604"
    biography = decode_emoji_sequence(biography1)
    full_name = os.environ['HOSTNAME']
    HOSTCATEGORY = os.environ['HOSTCATEGORY']
    hprofile_picurl = os.environ['PFP']

    try:
        print(biography)
        pages = await browser.pages()
        page1 = pages[1]

        # Open a new page (page2) for the target user's JSON
        page2 = await browser.newPage()
        await page2.goto(f"https://instagram.com/{HOSTUSER}/?__a=1&__d=dis")
        await asyncio.sleep(2)

        # Extract JSON from the content using a selector
        element = await page2.querySelector('body')
        content = await page2.evaluate('(element) => element.textContent', element)
        data = json.loads(content)
        business_match = re.search(r'"is_business_account":(true|false)', content)
        professional_match = re.search(r'"is_professional_account":(true|false)', content)
        category_name = re.search(r'"category_name":"(.*?)"', content)

        # Convert the string values to Python boolean values
        is_business_account = True if business_match and business_match.group(1) == "true" else False
        is_professional_account = True if professional_match and professional_match.group(1) == "true" else False

        # Determine the types based on the boolean values
        Creator = not is_business_account and is_professional_account
        Business = is_business_account and is_professional_account

        current_directory = os.path.dirname(os.path.abspath(__file__))

        # Define the image path
        hprofile_pic = os.path.join(current_directory, "downloaded_image.jpg")

        download_image(hprofile_picurl, hprofile_pic)

        await page1.bringToFront()
        await page1.goto(f"https://instagram.com/accounts/edit")
        await asyncio.sleep(3)
        await update.message.reply_text('Resetting...')
        if Business or Creator:
            if HOSTCATEGORY == category_name:
                pass
            if HOSTCATEGORY != category_name:
                await page1.goto(f"https://www.instagram.com/accounts/edit")  # navigate to edit page
                await asyncio.sleep(3)
                for _ in range(22):
                    await page1.keyboard.press('Tab')
                    await asyncio.sleep(0.5)
                await page1.keyboard.press('Enter')
                await asyncio.sleep(5)
        if not Business or Creator:
            await page1.goto(f"https://www.instagram.com/accounts/edit")  
            await asyncio.sleep(3)
            for _ in range(21):
                await page1.keyboard.press('Tab')
                await asyncio.sleep(0.5)
            await page1.keyboard.press('Enter')
            await asyncio.sleep(2)
            
            await page1.keyboard.press('Tab')
            await page1.keyboard.press('ArrowDown')
            await page1.keyboard.press('ArrowUp')
            await page1.keyboard.press('Tab')
            await page1.keyboard.press('Tab')
            await page1.keyboard.press('Tab')
            await asyncio.sleep(1)
            await page1.keyboard.press('Enter')
            await asyncio.sleep(2)

            # if Business:
            #     if not business_email:
            #         business_email = os.environ.get('EMAIL')
            #     # If business_phone_number is null or not present, get from environment variable
            #     if not business_phone_number:
            #         business_phone_number = os.environ.get('PHONE')
            #     if not street_address:
            #         street_address = os.environ.get('ADDRESS')
            #     if not zip_code:
            #         zip_code = os.environ.get('ZIP')
            #     if not city_name:
            #         city_name = os.environ.get('CITY')

            #     hiddenbiz = not (business_phone_number or street_address or zip_code or city_name)


            for _ in range(11):
                await page1.keyboard.press('Tab')
                await asyncio.sleep(1)
            await page1.keyboard.press('ArrowDown')
            await asyncio.sleep(1)

            await page1.keyboard.press('Tab')
            await asyncio.sleep(1)
            await page1.keyboard.press('Enter')
            await asyncio.sleep(2)
            #confirmpage
            await page1.keyboard.press('Tab')
            await asyncio.sleep(0.5)
            await page1.keyboard.press('Tab')
            await page1.keyboard.press('Enter')
            #categorypage
            # Find an element that contains the text "checkbox"
            await asyncio.sleep(2)
            await page1.evaluate('''() => {
                window.scrollTo(0, 0);
            }''')
            await asyncio.sleep(1)

            await click_checkbox_via_js(page1)

            await page1.keyboard.press('Tab')
            await asyncio.sleep(0.5)
            await page1.keyboard.press('Tab')
            await page1.keyboard.press('Enter')
            await asyncio.sleep(0.5)
            await page1.keyboard.type(HOSTCATEGORY)
            await asyncio.sleep(3)
            await page1.keyboard.press('Tab')
            await asyncio.sleep(0.5)
            await page1.keyboard.press('ArrowDown')
            await asyncio.sleep(0.5)
            await page1.keyboard.press('ArrowUp')
            await asyncio.sleep(0.5)
            await page1.keyboard.press('Tab')
            await asyncio.sleep(0.5)
            await page1.keyboard.press('Tab')
            await asyncio.sleep(0.5)
            await page1.keyboard.press('Enter')
            await asyncio.sleep(1)
            # #bizpage
            # if Business and hiddenbiz == True:
            #     for _ in range(18):
            #         await page1.keyboard.press('Tab')
            #         await asyncio.sleep(1)
            #     await page1.keyboard.press('Enter')
            # if Business and hiddenbiz == False:
            #     await asyncio.sleep(2)
            #     await page1.evaluate('''() => {
            #         window.scrollTo(0, 0);
            #     }''')
            #     await page1.keyboard.press('Tab')
            #     await page1.keyboard.press('Tab')
            #     await page1.keyboard.press('Enter')
            #     await asyncio.sleep(0.5)
            #     await page1.keyboard.type(business_email)
            #     await asyncio.sleep(0.5)
            #     await page1.keyboard.press('Tab')
            #     await asyncio.sleep(0.5)
            #     await page1.keyboard.press('Tab')
            #     await page1.keyboard.press('Enter')
            #     await asyncio.sleep(0.5)
            #     await page1.keyboard.type(business_phone_number)
            #     await page1.keyboard.press('Tab')
            #     await page1.keyboard.press('Enter')
            #     await asyncio.sleep(0.5)
            #     await page1.keyboard.type(street_address)
            #     await page1.keyboard.press('Tab')
            #     await page1.keyboard.press('Enter')
            #     await asyncio.sleep(0.5)
            #     await page1.keyboard.type(city_name)
            #     await asyncio.sleep(3)
            #     await page1.keyboard.press('Tab')
            #     await asyncio.sleep(0.5)
            #     await page1.keyboard.press('Enter')
            #     await page1.keyboard.press('Tab')
            #     await page1.click('input[name="zip code"]')
            #     await asyncio.sleep(0.5)

            #     await page1.keyboard.type(zip_code)
            #     await page1.evaluate('''() => {
            #         window.scrollTo(0, 0);
            #     }''')
            #     await asyncio.sleep(0.5)

            #     await click_checkbox_via_js(page1)
            #     for _ in range(2):
            #         await page1.keyboard.press('Tab')
            #         await asyncio.sleep(0.5)
            #     await page1.keyboard.press('Enter')
    #            await asyncio.sleep(3)

            await asyncio.sleep(3)

            await page1.keyboard.press('Tab')
            await page1.keyboard.press('Tab')
            await page1.keyboard.press('Enter')
            # if Business:
            #     update.message.reply_text(f'Switched to Business Account and Category has been set to {category_name}.')
            #     category_changed = True
            # if Creator:
            await update.message.reply_text(f'Switched to Business Account and Category has been set to {hcategory_name}.')
            category_changed = True

        if hprofile_pic:


            browser1 = await launch(headless=False)  # Adjust launch parameters as per your requirements

            # Open a new page in the new browser instance
            page3 = await browser1.newPage()
            await page3.goto(f"https://www.instagram.com/accounts/edit")
            await asyncio.sleep(2)
            current_url = page3.url

            if "challenge" in current_url or "?next" in current_url or "instagram.com" == current_url:
                    await page3.goto('https://instagram.com')
                    await asyncio.sleep(3)
                    
                    # Simulate the tab presses and type in user and pass
                    for _ in range(2):
                        await page3.keyboard.press('Tab')
                        await asyncio.sleep(0.5)
                    await page3.keyboard.type(HOSTUSER)
                    
                    await page3.keyboard.press('Tab')
                    await page3.keyboard.type(HOSTPASS)
                    
                    for _ in range(2):
                        await page3.keyboard.press('Tab')
                        await asyncio.sleep(0.5)
                    
                    await page3.keyboard.press('Enter')
                    await page3.waitForNavigation()

                    await asyncio.sleep(2)


                    if "/challenge" in current_url:
                        try:
                            # Define your captcha selector
                            # captcha_selector = '.rc-image-tile-33[src^="https://www.google.com/recaptcha/api2/payload?p="]'
                            captcha_selector = 'recaptcha-checkbox goog-inline-block recaptcha-checkbox-unchecked rc-anchor-checkbox'
                            # Wait for the captcha selector to appear for a defined timeout
                            await asyncio.sleep(6)                
                            if captcha_selector:
                                status = await process_images(page3)  
                                
                            else:
                                await update.message.reply_text("Captcha element found but couldn't be selected.")
                                status = "CAPTCHA_ERROR"
                            
                        except TimeoutError:
                            # If the captcha element doesn't appear in the given timeout, handle accordingly.
                            await update.message.reply_text("Timeout while waiting for the captcha.")
                            status = "CAPTCHA_TIMEOUT"
                            

                    if "accounts/suspended/" in current_url:
                        status = "SUSPENDED ACCOUNT"
                                        
                    
                    else:
                        if not "/challenge" in current_url:
                            status = "SUCCESS"
                            for _ in range(10):
                                await page3.keyboard.press('Tab')
                                await asyncio.sleep(0.5)
                    
                            await page3.keyboard.press('Enter')
                            await asyncio.sleep(1)
                            await page3.keyboard.press('Enter')
                        else:
                            print("Unknown scenario encountered.")
                            await update.message.reply_text("Had to login again. Please ensure the account is not facing any challenges.")
                            status = "UNKNOWN"

                    print(f"Login status determined: {status}")  # <-- Add this line

                    if status == "SUCCESS":
                        
                        await page3.goto(f"https://www.instagram.com/accounts/edit")  

                        await asyncio.sleep(2)
                        for _ in range(24):
                            await page3.keyboard.press('Tab')
                            await asyncio.sleep(1)
                        await page3.keyboard.press('Enter')
                        for _ in range(3):
                            await page3.keyboard.press('Tab')
                            await asyncio.sleep(1)
                        await page3.keyboard.press('Enter')
                        # Upload the profile picture
                        file_input = await page3.querySelector("input[type='file']")
                        await file_input.uploadFile(hprofile_pic)
                        await asyncio.sleep(1)
                        os.remove(hprofile_pic)  # Clean up the temporary file
                        await page3.reload()
                        await asyncio.sleep(3)
                        await page3.close()
                        await browser1.close()
                        await page1.bringToFront()
                        await update.message.reply_text("Profile picture has been changed successfully!")


                        profile_pic_changed = True

        
        if biography:

            await page1.goto(f"https://www.instagram.com/accounts/edit")  
            await asyncio.sleep(4)
            for _ in range(25):
                await page1.keyboard.press('Tab')
                await asyncio.sleep(0.5)
            await page1.keyboard.press('Enter')
            await page1.keyboard.down('Control')
            await page1.keyboard.press('A')
            await page1.keyboard.up('Control')
            await page1.keyboard.press('Backspace')
            await page1.keyboard.type(biography)
            for _ in range(6):
                await page1.keyboard.press('Tab')
                await asyncio.sleep(1)
            await page1.keyboard.press('Enter')
            await asyncio.sleep(3)
            await update.message.reply_text(f"Bio Changed to {biography}")
            bio_changed = True
        if not biography:
            await update.message.reply_text("No bio, bio not changed.")

        if full_name:
            await page1.goto(f"https://www.instagram.com/accounts/edit")  
            await asyncio.sleep(5)
            for _ in range(11):
                await page1.keyboard.press('Tab')
                await asyncio.sleep(1)
            await page1.keyboard.press('Enter')
            await asyncio.sleep(3)
            #inmeta:
            for _ in range(2):
                await page1.keyboard.press('Tab')
                await asyncio.sleep(1)
            await page1.keyboard.press('Enter')
            await asyncio.sleep(2)

            for _ in range(3):
                await page1.keyboard.press('Tab')
                await asyncio.sleep(1)
            await page1.keyboard.press('Enter')
            await asyncio.sleep(2)

            await page1.keyboard.press('Tab')
            await asyncio.sleep(1)
            await page1.keyboard.press('Enter')
            await asyncio.sleep(2)
            await page1.keyboard.down('Control')
            await page1.keyboard.press('A')
            await page1.keyboard.up('Control')
            await page1.keyboard.press('Backspace')
            await page1.keyboard.type(full_name)
            for _ in range(2):
                await page1.keyboard.press('Tab')
                await asyncio.sleep(1)
            await page1.keyboard.press('Enter')
            await asyncio.sleep(2)
            await update.message.reply_text("Name Changed")
            await page1.goto(f"https://www.instagram.com/accounts/edit")  # navigate to edit page
            await asyncio.sleep(3)
            full_name_changed = True


        if profile_pic_changed or bio_changed or full_name_changed or category_changed:
            status = "reset"
            user = update.message.from_user

            user = update.message.from_user
            message_to_log = f"{current_time} - BOT RESET BY User {user.username} ({user.id})"
            await log_to_group(update, context, message_to_log)

            await update.message.reply_text('Target reset:')
            if profile_pic_changed:
                await update.message.reply_text('Profile Pic = reset')

            if bio_changed:
                await update.message.reply_text('Bio = reset')

            if full_name_changed:
                await update.message.reply_text('Full Name = reset')
            
            if category_changed:
                await update.message.reply_text('Category = reset')
            if not profile_pic_changed:
                await update.message.reply_text('Profile Pic was not reset')

            if not bio_changed:
                await update.message.reply_text('Bio was not reset')

            if not full_name_changed:
                await update.message.reply_text('Full Name was not reset')

            if not category_changed:
                await update.message.reply_text('Category was not reset')

            await page1.goto(f"https://www.instagram.com/{HOSTUSER}")  
            await asyncio.sleep(3)
            sspage_path = "page.png"
            await page1.screenshot({'path': sspage_path})
            with open(sspage_path, 'rb') as sspage:
                await update.message.reply_photo(sspage)
            os.remove(sspage_path)  

        if status == "reset":
            await update.message.reply_text("Reset profile!")
            return ConversationHandler.END

    except Exception as e:
        await update.message.reply_text(f"Error: {str(e)}")
        return ConversationHandler.END

async def process_input(update, context):
    status = "pending"
    profile_pic_changed = False
    bio_changed = False
    full_name_changed = False
    category_changed = False
    try:
        target_input = update.message.text

        if target_input.startswith("@"):
            target_username = target_input[1:]
        elif target_input.startswith("https://www.instagram.com/"):
            target_username = target_input.split("/")[-2]
        else:
            await update.message.reply_text("Invalid input!")
            return ConversationHandler.END

        pages = await browser.pages()
        page1 = pages[1]

        # Open a new page (page2) for the target user's JSON
        page2 = await browser.newPage()
        await page2.goto(f"https://instagram.com/{target_username}/?__a=1&__d=dis")
        await asyncio.sleep(2)

        # Extract JSON from the content using a selector
        element = await page2.querySelector('body')
        content = await page2.evaluate('(element) => element.textContent', element)
        data = json.loads(content)
        
        profile_pic_url = re.search(r'"profile_pic_url_hd":"(.*?)"', content)



        # Extracting values from content
        biography = re.search(r'"biography":"(.*?)"', content)
        full_name = re.search(r'"full_name":"(.*?)"', content)
        category_name = re.search(r'"category_name":"(.*?)"', content)

        # Assigning the values
        profile_pic_url = profile_pic_url.group(1) if profile_pic_url and profile_pic_url.group(1) != "null" else None

        biography = biography.group(1) if biography and biography.group(1) != "" else None
        biography1 = biography.replace('\\n', ' ')
        cleaned_biography = decode_emoji_sequence(biography1) if biography else None



        full_name = full_name.group(1) if full_name and full_name.group(1) != "null" else None
        # Assuming you've already parsed the data into a dictionary named `data`
        business_match = re.search(r'"is_business_account":(true|false)', content)
        professional_match = re.search(r'"is_professional_account":(true|false)', content)

        # Convert the string values to Python boolean values
        is_business_account = True if business_match and business_match.group(1) == "true" else False
        is_professional_account = True if professional_match and professional_match.group(1) == "true" else False

        # Determine the types based on the boolean values
        Creator = not is_business_account and is_professional_account
        Business = is_business_account and is_professional_account


        business_email_match = re.search(r'"business_email":"(.*?)"', content)
        business_phone_number_match = re.search(r'"business_phone_number":"(.*?)"', content)
        street_address_match = re.search(r'"street_address":"(.*?)"', content)
        zip_code_match = re.search(r'"zip_code":"(.*?)"', content)
        city_name_match = re.search(r'"city_name":"(.*?)"', content)

        # Assigning the extracted values (if found) or setting them to None
        business_email = business_email_match.group(1) if business_email_match else None
        business_phone_number = business_phone_number_match.group(1) if business_phone_number_match else None
        street_address = street_address_match.group(1) if street_address_match else None
        zip_code = zip_code_match.group(1) if zip_code_match else None
        city_name = city_name_match.group(1) if city_name_match else None

        # Cleaning the city_name by rstripping backslashes
        cleaned_city_name = city_name.rstrip("\\") if city_name else None

        # Check if all the values are None to determine the hiddenbiz value
        hiddenbiz = all(x is None for x in [business_email, business_phone_number, street_address, zip_code, cleaned_city_name])
        category_name = category_name.group(1) if category_name and category_name.group(1) != "null" else None
        await page1.bringToFront()
        local_filename = "temp_profile_pic.jpg"
        download_image(profile_pic_url, local_filename)
        await update.message.reply_text('Profile Picture from target account to be changed:')
        await update.message.reply_photo(local_filename)
        await update.message.reply_text(f'Other info to be changed from target account:\n NAME: {full_name}\n BIO: {cleaned_biography}\n CATEGORY: {category_name}\n')
        print(cleaned_biography)
        print(full_name)
        print(Business)
        print(Creator)

        if profile_pic_url:
            browser1 = await launch(headless=False)  # Adjust launch parameters as per your requirements
            page3 = await browser1.newPage()
            await page3.goto(f"https://www.instagram.com/accounts/edit")  

            await asyncio.sleep(2)
            current_url = page3.url

            if "challenge" in current_url or "?next" in current_url or "instagram.com" == current_url:
                    await page3.goto('https://instagram.com')
                    await asyncio.sleep(3)
                    
                    # Simulate the tab presses and type in user and pass
                    for _ in range(2):
                        await page3.keyboard.press('Tab')
                        await asyncio.sleep(0.5)
                    await page3.keyboard.type(HOSTUSER)
                    
                    await page3.keyboard.press('Tab')
                    await page3.keyboard.type(HOSTPASS)
                    
                    for _ in range(2):
                        await page3.keyboard.press('Tab')
                        await asyncio.sleep(0.5)
                    
                    await page3.keyboard.press('Enter')
                    await page3.waitForNavigation()

                    await asyncio.sleep(2)


                    if "/challenge" in current_url:
                        try:
                            # Define your captcha selector
                            # captcha_selector = '.rc-image-tile-33[src^="https://www.google.com/recaptcha/api2/payload?p="]'
                            captcha_selector = 'recaptcha-checkbox goog-inline-block recaptcha-checkbox-unchecked rc-anchor-checkbox'
                            # Wait for the captcha selector to appear for a defined timeout
                            await asyncio.sleep(6)                
                            if captcha_selector:
                                status = await process_images(page3)  
                                
                            else:
                                await update.message.reply_text("Captcha element found but couldn't be selected.")
                                status = "CAPTCHA_ERROR"
                            
                        except TimeoutError:
                            # If the captcha element doesn't appear in the given timeout, handle accordingly.
                            await update.message.reply_text("Timeout while waiting for the captcha.")
                            status = "CAPTCHA_TIMEOUT"
                            

                    if "accounts/suspended/" in current_url:
                        status = "SUSPENDED ACCOUNT"
                                        
                    
                    else:
                        if not "/challenge" in current_url:
                            status = "SUCCESS"
                            for _ in range(10):
                                await page3.keyboard.press('Tab')
                                await asyncio.sleep(0.5)
                    
                            await page3.keyboard.press('Enter')
                            await asyncio.sleep(1)
                            await page3.keyboard.press('Enter')
                        else:
                            print("Unknown scenario encountered.")
                            await update.message.reply_text("Had to login again. Please ensure the account is not facing any challenges.")
                            status = "UNKNOWN"

                    print(f"Login status determined: {status}")  # <-- Add this line

                    if status == "SUCCESS":
                        
                        await page3.goto(f"https://www.instagram.com/accounts/edit")  

                        await asyncio.sleep(2)
                        for _ in range(24):
                            await page3.keyboard.press('Tab')
                            await asyncio.sleep(1)
                        await page3.keyboard.press('Enter')
                        for _ in range(3):
                            await page3.keyboard.press('Tab')
                            await asyncio.sleep(1)
                        await page3.keyboard.press('Enter')
                        # Upload the profile picture
                        file_input = await page3.querySelector("input[type='file']")
                        await file_input.uploadFile(local_filename)
                        await asyncio.sleep(1)
                        os.remove(local_filename)  # Clean up the temporary file
                        await page3.reload()
                        await asyncio.sleep(3)
                        await page3.close()
                        await browser1.close()
                        await page1.bringToFront()

                        profile_pic_changed = True

            
         

        if biography:
            await page1.goto(f"https://www.instagram.com/accounts/edit")
            await asyncio.sleep(3) 
            for _ in range(25):
                await page1.keyboard.press('Tab')
                await asyncio.sleep(1)
            await page1.keyboard.press('Enter')
            await page1.keyboard.down('Control')
            await page1.keyboard.press('A')
            await page1.keyboard.up('Control')
            await page1.keyboard.press('Backspace')
            await page1.keyboard.type(cleaned_biography)
            for _ in range(6):
                await page1.keyboard.press('Tab')
                await asyncio.sleep(1)
            await page1.keyboard.press('Enter')
            await asyncio.sleep(3)
            await update.message.reply_text(f"Bio Changed to {cleaned_biography}")
            bio_changed = True
        if not biography:
            for _ in range(24):
                await page1.keyboard.press('Tab')
                await asyncio.sleep(1)
            await page1.keyboard.press('Enter')
            await page1.keyboard.down('Control')
            await page1.keyboard.press('A')
            await page1.keyboard.up('Control')
            await page1.keyboard.press('Backspace')
            for _ in range(5):
                await page1.keyboard.press('Tab')
                await asyncio.sleep(1)
            await page1.keyboard.press('Enter')
            await asyncio.sleep(3)
            await update.message.reply_text(f"Bio Changed to []")
            bio_changed = False
        
        if not full_name:
            await page1.goto(f"https://www.instagram.com/accounts/edit")  
            await asyncio.sleep(5)
            for _ in range(11):
                await page1.keyboard.press('Tab')
                await asyncio.sleep(1)
            await page1.keyboard.press('Enter')
            await asyncio.sleep(3)
            #inmeta:
            for _ in range(2):
                await page1.keyboard.press('Tab')
                await asyncio.sleep(1)
            await page1.keyboard.press('Enter')
            await asyncio.sleep(2)

            for _ in range(3):
                await page1.keyboard.press('Tab')
                await asyncio.sleep(1)
            await page1.keyboard.press('Enter')
            await asyncio.sleep(2)

            for _ in range(2):
                await page1.keyboard.press('Tab')
                await asyncio.sleep(1)
            await page1.keyboard.press('Enter')
            await asyncio.sleep(2)
            await page1.keyboard.down('Control')
            await page1.keyboard.press('A')
            await page1.keyboard.up('Control')
            await page1.keyboard.press('Backspace')                

            for _ in range(2):
                await page1.keyboard.press('Tab')
                await asyncio.sleep(1)
            await page1.keyboard.press('Enter')
            await asyncio.sleep(2)
            await update.message.reply_text("Name Changed")
            await page1.goto(f"https://www.instagram.com/accounts/edit")  # navigate to edit page
            await asyncio.sleep(3)
            full_name_changed = False

        if full_name:
            await page1.goto(f"https://www.instagram.com/accounts/edit")  
            await asyncio.sleep(5)
            for _ in range(11):
                await page1.keyboard.press('Tab')
                await asyncio.sleep(1)
            await page1.keyboard.press('Enter')
            await asyncio.sleep(3)
            #inmeta:
            await page1.keyboard.press('Tab')
            await asyncio.sleep(1)
            await page1.keyboard.press('Enter')
            await asyncio.sleep(2)

            for _ in range(3):
                await page1.keyboard.press('Tab')
                await asyncio.sleep(1)
            await page1.keyboard.press('Enter')
            await asyncio.sleep(2)

            for _ in range(2):
                await page1.keyboard.press('Tab')
                await asyncio.sleep(1)
            await page1.keyboard.press('Enter')
            await asyncio.sleep(2)
            await page1.keyboard.down('Control')
            await page1.keyboard.press('A')
            await page1.keyboard.up('Control')
            await page1.keyboard.press('Backspace')                

            await page1.keyboard.type(full_name)
            for _ in range(2):
                await page1.keyboard.press('Tab')
                await asyncio.sleep(1)
            await page1.keyboard.press('Enter')
            await asyncio.sleep(2)
            await update.message.reply_text("Name Changed")
            await page1.goto(f"https://www.instagram.com/accounts/edit")  # navigate to edit page
            await asyncio.sleep(3)
            full_name_changed = True

        if Business or Creator:
            await page1.goto(f"https://www.instagram.com/accounts/edit")  
            await asyncio.sleep(3)
            for _ in range(22):
                await page1.keyboard.press('Tab')
                await asyncio.sleep(0.5)
            await page1.keyboard.press('Enter')
            await asyncio.sleep(2)
            if Creator:
                for _ in range(11):
                    await page1.keyboard.press('Tab')
                    await asyncio.sleep(1)
                await page1.keyboard.press('ArrowDown')
                await page1.keyboard.press('ArrowUp')
                await page1.keyboard.press('Tab')
                await page1.keyboard.press('Tab')
                await page1.keyboard.press('Tab')
                await asyncio.sleep(1)
                await page1.keyboard.press('Enter')
                await asyncio.sleep(2)

            if Business:
                if not business_email:
                    business_email = os.environ.get('EMAIL')
                # If business_phone_number is null or not present, get from environment variable
                if not business_phone_number:
                    business_phone_number = os.environ.get('PHONE')
                if not street_address:
                    street_address = os.environ.get('ADDRESS')
                if not zip_code:
                    zip_code = os.environ.get('ZIP')
                if not city_name:
                    city_name = os.environ.get('CITY')

                hiddenbiz = not (business_phone_number or street_address or zip_code or city_name)


                for _ in range(11):
                    await page1.keyboard.press('Tab')
                    await asyncio.sleep(1)
                await page1.keyboard.press('ArrowDown')
                await asyncio.sleep(1)

                await page1.keyboard.press('Tab')
                await asyncio.sleep(1)
                await page1.keyboard.press('Enter')
                await asyncio.sleep(2)
            #confirmpage
            await page1.keyboard.press('Tab')
            await asyncio.sleep(0.5)
            await page1.keyboard.press('Tab')
            await page1.keyboard.press('Enter')
            #categorypage
            # Find an element that contains the text "checkbox"
            await asyncio.sleep(2)
            await page1.evaluate('''() => {
                window.scrollTo(0, 0);
            }''')
            await asyncio.sleep(1)

            await click_checkbox_via_js(page1)

            await page1.keyboard.press('Tab')
            await asyncio.sleep(0.5)
            await page1.keyboard.press('Tab')
            await page1.keyboard.press('Enter')
            await asyncio.sleep(0.5)
            await page1.keyboard.type(category_name)
            await asyncio.sleep(3)
            await page1.keyboard.press('Tab')
            await asyncio.sleep(0.5)
            await page1.keyboard.press('ArrowDown')
            await asyncio.sleep(0.5)
            await page1.keyboard.press('ArrowUp')
            await asyncio.sleep(0.5)
            await page1.keyboard.press('Tab')
            await asyncio.sleep(0.5)
            await page1.keyboard.press('Tab')
            await asyncio.sleep(0.5)
            await page1.keyboard.press('Enter')
            await asyncio.sleep(1)
            #bizpage
            if Business and hiddenbiz == True:
                for _ in range(18):
                    await page1.keyboard.press('Tab')
                    await asyncio.sleep(1)
                await page1.keyboard.press('Enter')
            if Business and hiddenbiz == False:
                await asyncio.sleep(2)
                await page1.evaluate('''() => {
                    window.scrollTo(0, 0);
                }''')
                await page1.keyboard.press('Tab')
                await page1.keyboard.press('Tab')
                await page1.keyboard.press('Enter')
                await asyncio.sleep(0.5)
                await page1.keyboard.type(business_email)
                await asyncio.sleep(0.5)
                await page1.keyboard.press('Tab')
                await asyncio.sleep(0.5)
                await page1.keyboard.press('Tab')
                await page1.keyboard.press('Enter')
                await asyncio.sleep(0.5)
                await page1.keyboard.type(business_phone_number)
                await page1.keyboard.press('Tab')
                await page1.keyboard.press('Enter')
                await asyncio.sleep(0.5)
                await page1.keyboard.type(street_address)
                await page1.keyboard.press('Tab')
                await page1.keyboard.press('Enter')
                await asyncio.sleep(0.5)
                await page1.keyboard.type(city_name)
                await asyncio.sleep(3)
                await page1.keyboard.press('Tab')
                await asyncio.sleep(0.5)
                await page1.keyboard.press('Enter')
                await page1.keyboard.press('Tab')
                await page1.click('input[name="zip code"]')
                await asyncio.sleep(0.5)

                await page1.keyboard.type(zip_code)
                await page1.evaluate('''() => {
                    window.scrollTo(0, 0);
                }''')
                await asyncio.sleep(0.5)

                await click_checkbox_via_js(page1)
                for _ in range(2):
                    await page1.keyboard.press('Tab')
                    await asyncio.sleep(0.5)
                await page1.keyboard.press('Enter')
                await asyncio.sleep(3)

            await page1.keyboard.press('Tab')
            await page1.keyboard.press('Tab')
            await page1.keyboard.press('Enter')
            if Business:
                update.message.reply_text(f'Switched to Business Account and Category has been set to {category_name}.')
                category_changed = True
            if Creator:
                update.message.reply_text(f'Switched to Business Account and Category has been set to {category_name}.')
                category_changed = True

        if profile_pic_changed or bio_changed or full_name_changed or category_changed:
            status = "impersonated"


            await update.message.reply_text('Target Impersonated:')
            if profile_pic_changed:
                await update.message.reply_text('Profile Pic = impersonated')

            if bio_changed:
                await update.message.reply_text('Bio = impersonated')

            if full_name_changed:
                await update.message.reply_text('Full Name = impersonated')
            
            if category_changed:
                await update.message.reply_text('Category = impersonated')
            if not profile_pic_changed:
                await update.message.reply_text('Profile Pic was not impersonated')

            if not bio_changed:
                await update.message.reply_text('Bio was not impersonated')

            if not full_name_changed:
                await update.message.reply_text('Full Name was not impersonated')

            if not category_changed:
                await update.message.reply_text('Category was not impersonated')

            await page1.goto(f"https://www.instagram.com/{HOSTUSER}")  
            await asyncio.sleep(3)
            sspage_path = "homepage.png"
            await page1.screenshot({'path': sspage_path})
            with open(sspage_path, 'rb') as sspage:
                await update.message.reply_photo(sspage)
            os.remove(sspage_path)  

        if status == "impersonated":
            await shannongram_update(page1, target_username, update)

    except Exception as e:
        await update.message.reply_text(f"Error: {str(e)}")
        return ConversationHandler.END

#tab down up tab tab
async def tab_and_sleep(page, num_tabs, sleep_duration=1):
    for _ in range(num_tabs):
        await page.keyboard.press('Tab')
        await asyncio.sleep(sleep_duration)

async def shannongram_update(page, target_user, update):
    await update.message.reply_text('Reporting Target...')
    await page.goto(f"https://www.instagram.com/{target_user}/")
    await asyncio.sleep(4)
    # Perform the sequence of actions
    await click_options_via_js(page)
    await asyncio.sleep(1)

    await tab_and_sleep(page, 2)
    await page.keyboard.press('Enter')
    await asyncio.sleep(1)

    await tab_and_sleep(page, 3)
    await page.keyboard.press('Enter')
    await asyncio.sleep(1)

    await tab_and_sleep(page, 3)
    await page.keyboard.press('Enter')
    await asyncio.sleep(1)

    await tab_and_sleep(page, 2)
    await page.keyboard.press('ArrowDown')
    await page.keyboard.press('ArrowUp')
    await page.keyboard.press('Tab')
    await page.keyboard.press('Enter')
    await asyncio.sleep(1)

    # Take a screenshot
    screenshot_path = "screenshot.png"
    await page.screenshot({'path': screenshot_path})

    # Send the screenshot to the user
    with open(screenshot_path, 'rb') as screenshot_file:
        await update.message.reply_photo(screenshot_file)

    os.remove(screenshot_path)  # Clean up the temporary file
    status = "REPORTED"
    if status == "REPORTED":
        await update.message.reply_text('Report Sent. User will be banned in the following 24 hr' + "'" + "s")

    user = update.message.from_user
    message_to_log = f"{current_time} - BOT RESET BY User {user.username} ({user.id})"
    await log_to_group(context, f"{current_time} - USER {user.username} ({user.id}) BANNED {target_username} WITH STATUS: {status}")

    return ConversationHandler.END

async def login_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.message.from_user.username
    if user not in allowed_users:
        await update.message.reply_text("You are not authorized to use this bot.")
        return
    if user in allowed_users: 
        status = context.user_data.get('status', None)
        print(f"Login status set in context: {status}")

        status = await login_to_instagram(update, context)
        context.user_data['status'] = status
        if status == "SUCCESS":
            await update.message.reply_text("Logged in successfully!")
        else:
            await update.message.reply_text(f'Login Status: {status}')

async def some_cancel_function(update: Update, _: CallbackContext) -> int:
    await update.message.reply_text('Operation cancelled!')
    return ConversationHandler.END

def main() -> None:
    application = Application.builder().token(TOKEN).build()

    conversation_handler = ConversationHandler(
        entry_points=[CommandHandler('bang', bang_command)],
        states={
            GET_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_input)],
        },
        fallbacks=[CommandHandler('cancel', some_cancel_function)],
    )

    
    # Build the application (assuming Application.builder() is valid in your context)

    # Add handlers to the application
    application.add_handler(conversation_handler)    

    application.add_handler(CommandHandler('close', close_browser))

    application.add_handler(CommandHandler('login', login_command))
    application.add_handler(CommandHandler('reset', resetinsta_command))
    application.add_handler(CommandHandler("getid", get_chat_id))
    application.add_handler(CommandHandler("adduser", add_user))
    application.add_handler(CommandHandler("removeuser", remove_user))
    application.add_handler(CommandHandler('setpfp', set_profile_pic))


    # Start the Bot's polling method
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
    loop = asyncio.get_event_loop()
    loop.run_until_complete(login_to_instagram())
    loop.run_until_complete(bang_command())
    loop.run_until_complete(resetinsta_command())