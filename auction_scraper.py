import argparse
import time
import requests
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import unicodedata

def normalize_text(text):
    return unicodedata.normalize('NFKD', text).encode('ASCII', 'ignore').decode('utf-8').lower()


# Ustawienia globalne
TELEGRAM_BOT_TOKEN = ""
TELEGRAM_CHAT_ID = "822088787"
CHECK_INTERVAL = 300  # 5 minut
seen_offers = set()

def parse_args():
    parser = argparse.ArgumentParser(description="OLX działki scraper")
    parser.add_argument("-c", "--city", type=str, default="warszawa", help="Miasto do przeszukania (np. warszawa, krakow)")
    return parser.parse_args()

def parse_price(price_str):
    try:
        return int(''.join(filter(str.isdigit, price_str)))
    except:
        return float('inf')

def build_search_url(city):
    base_url = "https://www.olx.pl/nieruchomosci/dzialki/sprzedaz"
    params = "?search%5Bfilter_enum_type%5D%5B0%5D=dzialki-budowlane&search%5Bfilter_float_m%3Afrom%5D=360&search%5Bfilter_float_price%3Afrom%5D=150000&search%5Bfilter_float_price%3Ato%5D=600000"
    return f"{base_url}/{city.lower()}/{params}"

seen_offers = set()

def get_offers(city):
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--log-level=3")  # <--- wyłączenie DevTools logowania
    options.add_experimental_option('excludeSwitches', ['enable-logging'])  # <-- Ta opcja wyłącza DevTools logi

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    search_url = build_search_url(city)
    driver.get(search_url)

    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div[data-cy='l-card']"))
        )
    except:
        print("❌ Brak ogłoszeń lub problem ze stroną.")
        driver.quit()
        return []

    offers = []
    elements = driver.find_elements(By.CSS_SELECTOR, "div[data-cy='l-card']")

    for item in elements:
        try:
            title_element = item.find_element(By.TAG_NAME, "a")
            price_element = item.find_element(By.CSS_SELECTOR, "p[data-testid='ad-price']")
            location_element = item.find_element(By.CSS_SELECTOR, "p[data-testid='location-date']")

            try:
                area_element = item.find_element(By.CSS_SELECTOR, "span[data-testid='area']")
                area = area_element.text.strip().replace(" m²", "").replace(" ", "")
            except:
                area = "Brak danych"

            title = title_element.text.strip()
            price = price_element.text.strip()
            location = location_element.text.strip()
            link = title_element.get_attribute("href")

            location_only = normalize_text(location.split("-")[0].strip())
            city_normalized = normalize_text(city)

            if city_normalized not in location_only:
                print(f"🚫 Pomijam ofertę spoza miasta ({location}).")
                continue




            # Obliczenie ceny za m²
            try:
                price_value = int(price.replace(" ", "").replace("zł", ""))
                area_value = int(area) if area != "Brak danych" else None
                price_per_m2 = round(price_value / area_value, 2) if area_value else "Brak danych"
            except:
                price_per_m2 = "Brak danych"

            if link not in seen_offers:
                seen_offers.add(link)
                offers.append((title, price, location, price_per_m2, link))

        except Exception as e:
            print(f"Błąd przetwarzania ogłoszenia: {e}")

    driver.quit()
    return offers

def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"}

    try:
        response = requests.post(url, data=payload)
        if response.status_code != 200:
            print(f"Błąd wysyłania Telegram: {response.status_code}, {response.text}")
    except Exception as e:
        print(f"Błąd połączenia Telegram: {e}")

def main(city):
    global seen_offers
    while True:
        print(f"🔍 Sprawdzam nowe oferty działek w mieście: {city.title()}...")
        offers = get_offers(city)

        # Sortowanie ofert wg ceny
        offers.sort(key=lambda x: parse_price(x[1]))

        # Pokazywanie w konsoli liczby znalezionych ofert
        print(f"🔹 Znaleziono {len(offers)} ofert.")

        # Budowanie zbiorczej wiadomości
        if offers:
            message = f"📢 *Nowe oferty działek w {city.title()}:*\n\n"
            for idx, (title, price, location, price_per_m2, link) in enumerate(offers, 1):
                message += (
                    f"*{idx}.* 🏡 {title}\n"
                    f"📍 {location}\n"
                    f"💰 {price} ({price_per_m2} zł/m²)\n"
                    f"🔗 [Link do ogłoszenia]({link})\n\n"
                )
            send_telegram_message(message)
        else:
            send_telegram_message(f"ℹ️ Brak nowych ofert w mieście {city.title()}.")

        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    args = parse_args()
    city = args.city.lower()
    print(f"🚀 Uruchamiam scraper OLX dla miasta: {city.title()}")
    main(city)
