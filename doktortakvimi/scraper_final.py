import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import random
import os
import json
from datetime import datetime
import logging
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import argparse

# Logging yapılandırması
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("doctor_scraper.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class DoctorScraper:
    def __init__(self, base_url, start_page=1, end_page=500, delay_min=3, delay_max=7, 
                 save_interval=10, proxy_list=None, checkpoint_file="checkpoint.json"):
        """
        Doktortakvimi sitesinden doktor bilgilerini çeken sınıf
        
        Args:
            base_url (str): Temel URL (ör: "https://www.doktortakvimi.com/ara")
            start_page (int): Başlangıç sayfa numarası
            end_page (int): Bitiş sayfa numarası
            delay_min (int): Minimum bekleme süresi (saniye)
            delay_max (int): Maksimum bekleme süresi (saniye)
            save_interval (int): Kaç sayfada bir verilerin kaydedileceği
            proxy_list (list): Kullanılacak proxy listesi
            checkpoint_file (str): Kontrol noktası dosyası
        """
        self.base_url = base_url
        self.start_page = start_page
        self.end_page = end_page
        self.delay_min = delay_min
        self.delay_max = delay_max
        self.save_interval = save_interval
        self.proxy_list = proxy_list or []
        self.checkpoint_file = checkpoint_file
        self.doctors_data = []
        self.last_scraped_page = self.load_checkpoint()
        
        # Kullanılabilecek User-Agent'lar
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36 Edg/91.0.864.59',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36'
        ]
        
        # Retry mekanizması
        self.session = requests.Session()
        retry_strategy = Retry(
            total=5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
            backoff_factor=1
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
    
    def load_checkpoint(self):
        """Kontrol noktasını yükler"""
        if os.path.exists(self.checkpoint_file):
            try:
                with open(self.checkpoint_file, 'r', encoding='utf-8') as f:
                    checkpoint_data = json.load(f)
                
                # Eski veriyi de yükleyelim
                doctors_file = checkpoint_data.get('doctors_file')
                if doctors_file and os.path.exists(doctors_file):
                    self.doctors_data = pd.read_csv(doctors_file, encoding='utf-8-sig').to_dict('records')
                    logger.info(f"Yüklenen doktor sayısı: {len(self.doctors_data)}")
                
                return checkpoint_data.get('last_page', self.start_page - 1)
            except Exception as e:
                logger.error(f"Kontrol noktası yüklenirken hata: {e}")
                return self.start_page - 1
        return self.start_page - 1
    
    def save_checkpoint(self, page, doctors_file=None):
        """Kontrol noktasını kaydeder"""
        try:
            checkpoint_data = {
                'last_page': page,
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'doctors_file': doctors_file
            }
            with open(self.checkpoint_file, 'w', encoding='utf-8') as f:
                json.dump(checkpoint_data, f, ensure_ascii=False, indent=4)
            logger.info(f"Kontrol noktası kaydedildi: Sayfa {page}")
        except Exception as e:
            logger.error(f"Kontrol noktası kaydedilirken hata: {e}")
    
    def get_random_proxy(self):
        """
        Proxy listesinden rastgele bir proxy seçer ve uygun formata dönüştürür
        IP:Port:Username:Password formatını http://Username:Password@IP:Port formatına dönüştürür
        """
        if not self.proxy_list:
            return None
            
        proxy_str = random.choice(self.proxy_list)
        return self.get_formatted_proxy(proxy_str)
    
    def get_formatted_proxy(self, proxy_str):
        """
        Proxy string'ini uygun formata dönüştürür
        """
        # IP:Port:Username:Password formatını kontrol et
        parts = proxy_str.split(':')
        if len(parts) == 4:  # ip:port:username:password
            ip, port, username, password = parts
            return f"http://{username}:{password}@{ip}:{port}"
        
        # Diğer durumlarda olduğu gibi kullan
        return proxy_str
    
    def get_random_user_agent(self):
        """Rastgele bir user agent döndürür"""
        return random.choice(self.user_agents)
    
    def get_page(self, page_number):
        """Belirtilen sayfa numarasındaki doktor listesi sayfasını alır"""
        # URL'de '?' karakteri var mı kontrolü
        if '?' in self.base_url:
            # URL'de zaten parametreler varsa & ile ekle
            url = f"{self.base_url}&page={page_number}"
        else:
            # URL'de henüz parametre yoksa ? ile başla
            url = f"{self.base_url}?page={page_number}"
            
        headers = {'User-Agent': self.get_random_user_agent()}
        proxies = {}
        
        logger.info(f"Sayfa alınıyor: {url}")
        
        # Proxy ile ve proxy olmadan deneme
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                # İlk denemede proxy kullan, sonraki denemelerde farklı proxy veya proxy olmadan dene
                if attempt == 0 and self.proxy_list:
                    proxy = self.get_random_proxy()
                    if proxy:
                        logger.info(f"Proxy kullanılıyor: {proxy}")
                        proxies = {'http': proxy, 'https': proxy}
                elif attempt == 1 and self.proxy_list and len(self.proxy_list) > 1:
                    # İkinci denemede farklı bir proxy dene
                    current_proxy = proxies.get('http', '')
                    available_proxies = [p for p in self.proxy_list if self.get_formatted_proxy(p) != current_proxy]
                    if available_proxies:
                        proxy = self.get_formatted_proxy(random.choice(available_proxies))
                        logger.info(f"Farklı proxy deneniyor: {proxy}")
                        proxies = {'http': proxy, 'https': proxy}
                    else:
                        # Farklı proxy yoksa proxy kullanma
                        logger.info("Farklı proxy bulunamadı, proxy olmadan deneniyor")
                        proxies = {}
                else:
                    # Son denemede proxy kullanma
                    logger.info("Proxy olmadan deneniyor")
                    proxies = {}
                
                response = self.session.get(url, headers=headers, proxies=proxies, timeout=15)  # Timeout süresini düşürdük
                response.raise_for_status()
                
                logger.info(f"Sayfa başarıyla alındı, durum kodu: {response.status_code}")
                return response.text
                
            except requests.RequestException as e:
                logger.error(f"Sayfa {page_number} alınırken hata (Deneme {attempt+1}/{max_attempts}): {e}")
                # Son denemede de başarısız olursa None döndür
                if attempt == max_attempts - 1:
                    return None
                # Sonraki deneme için bekle
                time.sleep(2)
        
        return None  # Tüm denemeler başarısız olursa None döndür
    
    def scrape_doctor_info(self, html_content):
        """
        HTML içeriğinden doktor bilgilerini çıkarır
        Bu fonksiyon çalışan koddan alınmıştır
        """
        if not html_content:
            return []
            
        soup = BeautifulSoup(html_content, 'html.parser')
        doctors_list = []
        
        logger.info("HTML içeriği ayıklanıyor...")
        
        # Tüm doktor kartlarını bul - çalışan koddan
        doctor_cards = soup.find_all('div', class_='dp-doctor-card')
        
        if not doctor_cards:
            logger.warning("dp-doctor-card sınıfına sahip elementler bulunamadı")
            return []
            
        logger.info(f"Toplam {len(doctor_cards)} doktor kartı bulundu")
        
        for card in doctor_cards:
            try:
                doctor_info = {}
                
                # Doktor adı
                name_element = card.find('span', attrs={'data-tracking-id': 'result-card-name'})
                if not name_element:
                    name_element = card.find('span', itemprop='name')
                    
                if name_element:
                    doctor_info['name'] = name_element.text.strip()
                else:
                    logger.debug(f"Doktor ismi bulunamadı, bu kartı atlıyor")
                    continue  # İsim bulunamadıysa bu doktoru atla
                
                # Profil resmi
                img_element = card.find('img')
                if img_element:
                    doctor_info['profile_image'] = img_element.get('src')
                
                # Branş bilgisi
                specialization = card.find('span', attrs={'data-test-id': 'doctor-specializations'})
                if not specialization:
                    specialization = card.find('h4', class_='h5')
                    
                if specialization:
                    doctor_info['specialization'] = specialization.text.strip()
                
                # Değerlendirme sayısı
                reviews = card.find('span', class_='opinion-numeral')
                if reviews:
                    doctor_info['reviews'] = reviews.text.strip()
                
                # Doktor onaylı profil mi?
                verified = card.find('span', attrs={'title': 'Teyit edilmiş profil'})
                doctor_info['verified_profile'] = bool(verified)
                
                # Profil URL'si
                profile_url = card.find('a', attrs={'data-id': 'address-context-cta'})
                if not profile_url:
                    profile_url = card.find('a', class_='text-body')
                    
                if profile_url:
                    doctor_info['profile_url'] = profile_url.get('href')
                    # Tam URL oluştur
                    if doctor_info['profile_url'] and not doctor_info['profile_url'].startswith('http'):
                        doctor_info['profile_url'] = f"https://www.doktortakvimi.com{doctor_info['profile_url']}"
                
                # Adres bilgisi ve diğer detaylar için doktor kartının altındaki adres kartını bul
                # Çalışan koddan alınan çözüm
                try:
                    # Doktor kartının parent elementini bulalım
                    parent = card.parent
                    if parent:
                        # Doktor kartından sonraki elementi bulalım
                        next_element = parent.find_next('div', class_='doctor-card-address')
                        if next_element:
                            # Adres metni
                            address_text = next_element.find('span', class_='text-truncate')
                            if address_text:
                                doctor_info['address'] = address_text.text.strip()
                            
                            # Google harita linki
                            map_link = next_element.find('a', attrs={'data-test-id': 'address-map-link'})
                            if map_link:
                                doctor_info['map_link'] = map_link.get('href')
                            
                            # Kurumsal isim (eğer varsa)
                            entity_name = next_element.find('p', attrs={'data-test-id': 'entity-name'})
                            if entity_name:
                                doctor_info['institution'] = entity_name.text.strip()
                            
                            # İl ve ilçe bilgileri (meta tag'lerden)
                            city = next_element.find('meta', attrs={'data-test-id': 'city-address'})
                            province = next_element.find('meta', attrs={'data-test-id': 'province-address'})
                            if city and province:
                                doctor_info['location'] = f"{city.get('content')}, {province.get('content')}"
                            
                            # Online hizmet bilgisi
                            online_service = next_element.find('a', class_='nav-link', text=lambda t: t and 'Online' in t)
                            doctor_info['online_available'] = bool(online_service)
                except Exception as e:
                    logger.error(f"Adres bilgisi alınırken hata: {e}")
                
                doctors_list.append(doctor_info)
                
            except Exception as e:
                logger.error(f"Doktor bilgisi ayıklanırken hata: {e}")
        
        return doctors_list
    
    def save_doctors_data(self, output_file=None):
        """Doktor verilerini CSV dosyasına kaydeder"""
        if not self.doctors_data:
            logger.warning("Kaydedilecek doktor verisi bulunamadı")
            return None
            
        if output_file is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_file = f"doctors_data_{timestamp}.csv"
        
        try:
            df = pd.DataFrame(self.doctors_data)
            df.drop_duplicates(subset=['name', 'profile_url'], keep='first', inplace=True)
            df.to_csv(output_file, index=False, encoding='utf-8-sig')
            logger.info(f"Doktor verileri kaydedildi: {output_file}")
            return output_file
        except Exception as e:
            logger.error(f"Veriler kaydedilirken hata: {e}")
            return None
    
    def scrape(self):
        """Tüm sayfaları tarar ve doktor bilgilerini çeker"""
        start_time = time.time()
        problem_pages = []  # Sorunlu sayfaları takip et
        
        for page in range(self.last_scraped_page + 1, self.end_page + 1):
            try:
                logger.info(f"Sayfa {page} taranıyor...")
                
                # Sayfayı al
                html_content = self.get_page(page)
                if not html_content:
                    logger.warning(f"Sayfa {page} alınamadı, atlıyor ve daha sonra tekrar deneyecek...")
                    problem_pages.append(page)  # Sorunlu sayfayı listeye ekle
                    continue
                
                # Çalışan kod, doktor bilgilerini ayıkla
                doctors = self.scrape_doctor_info(html_content)
                logger.info(f"Sayfa {page}: {len(doctors)} doktor bulundu")
                
                if not doctors:
                    # Boş sayfa geldi, bu bir sorun olabilir veya sayfalar bitmiş olabilir
                    logger.warning(f"Sayfa {page} boş geldi, doktor bulunamadı")
                    
                    # Ardışık 3 boş sayfa varsa taramayı sonlandır
                    if page > 2 and page not in problem_pages:
                        empty_count = 1
                        for p in range(page-1, page-3, -1):
                            if p in problem_pages:
                                empty_count += 1
                        
                        if empty_count >= 3:
                            logger.info(f"Ardışık 3 sayfa boş, tarama durduruluyor.")
                            break
                
                # Doktor bilgilerini listeye ekle
                self.doctors_data.extend(doctors)
                
                # Periyodik olarak veriyi kaydet
                if page % self.save_interval == 0:
                    output_file = self.save_doctors_data()
                    self.save_checkpoint(page, output_file)
                
                # Random bekleme süresi
                sleep_time = random.uniform(self.delay_min, self.delay_max)
                logger.info(f"Bekleniyor: {sleep_time:.2f} saniye...")
                time.sleep(sleep_time)
                
            except KeyboardInterrupt:
                logger.warning("Kullanıcı tarafından durduruldu")
                output_file = self.save_doctors_data()
                self.save_checkpoint(page - 1, output_file)
                break
                
            except Exception as e:
                logger.error(f"Sayfa {page} işlenirken hata: {e}")
                # Hata oluştuğunda da veriyi kaydedelim
                output_file = self.save_doctors_data()
                self.save_checkpoint(page - 1, output_file)
                # Daha uzun süre bekle
                time.sleep(random.uniform(10, 15))
        
        # Sorunlu sayfaları tekrar dene
        if problem_pages:
            logger.info(f"{len(problem_pages)} adet sorunlu sayfa tekrar deneniyor...")
            for page in problem_pages:
                try:
                    logger.info(f"Sorunlu sayfa {page} tekrar deneniyor...")
                    
                    # Sayfayı al (proxy olmadan dene)
                    html_content = self.get_page(page)
                    if not html_content:
                        logger.warning(f"Sayfa {page} tekrar denendiğinde de alınamadı, geçiliyor...")
                        continue
                    
                    # Doktor bilgilerini ayıkla
                    doctors = self.scrape_doctor_info(html_content)
                    logger.info(f"Sayfa {page}: {len(doctors)} doktor bulundu")
                    
                    # Doktor bilgilerini listeye ekle
                    self.doctors_data.extend(doctors)
                    
                    # Random bekleme süresi
                    sleep_time = random.uniform(self.delay_min, self.delay_max)
                    logger.info(f"Bekleniyor: {sleep_time:.2f} saniye...")
                    time.sleep(sleep_time)
                    
                except Exception as e:
                    logger.error(f"Sorunlu sayfa {page} tekrar denenirken hata: {e}")
                    time.sleep(5)  # Kısa bir bekleme
        
        # Final sonuçları kaydet
        output_file = self.save_doctors_data()
        self.save_checkpoint(self.end_page, output_file)
        
        elapsed_time = time.time() - start_time
        elapsed_minutes = elapsed_time / 60
        logger.info(f"Tarama tamamlandı. Toplam süre: {elapsed_minutes:.2f} dakika")
        logger.info(f"Toplam {len(self.doctors_data)} doktor verisi toplandı")
        
        return self.doctors_data

def load_proxies(proxy_file):
    """Proxy listesini dosyadan yükler"""
    if not os.path.exists(proxy_file):
        logger.warning(f"Proxy dosyası bulunamadı: {proxy_file}")
        return []
    
    proxies = []
    
    with open(proxy_file, 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):  # Boş satırları ve yorumları atla
                proxies.append(line)
    
    logger.info(f"Toplam {len(proxies)} adet proxy yüklendi")
    return proxies

def main():
    parser = argparse.ArgumentParser(description='Doktor Bilgilerini Çekme Programı')
    parser.add_argument('--start', type=int, default=1, help='Başlangıç sayfa numarası')
    parser.add_argument('--end', type=int, default=500, help='Bitiş sayfa numarası')
    parser.add_argument('--delay-min', type=float, default=3, help='Minimum gecikme süresi (saniye)')
    parser.add_argument('--delay-max', type=float, default=7, help='Maksimum gecikme süresi (saniye)')
    parser.add_argument('--save-interval', type=int, default=10, help='Kaydetme aralığı (sayfa)')
    parser.add_argument('--proxy-file', type=str, help='Proxy listesi dosyası')
    parser.add_argument('--output', type=str, help='Çıktı dosyası adı')
    parser.add_argument('--location', type=str, default='Ankara', help='Konum (şehir)')
    parser.add_argument('--url', type=str, default='https://www.doktortakvimi.com/ara', help='Temel URL')
    
    args = parser.parse_args()
    
    # Proxy listesini yükle
    proxies = load_proxies(args.proxy_file) if args.proxy_file else []
    
    # Temel URL oluştur
    base_url = f"{args.url}?q=&loc={args.location}"
    
    logger.info(f"Temel URL: {base_url}")
    
    # Scraper'ı başlat
    scraper = DoctorScraper(
        base_url=base_url,
        start_page=args.start,
        end_page=args.end,
        delay_min=args.delay_min,
        delay_max=args.delay_max,
        save_interval=args.save_interval,
        proxy_list=proxies
    )
    
    # Veri çekme işlemini başlat
    scraper.scrape()
    
    # Verileri kaydet
    if args.output:
        scraper.save_doctors_data(args.output)

if __name__ == "__main__":
    main()