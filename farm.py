import glob
import time
import requests
import yaml
import os
import shutil
from log import Log


class Farm:
    def __init__(self, farm_url, email):
        self.url = farm_url
        self.email = email
        self.time = 10
        self.total_error_time = 10
        self.log = Log()
        self.total_time = 10
        self.config_file = os.path.join(os.path.dirname(__file__), 'config/mail_config.yml')

    def get(self, request, json=True):
        # Get isteğini işleyip json data dönen fonksiyonumuz.
        try:
            response = requests.get('%s/%s' % (self.url, request))
            response.raise_for_status()  # HTTP hatalarını yakalamak için
            if json:
                self.total_error_time = 10
                return response.json()
            else:
                self.total_error_time = 10
                return response
        except requests.exceptions.RequestException as e:
            self.log.error('Sunucuya %s saniyedir erişilemedi tekrar bağlanmaya çalışıyor! Hata: %s' % (self.total_error_time, str(e)), continued=True)
            self.total_error_time += 10
            self.total_time = 10
            return -2

   

    def send_file(self, package, binary_path):
        # Oluşan çıktı dosyalarını çiftliğe gönderen fonksiyonumuz.
        output_files = glob.glob('/tmp/gonullu/%s/*.[lpe]*' % package)
        if not output_files:
            self.log.error('Dosya bulunamadı: /tmp/gonullu/%s/*.[lpe]*' % package)
            return False

        for file in output_files:
            retry_count = 0
            while True:  # Sonsuz döngü - dosya gönderilene kadar devam eder
                if self.send(file, binary_path):
                    break  # Başarılı olursa döngüden çık
                else:
                    retry_count += 1
                    self.log.warning(message='%s dosyası tekrar gönderilmeye çalışılacak. Deneme: %d' % (file, retry_count + 1), continued=True)
                    self.wait()
        
        # Tüm dosyalar başarıyla gönderildikten sonra /tmp/gonullu dizinini temizle
        try:
            shutil.rmtree('/tmp/gonullu', ignore_errors=True)
            self.log.success('Tüm dosyalar gönderildi, /tmp/gonullu dizini temizlendi.')
        except Exception as e:
            self.log.warning('Dizin temizlenirken hata oluştu: %s' % str(e))
        
        return True

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

        try:
            with open(file, 'rb') as f:
                files = {'file': f}
                # Timeout değerlerini artırıyoruz: (bağlantı timeout, okuma timeout)
                r = requests.post('%s/%s' % (self.url, 'upload'), 
                                files=files, 
                                data={'binrepopath': binary_path},
                                timeout=(60, 600))  # 30 saniye bağlantı, 300 saniye okuma timeout
                r.raise_for_status()
                hashx = self.sha1file(file)

                file = file.split('/')[-1]
                if hashx == r.text.strip():
                    self.log.success(message='%s dosyası başarı ile gönderildi.' % file)
                    return True
                else:
                    self.log.error(message='%s dosyası gönderilemedi!' % file)
                    return False
        except requests.exceptions.Timeout:
            self.log.error(message='%s dosyası gönderilirken zaman aşımı oluştu! Daha uzun bir süre bekleyiniz.' % file)
            return False
        except requests.exceptions.RequestException as e:
            self.log.error(message='%s dosyası gönderilemedi! Hata: %s' % (file, str(e)))
            return False

    def get_package(self):
        # Mail adresini kontrol et
        if not os.path.exists(self.config_file):
            # Yapılandırma dosyası yoksa oluştur
            config = {'email': None, 'is_verified': False}
            with open(self.config_file, 'w') as f:
                yaml.dump(config, f)

        # Yapılandırma dosyasını oku
        with open(self.config_file, 'r') as f:
            config = yaml.safe_load(f)

        # Eğer mail adresi doğrulanmışsa ve aynı mail adresi kullanılıyorsa
        if config.get('is_verified') and config.get('email') == self.email:
            request = '%s/%s' % ('requestPkg', self.email)
            response = self.get(request)
        else:
            # Mail adresini doğrula
            request = '%s/%s' % ('requestPkg', self.email)
            response = self.get(request)

            if response == -2:
                time.sleep(self.time)
                self.total_time += self.time
                return -2

            if response['state'] == 200:
                # Mail adresi doğrulandı, yapılandırma dosyasını güncelle
                config['email'] = self.email
                config['is_verified'] = True
                with open(self.config_file, 'w') as f:
                    yaml.dump(config, f)
                self.log.success('Mail adresi başarıyla doğrulandı.')
            elif response['state'] == 402:
                config['email'] = self.email
                config['is_verified'] = True
                with open(self.config_file, 'w') as f:
                    yaml.dump(config, f)
                self.log.success('Mail adresi başarıyla doğrul"andı.')
            elif response['state'] == 401:
                self.log.error(message='Mail adresiniz yetkili değil!')
                self.log.get_exit()
            else:
                self.log.error(message='Mail adresi doğrulanamadı!')
                self.log.get_exit()

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
            self.log.error(message='Mail adresiniz yetkili değil!')
            self.log.get_exit()

        elif response['state'] == 402:
            return -1

        elif response['state'] == 403:
            self.log.error(message='Docker imajı bulunamadı!')
            self.log.get_exit()

        else:
            self.log.error(message='Tanımlı olmayan bir hata oluştu!')
            self.log.get_exit()

    def wait(self, message='', reset=False):
        if reset:
            self.total_time = 0

        if message:
            information_message = '%d saniye%s' % (self.total_time, message)
            self.log.information(message=information_message, continued=True)
        time.sleep(self.time)
        self.total_time += self.time

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
