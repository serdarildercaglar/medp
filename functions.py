import sys
from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.support.ui import Select
from selenium.webdriver.support.ui import WebDriverWait as wait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.keys import Keys
from selenium.webdriver import ActionChains
from selenium.webdriver.common.keys import Keys
from bs4 import BeautifulSoup
import pandas as pd
import numpy as np
import requests
import time
import re
from fake_useragent import UserAgent
import undetected_chromedriver as uc

def get_driver(url):
    ua = UserAgent()
    options = uc.ChromeOptions()
    options.add_argument(f'user-agent={ua.random}')
    driver = uc.Chrome(options=options)
    driver.get(url)
    time.sleep(3)
    return driver



def click_tarama(driver):
    tarama_path = '//*[@id="navigation2"]/ul/li[2]/a'
    driver.find_element(By.XPATH, tarama_path).click()
    time.sleep(3)    
    
def üniversite_seç(driver, üniversite):
    path = '//*[@id="tabs-1"]/form/table/tbody/tr/td/table/tbody/tr[2]/td[2]/input[1]'
    driver.find_element(By.XPATH, path).click()
    driver.switch_to.window(driver.window_handles[1])
    # click by text
    time.sleep(2)
    driver.find_element(By.LINK_TEXT, üniversite).click()
    time.sleep(2)
    driver.switch_to.window(driver.window_handles[0])
    time.sleep(1)

    
def click_tez_türü(driver, tür="Tıpta Uzmanlık"):
    tez_türü_path = '//*[@id="tabs-1"]/form/table/tbody/tr/td/table/tbody/tr[2]/td[4]/select'
    driver.find_element(By.XPATH, tez_türü_path).click()
    # choose dropdown menu by text
    time.sleep(1)
    driver.find_element(By.XPATH, tez_türü_path).send_keys(tür)   
    time.sleep(1) 

def click_bul(driver):
    bul_path = '//*[@id="tabs-1"]/form/table/tbody/tr/td/table/tbody/tr[8]/td/input[3]'
    driver.find_element(By.XPATH, bul_path).click()
    time.sleep(2)    
    
def sonuç_sayısı(driver):
    soup = BeautifulSoup(driver.page_source, 'html.parser')
    sonuç_sayısı = soup.find("div", {"id": "divuyari"}).text
    sonuç_sayısı = re.findall(r'\d+', sonuç_sayısı)
    return int(sonuç_sayısı[0])    

def yıl_aralığı(driver, yıl1, yıl2):
    # yıl2 yıl1 den büyük olmalı
    yıl1_path = '//*[@id="tabs-1"]/form/table/tbody/tr/td/table/tbody/tr[2]/td[6]/select[1]'
    yıl2_path = '//*[@id="tabs-1"]/form/table/tbody/tr/td/table/tbody/tr[2]/td[6]/select[2]'
    driver.find_element(By.XPATH, yıl1_path).send_keys(yıl1)
    time.sleep(1)
    driver.find_element(By.XPATH, yıl2_path).send_keys(yıl2)
    time.sleep(1)
    
def click_process(driver, üni, sonuç=0, yıl1=0, yıl2=0):
    click_tarama(driver)
    üniversite_seç(driver, üni)
    click_tez_türü(driver)
    if yıl1 != 0:
        yıl_aralığı(driver, yıl1, yıl2)
    click_bul(driver)
    sonuç = sonuç_sayısı(driver)
    return sonuç    

def get_table(driver):
    
    soup = BeautifulSoup(driver.page_source, 'html.parser')
    # text/javascript
    data = soup.find_all("script", {"type": "text/javascript"})[5]
    data = str(data)    
    # tez no: >484903</span>" arasında kalan sayılar
    tez_no = re.findall(r'(?<=\)>)\d+(?=</span>)', data)
    yazar = re.findall(r'(?<=name: ")(.*?)(?=",)', data)
    yıl = re.findall(r'(?<=age: ")\d+(?=",)', data)
    title = re.findall(r'(?<=weight: ")(.*?)(?=</span>)', data)
    üniversite = re.findall(r'(?<=uni:")(.*?)(?=",)', data)
    tez_türü = re.findall(r'(?<=important: ")(.*?)(?=",)', data)
    konu = re.findall(r'(?<=someDate: ")(.*?)(?=",)', data)
    tez_detay  = r'#FF0000;\\\"(.+?)>'
    tez_detay = re.findall(tez_detay, data)
    
    return pd.DataFrame({"tez_no": tez_no,
                         "yazar": yazar,
                         "yıl": yıl,
                         "title": title,
                         "üniversite": üniversite,
                         "tez_türü": tez_türü,
                         "konu": konu,
                         "tez_detay": tez_detay})


def get_abstract(driver,tez_detay,tez_no):
    driver.execute_script(tez_detay)
    time.sleep(0.15)
    soup = BeautifulSoup(driver.page_source, 'html.parser')
    tezno = soup.find_all("tr", {"class": "renkp"})[0].find_all("td")[0].text.replace("\n\t","").strip()
    while tezno != tez_no:
        driver.execute_script(tez_detay)
        time.sleep(0.3)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        tezno = soup.find_all("tr", {"class": "renkp"})[0].find_all("td")[0].text.replace("\n\t","").strip()
        time.sleep(0.1)
    try:
        en_absract = soup.find(id = 'td1').text
    except:
        en_absract = np.nan
    try:
        tr_absract = soup.find(id = 'td0').text
    except:
        tr_absract = np.nan
    return en_absract, tr_absract         