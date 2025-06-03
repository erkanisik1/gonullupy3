import json
import random
import shutil

import psutil
from docker import client
from docker import APIClient

from log import Log


class Docker:
    def __init__(self, parameters=None, name=None):
        self.log = Log()
        self.name = name
        self.memory_limit = self.set_memory_limit(parameters.memory_limit if parameters else 50)
        self.binds = {}
        self.volumes = []
        self.package_name = None
        self.image = None
        self.cpu_set = self.set_cpu_set(parameters.cpu_set if parameters else 1)
        self.command = None
        self.client = None  # Docker client'ı
        self.host_config = None
        self.my_container = None
        self.tmp_status = False
        self.name = name

        # Docker client'ı başlat
        try:
            self.client = APIClient(base_url='unix://var/run/docker.sock', version='1.35')
            self.log.success("Docker client başarıyla başlatıldı")
        except Exception as e:
            self.log.error(f"Docker client başlatılamadı: {str(e)}")
            raise

    def start(self, name):
        # Container'ı başlatma işlemleri...
        if not self.name:
            self.log.error("Container adı sağlanmadı!")
            return False

        try:
            # Docker client'ı oluştur
            if not self.client:
                self.client = APIClient(base_url='unix://var/run/docker.sock', version='1.35')

            # Host config'i oluştur
            self.host_config = self.client.create_host_config(
                mem_limit='%sM' % self.memory_limit,
                binds=self.binds,
                security_opt=['seccomp:unconfined']
            )

            # Eski container'ı kontrol et ve temizle
            self.control_docker()

            # İmajı güncelle
            self.tmp_status = False
            message = '%s imajı güncelleniyor' % self.image
            for line in self.client.pull(self.image, stream=True):
                line = json.loads(line.decode('UTF-8'))
                if line['status'] == 'Downloading':
                    if self.tmp_status is False:
                        self.log.information(message=message)
                        self.tmp_status = True
                    print('  %s' % line['progress'], end='\r')

            if self.tmp_status is True:
                print('')
                self.log.information(message='İmaj son sürüme güncellendi')

            # Container'ı oluştur
            self.my_container = self.client.create_container(
                image=self.image,
                command=self.command,
                name=self.name,
                volumes=self.volumes,
                host_config=self.host_config
            )

            # Container'ı başlat
            self.client.start(self.name)
            self.log.success(f"Container başarıyla başlatıldı: {self.name}")
            return True

        except Exception as e:
            self.log.error(f"Container başlatma hatası: {str(e)}")
            return False

    def pause(self):
        # containerımızı durdurmak için çalıştıracağımız fonksiyonumuz.
        self.client.pause(self.name)

    def resume(self):
        # containerımızı devam ettirmek için çalıştıracağımız fonksiyonumuz.
        self.client.unpause(self.name)

    def stop(self):
        # konteynırımızda ki işlemi iptal etmek için çalıştıracağımız fonksiyonumuz.
        self.client.stop(self.name)

    def remove(self):
        # containerımızı silecek fonksiyonumuz
        state = self.client.inspect_container(self.name)
        state = state['State']['Running']
        if state is True:
            self.client.stop(self.name)
        self.client.remove_container(self.name)
        self.volumes = []
        self.binds = {}
        self.name = None
        if self.package_name is not None:
            shutil.rmtree('/tmp/gonullu/%s' % self.package_name, ignore_errors=True)
            shutil.rmtree('/tmp/varpisi/%s' % self.package_name, ignore_errors=True)
            self.package_name = None

    def get_logs(self):
        try:
            if not self.client or not self.name:
                return "Container logları alınamıyor."
            
            # Son 10 satır log'u al
            logs = self.client.logs(
                self.name,
                tail=10,
                timestamps=True,
                stream=False
            ).decode('utf-8')
            
            if not logs:
                return "Henüz log oluşturulmadı."
                
            # Logları satır satır ayır ve son satırı döndür
            log_lines = logs.strip().split('\n')
            if log_lines:
                return log_lines[-1]  # En son log satırını döndür
            return "Log bulunamadı."
            
        except Exception as e:
            return f"Log alınamadı: {str(e)}"

    def set_name(self, name):
        # Container adını güvenli bir şekilde oluştur
        if not name:
            self.log.error("Geçersiz paket adı!")
            return False

        self.package_name = name
        # Docker container isimleri için güvenli karakterler
        safe_chars = 'abcdefghijklmnopqrstuvxyzABCDEFGHIJKLMNOPQRSTUVXYZ-_1234567890'
        
        # İsmi güvenli hale getir
        safe_name = ''
        for char in name:
            if char in safe_chars:
                safe_name += char
            else:
                # Geçersiz karakteri rastgele güvenli bir karakterle değiştir
                safe_name += random.choice(safe_chars)
        
        # İsim en az 2 karakter olmalı
        if len(safe_name) < 2:
            safe_name += '_' + random.choice(safe_chars)
            
        self.name = safe_name
        self.log.information(f"Container adı oluşturuldu: {self.name}")
        return True

    @staticmethod
    def set_memory_limit(memory_limit):
        # ram limitimizi atadığımız fonksiyonumuz.
        return int((psutil.virtual_memory().total * (memory_limit / 100))) >> 20

    def set_image(self, image):
        # imajımızı atadığımız fonksiyonumuz.
        self.image = image

    @staticmethod
    def set_cpu_set(cpu_set):
        # atayacağımız cpularımızı atadığımız fonksiyonumuz.
        return int(cpu_set)

    def add_volume(self, local, indocker):
        # bölüm ekleyeceğimiz fonksiyonumuz.
        self.volumes.append(indocker)
        self.binds[local] = {'bind': indocker, 'mode': 'rw'}

    def set_command(self, application, queue_id, commit_id, package):
        # çalıştıracağımız komutu atadığımız fonksiyonumuz.
        self.command = '%s %s %s %s' % (application, queue_id, commit_id, package)

    def check(self):
        # derleme işlemi devam ediyor mu kontrol edelim
        for container in self.client.containers():
            if container['Names'][0].replace('/', '') == self.name:
                return 0
        else:
            return 1

    def control_docker(self):
        # oluşacak paketin adı ile önceden docker kaydı var mı kontrol edelim.
        for container in self.client.containers(all=True):
            if container['Names'][0].replace('/', '') == self.name:
                self.remove()

    def exit_signal(self, signal, frame):
        if self.name is not None:
            self.remove()

        self.log.blank_line()
        self.log.warning(message='CTRL+C\'ye tıkladınız!')
        self.log.get_exit()

    def start_container(self, name, image, volumes=None, command=None):
        """Container'ı başlatmak için yeni metod"""
        try:
            # Container adını ayarla
            self.name = name
            self.image = image
            self.command = command

            # Volume'ları ayarla
            if volumes:
                self.volumes = []
                self.binds = {}
                for local_path, volume_info in volumes.items():
                    self.add_volume(local_path, volume_info['bind'])

            # Host config'i oluştur
            self.host_config = self.client.create_host_config(
                mem_limit='%sM' % self.memory_limit,
                binds=self.binds,
                security_opt=['seccomp:unconfined']
            )

            # Eski container'ı kontrol et ve temizle
            self.control_docker()

            # İmajı güncelle
            self.tmp_status = False
            message = '%s imajı güncelleniyor' % self.image
            for line in self.client.pull(self.image, stream=True):
                line = json.loads(line.decode('UTF-8'))
                if line['status'] == 'Downloading':
                    if self.tmp_status is False:
                        self.log.information(message=message)
                        self.tmp_status = True
                    print('  %s' % line['progress'], end='\r')

            if self.tmp_status is True:
                print('')
                self.log.information(message='İmaj son sürüme güncellendi')

            # Container'ı oluştur
            self.my_container = self.client.create_container(
                image=self.image,
                command=self.command,
                name=self.name,
                volumes=self.volumes,
                host_config=self.host_config
            )

            # Container'ı başlat
            self.client.start(self.name)
            self.log.success(f"Container başarıyla başlatıldı: {self.name}")
            return self.my_container

        except Exception as e:
            self.log.error(f"Container başlatma hatası: {str(e)}")
            raise
