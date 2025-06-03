import os
import yaml
from Gdocker import Docker
from log import Log
import sys
import signal
import time
import uuid

class Volunteer(Docker):
    def __init__(self, params=None):
        Docker.__init__(self, params)
        self.log = Log()
        self.package = None
        self.commit_id = None
        self.queue_id = None
        self.repo = None
        self.branch = None
        self.kernel_requirement = None
        self.job = params.job if params else 5
        self.running = True
        self.container_name = None
        
        # Docker istemcisini başlat
        try:
            self.docker = Docker(params)
            self.log.success("Docker istemcisi başarıyla başlatıldı")
        except Exception as e:
            self.log.error(f"Docker istemcisi başlatılamadı: {str(e)}")
            raise
        
        # Uygulama dizinini belirle
        self.app_dir = os.path.dirname(os.path.abspath(__file__))
        self.temp_dir = os.path.join(self.app_dir, 'temp')
        
        # Geçici dizinleri oluştur
        self.gonullu_dir = os.path.join(self.temp_dir, 'gonullu')
        self.varpisi_dir = os.path.join(self.temp_dir, 'varpisi')
        self.build_dir = os.path.join(self.temp_dir, 'build')
        
        # Ana geçici dizini oluştur
        if not os.path.exists(self.temp_dir):
            os.makedirs(self.temp_dir)
        
        signal.signal(signal.SIGINT, self.exit_signal)
    
    def generate_container_name(self):
        """Rastgele container ismi oluştur"""
        random_id = str(uuid.uuid4())[:8]  # UUID'nin ilk 8 karakterini al
        return f"gonullu-{random_id}"

    def set_name(self, name):
        self.name = name
    
    def get_package_farm(self):
        try:
            response = self.farm.get_package()
            if response == -1:
                self.log.error('Paket alınamadı!')
                return -1
            if response == -2:
                self.log.information('Yeni paket bekleniyor...')
                return -2

            if not isinstance(response, dict):
                self.log.error('Geçersiz yanıt alındı!')
                return -1

            package = response.get('package')
            if not package:
                self.log.error('Paket adı bulunamadı!')
                return -1

            # Paket adını sınıf değişkenine kaydet
            self.package = package

            # Container ismi oluştur
            container_name = self.generate_container_name()
            self.log.information(f'Container ismi oluşturuldu: {container_name}')

            # Gerekli dizinleri oluştur
            package_dir = os.path.join(self.temp_dir, 'gonullu', package)
            varpisi_dir = os.path.join(self.temp_dir, 'varpisi', package)
            build_dir = os.path.join(self.temp_dir, 'build')

            for directory in [package_dir, varpisi_dir, build_dir]:
                os.makedirs(directory, exist_ok=True)
                self.log.information(f'Dizin hazırlandı: {directory}')

            # Build script'ini kopyala ve düzenle
            build_script = os.path.join(build_dir, f'build-{package}.sh')
            with open(os.path.join(self.app_dir, 'config', 'build.sh'), 'r') as src:
                script_content = src.read()

            # Değişkenleri ayarla
            kernel_requirement = ' kernel ' if self.sandbox_is_require() else ' '
            sandbox_option = ' --ignore-sandbox ' if not self.sandbox_is_require() else ' '
            
            # Script içeriğini güncelle
            script_content = script_content.replace('${KERNEL_REQUIREMENT}', kernel_requirement)
            script_content = script_content.replace('${JOB_COUNT}', str(self.job))
            script_content = script_content.replace('${SANDBOX_OPTION}', sandbox_option)
            script_content = script_content.replace('${PACKAGE_NAME}', package)
            script_content = script_content.replace('${BRANCH}', response.get('branch', 'master'))
            script_content = script_content.replace('${COMMIT_ID}', response.get('commit_id', 'HEAD'))

            # Script'i kaydet
            with open(build_script, 'w') as dst:
                dst.write(script_content)
            os.chmod(build_script, 0o755)

            # Container'ı başlat
            try:
                self.container = self.docker.start_container(
                    name=container_name,
                    image=response.get('dockerimage'),
                    volumes={
                        package_dir: {'bind': '/tmp/gonullu', 'mode': 'rw'},
                        varpisi_dir: {'bind': '/var/pisi', 'mode': 'rw'},
                        build_dir: {'bind': '/build', 'mode': 'rw'}
                    },
                    command=f'/build/build-{package}.sh'
                )
                
                # Container'ın başlatılmasını bekle
                time.sleep(5)
                
                # Container durumunu kontrol et
                try:
                    container_info = self.docker.client.inspect_container(container_name)
                    status = container_info['State']['Status']
                    
                    if status != 'running':
                        self.log.error(f'Container başlatılamadı. Durum: {status}')
                        if status == 'exited':
                            logs = self.docker.get_logs()
                            self.log.error(f'Container logları: {logs}')
                        return -1

                    self.log.success(f'Container başarıyla başlatıldı: {container_name}')
                    self.log.success(f'Paket başarıyla işleme alındı: {package}')
                    return response

                except Exception as e:
                    self.log.error(f'Container durum kontrolü hatası: {str(e)}')
                    return -1

            except Exception as e:
                self.log.error(f'Container başlatma hatası: {str(e)}')
                # Hata durumunda container'ı temizle
                try:
                    if self.container:
                        self.container.remove(force=True)
                except:
                    pass
                return -1

        except Exception as e:
            self.log.error(f'Paket işleme hatası: {str(e)}')
            return -1

    def sandbox_is_require(self):
        config_file = os.path.join(os.path.dirname(__file__), 'config/sandbox-requirement.yml')

        with open(config_file, 'r') as sandbox_file:
            try:
                #FIXME! yaml.load(input) is depricated
                if self.package in yaml.load(sandbox_file, Loader=yaml.FullLoader):
                    return False
            except:
                self.log.error(message='%s dosyası işlenemedi' % config_file)
                self.log.get_exit()

        return True

    def exit_signal(self, signum, frame):
        self.log.information("Çıkış sinyali alındı, program sonlandırılıyor...")
        self.running = False
        if hasattr(self, 'container') and self.container:
            try:
                self.container.stop()
                self.container.remove()
            except Exception as e:
                self.log.error(f"Container kapatılırken hata oluştu: {str(e)}")
        sys.exit(0)

    @staticmethod
    def preparation(kernel_require, sandbox_requirement, package, j=5):
        krn = ' '
        sandbox = ' '
        if kernel_require is True:
            krn = ' kernel '

        if sandbox_requirement is False:
            sandbox = ' --ignore-sandbox '

        build_sh = """#!/bin/bash
service dbus start && pisi cp && update-ca-certificates && pisi ar pisiBeta https://beta.pisilinux.org/pisi-index.xml.xz && pisi it --ignore-safety --ignore-dependency autoconf autogen automake binutils bison flex gawk gc gcc gnuconfig guile libmpc libsigsegv libtool-ltdl libtool lzo m4 make mpfr nasm pkgconfig yacc glibc-devel isl %s
pisi ar core --ignore-check https://github.com/pisilinux/core/raw/master/pisi-index.xml.xz && pisi ar main --ignore-check https://github.com/pisilinux/main/raw/master/pisi-index.xml.xz --at 2
pisi ur
sed -i 's/-j5/-j%d/g' /etc/pisi/pisi.conf
sed -i 's/build_host = localhost/build_host=farmV5/g'   /etc/pisi/pisi.conf
cd /root
pisi bi --ignore-safety%s-y $3 1>/root/%s/$1-$2-$3.log 2>/root/%s/$1-$2-$3.err
STAT=$?

# Derlenen paket dosyalarını kontrol et ve taşı
if [ -d "build" ]; then
    cd build
    for pisi_file in $(find . -name "*.pisi"); do
        if [ -f "$pisi_file" ]; then
            cp "$pisi_file" "/root/%s/$1-$2-$(basename $pisi_file)"
            echo "Paket dosyası taşındı: $pisi_file"
        fi
    done
fi

echo $STAT > /root/%s/$3.bitti
""" % (krn, j, sandbox, package, package, package, package)

        build_directory = os.path.join('/', 'tmp', 'gonullu', 'build')
        if not os.path.exists(build_directory):
            os.makedirs(build_directory)

        f = open(os.path.join(build_directory, 'build-%s.sh' % package), 'w')
        f.write(build_sh)
        f.close()
        os.chmod(os.path.join(build_directory, 'build-%s.sh' % package), 0o755)

    def check(self):
        try:
            if not hasattr(self, 'container') or not self.container:
                return True

            # Container'ın durumunu kontrol et
            self.container.reload()
            status = self.container.status

            if status == 'running':
                # Container çalışıyor, logları kontrol et
                logs = self.get_logs()
                if logs:
                    # Container çalışıyor ve log var
                    self.log.information(f"Container log: {logs}")
                    
                    # Container'ın çalışma durumunu kontrol et
                    try:
                        # Container'ın çalışma durumunu kontrol et
                        stats = self.container.stats(stream=False)
                        if stats and stats.get('cpu_stats'):
                            self.log.information("Container aktif olarak çalışıyor")
                            return False
                    except Exception as e:
                        self.log.error(f"Container durum kontrolü hatası: {str(e)}")
                    
                    return False
                else:
                    # Container çalışıyor ama log yok, hata olabilir
                    self.log.warning("Container çalışıyor ancak log bulunamadı")
                    return False
            elif status == 'exited':
                # Container sonlandı, çıkış kodunu kontrol et
                exit_code = self.container.attrs['State']['ExitCode']
                if exit_code == 0:
                    # Başarılı sonlanma, dosyaları kontrol et
                    package_dir = f'/tmp/gonullu/{self.package}'
                    if os.path.exists(package_dir):
                        # .bitti dosyasını kontrol et
                        bitti_file = os.path.join(package_dir, f'{self.package}.bitti')
                        if os.path.exists(bitti_file):
                            with open(bitti_file, 'r') as f:
                                success = int(f.read().strip())
                            if success == 0:
                                self.log.success("Container başarıyla tamamlandı")
                                return True
                            else:
                                self.log.error(f"Container hata ile sonlandı (kod: {success})")
                                return True
                        else:
                            self.log.error(f".bitti dosyası bulunamadı: {bitti_file}")
                            return True
                    else:
                        self.log.error(f"Paket dizini bulunamadı: {package_dir}")
                        return True
                else:
                    self.log.error(f"Container hata ile sonlandı (kod: {exit_code})")
                    return True
            else:
                # Beklenmeyen durum
                self.log.error(f"Container beklenmeyen durumda: {status}")
                return True

        except Exception as e:
            self.log.error(f"Container kontrol hatası: {str(e)}")
            return True

    def get_logs(self):
        try:
            if not hasattr(self, 'container') or not self.container:
                return None

            # Son 10 satır log al
            logs = self.container.logs(tail=10, timestamps=True).decode('utf-8')
            if logs:
                # Tüm logları döndür
                return logs.strip()
            return None
        except Exception as e:
            self.log.error(f"Log alma hatası: {str(e)}")
            return None

    def remove(self):
        try:
            # Container'ı durdur ve sil
            if hasattr(self, 'container') and self.container:
                try:
                    self.container.stop()
                    self.container.remove()
                    self.log.information("Container durduruldu ve silindi.")
                except Exception as e:
                    self.log.error(f"Container silme hatası: {str(e)}")

            # Container referansını temizle
            self.container = None

        except Exception as e:
            self.log.error(f"Container temizleme hatası: {str(e)}")

    def cleanup(self):
        """Geçici dizinleri temizle"""
        try:
            # Geçici dizinleri temizle
            if not hasattr(self, 'package') or not self.package:
                self.log.warning("Paket adı bulunamadı, temizlik atlanıyor.")
                return

            temp_dirs = [
                os.path.join(self.gonullu_dir, self.package),
                os.path.join(self.varpisi_dir, self.package),
                self.build_dir
            ]

            for directory in temp_dirs:
                if os.path.exists(directory):
                    try:
                        import shutil
                        shutil.rmtree(directory)
                        self.log.information(f"Geçici dizin temizlendi: {directory}")
                    except Exception as e:
                        self.log.error(f"Dizin temizleme hatası ({directory}): {str(e)}")

            self.log.success("Temizlik işlemi tamamlandı.")

        except Exception as e:
            self.log.error(f"Temizlik işlemi sırasında hata: {str(e)}")
