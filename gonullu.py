#!/usr/bin/env python3
import argparse
import os
import signal
import sys
import traceback
import subprocess
import time
from log import Log
from farm import Farm
from volunteer import Volunteer


def usage():
    print("""
Kullanim - Usage
Asagidaki satir, docker icindeki /etc/pisi/pisi.conf icinde bulunan
-j parametresini verecegimiz rakam ile degistirir.
\tgonullu -j 24
Asagidaki satir, docker icin islemcinin %70'ini, fiziksel hafizanin
%25'ini  ayirir.
\tgonullu --cpu=70 --memory=25
""")
    sys.exit()


def get_sudo_password():
    """Kullanıcıdan sudo şifresini al"""
    import getpass
    try:
        return getpass.getpass('Sudo şifresini girin: ')
    except KeyboardInterrupt:
        print("\nProgram sonlandırılıyor...")
        sys.exit(0)


def run_with_sudo():
    """Programı sudo ile yeniden başlat"""
    if os.geteuid() != 0:  # Root değilsek
        try:
            password = get_sudo_password()
            # Programı sudo ile yeniden başlat
            cmd = ['sudo', '-S', sys.executable] + sys.argv
            process = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
            process.communicate(password.encode())
            sys.exit(process.returncode)
        except KeyboardInterrupt:
            print("\nProgram sonlandırılıyor...")
            sys.exit(0)
        except Exception as e:
            print(f"\nHata oluştu: {str(e)}")
            sys.exit(1)


def main(log, volunteer, farm):
    try:
        # Farm nesnesini volunteer'a bağla
        volunteer.farm = farm
        farm.set_volunteer(volunteer)

        while True:
            try:
                # Paket al
                response = volunteer.get_package_farm()
                
                if response == -1:
                    log.error('Paket alınamadı!')
                    time.sleep(10)
                    continue
                    
                if response == -2:
                    log.information('Yeni paket bekleniyor...')
                    time.sleep(20)
                    continue

                # Paket işleme
                package = response.get('package')
                if not package:
                    log.error('Paket adı bulunamadı!')
                    continue

                # Paket dizinini kontrol et
                package_dir = f'/tmp/gonullu/{package}'
                if not os.path.exists(package_dir):
                    log.error(f'Paket dizini bulunamadı: {package_dir}')
                    continue

                # .bitti dosyasını bekle
                bitti_file = os.path.join(package_dir, f'{package}.bitti')
                while not os.path.exists(bitti_file):
                    log.information('Derleme işlemi devam ediyor...')
                    time.sleep(30)

                # Dosyaları gönder
                try:
                    if farm.send_file(package, response.get('binary_repo_dir', '')):
                        log.success(f'Paket başarıyla gönderildi: {package}')
                    else:
                        log.error(f'Paket gönderimi başarısız: {package}')
                except Exception as e:
                    log.error(f'Dosya gönderimi sırasında hata: {str(e)}')

                # Temizlik
                try:
                    volunteer.cleanup()
                except Exception as e:
                    log.error(f'Temizlik sırasında hata: {str(e)}')

            except Exception as e:
                log.error(f'Paket işleme hatası: {str(e)}')
                time.sleep(10)

    except KeyboardInterrupt:
        log.information('Program sonlandırılıyor...')
    except Exception as e:
        log.error(f'Bilinmeyen bir hata ile karşılaşıldı: {str(e)}')
        import traceback
        log.error(traceback.format_exc())
    finally:
        # Son temizlik
        try:
            volunteer.cleanup()
        except:
            pass


if __name__ == "__main__":
    log = Log()

    # Sinyal yönetimini ayarla
    def signal_handler(signum, frame):
        print("\nProgram sonlandırılıyor...")
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    parser = argparse.ArgumentParser(description='This is pisilinux volunteer application')
    parser.add_argument('-k', '--kullanim', action="store_true", dest='usage', default=False)
    parser.add_argument('-m', '--memory', action='store', dest='memory_limit', default=50, type=int)
    parser.add_argument('-c', '--cpu', action='store', dest='cpu_set', default=1, type=int)
    parser.add_argument('-e', '--email', action='store', dest='email', default='ilkermanap@gmail.com', type=str)
    parser.add_argument('-j', '--job', action='store', dest='job', default=5, type=int)

    args = parser.parse_args()

    if args.usage:
        usage()

    # Sudo kontrolü ve şifre sorma
    run_with_sudo()

    docker_socket_file = '/var/run/docker.sock'
    if not os.path.exists(docker_socket_file):
        log.error(message='Lütfen ilk önce docker servisini çalıştırınız!')
        log.get_exit()

    if not args.email:
        log.error(message='Lütfen bir mail adresi belirtiniz. (-e parametresi)')
        log.get_exit()

    print(args)

    #farm = Farm('https://ciftlik.pisilinux.org', args.email)
    farm = Farm('http://31.207.82.178/', args.email)
    volunteer = Volunteer(args)

    try:
        os.system("stty -echo")
        main(log, volunteer, farm)
    except SystemExit as e:
        # Program düzgün şekilde sonlandırıldı
        if e.code == 0:
            log.information("Program düzgün şekilde sonlandırıldı.")
        else:
            log.error(f"Program hata kodu {e.code} ile sonlandırıldı.")
    except Exception as e:
        log.error('Bilinmeyen bir hata ile karşılaşıldı: %s' % (traceback.format_exc()))
    finally:
        os.system("stty echo")
        sys.exit(0)
