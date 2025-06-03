import glob
import time
import requests
import signal
import sys
import os
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from urllib3 import PoolManager
import urllib3
from log import Log

class Farm:
    # Sabit değerler
    DEFAULT_WAIT_TIME = 10  # Saniye
    MAX_WAIT_TIME = 300     # 5 dakika
    ERROR_INCREMENT = 10    # Her hatada artacak süre
    MAX_ERROR_TIME = 600    # Maksimum hata bekleme süresi (10 dakika)
    REQUEST_TIMEOUT = 30    # HTTP istek timeout süresi
    MAX_RETRIES = 3        # Maksimum yeniden deneme sayısı
    POOL_CONNECTIONS = 10   # Bağlantı havuzu boyutu
    POOL_MAXSIZE = 10      # Maksimum bağlantı sayısı

    def __init__(self, farm_url, email):
        self.url = farm_url
        self.email = self.mail_control(email)
        self.time = self.DEFAULT_WAIT_TIME
        self.total_error_time = self.DEFAULT_WAIT_TIME
        self.log = Log()
        self.total_time = 0
        self.should_exit = False
        self.volunteer = None  # Volunteer referansı
        
        # HTTP oturumu oluştur ve yeniden deneme stratejisini ayarla
        self.session = requests.Session()
        retry_strategy = Retry(
            total=self.MAX_RETRIES,
            backoff_factor=1,
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=["GET", "POST"]
        )
        
        # Özel bağlantı havuzu yapılandırması
        adapter = HTTPAdapter(
            max_retries=retry_strategy,
            pool_connections=self.POOL_CONNECTIONS,
            pool_maxsize=self.POOL_MAXSIZE,
            pool_block=False
        )
        
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
        # Bağlantı havuzu uyarılarını kapat
        urllib3.disable_warnings()
        
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)

    def signal_handler(self, sig, frame):
        self.log.warning("Çıkış sinyali alındı, program sonlandırılıyor...")
        self.should_exit = True
        sys.exit(0)

    def get(self, request, json=True):
        # Get isteğini işleyip json data dönen fonksiyonumuz.
        while True:  # Sonsuz döngü
            try:
                # URL'yi düzgün şekilde oluştur
                base_url = self.url.rstrip('/')  # Sondaki slash'i kaldır
                request = request.lstrip('/')    # Baştaki slash'i kaldır
                url = f'{base_url}/{request}'
                
                self.log.information(f'İstek gönderiliyor: {url}')
                
                try:
                    response = self.session.get(
                        url,
                        timeout=(self.REQUEST_TIMEOUT, self.REQUEST_TIMEOUT),
                        headers={'Connection': 'close'}  # Her istekten sonra bağlantıyı kapat
                    )
                    
                    # HTTP durum kodunu kontrol et
                    if response.status_code == 500:
                        self.log.error(f'Sunucu hatası (500): {response.text}')
                        self.log.information('5 saniye sonra tekrar deneniyor...')
                        time.sleep(5)
                        continue
                        
                    if response.status_code != 200:
                        self.log.error(f'HTTP Hatası: {response.status_code} - {response.text}')
                        self.log.information('5 saniye sonra tekrar deneniyor...')
                        time.sleep(5)
                        continue
                    
                    response.raise_for_status()  # HTTP hatalarını yakalamak için
                    
                    if json:
                        try:
                            data = response.json()
                            self.log.information(f'Yanıt alındı: {data}')
                            return data
                        except ValueError as e:
                            self.log.error(f'JSON ayrıştırma hatası: {str(e)}')
                            self.log.error(f'Ham yanıt: {response.text}')
                            self.log.information('5 saniye sonra tekrar deneniyor...')
                            time.sleep(5)
                            continue
                    else:
                        return response
                        
                except requests.exceptions.RequestException as e:
                    self.log.error(f'Bağlantı hatası: {str(e)}')
                    self.log.information('5 saniye sonra tekrar deneniyor...')
                    time.sleep(5)
                    continue
                    
            except Exception as e:
                self.log.error(f'Beklenmeyen hata: {str(e)}')
                self.log.information('5 saniye sonra tekrar deneniyor...')
                time.sleep(5)
                continue

    def send_file(self, package, binary_path):
        if not package:
            self.log.error('Paket adı belirtilmedi!')
            return False

        # Kuyruk ID'sini al
        try:
            response = self.get(f'requestPkg/{self.email}')
            if not isinstance(response, dict) or response.get('state') != 200:
                self.log.error('Kuyruk ID alınamadı')
                return False
            kuyruk_id = response.get('kuyruk_id')
            if not kuyruk_id:
                self.log.error('Kuyruk ID bulunamadı')
                return False
        except Exception as e:
            self.log.error(f'Kuyruk ID alınırken hata: {str(e)}')
            return False

        while True:  # Sonsuz döngü
            try:
                # Dizin kontrolü
                package_dir = f'/tmp/gonullu/{package}'
                if not os.path.exists(package_dir):
                    self.log.error(f'Paket dizini bulunamadı: {package_dir}')
                    self.log.information('5 saniye sonra tekrar deneniyor...')
                    time.sleep(5)
                    continue

                # Önce pisi dosyasını kontrol et
                pisi_files = glob.glob(f'{package_dir}/*.pisi')
                pisi_exists = bool(pisi_files)  # Pisi dosyası var mı kontrolü
                
                if not pisi_exists:
                    self.log.error(f'Pisi dosyası bulunamadı: {package_dir}')
                    # Pisi dosyası yoksa başarısız olarak işaretle
                    try:
                        response = self.get(f'updaterunning/?id={kuyruk_id}&state=101')
                        if isinstance(response, dict) and response.get('status') == 'success':
                            self.log.success('Durum başarısız olarak güncellendi (Pisi dosyası yok)')
                            return False
                        else:
                            self.log.error(f'Durum güncellenemedi: {response}')
                            time.sleep(5)
                            continue
                    except Exception as e:
                        self.log.error(f'Durum güncelleme hatası: {str(e)}')
                        time.sleep(5)
                        continue
                else:
                    self.log.information(f'Pisi dosyası bulundu: {len(pisi_files)}')

                # Diğer dosyaları da kontrol et
                file_patterns = [
                    f'{package_dir}/*.err',   # Hata dosyaları
                    f'{package_dir}/*.log',   # Log dosyaları
                    f'{package_dir}/*.html'   # HTML dosyaları
                ]

                output_files = []
                # Pisi dosyalarını ekle
                output_files.extend(pisi_files)

                # Sonra diğer dosyaları ekle
                for pattern in file_patterns:
                    files = glob.glob(pattern)
                    if files:
                        output_files.extend(files)
                        self.log.information(f'{pattern} için {len(files)} dosya bulundu.')

                if not output_files:
                    self.log.error(f'Hiç dosya bulunamadı: {package_dir}')
                    self.log.information('5 saniye sonra tekrar deneniyor...')
                    time.sleep(5)
                    continue

                self.log.information(f'Toplam {len(output_files)} dosya gönderilecek.')

                success_count = 0
                for file in output_files:
                    try:
                        if self.send(file, binary_path):
                            success_count += 1
                        else:
                            self.log.warning(f'{file} dosyası gönderilemedi, tekrar deneniyor...')
                            time.sleep(5)
                            continue
                    except Exception as e:
                        self.log.error(f'Dosya gönderimi sırasında hata: {str(e)}')
                        self.log.information('5 saniye sonra tekrar deneniyor...')
                        time.sleep(5)
                        continue

                if success_count == len(output_files):
                    self.log.success(f'Tüm dosyalar başarıyla gönderildi: {package}')
                    # Durumu güncelle
                    try:
                        response = self.get(f'updaterunning/?id={kuyruk_id}&state=999')
                        if isinstance(response, dict) and response.get('status') == 'success':
                            self.log.success('Durum başarıyla güncellendi')
                            return True
                        else:
                            self.log.error(f'Durum güncellenemedi: {response}')
                            time.sleep(5)
                            continue
                    except Exception as e:
                        self.log.error(f'Durum güncelleme hatası: {str(e)}')
                        time.sleep(5)
                        continue
                else:
                    self.log.error(f'Bazı dosyalar gönderilemedi. Başarılı: {success_count}/{len(output_files)}')
                    # Durumu güncelle
                    try:
                        response = self.get(f'updaterunning/?id={kuyruk_id}&state=101')
                        if isinstance(response, dict) and response.get('status') == 'success':
                            self.log.success('Durum başarısız olarak güncellendi')
                        else:
                            self.log.error(f'Durum güncellenemedi: {response}')
                    except Exception as e:
                        self.log.error(f'Durum güncelleme hatası: {str(e)}')
                    
                    self.log.information('5 saniye sonra tekrar deneniyor...')
                    time.sleep(5)
                    continue

            except Exception as e:
                self.log.error(f'Dosya gönderme hatası: {str(e)}')
                self.log.information('5 saniye sonra tekrar deneniyor...')
                time.sleep(5)
                continue

    def send(self, file, binary_path):
        self.log.information(message='%s dosyası gönderiliyor.' % file.split('/')[-1])
        if file.split('.')[-1] in ('err', 'log'):
            with open(file, 'r') as f:
                content = f.read()
            with open('%s.html' % file, 'w') as html:
                html.write('<html><body><pre>')
                html.write(content)
                html.write('</pre></body></html>')
            file = '%s.html' % file

        while True:  # Sonsuz döngü
            try:
                with open(file, 'rb') as f:
                    files = {'file': f}
                    r = self.session.post(
                        '%s/%s' % (self.url, 'upload'),
                        files=files,
                        data={'binrepopath': binary_path},
                        timeout=(self.REQUEST_TIMEOUT, self.REQUEST_TIMEOUT),
                        headers={'Connection': 'close'}
                    )
                    
                    if r.status_code == 500:
                        self.log.error(f'Sunucu hatası (500): {r.text}')
                        self.log.information('5 saniye sonra tekrar deneniyor...')
                        time.sleep(5)
                        continue
                        
                    r.raise_for_status()  # HTTP hatalarını yakalamak için
                    hashx = self.sha1file(file)

                    file = file.split('/')[-1]
                    if hashx == r.text.strip():
                        self.log.success(message='%s dosyası başarı ile gönderildi.' % file)
                        return True
                    else:
                        self.log.error(message='%s dosyası gönderilemedi!' % file)
                        self.log.information('5 saniye sonra tekrar deneniyor...')
                        time.sleep(5)
                        continue
                        
            except requests.exceptions.RequestException as e:
                self.log.error(message='%s dosyası gönderilemedi! Hata: %s' % (file, str(e)))
                self.log.information('5 saniye sonra tekrar deneniyor...')
                time.sleep(5)
                continue
            except Exception as e:
                self.log.error(f'Beklenmeyen hata: {str(e)}')
                self.log.information('5 saniye sonra tekrar deneniyor...')
                time.sleep(5)
                continue

    def get_package(self):
        request = '%s/%s' % ('requestPkg', self.email)
        response = self.get(request)

        if response == -1:
            return -1

        if response == -2:
            time.sleep(self.time)
            self.total_time += self.time
            return -2

        if not isinstance(response, dict):
            self.log.error(message='Geçersiz yanıt alındı!')
            return -1

        if response['state'] == 200:
            self.log.information(message='Yeni paket bulundu, paketin adı: %s' % response['package'])
            self.total_time = 0
            return response

        elif response['state'] == 401:
            self.log.error(message='Mail adresiniz yetkili değil! Lütfen mail adresinizi kontrol edin: %s' % self.email)
            # Mail kontrolü yap
            mail_check = self.get('checkMail/%s' % self.email)
            if isinstance(mail_check, dict) and mail_check.get('state') == 200:
                self.log.information(message='Mail adresi doğrulandı, tekrar deneniyor...')
                time.sleep(5)  # Kısa bir bekleme
                return self.get_package()  # Tekrar dene
            sys.exit(1)

        elif response['state'] == 402:
            return -1

        elif response['state'] == 403:
            self.log.error(message='Docker imajı bulunamadı!')
            sys.exit(1)

        else:
            self.log.error(message='Tanımlı olmayan bir hata oluştu! Sunucu yanıtı: %s' % str(response))
            sys.exit(1)

    def wait(self, message=None, reset=False):
        if reset:
            self.total_time = 0
            self.total_error_time = self.DEFAULT_WAIT_TIME
            self.time = self.DEFAULT_WAIT_TIME

        try:
            start_time = time.time()
            time.sleep(self.time)
            elapsed_time = int(time.time() - start_time)
            self.total_time += elapsed_time
            
            # Her 5 dakikada bir bekleme süresini artır
            if self.total_time % self.MAX_WAIT_TIME == 0:
                self.time = min(self.time + self.DEFAULT_WAIT_TIME, self.MAX_WAIT_TIME)
            
            # Toplam bekleme süresini hesapla
            minutes = self.total_time // 60
            seconds = self.total_time % 60
            
            # Mesajı ve süreyi birleştir
            if message:
                if "derleme işlemi" in message and hasattr(self, 'volunteer'):
                    # Container loglarını al
                    container_log = self.volunteer.get_logs()
                    if minutes > 0:
                        self.log.information(f"{minutes} dakika {seconds} saniye - {container_log}")
                    else:
                        self.log.information(f"{seconds} saniye - {container_log}")
                else:
                    if minutes > 0:
                        self.log.information(f"{minutes} dakika {seconds} saniye {message}")
                    else:
                        self.log.information(f"{seconds} saniye {message}")
                
        except KeyboardInterrupt:
            self.signal_handler(signal.SIGINT, None)

    def get_total_time(self):
        return self.total_time

    def running_process(self):
        # Uygulama çalışmaya devam ettiği sürece siteye bildirim göndereceğiz.
        # TODO: İlker abiden devam ediyor olan uygulamalar kısmına bunun ile ilgili bir servis isteyeceğiz.
        pass

    def complete_process(self):
        # Uygulama çalışması bitince çalışacak olan prosedür fonksiyonumuz.
        pass

    @staticmethod
    def mail_control(email):
        # Mail adresinin geçerli formatını kontrol et
        if not email or '@' not in email:
            raise ValueError('Geçersiz mail adresi formatı!')
        return email.strip().lower()  # Mail adresini normalize et

    @staticmethod
    def sha1file(filepath):
        import hashlib
        sha = hashlib.sha1()
        with open(filepath, 'rb') as f:
            while True:
                block = f.read(2 ** 20)  # Magic number: one-megabyte blocks.
                if not block:
                    break
                sha.update(block)
            return sha.hexdigest()

    def set_volunteer(self, volunteer):
        self.volunteer = volunteer
